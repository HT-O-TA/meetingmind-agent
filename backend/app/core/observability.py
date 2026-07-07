"""可观测性与监控系统 - 支持执行追踪、性能监控和日志管理"""
import time
import json
from typing import Dict, List, Any, Optional, Callable
from enum import Enum
from datetime import datetime
from dataclasses import dataclass, asdict
from collections import defaultdict
from app.core.logger import app_logger

# ============================================
# Prometheus 指标定义（业务级自定义指标）
# ============================================
try:
    from prometheus_client import Counter, Histogram, Gauge, REGISTRY

    # RAG 请求总数，按复杂度分级标签
    PROM_RAG_REQUESTS = Counter(
        "meetingmind_rag_requests_total",
        "Total number of RAG requests",
        ["complexity_level"],  # S / R / C / A
    )

    # RAG 端到端延迟直方图（秒）
    PROM_RAG_LATENCY = Histogram(
        "meetingmind_rag_latency_seconds",
        "RAG end-to-end latency in seconds",
        ["complexity_level"],
        buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0),
    )

    # Agent 工具调用次数
    PROM_AGENT_TOOL_CALLS = Counter(
        "meetingmind_agent_tool_calls_total",
        "Total number of agent tool calls",
        ["tool_name"],
    )

    # 检索召回率 Gauge（最近一次评估值）
    PROM_RETRIEVAL_RECALL = Gauge(
        "meetingmind_retrieval_recall",
        "Latest retrieval recall rate",
    )

    # LLM 错误计数
    PROM_LLM_ERRORS = Counter(
        "meetingmind_llm_errors_total",
        "Total number of LLM errors",
        ["error_type"],
    )

    # ==================== Agent 执行链路指标 ====================
    
    # Agent 请求总数
    PROM_AGENT_REQUESTS = Counter(
        "meetingmind_agent_requests_total",
        "Total number of agent requests",
        ["task_type"],
    )

    # Agent 端到端延迟直方图（秒）
    PROM_AGENT_LATENCY = Histogram(
        "meetingmind_agent_latency_seconds",
        "Agent end-to-end latency in seconds",
        ["task_type"],
        buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 15.0),
    )

    # Planner 执行指标
    PROM_PLANNER_REQUESTS = Counter(
        "meetingmind_planner_requests_total",
        "Total number of planner requests",
    )
    
    PROM_PLANNER_LATENCY = Histogram(
        "meetingmind_planner_latency_seconds",
        "Planner latency in seconds",
        buckets=(0.1, 0.25, 0.5, 1.0, 2.0),
    )

    # Retriever 执行指标
    PROM_RETRIEVER_REQUESTS = Counter(
        "meetingmind_retriever_requests_total",
        "Total number of retriever requests",
        ["strategy"],
    )
    
    PROM_RETRIEVER_LATENCY = Histogram(
        "meetingmind_retriever_latency_seconds",
        "Retriever latency in seconds",
        ["strategy"],
        buckets=(0.05, 0.1, 0.25, 0.5, 1.0),
    )

    # Tool 执行指标
    PROM_TOOL_REQUESTS = Counter(
        "meetingmind_tool_requests_total",
        "Total number of tool requests",
        ["tool_name", "success"],
    )
    
    PROM_TOOL_LATENCY = Histogram(
        "meetingmind_tool_latency_seconds",
        "Tool execution latency in seconds",
        ["tool_name"],
        buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
    )

    # LLM 调用指标
    PROM_LLM_REQUESTS = Counter(
        "meetingmind_llm_requests_total",
        "Total number of LLM requests",
        ["model"],
    )
    
    PROM_LLM_LATENCY = Histogram(
        "meetingmind_llm_latency_seconds",
        "LLM latency in seconds",
        ["model"],
        buckets=(0.5, 1.0, 2.0, 3.0, 5.0, 10.0),
    )
    
    PROM_LLM_TOKENS = Counter(
        "meetingmind_llm_tokens_total",
        "Total LLM tokens used",
        ["model", "type"],  # type: prompt, completion
    )

    # Reflection 执行指标
    PROM_REFLECTION_REQUESTS = Counter(
        "meetingmind_reflection_requests_total",
        "Total number of reflection requests",
        ["action"],  # continue, retry, replan
    )
    
    PROM_REFLECTION_LATENCY = Histogram(
        "meetingmind_reflection_latency_seconds",
        "Reflection latency in seconds",
        buckets=(0.1, 0.25, 0.5, 1.0, 2.0),
    )

    # Agent 成功率
    PROM_AGENT_SUCCESS_RATE = Gauge(
        "meetingmind_agent_success_rate",
        "Agent success rate",
        ["task_type"],
    )

    # 重试次数
    PROM_RETRY_COUNT = Counter(
        "meetingmind_retry_count_total",
        "Total number of retries",
        ["component"],  # planner, retriever, tool, llm, reflection
    )

    # Token 成本估算
    PROM_TOKEN_COST = Gauge(
        "meetingmind_token_cost_usd",
        "Estimated token cost in USD",
        ["model"],
    )

    _PROMETHEUS_AVAILABLE = True
