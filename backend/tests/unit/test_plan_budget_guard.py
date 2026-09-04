"""规划层 P0 门禁：工具、依赖、预算和重复计划。"""

from app.services.plan_budget_guard import PlanBudgetGuard
from app.services.input_preprocessor import InputPreprocessor


def _plan(**overrides):
    plan = {
        "tasks": [
            {"task_id": "a", "task_type": "qa", "description": "先查", "dependencies": []},
            {"task_id": "b", "task_type": "qa", "description": "再答", "dependencies": ["a"]},
        ],
        "execution_order": ["a", "b"],
        "parallel_groups": [],
        "tool_calls": [{"tool_name": "search", "arguments": {}}],
    }
    plan.update(overrides)
    return plan


def test_rejects_unknown_tool_and_malformed_arguments():
    result = PlanBudgetGuard().validate(
        _plan(tool_calls=[{"tool_name": "not_registered", "arguments": []}]),
        available_tools={"search"},
    )
    assert not result.is_valid
    assert any("未注册工具" in error for error in result.errors)
    assert any("arguments 必须是对象" in error for error in result.errors)


def test_rejects_dependency_cycle_and_order_violation():
    result = PlanBudgetGuard().validate(
        _plan(
            tasks=[
                {"task_id": "a", "description": "a", "dependencies": ["b"]},
                {"task_id": "b", "description": "b", "dependencies": ["a"]},
            ],
            execution_order=["a", "b"],
        )
    )
    assert not result.is_valid
    assert any("循环" in error for error in result.errors)


def test_rejects_duplicate_ids_and_budget_overflow():
    result = PlanBudgetGuard().validate(
        _plan(
            tasks=[
                {"task_id": "a", "description": "a", "dependencies": []},
                {"task_id": "a", "description": "重复", "dependencies": []},
            ]
        ),
        max_tasks=1,
    )
    assert not result.is_valid
    assert any("重复" in error for error in result.errors)
    assert any("上限" in error for error in result.errors)


def test_fingerprint_is_stable_for_same_plan():
    plan = _plan()
    assert PlanBudgetGuard.fingerprint(plan) == PlanBudgetGuard.fingerprint(dict(plan))


def test_constraint_gate_rejects_threshold_violation():
    state = {
        "question": "查询预算低于500的方案",
        "task_anchor": {
            "goal": "查询预算低于500的方案",
            "constraints": [{"text": "预算低于500", "kind": "threshold", "polarity": "must", "value": "500"}],
        },
    }
    errors = InputPreprocessor.validate_constraints_for_plan(
        state,
        [{"tool_name": "search", "arguments": {"budget": 800}}],
    )
    assert any("阈值约束" in error for error in errors)
