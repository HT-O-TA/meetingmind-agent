"""日志与监控系统 - 提供日志记录、性能监控、统计功能
"""
import logging
import time
import asyncio
from typing import Dict, List, Optional, Any
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from collections import deque, defaultdict
from functools import wraps
import json


class LogLevel(Enum):
    """日志级别"""
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


@dataclass
class Metric:
    """性能指标"""
    name: str
    value: float
    unit: str = ""
    timestamp: float = 0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = time.time()
        if self.metadata is None:
            self.metadata = {}


@dataclass
class TraceSpan:
    """追踪跨度 - 记录 Agent 执行链路的详细信息"""
    span_id: str
    parent_id: Optional[str]
    operation_name: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    attributes: Dict[str, Any] = None
    
    # Agent 执行链路专用字段
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    token_cost_usd: float = 0.0
    retry_count: int = 0
    output: Optional[str] = None
    error: Optional[str] = None
    status: str = "running"  # running, completed, failed
    
    def __post_init__(self):
        if self.attributes is None:
            self.attributes = {}
            
    def finish(self):
        """结束跨度并计算持续时间"""
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        if self.error:
            self.status = "failed"
        else:
            self.status = "completed"
            
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，用于序列化"""
        return {
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "operation_name": self.operation_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration * 1000 if self.duration else None,
            "attributes": self.attributes,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "token_cost_usd": self.token_cost_usd,
            "retry_count": self.retry_count,
            "output": self.output,
            "error": self.error,
            "status": self.status,
        }


class AgentMonitor:
    """Agent 监控器"""
    
    def __init__(self, max_history: int = 1000, max_spans: int = 1000):
        self.logger = self._setup_logger()
        self.metrics: Dict[str, List[Metric]] = defaultdict(list)
        self.metric_history = deque(maxlen=max_history)
        self.spans: Dict[str, TraceSpan] = {}
        self.span_history = deque(maxlen=max_spans)
        self.active_spans: List[str] = []
        self.event_handlers: Dict[str, List[callable]] = defaultdict(list)
        
        self.agent_stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "total_latency_ms": 0.0,
            "total_retries": 0,
            "hallucination_count": 0,
            "task_success_scores": [],
            "tool_success_scores": [],
            "route_accuracy_scores": [],
            "reflection_scores": [],
            "latency_scores": [],
            "cost_efficiency_scores": [],
            "hallucination_risk_scores": []
        }
        
    def _setup_logger(self) -> logging.Logger:
        """设置日志记录器
        
        Returns:
            配置好的 Logger
        """
        logger = logging.getLogger("agent_monitor")
        logger.setLevel(logging.DEBUG)
        
        if not logger.handlers:
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(formatter)
            
            file_handler = logging.FileHandler("agent_monitor.log")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            
            logger.addHandler(console_handler)
            logger.addHandler(file_handler)
        
        return logger
    
    def log(self, level: LogLevel, message: str, **kwargs):
        """记录日志
        
        Args:
            level: 日志级别
            message: 日志消息
            **kwargs: 额外字段
        """
        self.logger.log(level.value, message, extra=kwargs)
        
    def info(self, message: str, **kwargs):
        self.log(LogLevel.INFO, message, **kwargs)
        
    def debug(self, message: str, **kwargs):
        self.log(LogLevel.DEBUG, message, **kwargs)
        
    def warning(self, message: str, **kwargs):
        self.log(LogLevel.WARNING, message, **kwargs)
        
    def error(self, message: str, **kwargs):
        self.log(LogLevel.ERROR, message, **kwargs)
        
    def critical(self, message: str, **kwargs):
        self.log(LogLevel.CRITICAL, message, **kwargs)
    
    def start_span(self, operation_name: str, parent_id: Optional[str] = None, attributes: Optional[Dict] = None) -> str:
        """开始追踪跨度
        
        Args:
            operation_name: 操作名称
            parent_id: 父跨度 ID
            attributes: 额外属性
            
        Returns:
            跨度 ID
        """
        import uuid
        span_id = str(uuid.uuid4())
        span = TraceSpan(
            span_id=span_id,
            parent_id=parent_id,
            operation_name=operation_name,
            start_time=time.time(),
            attributes=attributes or {}
        )
        self.spans[span_id] = span
        self.active_spans.append(span_id)
        return span_id
        
    def finish_span(self, span_id: Optional[str] = None, attributes: Optional[Dict] = None):
        """结束追踪跨度
        
        Args:
            span_id: 跨度 ID
            attributes: 额外属性
        """
        if span_id is None and self.active_spans:
            span_id = self.active_spans[-1]
        
        if span_id not in self.spans:
            return
            
        span = self.spans[span_id]
        span.finish()
        if attributes:
            span.attributes.update(attributes)
        self.span_history.append(span)
        
        if span_id in self.active_spans:
            self.active_spans.remove(span_id)
            
        # 记录指标
        self.record_metric(
            name=f"span.{span.operation_name}",
            value=span.duration,
            unit="s",
            metadata=span.attributes
        )
    
    def update_span_tokens(self, span_id: str, prompt_tokens: int = 0, completion_tokens: int = 0):
        """更新跨度的 Token 信息
        
        Args:
            span_id: 跨度 ID
            prompt_tokens: Prompt Token 数
            completion_tokens: Completion Token 数
        """
        if span_id in self.spans:
            span = self.spans[span_id]
            span.prompt_tokens = prompt_tokens
            span.completion_tokens = completion_tokens
            span.total_tokens = prompt_tokens + completion_tokens
    
    def update_span_cost(self, span_id: str, cost_usd: float):
        """更新跨度的成本信息
        
        Args:
            span_id: 跨度 ID
            cost_usd: 成本（美元）
        """
        if span_id in self.spans:
            span = self.spans[span_id]
            span.token_cost_usd = cost_usd
    
    def update_span_retry(self, span_id: str, retry_count: int):
        """更新跨度的重试次数
        
        Args:
            span_id: 跨度 ID
            retry_count: 重试次数
        """
        if span_id in self.spans:
            span = self.spans[span_id]
            span.retry_count = retry_count
    
    def update_span_output(self, span_id: str, output: str):
        """更新跨度的输出信息
        
        Args:
            span_id: 跨度 ID
            output: 输出内容
        """
        if span_id in self.spans:
            span = self.spans[span_id]
            # 限制输出长度，避免内存溢出
            max_output_len = 2000
            span.output = output[:max_output_len] if len(output) > max_output_len else output
    
    def update_span_error(self, span_id: str, error: str):
        """更新跨度的错误信息
        
        Args:
            span_id: 跨度 ID
            error: 错误内容
        """
        if span_id in self.spans:
            span = self.spans[span_id]
            span.error = error
            span.status = "failed"
    
    def record_metric(self, name: str, value: float, unit: str = "", metadata: Optional[Dict] = None):
        """记录指标
        
        Args:
            name: 指标名称
            value: 值
            unit: 单位
            metadata: 元数据
        """
        metric = Metric(
            name=name,
            value=value,
            unit=unit,
            timestamp=time.time(),
            metadata=metadata or {}
        )
        self.metrics[name].append(metric)
        self.metric_history.append(metric)
        
        # 保持在限制内
        if len(self.metrics[name]) > 1000:
            self.metrics[name] = self.metrics[name][-1000:]
    
    def record_agent_request(
        self,
        success: bool,
        latency_ms: float,
        token_cost_usd: float = 0.0,
        total_tokens: int = 0,
        retry_count: int = 0,
        hallucination_detected: bool = False,
        task_success: float = 0.0,
        tool_success: float = 0.0,
        route_accuracy: float = 0.0,
        reflection_score: float = 0.0,
        latency_score: float = 0.0,
        cost_efficiency: float = 0.0,
        hallucination_risk: float = 0.0
    ):
        """记录 Agent 请求统计
        
        Args:
            success: 是否成功
            latency_ms: 延迟(ms)
            token_cost_usd: 令牌成本(美元)
            total_tokens: 总令牌数
            retry_count: 重试次数
            hallucination_detected: 是否检测到幻觉
            task_success: 任务成功率
            tool_success: 工具成功率
            route_accuracy: 路由准确性
            reflection_score: 反思分数
            latency_score: 延迟分数
            cost_efficiency: 成本效率
            hallucination_risk: 幻觉风险
        """
        self.agent_stats["total_requests"] += 1
        if success:
            self.agent_stats["successful_requests"] += 1
        else:
            self.agent_stats["failed_requests"] += 1
        
        self.agent_stats["total_tokens"] += total_tokens
        self.agent_stats["total_cost_usd"] += token_cost_usd
        self.agent_stats["total_latency_ms"] += latency_ms
        self.agent_stats["total_retries"] += retry_count
        
        if hallucination_detected:
            self.agent_stats["hallucination_count"] += 1
        
        max_scores = 1000
        self.agent_stats["task_success_scores"].append(task_success)
        self.agent_stats["tool_success_scores"].append(tool_success)
        self.agent_stats["route_accuracy_scores"].append(route_accuracy)
        self.agent_stats["reflection_scores"].append(reflection_score)
        self.agent_stats["latency_scores"].append(latency_score)
        self.agent_stats["cost_efficiency_scores"].append(cost_efficiency)
        self.agent_stats["hallucination_risk_scores"].append(hallucination_risk)
        
        if len(self.agent_stats["task_success_scores"]) > max_scores:
            for key in [
                "task_success_scores", "tool_success_scores", "route_accuracy_scores",
                "reflection_scores", "latency_scores", "cost_efficiency_scores",
                "hallucination_risk_scores"
            ]:
                self.agent_stats[key] = self.agent_stats[key][-max_scores:]
            
    def get_agent_stats(self) -> Dict[str, Any]:
        """获取 Agent 统计信息
        
        Returns:
            统计信息字典
        """
        stats = self.agent_stats.copy()
        total = stats["total_requests"]
        
        if total > 0:
            stats["success_rate"] = stats["successful_requests"] / total
            stats["error_rate"] = stats["failed_requests"] / total
            stats["avg_latency_ms"] = stats["total_latency_ms"] / total
            stats["avg_tokens"] = stats["total_tokens"] / total
            stats["avg_cost_usd"] = stats["total_cost_usd"] / total
            stats["avg_retries"] = stats["total_retries"] / total
            stats["hallucination_rate"] = stats["hallucination_count"] / total
        else:
            stats["success_rate"] = 0.0
            stats["error_rate"] = 0.0
            stats["avg_latency_ms"] = 0.0
            stats["avg_tokens"] = 0
            stats["avg_cost_usd"] = 0.0
            stats["avg_retries"] = 0.0
            stats["hallucination_rate"] = 0.0
        
        for key in [
            "task_success_scores", "tool_success_scores", "route_accuracy_scores",
            "reflection_scores", "latency_scores", "cost_efficiency_scores",
            "hallucination_risk_scores"
        ]:
            scores = stats[key]
            if scores:
                avg_key = key.replace("_scores", "_avg")
                stats[avg_key] = sum(scores) / len(scores)
            else:
                avg_key = key.replace("_scores", "_avg")
                stats[avg_key] = 0.0
        
        stats["overall_score"] = self._calculate_overall_score(stats)
        
        return stats
    
    def _calculate_overall_score(self, stats: Dict[str, Any]) -> float:
        """计算综合评分
        
        Args:
            stats: 统计信息
            
        Returns:
            综合评分
        """
        weights = {
            "task_success_avg": 0.20,
            "tool_success_avg": 0.15,
            "route_accuracy_avg": 0.10,
            "reflection_avg": 0.10,
            "latency_avg": 0.15,
            "cost_efficiency_avg": 0.15,
            "hallucination_risk_avg": 0.15
        }
        
        total_score = 0.0
        total_weight = 0.0
        
        for key, weight in weights.items():
            if key in stats:
                if key == "hallucination_risk_avg":
                    total_score += (1.0 - stats[key]) * weight
                else:
                    total_score += stats[key] * weight
                total_weight += weight
        
        return total_score / total_weight if total_weight > 0 else 0.0
    
    def reset_agent_stats(self):
        """重置 Agent 统计信息"""
        self.agent_stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "total_latency_ms": 0.0,
            "total_retries": 0,
            "hallucination_count": 0,
            "task_success_scores": [],
            "tool_success_scores": [],
            "route_accuracy_scores": [],
            "reflection_scores": [],
            "latency_scores": [],
            "cost_efficiency_scores": [],
            "hallucination_risk_scores": []
        }
            
    def get_metric_stats(self, name: str) -> Dict[str, Any]:
        """获取指标统计信息
        
        Args:
            name: 指标名称
            
        Returns:
            统计信息字典
        """
        if name not in self.metrics or not self.metrics[name]:
            return {}
            
        values = [m.value for m in self.metrics[name]]
        return {
            "count": len(values),
            "avg": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "latest": values[-1]
        }
        
    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """获取所有指标统计
        
        Returns:
            所有指标统计字典
        """
        return {name: self.get_metric_stats(name) for name in self.metrics}
        
    def get_spans(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取最近的追踪跨度
        
        Args:
            limit: 返回数量限制
            
        Returns:
            跨度列表
        """
        spans = list(self.span_history)[-limit:]
        return [span.to_dict() for span in spans]
    
    def get_trace_tree(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取追踪树结构（按时间排序的完整执行链路）
        
        Args:
            limit: 返回数量限制
            
        Returns:
            追踪树列表
        """
        spans = list(self.span_history)[-limit:]
        
        span_dict = {span.span_id: span.to_dict() for span in spans}
        result = []
        
        for span in spans:
            span_data = span.to_dict()
            children = []
            for child_span in spans:
                if child_span.parent_id == span.span_id:
                    children.append(child_span.to_dict())
            
            if children:
                span_data["children"] = children
            
            if span.parent_id is None:
                result.append(span_data)
        
        return result
    
    def get_span_by_id(self, span_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID 获取跨度信息
        
        Args:
            span_id: 跨度 ID
            
        Returns:
            跨度信息
        """
        for span in self.span_history:
            if span.span_id == span_id:
                return span.to_dict()
        return None
    
    def get_spans_by_operation(self, operation_name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """根据操作名称获取跨度
        
        Args:
            operation_name: 操作名称
            limit: 返回数量限制
            
        Returns:
            跨度列表
        """
        spans = [span for span in self.span_history if span.operation_name == operation_name]
        return [span.to_dict() for span in spans[-limit:]]
    
    def subscribe(self, event: str, handler: callable):
        """订阅事件
        
        Args:
            event: 事件名称
            handler: 事件处理函数
        """
        self.event_handlers[event].append(handler)
        
    def emit(self, event: str, **kwargs):
        """触发事件
        
        Args:
            event: 事件名称
            **kwargs: 事件数据
        """
        for handler in self.event_handlers.get(event, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    asyncio.create_task(handler(**kwargs))
                else:
                    handler(**kwargs)
            except Exception as e:
                self.logger.error(f"Error in event handler: {e}")
                
    def get_monitor_status(self) -> Dict[str, Any]:
        """获取监控器状态
        
        Returns:
            状态信息
        """
        return {
            "metrics_count": sum(len(v) for v in self.metrics.values()),
            "spans_count": len(self.span_history),
            "active_spans": len(self.active_spans),
            "metrics": self.get_all_metrics(),
            "timestamp": time.time()
        }


def monitor_timing(monitor: Optional[AgentMonitor], name: str = None):
    """装饰器 - 监控函数执行时间（monitor 为 None 时直接透传，不做监控）

    Args:
        monitor: 监控器，可为 None
        name: 指标名称（可选，默认使用函数名）
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            if monitor is None:
                return await func(*args, **kwargs)
            span_name = name or func.__name__
            span_id = monitor.start_span(span_name)
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start
                monitor.record_metric(f"func.{span_name}", duration, "s")
                monitor.finish_span(span_id, {"function": func.__name__})

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            if monitor is None:
                return func(*args, **kwargs)
            span_name = name or func.__name__
            span_id = monitor.start_span(span_name)
            start = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start
                monitor.record_metric(f"func.{span_name}", duration, "s")
                monitor.finish_span(span_id, {"function": func.__name__})

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    return decorator


# 全局监控器实例
_global_monitor: Optional[AgentMonitor] = None

def get_monitor() -> AgentMonitor:
    """获取全局监控器
    
    Returns:
        全局监控器实例
    """
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = AgentMonitor()
    return _global_monitor
