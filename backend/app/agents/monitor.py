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
    """追踪跨度"""
    span_id: str
    parent_id: Optional[str]
    operation_name: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    attributes: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.attributes is None:
            self.attributes = {}
            
    def finish(self):
        """结束跨度并计算持续时间"""
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time


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
        return [
            {
                "span_id": span.span_id,
                "parent_id": span.parent_id,
                "operation_name": span.operation_name,
                "start_time": span.start_time,
                "end_time": span.end_time,
                "duration": span.duration,
                "attributes": span.attributes
            }
            for span in spans
        ]
    
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
