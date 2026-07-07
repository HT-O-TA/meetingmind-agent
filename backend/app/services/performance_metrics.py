"""统一性能指标服务 - 收集和聚合系统性能数据"""
import time
import statistics
import json
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from collections import deque

from app.core.observability import get_observability_system
from app.core.cache_init import get_cache_stats
from app.core.fault_tolerance import get_fault_tolerance_system
from app.agents.monitor import get_monitor
from app.agents.trace_integration import get_execution_tracer


class PerformanceMetrics:
    """性能指标收集器"""
    
    def __init__(self):
        self._request_timestamps = deque(maxlen=10000)
        self._latency_records = deque(maxlen=10000)
        self._token_cost_records = deque(maxlen=10000)
        self._tool_executions = deque(maxlen=10000)
        self._start_time = time.time()
    
    def record_request(self, latency_ms: float = 0.0, token_cost_usd: float = 0.0):
        """记录请求"""
        self._request_timestamps.append(time.time())
        self._latency_records.append(latency_ms)
        if token_cost_usd > 0:
            self._token_cost_records.append(token_cost_usd)
    
    def record_tool_execution(self, tool_id: str, success: bool, latency_ms: float, retry_count: int = 0):
        """记录工具执行"""
        self._tool_executions.append({
            "timestamp": time.time(),
            "tool_id": tool_id,
            "success": success,
            "latency_ms": latency_ms,
            "retry_count": retry_count
        })
    
    def calculate_qps(self, window_seconds: int = 60) -> float:
        """计算 QPS"""
        now = time.time()
        cutoff = now - window_seconds
        count = sum(1 for ts in self._request_timestamps if ts >= cutoff)
        return count / window_seconds
    
    def calculate_latency_percentiles(self) -> Dict[str, float]:
        """计算延迟百分位数"""
        if not self._latency_records:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "avg": 0.0, "min": 0.0, "max": 0.0}
        
        sorted_latencies = sorted(self._latency_records)
        n = len(sorted_latencies)
        
        return {
            "p50": float(sorted_latencies[int(n * 0.50)]),
            "p95": float(sorted_latencies[int(n * 0.95)]),
            "p99": float(sorted_latencies[int(n * 0.99)]),
            "avg": float(sum(sorted_latencies) / n),
            "min": float(sorted_latencies[0]),
            "max": float(sorted_latencies[-1]),
            "count": n
        }
    
    def calculate_token_cost(self) -> Dict[str, float]:
        """计算 Token 成本"""
        if not self._token_cost_records:
            return {"total_usd": 0.0, "avg_usd": 0.0, "count": 0}
        
        total = sum(self._token_cost_records)
        return {
            "total_usd": total,
            "avg_usd": total / len(self._token_cost_records),
            "count": len(self._token_cost_records)
        }
    
    def _calculate_tool_execution_stats(self) -> Dict[str, Any]:
        """计算工具执行统计"""
        if not self._tool_executions:
            return {"total": 0, "success_rate": 0.0, "avg_latency_ms": 0.0, "by_tool": {}}
        
        total = len(self._tool_executions)
        successes = sum(1 for e in self._tool_executions if e["success"])
        total_latency = sum(e["latency_ms"] for e in self._tool_executions)
        
        by_tool = {}
        for e in self._tool_executions:
            tool_id = e["tool_id"]
            if tool_id not in by_tool:
                by_tool[tool_id] = {"total": 0, "success": 0, "total_latency_ms": 0.0}
            by_tool[tool_id]["total"] += 1
            by_tool[tool_id]["success"] += 1 if e["success"] else 0
            by_tool[tool_id]["total_latency_ms"] += e["latency_ms"]
        
        for tool_id, stats in by_tool.items():
            stats["success_rate"] = stats["success"] / stats["total"] if stats["total"] > 0 else 0.0
            stats["avg_latency_ms"] = stats["total_latency_ms"] / stats["total"] if stats["total"] > 0 else 0.0
        
        return {
            "total": total,
            "success_rate": successes / total if total > 0 else 0.0,
            "avg_latency_ms": total_latency / total if total > 0 else 0.0,
            "by_tool": by_tool
        }
    
    def get_performance_matrix(self) -> Dict[str, Any]:
        """获取完整性能矩阵"""
        latency = self.calculate_latency_percentiles()
        cache_stats = get_cache_stats()
        retry_stats = get_fault_tolerance_system().get_retry_manager().get_retry_statistics()
        monitor_stats = get_monitor().get_agent_stats()
        
        metrics_collector = get_observability_system().get_metrics_collector()
        metrics_summary = metrics_collector.get_metric_summary()
        
        tool_requests = metrics_summary.get("tool_requests", {})
        llm_requests = metrics_summary.get("llm_requests", {})
        
        tool_success_rate = 0.0
        if tool_requests.get("count", 0) > 0:
            tool_success_rate = (tool_requests.get("success_count", 0) or 0) / tool_requests["count"]
        
        tool_exec_stats = self._calculate_tool_execution_stats()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": time.time() - self._start_time,
            "qps": {
                "current": self.calculate_qps(60),
                "5min": self.calculate_qps(300),
                "15min": self.calculate_qps(900)
            },
            "latency_ms": latency,
            "cache": {
                "hit_rate": cache_stats["hit_rate"],
                "total_hits": cache_stats["total_hits"],
                "total_misses": cache_stats["total_misses"],
                "api_cache_hit_rate": cache_stats["api_cache_hit_rate"],
                "llm_cache_hit_rate": cache_stats["llm_cache_hit_rate"],
                "enabled": cache_stats["enabled"]
            },
            "token_cost": {
                "total_usd": monitor_stats.get("total_cost_usd", 0.0),
                "avg_usd": monitor_stats.get("avg_cost_usd", 0.0),
                "total_tokens": monitor_stats.get("total_tokens", 0)
            },
            "tool": {
                "total_requests": tool_requests.get("count", 0) + tool_exec_stats["total"],
                "success_rate": max(tool_success_rate, tool_exec_stats["success_rate"]),
                "avg_latency_ms": tool_exec_stats["avg_latency_ms"],
                "by_tool": tool_exec_stats["by_tool"]
            },
            "agent": {
                "total_requests": monitor_stats.get("total_requests", 0),
                "success_rate": monitor_stats.get("success_rate", 0.0),
                "error_rate": monitor_stats.get("error_rate", 0.0),
                "avg_latency_ms": monitor_stats.get("avg_latency_ms", 0.0)
            },
            "retry": {
                "total_retries": retry_stats.get("total_retries", 0),
                "retry_rate": retry_stats.get("retry_rate", 0.0),
                "success_rate": retry_stats.get("success_rate", 0.0),
                "by_component": retry_stats.get("by_component", {})
            },
            "llm": {
                "total_requests": llm_requests.get("count", 0),
                "avg_latency_seconds": llm_requests.get("avg", 0.0)
            },
            "overall_score": monitor_stats.get("overall_score", 0.0)
        }
    
    def get_latency_stats(self) -> Dict[str, Any]:
        """获取延迟统计"""
        return {
            "latency_ms": self.calculate_latency_percentiles(),
            "qps": {
                "1min": self.calculate_qps(60),
                "5min": self.calculate_qps(300),
                "15min": self.calculate_qps(900)
            }
        }
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return get_cache_stats()
    
    def get_cost_stats(self) -> Dict[str, Any]:
        """获取成本统计"""
        monitor_stats = get_monitor().get_agent_stats()
        token_cost = self.calculate_token_cost()
        
        return {
            "token": token_cost,
            "agent": {
                "total_cost_usd": monitor_stats.get("total_cost_usd", 0.0),
                "avg_cost_usd": monitor_stats.get("avg_cost_usd", 0.0),
                "total_tokens": monitor_stats.get("total_tokens", 0),
                "avg_tokens": monitor_stats.get("avg_tokens", 0)
            }
        }
    
    def get_retry_stats(self) -> Dict[str, Any]:
        """获取重试统计"""
        return get_fault_tolerance_system().get_retry_manager().get_retry_statistics()
    
    def reset(self):
        """重置统计"""
        self._request_timestamps.clear()
        self._latency_records.clear()
        self._token_cost_records.clear()
        self._tool_executions.clear()
        self._start_time = time.time()
    
    def generate_full_report(self) -> Dict[str, Any]:
        """
        生成完整的性能数据报告
        
        包含：
        - P50/P95/P99 延迟
        - QPS（1min/5min/15min）
        - 缓存命中率
        - 工具调用成功率
        - Agent 成功率
        - 路由准确率
        - Token 成本统计
        - 系统健康状态
        """
        latency = self.calculate_latency_percentiles()
        cache_stats = get_cache_stats()
        retry_stats = get_fault_tolerance_system().get_retry_manager().get_retry_statistics()
        monitor_stats = get_monitor().get_agent_stats()
        metrics_collector = get_observability_system().get_metrics_collector()
        metrics_summary = metrics_collector.get_metric_summary()
        tracer = get_execution_tracer()
        
        tool_exec_stats = self._calculate_tool_execution_stats()
        
        qps_data = {
            "current": self.calculate_qps(60),
            "5min": self.calculate_qps(300),
            "15min": self.calculate_qps(900)
        }
        
        token_cost_data = self.calculate_token_cost()
        
        recent_traces = tracer.get_recent_traces(10)
        trace_summary = []
        for trace in recent_traces:
            trace_summary.append({
                "trace_id": trace["trace_id"],
                "duration_ms": trace["summary"]["total_duration_ms"],
                "total_tokens": trace["summary"]["total_tokens"],
                "total_cost_usd": trace["summary"]["total_cost_usd"],
                "status": trace["status"],
                "step_count": trace["summary"]["total_steps"]
            })
        
        health_status = self._evaluate_health_status(latency, cache_stats, monitor_stats)
        
        report = {
            "report_id": f"perf_{uuid.uuid4().hex[:8]}",
            "timestamp": datetime.now().isoformat(),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "uptime": {
                "seconds": int(time.time() - self._start_time),
                "hours": round((time.time() - self._start_time) / 3600, 2)
            },
            "health_status": health_status,
            
            "latency": {
                "p50_ms": latency["p50"],
                "p95_ms": latency["p95"],
                "p99_ms": latency["p99"],
                "avg_ms": latency["avg"],
                "min_ms": latency["min"],
                "max_ms": latency["max"],
                "sample_count": latency["count"]
            },
            
            "qps": {
                "1min": round(qps_data["current"], 2),
                "5min": round(qps_data["5min"], 2),
                "15min": round(qps_data["15min"], 2)
            },
            
            "cache": {
                "hit_rate": round(cache_stats["hit_rate"] * 100, 2),
                "api_cache_hit_rate": round(cache_stats["api_cache_hit_rate"] * 100, 2),
                "llm_cache_hit_rate": round(cache_stats["llm_cache_hit_rate"] * 100, 2),
                "total_hits": cache_stats["total_hits"],
                "total_misses": cache_stats["total_misses"],
                "enabled": cache_stats["enabled"]
            },
            
            "token_cost": {
                "total_usd": round(token_cost_data["total_usd"], 4),
                "avg_usd_per_request": round(token_cost_data["avg_usd"], 6),
                "total_requests": token_cost_data["count"],
                "agent_total_cost_usd": round(monitor_stats.get("total_cost_usd", 0.0), 4),
                "agent_total_tokens": monitor_stats.get("total_tokens", 0),
                "agent_avg_tokens": monitor_stats.get("avg_tokens", 0)
            },
            
            "tool_execution": {
                "total_requests": tool_exec_stats["total"],
                "success_rate": round(tool_exec_stats["success_rate"] * 100, 2),
                "avg_latency_ms": round(tool_exec_stats["avg_latency_ms"], 2),
                "by_tool": tool_exec_stats["by_tool"]
            },
            
            "agent": {
                "total_requests": monitor_stats.get("total_requests", 0),
                "successful_requests": monitor_stats.get("successful_requests", 0),
                "failed_requests": monitor_stats.get("failed_requests", 0),
                "success_rate": round(monitor_stats.get("success_rate", 0.0) * 100, 2),
                "error_rate": round(monitor_stats.get("error_rate", 0.0) * 100, 2),
                "avg_latency_ms": round(monitor_stats.get("avg_latency_ms", 0.0), 2),
                "avg_cost_usd": round(monitor_stats.get("avg_cost_usd", 0.0), 6),
                "avg_tokens": monitor_stats.get("avg_tokens", 0)
            },
            
            "retry": {
                "total_retries": retry_stats.get("total_retries", 0),
                "retry_rate": round(retry_stats.get("retry_rate", 0.0) * 100, 2),
                "success_rate": round(retry_stats.get("success_rate", 0.0) * 100, 2),
                "by_component": retry_stats.get("by_component", {})
            },
            
            "llm": {
                "total_requests": metrics_summary.get("llm_requests", {}).get("count", 0),
                "avg_latency_seconds": round(metrics_summary.get("llm_requests", {}).get("avg", 0.0), 2)
            },
            
            "evaluation": {
                "task_success_scores": monitor_stats.get("task_success_scores", []),
                "tool_success_scores": monitor_stats.get("tool_success_scores", []),
                "route_accuracy_scores": monitor_stats.get("route_accuracy_scores", []),
                "avg_task_success": round(self._calculate_avg_score(monitor_stats.get("task_success_scores", [])), 2),
                "avg_tool_success": round(self._calculate_avg_score(monitor_stats.get("tool_success_scores", [])), 2),
                "avg_route_accuracy": round(self._calculate_avg_score(monitor_stats.get("route_accuracy_scores", [])), 2)
            },
            
            "recent_traces": trace_summary,
            
            "summary": {
                "total_requests": monitor_stats.get("total_requests", 0),
                "overall_success_rate": round(monitor_stats.get("success_rate", 0.0) * 100, 2),
                "overall_score": round(monitor_stats.get("overall_score", 0.0) * 100, 2),
                "total_cost_usd": round(monitor_stats.get("total_cost_usd", 0.0), 4),
                "recommendation": self._generate_recommendation(health_status, latency, cache_stats, monitor_stats)
            }
        }
        
        return report
    
    def _evaluate_health_status(
        self,
        latency: Dict[str, float],
        cache_stats: Dict[str, Any],
        monitor_stats: Dict[str, Any]
    ) -> str:
        """评估系统健康状态"""
        error_rate = monitor_stats.get("error_rate", 0.0)
        success_rate = monitor_stats.get("success_rate", 0.0)
        cache_hit_rate = cache_stats.get("hit_rate", 0.0)
        p95_latency = latency.get("p95", 0.0)
        
        if error_rate > 0.1 or success_rate < 0.8:
            return "critical"
        elif error_rate > 0.05 or success_rate < 0.9:
            return "warning"
        elif p95_latency > 5000:
            return "warning"
        elif cache_hit_rate < 0.3:
            return "warning"
        else:
            return "healthy"
    
    def _calculate_avg_score(self, scores: List[float]) -> float:
        """计算平均分数"""
        if not scores:
            return 0.0
        return sum(scores) / len(scores)
    
    def _generate_recommendation(
        self,
        health_status: str,
        latency: Dict[str, float],
        cache_stats: Dict[str, Any],
        monitor_stats: Dict[str, Any]
    ) -> List[str]:
        """生成优化建议"""
        recommendations = []
        
        if health_status == "critical":
            recommendations.append("系统负载过高，请检查资源使用情况")
            recommendations.append("错误率超过 10%，请排查关键服务")
        
        if health_status == "warning":
            recommendations.append("系统状态异常，请关注监控指标")
        
        if latency.get("p95", 0.0) > 5000:
            recommendations.append("P95 延迟超过 5 秒，建议优化慢查询或增加缓存")
        
        if cache_stats.get("hit_rate", 0.0) < 0.5:
            recommendations.append("缓存命中率低于 50%，建议优化缓存策略")
        
        if monitor_stats.get("error_rate", 0.0) > 0.05:
            recommendations.append("错误率较高，建议检查日志排查问题")
        
        if not recommendations:
            recommendations.append("系统运行正常，继续保持")
        
        return recommendations


