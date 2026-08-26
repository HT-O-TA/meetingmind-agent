"""Agent 混合范式路由测试"""
from unittest.mock import MagicMock
from unittest.mock import AsyncMock
import asyncio
import json

import pytest

from app.agents.nodes import AgentNodes
from app.agents.state import TaskType, WorkflowType, RiskLevel, create_initial_state
from app.agents.human_in_the_loop import HumanInTheLoopService, ConfirmationType
from app.agents.tools.tool_metadata import Tool, ToolMetadata, ToolCategory, ToolParameter, ToolRiskLevel


@pytest.fixture
def nodes():
    llm_service = MagicMock()
    tool_manager = MagicMock()
    tool_manager.selector.format_tools_for_prompt.return_value = ""
    return AgentNodes(llm_service=llm_service, tool_manager=tool_manager)


@pytest.mark.asyncio
async def test_routes_simple_qa(nodes):
    state = create_initial_state("这个会议讨论了什么？")

    routed = await nodes.route_agent(state)

    assert routed["workflow_type"] == WorkflowType.SIMPLE_QA
    assert routed["task_type"] == TaskType.QA


@pytest.mark.asyncio
async def test_routes_todo_workflow(nodes):
    state = create_initial_state("请提取这次会议的待办事项")

    routed = await nodes.route_agent(state)

    assert routed["workflow_type"] == WorkflowType.TODO
    assert routed["task_type"] == TaskType.TODO


@pytest.mark.asyncio
async def test_routes_complex_workflow_for_multiple_intents(nodes):
    state = create_initial_state("请总结会议内容，并且提取待办事项和争议点")

    routed = await nodes.route_agent(state)

    assert routed["workflow_type"] == WorkflowType.COMPLEX
    assert routed["task_type"] == TaskType.MULTI


@pytest.mark.asyncio
async def test_greeting_skips_retrieval(nodes):
    state = create_initial_state("你好")

    routed = await nodes.route_agent(state)

    assert routed["workflow_type"] == WorkflowType.SIMPLE_QA
    assert routed["retrieval_required"] is False
    assert routed["route_decision"] is not None
    assert routed["route_decision"].schema_version == "route.v1"


@pytest.mark.asyncio
async def test_retrieve_node_populates_context(nodes):
    vector_service = MagicMock()
    search_results = [
        {
            "chunk_id": 1,
            "document_id": 2,
            "content": "会议讨论了项目进度",
            "chunk_index": 0,
            "similarity": 0.9,
        }
    ]
    vector_service.search_with_multi_retrieval = AsyncMock(return_value=search_results)
    vector_service.search_by_text = AsyncMock(return_value=[
        search_results[0]
    ])
    nodes.tool_manager.vector_search_service = vector_service
    state = create_initial_state("会议讨论了什么？")
    state["retrieval_required"] = True

    retrieved = await nodes.retrieve_node(state)

    assert len(retrieved["context"]) == 1
    assert retrieved["raw_context"] == ["会议讨论了项目进度"]
    assert retrieved["retrieval_confidence"] == 0.9
    assert retrieved["citations"][0]["document_id"] == 2


@pytest.mark.asyncio
async def test_validate_node_flags_empty_answer(nodes):
    state = create_initial_state("会议讨论了什么？")
    state["task_type"] = TaskType.QA
    state["workflow_type"] = WorkflowType.SIMPLE_QA
    state["answer"] = ""

    validated = await nodes.validate_node(state)

    assert "问答结果为空" in validated["validation_errors"]


@pytest.mark.asyncio
async def test_validate_node_accepts_valid_todos(nodes):
    state = create_initial_state("提取待办")
    state["task_type"] = TaskType.TODO
    state["workflow_type"] = WorkflowType.TODO
    state["todos"] = [{"content": "修复登录问题", "assignee": "张三", "deadline": "周五"}]

    validated = await nodes.validate_node(state)

    assert validated["validation_errors"] == []


@pytest.mark.asyncio
async def test_validate_node_flags_invalid_todos(nodes):
    state = create_initial_state("提取待办")
    state["task_type"] = TaskType.TODO
    state["workflow_type"] = WorkflowType.TODO
    state["todos"] = [{"assignee": "张三"}]

    validated = await nodes.validate_node(state)

    assert "第 1 个待办缺少内容" in validated["validation_errors"]


