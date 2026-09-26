"""低置信度外部写操作：应强制人工确认，而不是整份计划作废（真实 Opus 评测中 7/10 写操作因此静默失败）。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.agents.nodes import AgentNodes
from app.agents.state import create_initial_state
from app.agents.tools.tool_metadata import ToolRiskLevel
from app.services.plan_budget_guard import PlanBudgetGuard


def _nodes(external_effect: bool, risk=ToolRiskLevel.MEDIUM) -> AgentNodes:
    metadata = SimpleNamespace(
        risk_level=risk, risk_reason="测试", external_effect=external_effect,
        reversible=not external_effect, bulk_operation=False, requires_confirmation=external_effect,
    )
    tool_manager = MagicMock()
    tool_manager.registry.get.return_value = SimpleNamespace(metadata=metadata)
    nodes = AgentNodes(llm_service=MagicMock(), tool_manager=tool_manager)
    nodes._available_tool_names = lambda: None
    return nodes


def _plan(confidence: float) -> dict:
    return {
        "analysis": "", "execution_order": ["task_1"], "parallel_groups": [["task_1"]],
        "tasks": [{"task_id": "task_1", "task_type": "todo", "description": "改状态", "confidence": 0.9}],
        "tool_calls": [{"tool_name": "jira_update_issue", "arguments": {"issue_key": "KAN-3", "updates": {}},
                        "confidence": confidence, "uncertainty": "状态名需确认是否存在该 transition"}],
    }


def _validate(nodes, plan):
    state = create_initial_state("把 KAN-3 的状态改成 In Progress")
    ok = nodes._validate_and_track_plan(state, plan, PlanBudgetGuard(), 5)
    state["plan"] = plan
    return ok, state


def test_low_confidence_external_write_is_kept_and_forces_confirmation():
    nodes = _nodes(external_effect=True)
    ok, state = _validate(nodes, _plan(0.5))
    assert ok is True and not state.get("planning_blocked")
    risk, needs_confirm, reason = nodes._assess_tool_risk(state)
    assert needs_confirm is True
    assert "低置信度 0.50" in reason and "transition" in reason
    assert "未核实" in reason  # 模型自述须标注为未核实，防止诱导确认人


def test_low_confidence_forces_confirmation_even_when_write_authorized():
    # 即使本轮带显式写授权（MEDIUM 可自动放行的前提之一），低置信度的外部写仍须人工确认。
    nodes = _nodes(external_effect=True)
    ok, state = _validate(nodes, _plan(0.3))
    state["explicit_write_authorization"] = True
    assert ok is True
    assert nodes._assess_tool_risk(state)[1] is True


def test_low_confidence_read_only_call_is_flagged_without_forcing_confirmation():
    nodes = _nodes(external_effect=False, risk=ToolRiskLevel.LOW)
    ok, state = _validate(nodes, _plan(0.4))
    assert ok is True
    assert state["uncertainty_flags"] and not state["uncertainty_flags"][0].get("force_confirmation")
    assert nodes._assess_tool_risk(state)[1] is False