_performance_metrics: Optional[PerformanceMetrics] = None


def get_performance_metrics() -> PerformanceMetrics:
    """获取性能指标收集器"""
    global _performance_metrics
    if _performance_metrics is None:
        _performance_metrics = PerformanceMetrics()
    return _performance_metrics


async def record_performance(latency_ms: float = 0.0, token_cost_usd: float = 0.0):
    """记录性能数据"""
    pm = get_performance_metrics()
    pm.record_request(latency_ms, token_cost_usd)


async def get_performance_matrix() -> Dict[str, Any]:
    """获取完整性能矩阵"""
    return get_performance_metrics().get_performance_matrix()


async def get_latency_stats() -> Dict[str, Any]:
    """获取延迟统计"""
    return get_performance_metrics().get_latency_stats()


async def get_cache_performance() -> Dict[str, Any]:
    """获取缓存性能统计"""
    return get_performance_metrics().get_cache_stats()


async def get_cost_performance() -> Dict[str, Any]:
    """获取成本性能统计"""
    return get_performance_metrics().get_cost_stats()


async def get_retry_performance() -> Dict[str, Any]:
    """获取重试性能统计"""
    return get_performance_metrics().get_retry_stats()


async def generate_performance_report() -> Dict[str, Any]:
    """生成完整的性能数据报告"""
    return get_performance_metrics().generate_full_report()