@pytest.mark.asyncio
async def test_validate_node_flags_empty_complex_result(nodes):
    state = create_initial_state("总结会议并提取待办和争议点")
    state["task_type"] = TaskType.MULTI
    state["workflow_type"] = WorkflowType.COMPLEX

    validated = await nodes.validate_node(state)

    assert "复杂任务没有产生任何结果" in validated["validation_errors"]


@pytest.mark.asyncio
async def test_repair_node_adds_fallback_answer(nodes):
    state = create_initial_state("会议讨论了什么？")
    state["task_type"] = TaskType.QA
    state["workflow_type"] = WorkflowType.SIMPLE_QA
    state["answer"] = ""
    state["validation_errors"] = ["问答结果为空"]

    repaired = await nodes.repair_node(state)
    validated = await nodes.validate_node(repaired)

    assert repaired["repair_count"] == 1
    assert repaired["answer"]
    assert "问答结果为空" not in validated["validation_errors"]


@pytest.mark.asyncio
async def test_repair_node_normalizes_todo_fields(nodes):
    state = create_initial_state("提取待办")
    state["task_type"] = TaskType.TODO
    state["workflow_type"] = WorkflowType.TODO
    state["todos"] = [{"task": "修复登录超时"}]
    state["validation_errors"] = ["第 1 个待办缺少内容"]

    repaired = await nodes.repair_node(state)
    validated = await nodes.validate_node(repaired)

    assert repaired["todos"][0]["content"] == "修复登录超时"
    assert repaired["todos"][0]["assignee"] == ""
    assert repaired["todos"][0]["deadline"] == ""
    assert validated["validation_errors"] == []


@pytest.mark.asyncio
async def test_repair_node_normalizes_controversy_fields(nodes):
    state = create_initial_state("分析争议")
    state["task_type"] = TaskType.CONTROVERSY
    state["workflow_type"] = WorkflowType.CONTROVERSY
    state["controversies"] = [{"issue": "发布时间存在分歧", "parties": "产品部"}]
    state["validation_errors"] = ["第 1 个争议点缺少主题"]

    repaired = await nodes.repair_node(state)
    validated = await nodes.validate_node(repaired)

    assert repaired["controversies"][0]["topic"] == "发布时间存在分歧"
    assert repaired["controversies"][0]["parties"] == []
    assert validated["validation_errors"] == []


@pytest.mark.asyncio
async def test_risk_node_marks_readonly_query_low_risk(nodes):
    state = create_initial_state("总结这个会议")
    state["workflow_type"] = WorkflowType.MINUTES
    state["task_type"] = TaskType.MINUTES

    assessed = await nodes.risk_node(state)

    assert assessed["risk_level"] == RiskLevel.LOW
    assert assessed["requires_confirmation"] is False


@pytest.mark.asyncio
async def test_risk_node_requires_confirmation_for_delete(nodes):
    state = create_initial_state("删除这个会议")
    state["workflow_type"] = WorkflowType.SIMPLE_QA
    state["task_type"] = TaskType.QA

    assessed = await nodes.risk_node(state)

    assert assessed["risk_level"] == RiskLevel.CRITICAL
    assert assessed["requires_confirmation"] is True
    assert "删除类" in assessed["pending_action"]["reason"]


@pytest.mark.asyncio
async def test_confirmation_node_records_disabled_hitl(nodes):
    state = create_initial_state("删除这个会议")
    state["requires_confirmation"] = True
    state["risk_level"] = RiskLevel.CRITICAL
    state["pending_action"] = {"reason": "包含删除/清空类高风险动作"}
    state["enable_human_in_the_loop"] = False

    confirmed = await nodes.confirmation_node(state)
    validated = await nodes.validate_node(confirmed)

    assert confirmed["confirmation_status"] == "required_but_disabled"
    assert "该请求需要人工确认，但当前未启用人机协作" in validated["validation_errors"]


def test_tool_metadata_serializes_risk_fields():
    metadata = ToolMetadata(
        tool_id="send_notification",
        name="发送通知",
        description="发送一条通知",
        category=ToolCategory.NOTIFICATION,
        risk_level=ToolRiskLevel.HIGH,
        requires_confirmation=True,
        idempotent=False,
        allowed_workflows=["complex"],
    )

    data = metadata.to_dict()

    assert data["risk_level"] == "high"
    assert data["requires_confirmation"] is True
    assert data["idempotent"] is False
    assert data["allowed_workflows"] == ["complex"]


