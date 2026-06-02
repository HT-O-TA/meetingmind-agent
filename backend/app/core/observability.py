"""可观测性与监控系统 - 支持执行追踪、性能监控和日志管理"""
import time
import json
from typing import Dict, List, Any, Optional, Callable
from enum import Enum
from datetime import datetime
from dataclasses import dataclass, asdict
from collections import defaultdict
from app.core.logger import app_logger


class TraceStatus(str, Enum):
    """追踪状态"""
    STARTED = "started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class MetricType(str, Enum):
    """指标类型"""
    COUNTER = "counter"      # 计数器
    GAUGE = "gauge"          # 仪表盘
    HISTOGRAM = "histogram"  # 直方图
    TIMER = "timer"          # 计时器


@dataclass
class Span:
    """追踪跨度"""
    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    name: str
    start_time: datetime
    end_time: Optional[datetime]
    status: TraceStatus
    attributes: Dict[str, Any]
    events: List[Dict[str, Any]]
    duration_ms: Optional[float] = None
    
    def __post_init__(self):
        if self.end_time:
            self.duration_ms = (self.end_time - self.start_time).total_seconds() * 1000


@dataclass
class Trace:
    """追踪记录"""
    trace_id: str
    spans: List[Span]
    start_time: datetime
    end_time: Optional[datetime]
    status: TraceStatus
    metadata: Dict[str, Any]
    duration_ms: Optional[float] = None
    
    def __post_init__(self):
        if self.end_time:
            self.duration_ms = (self.end_time - self.start_time).total_seconds() * 1000


