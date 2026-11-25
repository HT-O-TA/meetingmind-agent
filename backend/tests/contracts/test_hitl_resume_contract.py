"""HITL 确认点恢复契约：恢复执行前必须用当前用户权限重新取回证据。"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents import agent_service as agent_service_module
from app.agents.agent_service import AgentService
from app.agents.state import create_initial_state
from app.services.input_preprocessor import InputPreprocessor
from app.services.token_budget_ledger import TokenBudgetLedger


def _snapshot():
    state = create_initial_state("生成纪要并创建 Jira 任务", meeting_id=7)
    state.update({"user_id": 1, "thread_id": "1:s:c", "agent_run_id": "run-1"})
    envelope = InputPreprocessor().build_envelope(state)
    envelope.setdefault("budget", {})["token_ledger"] = TokenBudgetLedger.from_settings("run-1").snapshot()
    state["input_envelope"] = envelope
    state["pending_action"] = {"source": "tool", "tool_name": "jira_create_issue"}
    state["retrieval_required"] = True
    state["context"] = []  # 与 checkpoint 白名单一致：证据原文不落盘
    return state


class _FakeHitl:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.finish_claim = AsyncMock(return_value=True)

    async def get_request_status(self, request_id, user_id):
        return {"status": "pending", "run_status": "pending", "details": {"thread_id": "1:s:c", "agent_run_id": "run-1"}}

    async def get_resume_state(self, request_id, user_id):
        return dict(self.snapshot)

    async def claim_request(self, request_id, user_id):
        return {"claim_token": "t"}


@pytest.mark.asyncio
async def test_approved_tool_cannot_resume_after_write_permission_is_revoked(monkeypatch):
    service = AgentService.__new__(AgentService)
    service.resume_access_scope = None
    service.hitl_service = _FakeHitl(_snapshot())
    service.hitl_service.get_request_status = AsyncMock(return_value={
        "status": "approved", "run_status": "pending",
        "details": {"thread_id": "1:s:c", "agent_run_id": "run-1"},
    })
    service.hitl_service.claim_request = AsyncMock()
    nodes = MagicMock()
    log = MagicMock()
    monkeypatch.setattr(agent_service_module, "AgentNodes", nodes)
    monkeypatch.setattr(agent_service_module, "app_logger", log)

    result = await service.resume_confirmation(
        "req-1", user_id=1, access_scope={"user_id": 1, "can_write": False},
    )

    assert result["success"] is False
    assert result["mode"] == "checkpoint_write_denied"
    service.hitl_service.claim_request.assert_not_awaited()
    nodes.assert_not_called()
    assert "reason=write_permission_revoked" in log.warning.call_args.args[0]


@pytest.mark.asyncio
async def test_resume_re_retrieves_evidence_under_current_access_scope(monkeypatch):
    service = AgentService.__new__(AgentService)
    service.llm_service = MagicMock()
    service.tool_manager = MagicMock()
    service.resume_access_scope = None
    service.hitl_service = _FakeHitl(_snapshot())
    service._acleanup_checkpoint = AsyncMock()
    service._state_to_result_payload = lambda state: {"context": state.get("context")}

    calls = []

    class FakeNodes:
        def __init__(self, *args):
            pass

        async def retrieve_node(self, state):
            calls.append("retrieve")
            state["context"] = [{"content": "证据", "access_scope_user": (state.get("access_scope") or {}).get("user_id")}]
            return state

        async def execute_agent(self, state):
            calls.append(("execute", len(state.get("context") or [])))
            return state

        async def replan_agent(self, state):
            return state

        async def validate_node(self, state):
            return state

    monkeypatch.setattr(agent_service_module, "AgentNodes", FakeNodes)

    result = await service.resume_confirmation("req-1", user_id=1)

    assert result["success"] is True
    # 先重检索，再执行；执行时证据非空
    assert calls == ["retrieve", ("execute", 1)]