@pytest.mark.asyncio
async def test_tool_risk_node_requires_confirmation_for_high_risk_tool(nodes):
    tool = Tool(
        ToolMetadata(
            tool_id="send_notification",
            name="发送通知",
            description="发送一条通知",
            category=ToolCategory.NOTIFICATION,
            risk_level=ToolRiskLevel.HIGH,
            requires_confirmation=True,
            idempotent=False,
        )
    )
    nodes.tool_manager.registry.get.return_value = tool
    state = create_initial_state("总结会议并通知相关人员")
    state["workflow_type"] = WorkflowType.COMPLEX
    state["task_type"] = TaskType.MULTI
    state["plan"] = {
        "analysis": "需要发送通知",
        "tasks": [],
        "execution_order": [],
        "parallel_groups": [],
        "tool_calls": [{"tool_name": "send_notification", "arguments": {"title": "会议纪要"}}],
    }

    assessed = await nodes.tool_risk_node(state)

    assert assessed["risk_level"] == RiskLevel.HIGH
    assert assessed["requires_confirmation"] is True
    assert assessed["pending_action"]["source"] == "tool"
    assert "send_notification:high" in assessed["pending_action"]["reason"]


@pytest.mark.asyncio
async def test_tool_risk_node_allows_low_risk_tool(nodes):
    tool = Tool(
        ToolMetadata(
            tool_id="answer_question",
            name="回答问题",
            description="根据上下文回答用户问题",
            category=ToolCategory.GENERATE,
            risk_level=ToolRiskLevel.LOW,
        )
    )
    nodes.tool_manager.registry.get.return_value = tool
    state = create_initial_state("总结会议")
    state["workflow_type"] = WorkflowType.COMPLEX
    state["task_type"] = TaskType.MULTI
    state["plan"] = {
        "analysis": "只读问答",
        "tasks": [],
        "execution_order": [],
        "parallel_groups": [],
        "tool_calls": [{"tool_name": "answer_question", "arguments": {}}],
    }

    assessed = await nodes.tool_risk_node(state)

    assert assessed["risk_level"] == RiskLevel.LOW
    assert assessed["requires_confirmation"] is False
    assert assessed["pending_action"] is None


@pytest.mark.asyncio
async def test_execute_tool_calls_rejects_tool_outside_allowed_workflow(nodes):
    tool = Tool(
        ToolMetadata(
            tool_id="generate_minutes",
            name="生成会议纪要",
            description="生成结构化会议纪要",
            category=ToolCategory.GENERATE,
            allowed_workflows=["minutes"],
            parameters=[
                ToolParameter(name="context", type="string", description="会议内容", required=True),
            ],
        )
    )
    nodes.tool_manager.registry.get.return_value = tool
    nodes.tool_manager.execute_tool = AsyncMock()
    state = create_initial_state("回答会议问题")
    state["workflow_type"] = WorkflowType.SIMPLE_QA

    await nodes._execute_tool_calls(state, [{"tool_name": "generate_minutes", "arguments": {}}])

    nodes.tool_manager.execute_tool.assert_not_called()
    assert state["validation_errors"][0].startswith("policy_denied:")
    assert state["policy_results"][0]["code"] == "policy_denied"
    assert state["policy_results"][0]["allowed"] is False
    assert state["policy_results"][0]["tool_name"] == "generate_minutes"


@pytest.mark.asyncio
async def test_execute_tool_calls_rejects_unconfirmed_high_risk_tool(nodes):
    tool = Tool(
        ToolMetadata(
            tool_id="send_notification",
            name="发送通知",
            description="发送通知",
            category=ToolCategory.NOTIFICATION,
            risk_level=ToolRiskLevel.HIGH,
            requires_confirmation=True,
        )
    )
    nodes.tool_manager.registry.get.return_value = tool
    nodes.tool_manager.execute_tool = AsyncMock()
    state = create_initial_state("发送会议通知")
    state["workflow_type"] = WorkflowType.COMPLEX
    state["confirmation_status"] = "not_required"

    await nodes._execute_tool_calls(state, [{"tool_name": "send_notification", "arguments": {}}])

    nodes.tool_manager.execute_tool.assert_not_called()
    assert state["validation_errors"][0].startswith("confirmation_required:")
    assert state["policy_results"][0]["code"] == "confirmation_required"
    assert state["policy_results"][0]["risk_level"] == "high"