@dataclass
class Metric:
    """指标"""
    name: str
    type: MetricType
    value: float
    labels: Dict[str, str]
    timestamp: datetime
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class LogEntry:
    """日志条目"""
    log_id: str
    level: str
    message: str
    timestamp: datetime
    context: Dict[str, Any]
    trace_id: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class Tracer:
    """分布式追踪器"""
    
    def __init__(self):
        self._traces: Dict[str, Trace] = {}
        self._current_span: Optional[Span] = None
    
    def start_trace(self, trace_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> str:
        """开始追踪"""
        if trace_id is None:
            trace_id = f"trace_{int(time.time() * 1000)}_{id(self)}"
        
        trace = Trace(
            trace_id=trace_id,
            spans=[],
            start_time=datetime.now(),
            end_time=None,
            status=TraceStatus.STARTED,
            metadata=metadata or {}
        )
        
        self._traces[trace_id] = trace
        app_logger.debug(f"[Tracer] 开始追踪: {trace_id}")
        return trace_id
    
    def start_span(self, name: str, trace_id: str, parent_span_id: Optional[str] = None) -> str:
        """开始跨度"""
        if trace_id not in self._traces:
            self.start_trace(trace_id)
        
        span_id = f"span_{int(time.time() * 1000)}_{id(self)}"
        span = Span(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            name=name,
            start_time=datetime.now(),
            end_time=None,
            status=TraceStatus.STARTED,
            attributes={},
            events=[]
        )
        
        self._traces[trace_id].spans.append(span)
        self._current_span = span
        
        app_logger.debug(f"[Tracer] 开始跨度: {span_id} ({name})")
        return span_id
    
    def end_span(self, span_id: str, status: TraceStatus = TraceStatus.COMPLETED):
        """结束跨度"""
        for trace in self._traces.values():
            for span in trace.spans:
                if span.span_id == span_id:
                    span.end_time = datetime.now()
                    span.status = status
                    span.duration_ms = (span.end_time - span.start_time).total_seconds() * 1000
                    app_logger.debug(f"[Tracer] 结束跨度: {span_id} ({span.duration_ms:.2f}ms)")
                    return
    
    def end_trace(self, trace_id: str, status: TraceStatus = TraceStatus.COMPLETED):
        """结束追踪"""
        if trace_id not in self._traces:
            return
        
        trace = self._traces[trace_id]
        trace.end_time = datetime.now()
        trace.status = status
        trace.duration_ms = (trace.end_time - trace.start_time).total_seconds() * 1000
        
        app_logger.debug(f"[Tracer] 结束追踪: {trace_id} ({trace.duration_ms:.2f}ms)")
    
    def add_span_attribute(self, span_id: str, key: str, value: Any):
        """添加跨度属性"""
        for trace in self._traces.values():
            for span in trace.spans:
                if span.span_id == span_id:
                    span.attributes[key] = value
                    return
    
    def add_span_event(self, span_id: str, name: str, attributes: Optional[Dict[str, Any]] = None):
        """添加跨度事件"""
        for trace in self._traces.values():
            for span in trace.spans:
                if span.span_id == span_id:
                    span.events.append({
                        "name": name,
                        "timestamp": datetime.now().isoformat(),
                        "attributes": attributes or {}
                    })
                    return
    
    def get_trace(self, trace_id: str) -> Optional[Trace]:
        """获取追踪"""
        return self._traces.get(trace_id)
    
    def get_recent_traces(self, limit: int = 10) -> List[Trace]:
        """获取最近的追踪"""
        traces = list(self._traces.values())
        traces.sort(key=lambda t: t.start_time, reverse=True)
        return traces[:limit]


class MetricsCollector:
    """指标收集器"""
    
    def __init__(self):
        self._metrics: List[Metric] = []
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
    
    def increment_counter(self, name: str, labels: Optional[Dict[str, str]] = None):
        """增加计数器"""
        self._counters[name] += 1
        self._record_metric(name, MetricType.COUNTER, self._counters[name], labels)
    
    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """设置仪表盘值"""
        self._gauges[name] = value
        self._record_metric(name, MetricType.GAUGE, value, labels)
    
    def record_histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """记录直方图值"""
        self._histograms[name].append(value)
        self._record_metric(name, MetricType.HISTOGRAM, value, labels)
    
    def record_timer(self, name: str, duration_ms: float, labels: Optional[Dict[str, str]] = None):
        """记录计时"""
        self._record_metric(name, MetricType.TIMER, duration_ms, labels)
    
    def _record_metric(self, name: str, type: MetricType, value: float, labels: Optional[Dict[str, str]]):
        """记录指标"""
        metric = Metric(
            name=name,
            type=type,
            value=value,
            labels=labels or {},
            timestamp=datetime.now()
        )
        self._metrics.append(metric)
        
        # 保持指标数量在限制范围内
        max_metrics = 1000
        while len(self._metrics) > max_metrics:
            self._metrics.pop(0)
    
    def get_metrics(self, name: Optional[str] = None) -> List[Metric]:
        """获取指标"""
        if name:
            return [m for m in self._metrics if m.name == name]
        return self._metrics
    
    def get_metric_summary(self) -> Dict[str, Any]:
        """获取指标摘要"""
        summary = {}
        
        for metric in self._metrics:
            key = metric.name
            if key not in summary:
                summary[key] = {
                    "type": metric.type.value,
                    "count": 0,
                    "sum": 0.0,
                    "min": float('inf'),
                    "max": float('-inf'),
                    "labels": set()
                }
            
            summary[key]["count"] += 1
            summary[key]["sum"] += metric.value
            summary[key]["min"] = min(summary[key]["min"], metric.value)
            summary[key]["max"] = max(summary[key]["max"], metric.value)
            summary[key]["labels"].update(metric.labels.keys())
        
        # 计算平均值
        for key in summary:
            if summary[key]["count"] > 0:
                summary[key]["avg"] = summary[key]["sum"] / summary[key]["count"]
            summary[key]["labels"] = list(summary[key]["labels"])
        
        return summary
    
    def get_counters(self) -> Dict[str, int]:
        """获取计数器"""
        return dict(self._counters)


class LogManager:
    """日志管理器"""
    
    def __init__(self):
        self._logs: List[LogEntry] = []
    
    def log(self, level: str, message: str, context: Optional[Dict[str, Any]] = None, trace_id: Optional[str] = None):
        """记录日志"""
        log_entry = LogEntry(
            log_id=f"log_{int(time.time() * 1000)}_{id(self)}",
            level=level.upper(),
            message=message,
            context=context or {},
            trace_id=trace_id,
            timestamp=datetime.now()
        )
        
        self._logs.append(log_entry)
        
        # 保持日志数量在限制范围内
        max_logs = 500
        while len(self._logs) > max_logs:
            self._logs.pop(0)
        
        # 同步到标准日志
        if level.upper() == "ERROR":
            app_logger.error(message, extra=context)
        elif level.upper() == "WARNING":
            app_logger.warning(message, extra=context)
        elif level.upper() == "INFO":
            app_logger.info(message, extra=context)
        else:
            app_logger.debug(message, extra=context)
    
    def debug(self, message: str, context: Optional[Dict[str, Any]] = None, trace_id: Optional[str] = None):
        """记录调试日志"""
        self.log("DEBUG", message, context, trace_id)
    
    def info(self, message: str, context: Optional[Dict[str, Any]] = None, trace_id: Optional[str] = None):
        """记录信息日志"""
        self.log("INFO", message, context, trace_id)
    
    def warning(self, message: str, context: Optional[Dict[str, Any]] = None, trace_id: Optional[str] = None):
        """记录警告日志"""
        self.log("WARNING", message, context, trace_id)
    
    def error(self, message: str, context: Optional[Dict[str, Any]] = None, trace_id: Optional[str] = None):
        """记录错误日志"""
        self.log("ERROR", message, context, trace_id)
    
    def get_logs(self, level: Optional[str] = None, limit: int = 50) -> List[LogEntry]:
        """获取日志"""
        logs = self._logs
        if level:
            logs = [l for l in logs if l.level == level.upper()]
        
        return logs[-limit:]


class ObservabilitySystem:
    """可观测性系统"""
    
    def __init__(self):
        self._tracer = Tracer()
        self._metrics_collector = MetricsCollector()
        self._log_manager = LogManager()
        self._start_time = datetime.now()
    
    def get_tracer(self) -> Tracer:
        """获取追踪器"""
        return self._tracer
    
    def get_metrics_collector(self) -> MetricsCollector:
        """获取指标收集器"""
        return self._metrics_collector
    
    def get_log_manager(self) -> LogManager:
        """获取日志管理器"""
        return self._log_manager
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        uptime = (datetime.now() - self._start_time).total_seconds()
        
        return {
            "status": "healthy",
            "uptime_seconds": uptime,
            "uptime_formatted": self._format_uptime(uptime),
            "timestamp": datetime.now().isoformat()
        }
    
    def _format_uptime(self, seconds: float) -> str:
        """格式化运行时间"""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}天")
        if hours > 0:
            parts.append(f"{hours}小时")
        if minutes > 0:
            parts.append(f"{minutes}分钟")
        parts.append(f"{secs}秒")
        
        return " ".join(parts)
    
    def get_overview(self) -> Dict[str, Any]:
        """获取概览信息"""
        traces = self._tracer.get_recent_traces(5)
        metrics = self._metrics_collector.get_metric_summary()
        logs = self._log_manager.get_logs(limit=10)
        health = self.get_health_status()
        
        return {
            "health": health,
            "recent_traces": len(traces),
            "metrics_summary": metrics,
            "recent_logs_count": len(logs),
            "start_time": self._start_time.isoformat()
        }


