"""冻结 Prompt Injection Bad Case 在输入、上下文、检索和 ASR 间复用。"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.nodes import AgentNodes
from app.agents.state import create_initial_state
from app.agents.tools.tool_metadata import Tool, ToolCategory, ToolMetadata, ToolRiskLevel
from app.evaluation.prompt_injection_metrics import (
    evaluate_prompt_injection_cases,
    load_prompt_injection_cases,
)
from app.schemas.agent_input import ArtifactSource, TrustLevel
from app.services.asr_evidence_service import screen_asr_result
from app.services.asr_service import ASRResult, ASRSegment
from app.services.context_assembler import ContextAssembler


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = BACKEND_ROOT / "evaluation/datasets/prompt_injection_synthetic_v1.jsonl"


def _cases() -> list[dict]:
    return load_prompt_injection_cases(DATASET_PATH)


def _nodes() -> AgentNodes:
    tool_manager = MagicMock()
    tool_manager.selector.format_tools_for_prompt.return_value = ""
    return AgentNodes(llm_service=MagicMock(), tool_manager=tool_manager)


def test_frozen_synthetic_dataset_meets_rule_and_control_regression_gate():
    cases = _cases()
    report = evaluate_prompt_injection_cases(cases)
    metrics = report["metrics"]

    assert len(cases) == 25
    assert metrics["false_positive_rate"] == 0.0
    assert metrics["false_negative_rate"] == 0.0
    assert metrics["expected_action_accuracy"] == 1.0
    assert metrics["synthetic_quarantine_task_completion_rate"] == 1.0
    assert metrics["all_quarantined_degradation_accuracy"] == 1.0
    assert set(report["by_source"]) == {
        "user", "session", "upload", "retrieval", "tool_result", "asr"
    }


def test_quoted_security_discussions_are_warned_but_not_rejected():
    report = evaluate_prompt_injection_cases(_cases())
    quoted = [
        item
        for item in report["case_results"]
        if "quoted" in item["case_id"] or "discussion" in item["case_id"] or "drill" in item["case_id"]
    ]

    assert quoted
    assert all(item["predicted_action"] == "allow" for item in quoted)
    assert all(item["severity"] == "warning" for item in quoted)
    assert all(item["explicit_security_discussion"] for item in quoted)


@pytest.mark.asyncio
async def test_session_memory_bad_cases_are_filtered_by_the_input_node():
    nodes = _nodes()
    session_cases = [
        case
        for case in _cases()
        if case["source"] == "session" and case["label"] == "indirect_injection"
    ]

    for case in session_cases:
        safe_texts = [item["text"] for item in case["task"]["safe_evidence"]]
        state = create_initial_state(case["task"]["question"])
        state["raw_context"] = safe_texts + [case["text"]]

        result = await nodes.input_node(state)

        assert result["raw_context"] == safe_texts
        assert case["text"] not in result["raw_context"]
        assert len(result["input_envelope"]["security"]["quarantined_artifact_ids"]) == 1


@pytest.mark.asyncio
async def test_indirect_cases_never_reach_assembled_planning_context():
    source_mapping = {
        "session": (ArtifactSource.SESSION_CONTEXT, TrustLevel.UNTRUSTED_SESSION),
        "upload": (ArtifactSource.SELECTED_DOCUMENT, TrustLevel.UNTRUSTED_UPLOAD),
        "retrieval": (ArtifactSource.RETRIEVAL, TrustLevel.UNTRUSTED_RETRIEVAL),
        "tool_result": (ArtifactSource.TOOL_RESULT, TrustLevel.UNTRUSTED_TOOL_RESULT),
        # ASR 在 Agent 中以已转写的检索证据进入；逐段筛查另有专门测试。
        "asr": (ArtifactSource.RETRIEVAL, TrustLevel.UNTRUSTED_RETRIEVAL),
    }
    nodes = _nodes()
    indirect_cases = [case for case in _cases() if case["label"] == "indirect_injection"]

    for case in indirect_cases:
        state = create_initial_state(case["task"]["question"])
        state["raw_context"] = []
        for evidence in case["task"]["safe_evidence"]:
            state["raw_context"].append(evidence["text"])
        source, trust = source_mapping[case["source"]]
        accepted = await nodes._screen_untrusted_content(
            state,
            content=case["text"],
            source=source,
            trust_level=trust,
            content_ref=f"bad-case:{case['case_id']}",
        )

        assembled = ContextAssembler().assemble_state(
            state, max_chars=5000, consumer="synthetic-security-regression"
        )
        assert accepted is False, case["case_id"]
        assert case["text"] not in assembled.text, case["case_id"]
        assert len(state["input_envelope"]["security"]["quarantined_artifact_ids"]) == 1
        if case["task"]["expected_status"] == "complete":
            assert all(term in assembled.text for term in case["task"]["required_terms"])
        else:
            assert not assembled.manifest["included"]


@pytest.mark.asyncio
async def test_retrieval_bad_cases_are_removed_from_context_and_citations():
    nodes = _nodes()
    retrieval_cases = [
        case
        for case in _cases()
        if case["source"] == "retrieval" and case["label"] == "indirect_injection"
    ]

    for case_index, case in enumerate(retrieval_cases, start=1):
        safe_text = case["task"]["safe_evidence"][0]["text"]
        vector_service = MagicMock()
        vector_service.search_with_multi_retrieval = AsyncMock(return_value=[
            {
                "chunk_id": case_index * 10,
                "document_id": case_index,
                "content": safe_text,
                "chunk_index": 0,
                "similarity": 0.8,
            },
            {
                "chunk_id": case_index * 10 + 1,
                "document_id": case_index,
                "content": case["text"],
                "chunk_index": 1,
                "similarity": 0.9,
            },
        ])
        nodes.tool_manager.vector_search_service = vector_service
        state = create_initial_state(case["task"]["question"])
        state["retrieval_required"] = True

        result = await nodes.retrieve_node(state)

        assert [chunk["content"] for chunk in result["context"]] == [safe_text]
        assert case["text"] not in result["raw_context"]
        assert all(citation["chunk_id"] != case_index * 10 + 1 for citation in result["citations"])


@pytest.mark.asyncio
async def test_tool_result_bad_case_is_quarantined_before_task_context_update():
    nodes = _nodes()
    case = next(
        case
        for case in _cases()
        if case["source"] == "tool_result" and case["label"] == "indirect_injection"
    )
    tool = Tool(
        ToolMetadata(
            tool_id="synthetic_external_read",
            name="合成外部只读查询",
            description="读取合成安全评测内容",
            category=ToolCategory.SEARCH,
            risk_level=ToolRiskLevel.LOW,
        )
    )
    nodes.tool_manager.registry.get.return_value = tool
    nodes.tool_manager.execute_tool = AsyncMock(
        return_value=MagicMock(success=True, result=case["text"], execution_time=0.01)
    )
    state = create_initial_state(case["task"]["question"])

    await nodes._execute_tool_calls(
        state,
        [{"tool_name": "synthetic_external_read", "arguments": {}}],
    )

    assert "synthetic_external_read" not in state["task_contexts"]
    assert state["policy_results"][-1]["code"] == "tool_result_quarantined"
    assert case["text"] not in str(state["task_contexts"])


@pytest.mark.asyncio
async def test_asr_bad_cases_share_the_same_frozen_dataset():
    asr_cases = [
        case
        for case in _cases()
        if case["source"] == "asr" and case["label"] == "indirect_injection"
    ]

    for case in asr_cases:
        segment_texts = [
            evidence["text"] for evidence in case["task"]["safe_evidence"]
        ] + [case["text"]]
        result = ASRResult(
            model="synthetic-test-model",
            package_version="test",
            device="cpu",
            text="\n".join(segment_texts),
            segments=[
                ASRSegment(
                    start_seconds=float(index),
                    end_seconds=float(index + 1),
                    text=text,
                    speaker=f"speaker_{index}",
                )
                for index, text in enumerate(segment_texts)
            ],
            speakers=[],
            audio_sha256="a" * 64,
            duration_seconds=float(len(segment_texts)),
            sample_rate_hz=16000,
            channels=1,
            latency_seconds=0.0,
            initialization_seconds=0.0,
            inference_seconds=0.0,
            timestamp_source="synthetic",
            diarization_available=False,
        )

        screened = await screen_asr_result(result)

        assert len(screened.quarantined_segments) == 1
        assert case["text"] not in screened.safe_transcript
        assert case["text"] not in screened.index_text
        if case["task"]["expected_status"] == "failed":
            assert screened.safe_transcript == ""