except Exception:
    _PROMETHEUS_AVAILABLE = False


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
    
    class _SpanContext:
        def __init__(self, tracer: "Tracer", span_id: str):
            self._tracer = tracer
            self.span_id = span_id

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            status = TraceStatus.FAILED if exc_type else TraceStatus.COMPLETED
            self._tracer.end_span(self.span_id, status)
            return False

        def __str__(self) -> str:
            return self.span_id

        def set_attribute(self, key: str, value: Any):
            self._tracer.add_span_attribute(self.span_id, key, value)

    def start_span(self, name: str, trace_id: Optional[str] = None, parent_span_id: Optional[str] = None):
        """开始跨度"""
        return_context = trace_id is None
        if trace_id is None:
            trace_id = self.start_trace()
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
        if return_context:
            return Tracer._SpanContext(self, span_id)
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
    
    def get_trace(self, trace_id: Optional[str] = None):
        """获取追踪"""
        if trace_id is None:
            return self.get_recent_traces()
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

    def increment(self, name: str, labels: Optional[Dict[str, str]] = None):
        """兼容旧接口。"""
        self.increment_counter(name, labels)
    
    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """设置仪表盘值"""
        self._gauges[name] = value
        self._record_metric(name, MetricType.GAUGE, value, labels)
    
    def record_histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """记录直方图值"""
        self._histograms[name].append(value)
        self._record_metric(name, MetricType.HISTOGRAM, value, labels)

    def record(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """兼容旧接口。"""
        self.record_histogram(name, value, labels)
    
    def record_timer(self, name: str, duration_ms: float, labels: Optional[Dict[str, str]] = None):
        """记录计时"""
        self._record_metric(name, MetricType.TIMER, duration_ms, labels)

    # ============================================
    # Prometheus 桥接方法（业务事件 → Prometheus 指标）
    # ============================================

    def track_rag_request(self, complexity_level: str, latency_seconds: float):
        """记录 RAG 请求（同步内部指标 + Prometheus）"""
        self.increment_counter("rag_requests", {"complexity_level": complexity_level})
        self.record_histogram("rag_latency_seconds", latency_seconds, {"complexity_level": complexity_level})
        if _PROMETHEUS_AVAILABLE:
            try:
                PROM_RAG_REQUESTS.labels(complexity_level=complexity_level).inc()
                PROM_RAG_LATENCY.labels(complexity_level=complexity_level).observe(latency_seconds)
            except Exception:
                pass

    def track_agent_tool_call(self, tool_name: str):
        """记录 Agent 工具调用（同步内部指标 + Prometheus）"""
        self.increment_counter("agent_tool_calls", {"tool_name": tool_name})
        if _PROMETHEUS_AVAILABLE:
            try:
                PROM_AGENT_TOOL_CALLS.labels(tool_name=tool_name).inc()
            except Exception:
                pass

    def set_retrieval_recall(self, value: float):
        """设置检索召回率（同步内部指标 + Prometheus）"""
        self.set_gauge("retrieval_recall", value)
        if _PROMETHEUS_AVAILABLE:
            try:
                PROM_RETRIEVAL_RECALL.set(value)
            except Exception:
                pass

    def track_llm_error(self, error_type: str):
        """记录 LLM 错误（同步内部指标 + Prometheus）"""
        self.increment_counter("llm_errors", {"error_type": error_type})
        if _PROMETHEUS_AVAILABLE:
            try:
                PROM_LLM_ERRORS.labels(error_type=error_type).inc()
            except Exception:
                pass

    # ==================== Agent 执行链路追踪方法 ====================

    def track_agent_request(self, task_type: str, latency_seconds: float, success: bool = True):
        """记录 Agent 请求"""
        self.increment_counter("agent_requests", {"task_type": task_type})
        self.record_histogram("agent_latency_seconds", latency_seconds, {"task_type": task_type})
        if _PROMETHEUS_AVAILABLE:
            try:
                PROM_AGENT_REQUESTS.labels(task_type=task_type).inc()
                PROM_AGENT_LATENCY.labels(task_type=task_type).observe(latency_seconds)
                PROM_AGENT_SUCCESS_RATE.labels(task_type=task_type).set(1.0 if success else 0.0)
            except Exception:
                pass

    def track_planner(self, latency_seconds: float):
        """记录 Planner 执行"""
        self.increment_counter("planner_requests")
        self.record_histogram("planner_latency_seconds", latency_seconds)
        if _PROMETHEUS_AVAILABLE:
            try:
                PROM_PLANNER_REQUESTS.inc()
                PROM_PLANNER_LATENCY.observe(latency_seconds)
            except Exception:
                pass

    def track_retriever(self, strategy: str, latency_seconds: float):
        """记录 Retriever 执行"""
        self.increment_counter("retriever_requests", {"strategy": strategy})
        self.record_histogram("retriever_latency_seconds", latency_seconds, {"strategy": strategy})
        if _PROMETHEUS_AVAILABLE:
            try:
                PROM_RETRIEVER_REQUESTS.labels(strategy=strategy).inc()
                PROM_RETRIEVER_LATENCY.labels(strategy=strategy).observe(latency_seconds)
            except Exception:
                pass

    def track_tool(self, tool_name: str, latency_seconds: float, success: bool = True):
        """记录 Tool 执行"""
        self.increment_counter("tool_requests", {"tool_name": tool_name, "success": str(success)})
        self.record_histogram("tool_latency_seconds", latency_seconds, {"tool_name": tool_name})
        if _PROMETHEUS_AVAILABLE:
            try:
                PROM_TOOL_REQUESTS.labels(tool_name=tool_name, success=str(success)).inc()
                PROM_TOOL_LATENCY.labels(tool_name=tool_name).observe(latency_seconds)
            except Exception:
                pass

    def track_llm(self, model: str, latency_seconds: float, prompt_tokens: int = 0, completion_tokens: int = 0):
        """记录 LLM 调用"""
        self.increment_counter("llm_requests", {"model": model})
        self.record_histogram("llm_latency_seconds", latency_seconds, {"model": model})
        if _PROMETHEUS_AVAILABLE:
            try:
                PROM_LLM_REQUESTS.labels(model=model).inc()
                PROM_LLM_LATENCY.labels(model=model).observe(latency_seconds)
                if prompt_tokens > 0:
                    PROM_LLM_TOKENS.labels(model=model, type="prompt").inc(prompt_tokens)
                if completion_tokens > 0:
                    PROM_LLM_TOKENS.labels(model=model, type="completion").inc(completion_tokens)
            except Exception:
                pass

    def track_reflection(self, action: str, latency_seconds: float):
        """记录 Reflection 执行"""
        self.increment_counter("reflection_requests", {"action": action})
        self.record_histogram("reflection_latency_seconds", latency_seconds)
        if _PROMETHEUS_AVAILABLE:
            try:
                PROM_REFLECTION_REQUESTS.labels(action=action).inc()
                PROM_REFLECTION_LATENCY.observe(latency_seconds)
            except Exception:
                pass

    def track_retry(self, component: str):
        """记录重试"""
        self.increment_counter("retry_count", {"component": component})
        if _PROMETHEUS_AVAILABLE:
            try:
                PROM_RETRY_COUNT.labels(component=component).inc()
            except Exception:
                pass

    def set_token_cost(self, model: str, cost_usd: float):
        """设置 Token 成本"""
        self.set_gauge("token_cost_usd", cost_usd, {"model": model})
        if _PROMETHEUS_AVAILABLE:
            try:
                PROM_TOKEN_COST.labels(model=model).set(cost_usd)
            except Exception:
                pass

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
    
    def get_metrics(self, name: Optional[str] = None):
        """获取指标"""
        if name:
            return [m for m in self._metrics if m.name == name]
        return self.get_metric_summary()
    
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