# 全局可观测性系统实例
observability_system = ObservabilitySystem()


def get_observability_system() -> ObservabilitySystem:
    """获取可观测性系统实例"""
    return observability_system


def trace_decorator(trace_name: str):
    """追踪装饰器"""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            tracer = get_observability_system().get_tracer()
            metrics = get_observability_system().get_metrics_collector()
            
            trace_id = tracer.start_trace()
            span_id = tracer.start_span(trace_name, trace_id)
            
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                tracer.end_span(span_id, TraceStatus.COMPLETED)
                tracer.end_trace(trace_id, TraceStatus.COMPLETED)
                return result
            except Exception as e:
                tracer.end_span(span_id, TraceStatus.FAILED)
                tracer.end_trace(trace_id, TraceStatus.FAILED)
                metrics.increment_counter("errors", {"function": trace_name})
                raise
            finally:
                duration = (time.time() - start_time) * 1000
                metrics.record_timer(f"{trace_name}_duration", duration)
                metrics.increment_counter(f"{trace_name}_calls")
        
        def sync_wrapper(*args, **kwargs):
            tracer = get_observability_system().get_tracer()
            metrics = get_observability_system().get_metrics_collector()
            
            trace_id = tracer.start_trace()
            span_id = tracer.start_span(trace_name, trace_id)
            
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                tracer.end_span(span_id, TraceStatus.COMPLETED)
                tracer.end_trace(trace_id, TraceStatus.COMPLETED)
                return result
            except Exception as e:
                tracer.end_span(span_id, TraceStatus.FAILED)
                tracer.end_trace(trace_id, TraceStatus.FAILED)
                metrics.increment_counter("errors", {"function": trace_name})
                raise
            finally:
                duration = (time.time() - start_time) * 1000
                metrics.record_timer(f"{trace_name}_duration", duration)
                metrics.increment_counter(f"{trace_name}_calls")
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator
