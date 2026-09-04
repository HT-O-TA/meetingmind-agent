"""轻量 ContextAssembler 的预算、去重、投影与清单契约。"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.nodes import AgentNodes
from app.agents.state import create_initial_state
from app.services.context_assembler import ContextAssembler
from app.services.input_preprocessor import InputPreprocessor
from app.services.llm_service import LLMService


def test_context_assembler_prioritizes_current_evidence_and_never_exceeds_budget():
    assembler = ContextAssembler(
        max_item_chars=180,
        max_items=6,
        max_chunks_per_document=2,
        anchor_max_chars=120,
    )
    state = create_initial_state("总结会议")
    state["task_anchor"] = {
        "required_outputs": ["answer"],
        "hard_constraints": ["只使用允许范围内的会议证据"],
    }
    state["task_contexts"] = {
        "get_document_content": {
            "task_id": "read",
            "data": {"content": "工具读取的当前文档证据", "api_token": "must-not-leak"},
            "metadata": {},
        }
    }
    state["context"] = [
        {
            "document_id": 1,
            "chunk_index": 0,
            "content": "当前检索证据",
            "similarity": 0.95,
        }
    ]
    state["raw_context"] = ["最近会话内容", "更旧会话内容"]

    result = assembler.assemble_state(state, max_chars=520, consumer="answer_node")

    assert len(result.text) <= 520
    assert result.text.index("工具读取的当前文档证据") < result.text.index("最近会话内容")
    assert result.manifest["consumer"] == "answer_node"
    assert result.manifest["source_counts"]["tool_result"] == 1
    assert result.manifest["included"][0]["authority"] == "tool"
    manifest_text = json.dumps(result.manifest, ensure_ascii=False)
    assert "工具读取的当前文档证据" not in manifest_text
    assert "must-not-leak" not in result.text
    assert "must-not-leak" not in manifest_text


def test_context_assembler_deduplicates_retrieval_mirror_in_raw_context():
    assembler = ContextAssembler(max_item_chars=200, max_items=5)
    state = create_initial_state("会议决定了什么")
    state["context"] = [
        {
            "document_id": 2,
            "chunk_index": 0,
            "speaker_name": "speaker_0",
            "content": "会议决定周五发布",
            "similarity": 0.9,
        }
    ]
    state["raw_context"] = ["[speaker_0]: 会议决定周五发布"]

    result = assembler.assemble_state(state, max_chars=600, consumer="answer_node")

    assert result.text.count("会议决定周五发布") == 1
    assert result.manifest["deduplicated_count"] == 1
    assert result.manifest["dropped"][0]["reason"] == "duplicate"


def test_context_assembler_keeps_document_diversity_with_a_simple_cap():
    assembler = ContextAssembler(
        max_item_chars=100,
        max_items=8,
        max_chunks_per_document=2,
    )
    state = create_initial_state("对比会议证据")
    state["context"] = [
        {
            "document_id": 1,
            "chunk_index": index,
            "content": f"文档一证据{index}",
            "similarity": 0.9 - index * 0.01,
        }
        for index in range(5)
    ] + [
        {
            "document_id": 2,
            "chunk_index": 0,
            "content": "文档二证据",
            "similarity": 0.7,
        }
    ]

    result = assembler.assemble_state(state, max_chars=1200, consumer="answer_node")

    refs = [item["content_ref"] for item in result.manifest["included"]]
    assert sum("document:1" in ref for ref in refs) == 2
    assert sum("document:2" in ref for ref in refs) == 1
    assert any(
        item["reason"] == "document_diversity_limit"
        for item in result.manifest["dropped"]
    )


def test_context_assembler_uses_prefix_truncation_instead_of_preserving_stale_tail():
    assembler = ContextAssembler(max_item_chars=100, max_items=2)
    current_prefix = "当前决定" * 30
    state = create_initial_state("总结")
    state["raw_context"] = [current_prefix + "不应保留的陈旧尾部"]

    result = assembler.assemble_state(state, max_chars=400, consumer="answer_node")

    assert "…[截断]" in result.text
    assert "不应保留的陈旧尾部" not in result.text
    assert result.manifest["truncated_count"] == 1


def test_context_assembler_separates_tool_error_from_business_evidence():
    assembler = ContextAssembler(max_item_chars=180, max_items=4)
    state = create_initial_state("总结")
    state["task_contexts"] = {
        "search_document": {
            "task_id": "search",
            "data": {"success": False, "status": "403 Forbidden", "error": "permission denied"},
            "metadata": {},
        }
    }

    result = assembler.assemble_state(state, max_chars=500, consumer="answer_node")

    assert "不是会议事实" in result.text
    assert "tool_error" in result.text
    assert result.manifest["source_counts"]["tool_error"] == 1
    assert result.manifest["included"][0]["authority"] == "tool"


def test_context_manifest_reports_reasonable_token_estimate():
    result = ContextAssembler().assemble_texts(
        ["中文会议内容和 English notes"],
        max_chars=500,
        consumer="answer_node",
    )

    assert result.manifest["estimated_token_count"] < result.manifest["estimated_token_upper_bound"]
    assert result.manifest["token_estimation_method"] == "mixed_text_heuristic_v1"


def test_agent_node_attaches_manifest_to_state_and_input_budget():
    state = create_initial_state("总结会议")
    state["input_envelope"] = InputPreprocessor().build_envelope(state)
    state["task_anchor"] = state["input_envelope"]["task_anchor"]
    state["raw_context"] = ["会议决定周五发布"]
    tool_manager = MagicMock()
    tool_manager.selector.format_tools_for_prompt.return_value = ""
    nodes = AgentNodes(llm_service=MagicMock(), tool_manager=tool_manager)

    formatted = nodes._format_context(state, consumer="simple_qa_node")

    assert "会议决定周五发布" in formatted
    assert state["context_manifest"]["schema_version"] == "context-manifest.v1"
    assert (
        state["input_envelope"]["budget"]["context_manifest"]
        == state["context_manifest"]
    )


@pytest.mark.asyncio
async def test_rag_generation_uses_the_same_context_assembler():
    service = LLMService()
    service.chat = AsyncMock(return_value="回答")

    answer = await service.generate_answer(
        "会议决定了什么？",
        ["会议决定周五发布", "会议决定周五发布", "补充证据"],
    )

    prompt = service.chat.await_args.kwargs["messages"][1]["content"]
    assert answer == "回答"
    assert prompt.count("会议决定周五发布") == 1
    assert "【不可信外部内容" in prompt
    assert service.last_context_manifest["deduplicated_count"] == 1
