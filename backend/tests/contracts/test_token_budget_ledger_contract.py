"""模型调用前 Token 硬门禁与运行级累计账本契约。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.nodes import AgentNodes
from app.agents.state import create_initial_state
from app.services.input_preprocessor import InputPreprocessor
from app.services.llm_service import LLMService
from app.services.token_budget_ledger import (
    ModelTokenCounter,
    TokenBudgetExceeded,
    TokenBudgetLedger,
    activate_token_budget_ledger,
    token_budget_node_scope,
)


def _ledger(**overrides) -> TokenBudgetLedger:
    config = {
        "run_id": "run_budget_test",
        "default_context_window_tokens": 1000,
        "model_context_windows": {"test-model": 1000},
        "max_run_tokens": 200,
        "max_node_tokens": 100,
        "max_calls": 4,
        "safety_margin_ratio": 0.1,
        "counter": ModelTokenCounter({"test-model": len}),
    }
    config.update(overrides)
    return TokenBudgetLedger(**config)


def _messages(content: str = "hello") -> list[dict[str, str]]:
    return [{"role": "user", "content": content}]


def test_ledger_reserves_worst_case_then_reconciles_provider_usage():
    ledger = _ledger()

    decision = ledger.reserve(
        messages=_messages(),
        model="test-model",
        requested_output_tokens=20,
        node="plan_node",
    )
    assert decision["status"] == "reserved"
    assert decision["count_method"] == "registered:test-model"

    completed = ledger.complete(
        decision["decision_id"],
        actual_input_tokens=11,
        actual_output_tokens=7,
    )
    snapshot = ledger.snapshot()

    assert completed["status"] == "completed"
    assert completed["accounted_tokens"] == 18
    assert snapshot["accounted_run_tokens"] == 18
    assert snapshot["accounted_node_tokens"] == {"plan_node": 18}


@pytest.mark.parametrize(
    ("overrides", "node", "content", "output_tokens", "reason"),
    [
        (
            {"default_context_window_tokens": 30, "model_context_windows": {}},
            "answer_node",
            "x" * 20,
            5,
            "model_context_window_exceeded",
        ),
        (
            {"max_node_tokens": 20},
            "answer_node",
            "hello",
            5,
            "node_token_budget_exceeded",
        ),
        (
            {"max_run_tokens": 20},
            "answer_node",
            "hello",
            5,
            "run_token_budget_exceeded",
        ),
        (
            {"max_calls": 1},
            "answer_node",
            "hello",
            5,
            "run_call_count_exceeded",
        ),
    ],
)
def test_ledger_rejects_each_hard_limit_before_a_new_call(
    overrides, node, content, output_tokens, reason
):
    ledger = _ledger(**overrides)
    if reason == "run_call_count_exceeded":
        first = ledger.reserve(
            messages=_messages("a"),
            model="test-model",
            requested_output_tokens=1,
            node=node,
        )
        ledger.complete(first["decision_id"], actual_input_tokens=1, actual_output_tokens=1)

    with pytest.raises(TokenBudgetExceeded) as exc_info:
        ledger.reserve(
            messages=_messages(content),
            model="test-model",
            requested_output_tokens=output_tokens,
            node=node,
        )

    assert reason in exc_info.value.decision["reason"]
    assert ledger.snapshot()["rejected_calls"] == 1


def test_ledger_snapshot_restore_preserves_run_and_node_consumption():
    ledger = _ledger()
    first = ledger.reserve(
        messages=_messages("first"),
        model="test-model",
        requested_output_tokens=10,
        node="execute_node",
    )
    ledger.complete(first["decision_id"], actual_input_tokens=8, actual_output_tokens=4)

    restored = TokenBudgetLedger.from_snapshot(
        ledger.snapshot(),
        counter=ModelTokenCounter({"test-model": len}),
    )
    second = restored.reserve(
        messages=_messages("second"),
        model="test-model",
        requested_output_tokens=10,
        node="execute_node",
    )

    assert second["projected_run_tokens"] > 12
    assert second["projected_node_tokens"] > 12
    assert restored.snapshot()["accepted_calls"] == 2


def test_hitl_resume_state_carries_the_same_budget_snapshot():
    ledger = _ledger()
    first = ledger.reserve(
        messages=_messages("before confirmation"),
        model="test-model",
        requested_output_tokens=10,
        node="execute_node",
    )
    ledger.complete(first["decision_id"], actual_input_tokens=9, actual_output_tokens=3)
    state = create_initial_state("创建任务")
    state["agent_run_id"] = ledger.run_id
    state["input_envelope"] = InputPreprocessor().build_envelope(state)
    tool_manager = MagicMock()
    tool_manager.selector.format_tools_for_prompt.return_value = ""
    nodes = AgentNodes(llm_service=MagicMock(), tool_manager=tool_manager)

    with activate_token_budget_ledger(ledger):
        resume_state = nodes._build_resume_state(state)

    saved = resume_state["input_envelope"]["budget"]["token_ledger"]
    restored = TokenBudgetLedger.from_snapshot(
        saved,
        counter=ModelTokenCounter({"test-model": len}),
    )

    assert saved["run_id"] == ledger.run_id
    assert saved["accounted_run_tokens"] == 12
    assert restored.snapshot()["accounted_run_tokens"] == 12


@pytest.mark.asyncio
async def test_llm_service_records_provider_usage_on_shared_agent_ledger():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
    )
    create = AsyncMock(return_value=response)
    service = LLMService()
    service.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    ledger = _ledger()

    with activate_token_budget_ledger(ledger), token_budget_node_scope("plan_node"):
        result = await service.chat(
            messages=_messages(),
            model="test-model",
            max_tokens=20,
        )

    assert result == "ok"
    create.assert_awaited_once()
    assert ledger.snapshot()["accounted_run_tokens"] == 18
    assert ledger.snapshot()["decisions"][0]["node"] == "plan_node"


@pytest.mark.asyncio
async def test_llm_service_does_not_call_provider_after_preflight_rejection():
    create = AsyncMock()
    service = LLMService()
    service.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    ledger = _ledger(
        default_context_window_tokens=30,
        model_context_windows={},
    )

    with activate_token_budget_ledger(ledger), token_budget_node_scope("answer_node"):
        with pytest.raises(TokenBudgetExceeded):
            await service.chat(
                messages=_messages("x" * 20),
                model="test-model",
                max_tokens=5,
            )

    create.assert_not_awaited()
    assert service.last_budget_decision["status"] == "rejected"


@pytest.mark.asyncio
async def test_cancelled_provider_call_is_visible_as_failed_reservation():
    create = AsyncMock(side_effect=asyncio.CancelledError())
    service = LLMService()
    service.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    ledger = _ledger()

    with activate_token_budget_ledger(ledger), token_budget_node_scope("answer_node"):
        with pytest.raises(asyncio.CancelledError):
            await service.chat(
                messages=_messages(),
                model="test-model",
                max_tokens=5,
            )

    snapshot = ledger.snapshot()
    assert snapshot["failed_calls"] == 1
    assert snapshot["decisions"][0]["reason"] == "provider_call_failed:CancelledError"


def test_unknown_qwen_model_uses_explicit_conservative_counter():
    count = ModelTokenCounter().count_text("中A", "qwen-future")

    assert count.tokens == len("中A".encode("utf-8"))
    assert count.method == "conservative_utf8_upper_bound_v1"
