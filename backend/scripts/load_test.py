"""Locust 压测脚本 - 用于生成真实的 QPS 和延迟数据"""
import json
import time
from locust import HttpUser, task, between, SequentialTaskSet, constant
from locust.env import Environment
from locust.stats import stats_printer, stats_history
from locust.log import setup_logging
import logging
import random

setup_logging("INFO", None)

TEST_QUERIES = [
    "会议的主要议题是什么？",
    "张三在会议中提出了哪些建议？",
    "总结一下上周的项目进度会议",
    "会议中有哪些待办事项？",
    "讨论了哪些技术方案？",
    "下一次会议什么时候召开？",
    "会议记录中提到的风险有哪些？",
    "客户反馈的主要问题是什么？",
]


class AgentTestTasks(SequentialTaskSet):
    """Agent 业务测试任务"""
    
    @task(3)
    def test_agent_query(self):
        """测试 Agent 查询接口 - 真实业务负载"""
        query = random.choice(TEST_QUERIES)
        self.client.post("/api/v1/agents/query", json={
            "question": query,
            "enable_tool_calling": True,
            "enable_memory": True,
            "enable_human_in_the_loop": False
        })
    
    @task(1)
    def test_agent_health(self):
        """测试 Agent 健康检查"""
        self.client.get("/api/v1/agents/health")
    
    @task(1)
    def test_agent_tools(self):
        """测试获取工具列表"""
        self.client.get("/api/v1/agents/tools")


class RAGTestTasks(SequentialTaskSet):
    """RAG 业务测试任务"""
    
    @task(2)
    def test_rag_query(self):
        """测试 RAG 查询接口"""
        query = random.choice(TEST_QUERIES)
        self.client.get("/api/v1/rag/query", params={
            "query": query,
            "top_k": 5
        })
    
    @task(1)
    def test_rag_health(self):
        """测试 RAG 健康检查"""
        self.client.get("/api/v1/rag/health")
    
    @task(1)
    def test_vector_search(self):
        """测试向量搜索"""
        self.client.get("/api/v1/vector-search/query", params={
            "query": random.choice(TEST_QUERIES),
            "top_k": 5
        })


class PerformanceTestTasks(SequentialTaskSet):
    """性能指标接口测试任务"""
    
    @task(1)
    def test_performance_matrix(self):
        """测试性能矩阵接口"""
        self.client.get("/api/v1/performance/matrix")
    
    @task(1)
    def test_latency_stats(self):
        """测试延迟统计接口"""
        self.client.get("/api/v1/performance/latency")
    
    @task(1)
    def test_cache_stats(self):
        """测试缓存统计接口"""
        self.client.get("/api/v1/performance/cache")


class BusinessLoadTestUser(HttpUser):
    """业务负载测试用户"""
    wait_time = between(0.5, 2.0)
    tasks = [AgentTestTasks, RAGTestTasks, PerformanceTestTasks]


def run_load_test(host: str = "http://localhost:8000", users: int = 10, spawn_rate: int = 2, duration: int = 60):
    """
    运行负载测试
    
    Args:
        host: 目标服务地址
        users: 并发用户数
        spawn_rate: 每秒生成用户数
        duration: 测试持续时间（秒）
    """
    env = Environment(user_classes=[BusinessLoadTestUser], host=host)
    env.create_local_runner()
    
    env.events.request_success.add_listener(
        lambda request_type, name, response_time, response_length, **kwargs:
        logging.info(f"SUCCESS {request_type} {name} {response_time:.2f}ms {response_length}bytes")
    )
    
    env.events.request_failure.add_listener(
        lambda request_type, name, response_time, exception, **kwargs:
        logging.error(f"FAILURE {request_type} {name} {response_time:.2f}ms {exception}")
    )
    
    stats_printer(env.stats)
    stats_history(env.stats)
    
    env.runner.start(users, spawn_rate=spawn_rate)
    
    try:
        time.sleep(duration)
    except KeyboardInterrupt:
        pass
    
    env.runner.quit()
    
    print("\n" + "="*60)
    print("LOAD TEST RESULTS")
    print("="*60)
    print(f"Total requests: {env.stats.total.num_requests}")
    print(f"Total failures: {env.stats.total.num_failures}")
    print(f"Request rate: {env.stats.total.total_rps:.2f} requests/s")
    print(f"Total response time:")
    print(f"  Min: {env.stats.total.min_response_time:.2f}ms")
    print(f"  Max: {env.stats.total.max_response_time:.2f}ms")
    print(f"  Average: {env.stats.total.avg_response_time:.2f}ms")
    print(f"  Median: {env.stats.total.median_response_time:.2f}ms")
    print(f"  P95: {env.stats.total.get_response_time_percentile(0.95):.2f}ms")
    print(f"  P99: {env.stats.total.get_response_time_percentile(0.99):.2f}ms")
    print("\nPer-endpoint statistics:")
    for name, stats in env.stats.entries.items():
        print(f"\n  {name}:")
        print(f"    Requests: {stats.num_requests}")
        print(f"    Failures: {stats.num_failures}")
        print(f"    Avg: {stats.avg_response_time:.2f}ms")
        print(f"    P95: {stats.get_response_time_percentile(0.95):.2f}ms")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Locust Load Test")
    parser.add_argument("--host", default="http://localhost:8000", help="Target host")
    parser.add_argument("--users", type=int, default=10, help="Number of concurrent users")
    parser.add_argument("--spawn-rate", type=int, default=2, help="Users per second")
    parser.add_argument("--duration", type=int, default=60, help="Test duration in seconds")
    
    args = parser.parse_args()
    
    run_load_test(
        host=args.host,
        users=args.users,
        spawn_rate=args.spawn_rate,
        duration=args.duration
    )