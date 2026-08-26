"""进程内 Agent 节点 Trace；只记录真实执行，不生成伪造成本或评测数据。"""

from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any, Deque, Dict, List, Optional


@dataclass
class TraceSpan:
    span_id: str
    operation_name: str
    component_type: str
    started_at: float
    status: str = "running"
    duration_ms: Optional[float] = None
    retry_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    output: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TraceStore:
    """有界 Trace 存储；重启即清空，避免把演示数据冒充持久化观测。"""

    def __init__(self, max_spans: int = 200):
        self.max_spans = max_spans
        self._active: Dict[str, tuple[TraceSpan, float]] = {}
        self._completed: Deque[TraceSpan] = deque(maxlen=max_spans)

    def start(self, operation_name: str, component_type: str) -> str:
        span = TraceSpan(
            span_id=f"span_{uuid.uuid4().hex[:16]}",
            operation_name=operation_name,
            component_type=component_type,
            started_at=time.time(),
        )
        self._active[span.span_id] = (span, time.perf_counter())
        return span.span_id

    def update(self, span_id: str, **changes: Any) -> None:
        entry = self._active.get(span_id)
        if not entry:
            return
        span = entry[0]
        for key, value in changes.items():
            if hasattr(span, key):
                setattr(span, key, value)

    def finish(self, span_id: str, error: Optional[str] = None) -> None:
        entry = self._active.pop(span_id, None)
        if not entry:
            return
        span, started = entry
        span.duration_ms = round((time.perf_counter() - started) * 1000, 2)
        span.error = error or span.error
        span.status = "failed" if span.error else "completed"
        self._completed.append(span)

    def list(self, limit: int = 100, operation_name: Optional[str] = None) -> List[Dict[str, Any]]:
        spans = reversed(self._completed)
        if operation_name:
            spans = (span for span in spans if span.operation_name == operation_name)
        return [span.to_dict() for _, span in zip(range(max(0, limit)), spans)]

    def get(self, span_id: str) -> Optional[Dict[str, Any]]:
        active = self._active.get(span_id)
        if active:
            return active[0].to_dict()
        for span in reversed(self._completed):
            if span.span_id == span_id:
                return span.to_dict()
        return None

    def summary(self) -> Dict[str, Any]:
        spans = list(self._completed)
        completed = [span for span in spans if span.status == "completed"]
        durations = [span.duration_ms or 0.0 for span in spans]
        return {
            "retained_spans": len(spans),
            "active_spans": len(self._active),
            "success_rate": round(len(completed) / len(spans), 4) if spans else None,
            "average_latency_ms": round(sum(durations) / len(durations), 2) if durations else None,
            "storage": "bounded_process_memory",
        }


_trace_store = TraceStore()


def get_trace_store() -> TraceStore:
    return _trace_store


class AgentTraceContext:
    """Agent 节点使用的同步/异步上下文管理器。"""

    def __init__(
        self,
        operation_name: str,
        component_type: str = "agent",
        parent_span_id: Optional[str] = None,
    ):
        self.operation_name = operation_name
        self.component_type = component_type
        self.parent_span_id = parent_span_id
        self.span_id: Optional[str] = None

    def _enter(self) -> "AgentTraceContext":
        self.span_id = get_trace_store().start(self.operation_name, self.component_type)
        return self

    def _exit(self, error: Optional[BaseException]) -> bool:
        if self.span_id:
            get_trace_store().finish(self.span_id, str(error) if error else None)
        return False

    async def __aenter__(self) -> "AgentTraceContext":
        return self._enter()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        return self._exit(exc_val)

    def __enter__(self) -> "AgentTraceContext":
        return self._enter()

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        return self._exit(exc_val)

    def _update(self, **changes: Any) -> None:
        if self.span_id:
            get_trace_store().update(self.span_id, **changes)

    def update_tokens(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        self._update(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)

    def update_cost(self, cost_usd: float) -> None:
        self._update(cost_usd=cost_usd)

    def update_retry(self, retry_count: int) -> None:
        self._update(retry_count=retry_count)

    def update_output(self, output: str) -> None:
        self._update(output=output[:500])

    def update_error(self, error: str) -> None:
        self._update(error=error[:500])
