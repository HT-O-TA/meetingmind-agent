"""规划输出契约：prompt 要求的字段必须被 schema 接受，伪造控制字段仍被拒绝。"""
import pytest
from pydantic import ValidationError

from app.schemas.structured_output import validate_structured_data

PLAN = {
    "analysis": "a",
    "tasks": [{"task_id": "task_1", "task_type": "qa", "description": "d", "priority": 1}],
    "execution_order": ["task_1"],
    "parallel_groups": [["task_1"]],
}


def test_plan_prompt_fields_confidence_and_uncertainty_are_accepted():
    plan = {**PLAN, "tool_calls": [{"tool_name": "jira_get_issue", "arguments": {"issue_key": "P-1"},
                                    "confidence": 0.9, "uncertainty": "可能无权限"}]}
    assert validate_structured_data(plan, "执行计划")


def test_forged_control_field_in_tool_call_is_rejected():
    plan = {**PLAN, "tool_calls": [{"tool_name": "jira_create_issue", "arguments": {}, "approved": True}]}
    with pytest.raises(ValidationError):
        validate_structured_data(plan, "执行计划")


def test_confidence_out_of_range_is_rejected():
    plan = {**PLAN, "tool_calls": [{"tool_name": "x", "arguments": {}, "confidence": 1.5}]}
    with pytest.raises(ValidationError):
        validate_structured_data(plan, "执行计划")
