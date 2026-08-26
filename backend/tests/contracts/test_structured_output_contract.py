"""版本化结构化输出、修复和工具参数外壳契约。"""
import json

import pytest
from pydantic import ValidationError

from app.schemas.structured_output import (
    DecisionOutput,
    MinutesOutput,
    StructuredOutputEnvelope,
    repair_json_text,
    validate_structured_data,
    validate_tool_call,
)


def test_todo_output_is_normalized_and_keeps_evidence_fields():
    result = validate_structured_data(
        [{"content": "提交报告", "assignee": "张三", "priority": "high"}],
        "待办事项",
    )

    assert result[0]["deadline"] == ""
    assert result[0]["source_type"] == "unknown"
    assert result[0]["uncertainties"] == []
    assert result[0]["degradation_info"] == []


def test_missing_required_todo_content_is_rejected():
    with pytest.raises(ValidationError):
        validate_structured_data([{"assignee": "张三"}], "待办事项")


def test_json_repair_is_bounded_to_fence_and_trailing_comma():
    repaired = repair_json_text('说明：```json\n[{"content":"提交报告",}]\n```')

    assert json.loads(repaired) == [{"content": "提交报告"}]


def test_minutes_and_decision_share_versioned_evidence_contract():
    minutes = MinutesOutput(
        content="会议确认周五上线。",
        decisions=[DecisionOutput(content="周五上线", source_id="chunk-7")],
    )
    envelope = StructuredOutputEnvelope(
        output_type="minutes",
        data=minutes.model_dump(),
        prompt_version="agent.minutes.v1",
        model_version="qwen3.6-plus",
        source_id="chunk-7",
        source_type="meeting_chunk",
    )

    assert envelope.schema_version == "extraction.v1"
    assert envelope.data["decisions"][0]["source_id"] == "chunk-7"
    assert envelope.prompt_version == "agent.minutes.v1"


def test_tool_call_outer_schema_rejects_non_object_arguments():
    with pytest.raises(ValidationError):
        validate_tool_call("create_task", ["not", "an", "object"])
