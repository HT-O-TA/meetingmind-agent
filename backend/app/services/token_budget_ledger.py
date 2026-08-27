"""模型调用前的 Token 硬门禁与运行级累计账本。"""

from __future__ import annotations

import json
import math
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Iterator, Mapping, Optional

from app.core.config import settings


class TokenBudgetExceeded(RuntimeError):
    """输入、节点累计或整次运行预算不允许继续调用模型。"""

    def __init__(self, decision: Mapping[str, Any]) -> None:
        self.decision = dict(decision)
        super().__init__(str(self.decision.get("reason") or "LLM Token 预算不足"))


@dataclass(frozen=True)
class TokenCount:
    tokens: int
    method: str


class ModelTokenCounter:
    """优先使用已安装的匹配 tokenizer，否则返回保守 UTF-8 上界。"""

    MESSAGE_OVERHEAD_TOKENS = 6
    REQUEST_OVERHEAD_TOKENS = 3

    def __init__(
        self,
        counters: Optional[Mapping[str, Callable[[str], int]]] = None,
    ) -> None:
        self._counters = dict(counters or {})

    def count_text(self, text: str, model: str) -> TokenCount:
        value = str(text or "")
        counter = self._counters.get(model)
        if counter is not None:
            return TokenCount(max(0, int(counter(value))), f"registered:{model}")

        # tiktoken 只在它明确认识模型时使用；不能拿 OpenAI 编码冒充 Qwen tokenizer。
        if model.startswith(("gpt-", "o1", "o3", "o4")):
            try:
                import tiktoken  # type: ignore

                encoding = tiktoken.encoding_for_model(model)
                return TokenCount(len(encoding.encode(value)), f"tiktoken:{encoding.name}")
            except (ImportError, KeyError, ValueError):
                pass

        # 对当前纯文本入口，UTF-8 字节数是刻意偏大的预调用上界；真实 usage 回写后校准。
        return TokenCount(len(value.encode("utf-8")), "conservative_utf8_upper_bound_v1")

    def count_messages(self, messages: Iterable[Mapping[str, Any]], model: str) -> TokenCount:
        total = self.REQUEST_OVERHEAD_TOKENS
        methods: set[str] = set()
        for message in messages:
            total += self.MESSAGE_OVERHEAD_TOKENS
            role = self.count_text(str(message.get("role") or ""), model)
            methods.add(role.method)
            total += role.tokens
            content = message.get("content")
            if isinstance(content, str):
                serialized = content
            else:
                serialized = json.dumps(content, ensure_ascii=False, sort_keys=True, default=str)
            counted = self.count_text(serialized, model)
            methods.add(counted.method)
            total += counted.tokens
            if message.get("name") is not None:
                named = self.count_text(str(message["name"]), model)
                methods.add(named.method)
                total += named.tokens
        method = "+".join(sorted(methods)) if methods else "empty_messages"
        return TokenCount(total, method)


@dataclass
class TokenBudgetDecision:
    decision_id: str
    node: str
    model: str
    status: str
    count_method: str
    model_context_window_tokens: int
    estimated_input_tokens: int
    requested_output_tokens: int
    safety_margin_tokens: int
    projected_call_tokens: int
    projected_node_tokens: int
    projected_run_tokens: int
    actual_input_tokens: Optional[int] = None
    actual_output_tokens: Optional[int] = None
    accounted_tokens: Optional[int] = None
    reason: Optional[str] = None
    created_at: str = ""


