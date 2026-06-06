"""单元测试 - Agent 状态模块"""
import pytest
from app.agents.state import TaskType, AgentResult, create_initial_state


class TestTaskType:
    def test_all_values_exist(self):
        assert TaskType.QA.value == "qa"
        assert TaskType.MINUTES.value == "minutes"
        assert TaskType.TODO.value == "todo"
        assert TaskType.CONTROVERSY.value == "controversy"
        assert TaskType.MULTI.value == "multi"

    def test_from_string(self):
        assert TaskType("qa") == TaskType.QA
        assert TaskType("multi") == TaskType.MULTI

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            TaskType("nonexistent")


class TestAgentResult:
    def test_success_result(self):
        result = AgentResult(
            success=True,
            task_type=TaskType.QA,
            answer="这是回答",
        )
        assert result.success is True
        assert result.answer == "这是回答"
        assert result.error is None

    def test_failure_result(self):
        result = AgentResult(
            success=False,
            task_type=TaskType.QA,
            error="LLM 调用失败",
        )
        assert result.success is False
        assert result.error == "LLM 调用失败"
        assert result.answer is None


class TestCreateInitialState:
    def test_creates_valid_state(self):
        state = create_initial_state("测试问题")
        assert state["question"] == "测试问题"
        assert state["cot_thoughts"] == []
        assert state["task_contexts"] == {}
        assert state["agents_involved"] == []

    def test_with_meeting_id(self):
        state = create_initial_state("问题", meeting_id=42)
        assert state["meeting_id"] == 42

    def test_with_document_ids(self):
        state = create_initial_state("问题", document_ids=[1, 2, 3])
        assert state["document_ids"] == [1, 2, 3]
