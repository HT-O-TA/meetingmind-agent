"""Locust 性能压测脚本 - 测试 MeetingMind API"""
from locust import HttpUser, task, between, constant_pacing
import json
import random


class MeetingMindUser(HttpUser):
    """模拟用户行为"""
    wait_time = between(1, 3)  # 用户请求间隔 1-3 秒
    host = "http://localhost:8000"
    
    # 测试问题池
    questions = [
        "你好",
        "会议中有哪些讨论要点",
        "今天的会议时间是什么时候",
        "总结上周的会议内容",
        "提取会议中的行动项",
        "分析销售数据的增长趋势",
        "比较2024年和2025年的业绩",
        "下一步计划是什么",
        "谁负责这个项目",
        "会议记录在哪里"
    ]
    
    def on_start(self):
        """用户初始化 - 登录获取token"""
        # 尝试登录
        try:
            response = self.client.post(
                "/api/v1/users/login",
                json={"username": "testuser", "password": "test123"}
            )
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("data", {}).get("access_token")
                self.auth_header = {"Authorization": f"Bearer {self.token}"}
            else:
                # 如果登录失败，尝试注册
                self.client.post(
                    "/api/v1/users/register",
                    json={"email": f"locust_{random.randint(1, 10000)}@test.com", 
                          "password": "test123", 
                          "username": f"locust_{random.randint(1, 10000)}"}
                )
                response = self.client.post(
                    "/api/v1/users/login",
                    json={"username": "testuser", "password": "test123"}
                )
                if response.status_code == 200:
                    data = response.json()
                    self.token = data.get("data", {}).get("access_token")
                    self.auth_header = {"Authorization": f"Bearer {self.token}"}
                else:
                    self.auth_header = {}
        except Exception:
            self.auth_header = {}
    
    @task(3)
    def test_rag_ask(self):
        """测试 RAG 问答接口（权重3）"""
        question = random.choice(self.questions)
        self.client.post(
            "/api/v1/rag/ask",
            json={"question": question, "top_k": 3},
            headers=self.auth_header
        )
    
    @task(2)
    def test_agent_query(self):
        """测试 Agent 查询接口（权重2）"""
        question = random.choice(self.questions)
        self.client.post(
            "/api/v1/agents/query",
            json={"question": question},
            headers=self.auth_header
        )
    
    @task(1)
    def test_health(self):
        """测试健康检查接口（权重1）"""
        self.client.get("/health")
    
    @task(1)
    def test_vector_search(self):
        """测试向量检索接口（权重1）"""
        self.client.post(
            "/api/v1/vector-search/search",
            json={"content": "会议要点", "top_k": 5},
            headers=self.auth_header
        )
    
    @task(1)
    def test_document_list(self):
        """测试文档列表接口（权重1）"""
        self.client.get(
            "/api/v1/documents",
            headers=self.auth_header
        )


class FastUser(HttpUser):
    """快速用户 - 更短的等待时间，更高并发"""
    wait_time = constant_pacing(0.5)  # 每0.5秒发送一个请求
    host = "http://localhost:8000"
    
    def on_start(self):
        """用户初始化"""
        self.auth_header = {}
    
    @task(5)
    def test_health_fast(self):
        """快速测试健康检查"""
        self.client.get("/health")
    
    @task(3)
    def test_rag_fast(self):
        """快速测试RAG问答"""
        self.client.post(
            "/api/v1/rag/ask",
            json={"question": "快速测试", "top_k": 3}
        )


class LoadTestScenario:
    """性能测试场景配置"""
    # 测试场景
    scenarios = {
        "normal_load": {
            "users": 10,
            "spawn_rate": 1,
            "duration": "60s"
        },
        "medium_load": {
            "users": 50,
            "spawn_rate": 5,
            "duration": "120s"
        },
        "high_load": {
            "users": 100,
            "spawn_rate": 10,
            "duration": "180s"
        }
    }