class TokenBudgetLedger:
    """在发出请求前预留最坏情况预算，响应后用供应商 usage 校准。"""

    SCHEMA_VERSION = "token-budget.v1"

    def __init__(
        self,
        *,
        run_id: str,
        default_context_window_tokens: int,
        model_context_windows: Optional[Mapping[str, int]] = None,
        max_run_tokens: int,
        max_node_tokens: int,
        max_calls: int,
        safety_margin_ratio: float,
        counter: Optional[ModelTokenCounter] = None,
    ) -> None:
        if default_context_window_tokens <= 0:
            raise ValueError("default_context_window_tokens 必须大于 0")
        if max_run_tokens <= 0 or max_node_tokens <= 0 or max_calls <= 0:
            raise ValueError("运行、节点和调用次数预算必须大于 0")
        if not 0 <= safety_margin_ratio < 1:
            raise ValueError("safety_margin_ratio 必须位于 [0, 1)")
        self.run_id = run_id
        self.default_context_window_tokens = default_context_window_tokens
        self.model_context_windows = {
            str(key): int(value)
            for key, value in dict(model_context_windows or {}).items()
            if int(value) > 0
        }
        self.max_run_tokens = max_run_tokens
        self.max_node_tokens = max_node_tokens
        self.max_calls = max_calls
        self.safety_margin_ratio = safety_margin_ratio
        self.counter = counter or ModelTokenCounter()
        self._decisions: dict[str, TokenBudgetDecision] = {}
        self._decision_order: list[str] = []
        self._node_accounted: dict[str, int] = {}
        self._run_accounted = 0
        self._accepted_calls = 0
        self._completed_calls = 0
        self._failed_calls = 0
        self._rejected_calls = 0
        self._overrun_detected = False

    @classmethod
    def from_settings(
        cls,
        run_id: str,
        *,
        counter: Optional[ModelTokenCounter] = None,
    ) -> "TokenBudgetLedger":
        return cls(
            run_id=run_id,
            default_context_window_tokens=settings.LLM_CONTEXT_WINDOW_TOKENS,
            model_context_windows=settings.llm_model_context_windows,
            max_run_tokens=settings.LLM_RUN_TOKEN_BUDGET,
            max_node_tokens=settings.LLM_NODE_TOKEN_BUDGET,
            max_calls=settings.LLM_MAX_CALLS_PER_RUN,
            safety_margin_ratio=settings.LLM_TOKEN_SAFETY_MARGIN_RATIO,
            counter=counter,
        )

    @classmethod
    def from_snapshot(
        cls,
        snapshot: Mapping[str, Any],
        *,
        counter: Optional[ModelTokenCounter] = None,
    ) -> "TokenBudgetLedger":
        """从 HITL 快照恢复账本，确认恢复不能获得一份全新的预算。"""
        if snapshot.get("schema_version") != cls.SCHEMA_VERSION:
            raise ValueError("不支持的 TokenBudgetLedger 快照版本")
        ledger = cls(
            run_id=str(snapshot.get("run_id") or "unscoped"),
            default_context_window_tokens=int(snapshot["default_context_window_tokens"]),
            model_context_windows=snapshot.get("model_context_windows") or {},
            max_run_tokens=int(snapshot["max_run_tokens"]),
            max_node_tokens=int(snapshot["max_node_tokens"]),
            max_calls=int(snapshot["max_calls"]),
            safety_margin_ratio=float(snapshot["safety_margin_ratio"]),
            counter=counter,
        )
        ledger._accepted_calls = max(0, int(snapshot.get("accepted_calls", 0)))
        ledger._completed_calls = max(0, int(snapshot.get("completed_calls", 0)))
        ledger._failed_calls = max(0, int(snapshot.get("failed_calls", 0)))
        ledger._rejected_calls = max(0, int(snapshot.get("rejected_calls", 0)))
        ledger._run_accounted = max(0, int(snapshot.get("accounted_run_tokens", 0)))
        ledger._node_accounted = {
            str(node): max(0, int(tokens))
            for node, tokens in dict(snapshot.get("accounted_node_tokens") or {}).items()
        }
        ledger._overrun_detected = bool(snapshot.get("overrun_detected", False))
        for raw in snapshot.get("decisions") or []:
            if not isinstance(raw, Mapping):
                continue
            try:
                decision = TokenBudgetDecision(**dict(raw))
            except (TypeError, ValueError):
                continue
            ledger._decisions[decision.decision_id] = decision
            ledger._decision_order.append(decision.decision_id)
        return ledger

    def context_window_for(self, model: str) -> int:
        return self.model_context_windows.get(model, self.default_context_window_tokens)

    def reserve(
        self,
        *,
        messages: Iterable[Mapping[str, Any]],
        model: str,
        requested_output_tokens: int,
        node: str,
    ) -> dict[str, Any]:
        node = node or "unscoped"
        output_tokens = max(1, int(requested_output_tokens))
        window = self.context_window_for(model)
        counted = self.counter.count_messages(messages, model)
        safety_margin = int(math.ceil(window * self.safety_margin_ratio))
        call_tokens = counted.tokens + output_tokens
        node_tokens = self._node_accounted.get(node, 0) + call_tokens
        run_tokens = self._run_accounted + call_tokens

        reasons = []
        if counted.tokens + output_tokens + safety_margin > window:
            reasons.append("model_context_window_exceeded")
        if node_tokens > self.max_node_tokens:
            reasons.append("node_token_budget_exceeded")
        if run_tokens > self.max_run_tokens:
            reasons.append("run_token_budget_exceeded")
        if self._accepted_calls >= self.max_calls:
            reasons.append("run_call_count_exceeded")

        decision = TokenBudgetDecision(
            decision_id=f"budget_{uuid.uuid4().hex[:16]}",
            node=node,
            model=model,
            status="rejected" if reasons else "reserved",
            count_method=counted.method,
            model_context_window_tokens=window,
            estimated_input_tokens=counted.tokens,
            requested_output_tokens=output_tokens,
            safety_margin_tokens=safety_margin,
            projected_call_tokens=call_tokens,
            projected_node_tokens=node_tokens,
            projected_run_tokens=run_tokens,
            accounted_tokens=0 if reasons else call_tokens,
            reason=",".join(reasons) if reasons else None,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._decisions[decision.decision_id] = decision
        self._decision_order.append(decision.decision_id)
        if reasons:
            self._rejected_calls += 1
            raise TokenBudgetExceeded(asdict(decision))

        self._accepted_calls += 1
        self._run_accounted = run_tokens
        self._node_accounted[node] = node_tokens
        return asdict(decision)

    def complete(
        self,
        decision_id: str,
        *,
        actual_input_tokens: Optional[int],
        actual_output_tokens: Optional[int],
    ) -> dict[str, Any]:
        decision = self._decisions[decision_id]
        if decision.status != "reserved":
            return asdict(decision)

        if actual_input_tokens is not None and actual_output_tokens is not None:
            actual_total = max(0, int(actual_input_tokens)) + max(0, int(actual_output_tokens))
            delta = actual_total - decision.projected_call_tokens
            self._run_accounted += delta
            self._node_accounted[decision.node] = (
                self._node_accounted.get(decision.node, 0) + delta
            )
            decision.actual_input_tokens = max(0, int(actual_input_tokens))
            decision.actual_output_tokens = max(0, int(actual_output_tokens))
            decision.accounted_tokens = actual_total
        decision.status = "completed"
        self._completed_calls += 1
        if (
            self._run_accounted > self.max_run_tokens
            or self._node_accounted.get(decision.node, 0) > self.max_node_tokens
            or (
                decision.actual_input_tokens is not None
                and decision.actual_output_tokens is not None
                and decision.actual_input_tokens
                + decision.actual_output_tokens
                + decision.safety_margin_tokens
                > decision.model_context_window_tokens
            )
        ):
            self._overrun_detected = True
        return asdict(decision)

    def fail(self, decision_id: str, error: BaseException) -> dict[str, Any]:
        decision = self._decisions[decision_id]
        if decision.status == "reserved":
            decision.status = "failed"
            decision.reason = f"provider_call_failed:{error.__class__.__name__}"
            self._failed_calls += 1
        return asdict(decision)

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "run_id": self.run_id,
            "default_context_window_tokens": self.default_context_window_tokens,
            "model_context_windows": dict(self.model_context_windows),
            "max_run_tokens": self.max_run_tokens,
            "max_node_tokens": self.max_node_tokens,
            "max_calls": self.max_calls,
            "safety_margin_ratio": self.safety_margin_ratio,
            "accepted_calls": self._accepted_calls,
            "completed_calls": self._completed_calls,
            "failed_calls": self._failed_calls,
            "rejected_calls": self._rejected_calls,
            "accounted_run_tokens": self._run_accounted,
            "accounted_node_tokens": dict(self._node_accounted),
            "overrun_detected": self._overrun_detected,
            "decisions": [
                asdict(self._decisions[decision_id])
                for decision_id in self._decision_order[-100:]
            ],
        }


_active_ledger: ContextVar[Optional[TokenBudgetLedger]] = ContextVar(
    "meetingmind_token_budget_ledger", default=None
)
_active_node: ContextVar[str] = ContextVar(
    "meetingmind_token_budget_node", default="unscoped"
)


def get_active_token_budget_ledger() -> Optional[TokenBudgetLedger]:
    return _active_ledger.get()


def get_active_token_budget_node() -> str:
    return _active_node.get()


@contextmanager
def activate_token_budget_ledger(ledger: TokenBudgetLedger) -> Iterator[TokenBudgetLedger]:
    token = _active_ledger.set(ledger)
    try:
        yield ledger
    finally:
        _active_ledger.reset(token)


@contextmanager
def token_budget_node_scope(node: str) -> Iterator[None]:
    token = _active_node.set(node or "unscoped")
    try:
        yield
    finally:
        _active_node.reset(token)


__all__ = [
    "ModelTokenCounter",
    "TokenBudgetExceeded",
    "TokenBudgetLedger",
    "activate_token_budget_ledger",
    "get_active_token_budget_ledger",
    "get_active_token_budget_node",
    "token_budget_node_scope",
]