@pytest.mark.asyncio
async def test_execute_tool_calls_limits_retry_for_non_idempotent_tool(nodes):
    tool = Tool(
        ToolMetadata(
            tool_id="send_notification",
            name="发送通知",
            description="发送通知",
            category=ToolCategory.NOTIFICATION,
            risk_level=ToolRiskLevel.HIGH,
            requires_confirmation=True,
            idempotent=False,
        )
    )
    nodes.tool_manager.registry.get.return_value = tool
    nodes.tool_manager.execute_tool = AsyncMock(
        return_value=MagicMock(success=True, result={"ok": True}, execution_time=0.1)
    )
    state = create_initial_state("发送会议通知")
    state["workflow_type"] = WorkflowType.COMPLEX
    state["confirmation_status"] = "approved"
    arguments = {}
    prepared = nodes._prepare_tool_arguments("send_notification", arguments, state)
    state["approved_tool_call"] = {
        "tool_name": "send_notification",
        "idempotency_key": nodes._tool_idempotency_key(
            state, "send_notification", 0, prepared
        ),
    }

    await nodes._execute_tool_calls(
        state, [{"tool_name": "send_notification", "arguments": arguments}]
    )

    nodes.tool_manager.execute_tool.assert_awaited_once()
    assert nodes.tool_manager.execute_tool.await_args.kwargs["retry_count"] == 1
    assert state["task_contexts"]["send_notification"]["data"] == {"ok": True}
    assert state["policy_results"][0]["code"] == "allowed"
    assert state["policy_results"][0]["retry_count"] == 1


def test_prepare_tool_arguments_normalizes_document_id(nodes):
    state = create_initial_state("请分析ID为4的会议文档")

    prepared = nodes._prepare_tool_arguments("get_document_content", {"id": "4"}, state)

    assert prepared == {"document_id": 4}


@pytest.mark.asyncio
async def test_document_multi_deliverable_request_uses_deterministic_plan(nodes):
    state = create_initial_state("请分析ID为4的会议文档，总结会议主要内容，提取待办事项，生成会议纪要，并识别其中的争议点")

    result = await nodes.plan_agent(state)

    tool_names = [call["tool_name"] for call in result["plan"]["tool_calls"]]
    assert result["task_type"] == TaskType.MULTI
    assert tool_names == [
        "get_document_content",
        "answer_question",
        "extract_todos",
        "generate_minutes",
        "detect_controversies",
    ]
    assert result["plan"]["tool_calls"][0]["arguments"] == {"document_id": 4}


def test_prepare_tool_arguments_maps_content_to_context(nodes):
    state = create_initial_state("提取待办")

    prepared = nodes._prepare_tool_arguments("extract_todos", {"content": "张三负责修复登录"}, state)

    assert prepared == {"context": "张三负责修复登录"}


def test_prepare_tool_arguments_uses_previous_search_context(nodes):
    state = create_initial_state("生成会议纪要")
    state["task_contexts"] = {
        "search_document": {
            "task_id": "search_document",
            "data": [{"content": "会议讨论了上线计划"}],
            "metadata": {},
        }
    }

    prepared = nodes._prepare_tool_arguments("generate_minutes", {}, state)

    assert prepared["context"] == "会议讨论了上线计划"


def test_apply_tool_result_updates_state_outputs(nodes):
    state = create_initial_state("总结并提取待办")

    nodes._apply_tool_result_to_state(state, "get_document_content", {"content": "会议全文"})
    nodes._apply_tool_result_to_state(state, "extract_todos", [{"content": "整理纪要"}])
    nodes._apply_tool_result_to_state(state, "generate_minutes", "会议纪要正文")

    assert state["raw_context"] == ["会议全文"]
    assert state["todos"] == [{"content": "整理纪要"}]
    assert state["minutes"] == "会议纪要正文"


@pytest.mark.asyncio
async def test_replan_uses_weighted_score_instead_of_llm_overall(nodes):
    nodes.llm_service.chat = AsyncMock(return_value=json.dumps({
        "overall_score": 0.12,
        "metrics": {
            "task_completion": 0.2,
            "correctness": 0.9,
            "process_efficiency": 0.5,
            "expression": 0.8,
            "risk": 0.9,
        },
        "confidence": 0.8,
        "issues": ["缺少待办事项和争议点"],
        "suggestions": ["补齐所有请求的输出字段"],
        "needs_retry": False,
    }, ensure_ascii=False))
    state = create_initial_state("请分析ID为4的会议文档，总结会议主要内容，提取待办事项，生成会议纪要，并识别其中的争议点")
    state["answer"] = "主要内容摘要"

    result = await nodes.replan_agent(state)

    assert result["reflection"]["overall_score"] == pytest.approx(0.58)
    assert result["reflection"]["needs_retry"] is True
    assert result["reflection"]["repair_plan"]["missing_outputs"] == ["todos", "minutes", "controversies"]
    assert result["reflection"]["repair_plan"]["required_tools"] == [
        "get_document_content",
        "extract_todos",
        "generate_minutes",
        "detect_controversies",
    ]
    assert any(
        "缺少待办事项和争议点" in (thought.get("observation") or "")
        for thought in result["cot_thoughts"]
    )


@pytest.mark.asyncio
async def test_replan_repair_plan_forces_required_tools_into_next_plan(nodes):
    nodes.llm_service.chat = AsyncMock(return_value=json.dumps({
        "analysis": "LLM 忽略了修复计划，只生成问答",
        "tasks": [{
            "task_id": "qa_only",
            "task_type": "qa",
            "description": "只回答问题",
            "priority": 1,
            "tool_to_use": "answer_question",
        }],
        "tool_calls": [{"tool_name": "answer_question", "arguments": {"question": "{{question}}", "context": "{{context}}"}}],
        "execution_order": ["qa_only"],
        "parallel_groups": [["qa_only"]],
    }, ensure_ascii=False))
    state = create_initial_state("请分析会议内容，总结主要内容，提取待办事项，生成会议纪要，并识别其中的争议点")
    state["reflection"] = {
        "overall_score": 0.54,
        "needs_retry": True,
        "retry_count": 1,
        "issues": ["缺少待办事项、会议纪要和争议点"],
        "suggestions": ["补齐所有请求的输出字段"],
        "repair_plan": {
            "missing_outputs": ["todos", "minutes", "controversies"],
            "required_tools": ["extract_todos", "generate_minutes", "detect_controversies"],
            "avoid_tools": [],
            "context_required": True,
            "repair_strategy": "补齐缺失交付物",
        },
    }

    result = await nodes.plan_agent(state)

    tool_names = [call["tool_name"] for call in result["plan"]["tool_calls"]]
    assert tool_names == [
        "answer_question",
        "extract_todos",
        "generate_minutes",
        "detect_controversies",
    ]
    assert result["plan"]["repair_plan_applied"]["added_tools"] == [
        "extract_todos",
        "generate_minutes",
        "detect_controversies",
    ]


@pytest.mark.asyncio
async def test_replan_does_not_request_result_confirmation_after_final_output(nodes):
    nodes.llm_service.chat = AsyncMock(return_value=json.dumps({
        "metrics": {
            "task_completion": 0.9,
            "correctness": 0.9,
            "process_efficiency": 0.9,
            "expression": 0.9,
            "risk": 0.9,
        },
        "confidence": 0.9,
        "issues": [],
        "suggestions": [],
        "needs_retry": False,
    }, ensure_ascii=False))
    nodes.hitl_service.request_confirmation = AsyncMock(return_value=True)
    state = create_initial_state("总结会议内容")
    state["enable_human_in_the_loop"] = True
    state["answer"] = "会议总结"

    await nodes.replan_agent(state)

    nodes.hitl_service.request_confirmation.assert_not_awaited()


@pytest.mark.asyncio
async def test_hitl_pending_request_is_visible(fake_redis):
    service = HumanInTheLoopService()
    service.redis = fake_redis

    request_id = await service.request_confirmation(
        confirm_type=ConfirmationType.CRITICAL_ACTION,
        title="确认删除",
        message="确认删除会议？",
        timeout_seconds=5,
    )
    pending = await service.list_pending_requests()

    assert len(pending) == 1
    assert pending[0]["title"] == "确认删除"
    assert pending[0]["request_id"] == request_id
    assert await service.respond_to_request(request_id, "approved") is True
    assert await service.list_pending_requests() == []


@pytest.mark.asyncio
async def test_hitl_stores_resume_snapshot_after_approval(fake_redis):
    service = HumanInTheLoopService()
    service.redis = fake_redis
    resume_state = {
        "question": "发送通知",
        "pending_action": {"source": "tool"},
        "plan": {"tool_calls": [{"tool_name": "send_notification", "arguments": {}}]},
    }

    request_id = await service.request_confirmation(
        confirm_type=ConfirmationType.CRITICAL_ACTION,
        title="确认工具",
        message="确认发送通知？",
        details={"source": "tool"},
        resume_state=resume_state,
        timeout_seconds=5,
    )

    assert await service.get_resume_state(request_id) == resume_state
    assert await service.respond_to_request(request_id, "approved") is True
    assert await service.get_resume_state(request_id) == resume_state
    assert await service.list_pending_requests() == []
