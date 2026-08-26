"""统一离线评估公式的确定性测试。"""
import pytest

from app.evaluation.offline_metrics import (
    evaluate_records,
    percentile,
    precision_recall_f1,
    retrieval_metrics,
)


def test_retrieval_metrics_include_recall_mrr_and_ndcg():
    metrics = retrieval_metrics(["a", "b"], ["x", "a", "b"], k=3)

    assert metrics["recall_at_k"] == 1.0
    assert metrics["mrr"] == 0.5
    assert 0.0 < metrics["ndcg_at_k"] < 1.0


def test_extraction_field_metrics_penalize_missing_field():
    metrics = precision_recall_f1(
        [{"content": "任务", "assignee": "张三"}],
        [{"content": "任务"}],
    )

    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 0.5
    assert metrics["f1"] == pytest.approx(2 / 3)


def test_p95_uses_nearest_rank():
    assert percentile([10, 20, 30, 40, 50], 0.95) == 50


def test_unified_report_covers_all_main_sections():
    record = {
        "retrieval": {"relevant_ids": ["d1"], "retrieved_ids": ["d1"]},
        "generation": {
            "question": "何时上线",
            "answer": "周五上线",
            "contexts": ["项目周五上线"],
            "citation_ids": ["d1"],
        },
        "extraction": {"expected": [], "predicted": [], "raw_output": "[]"},
        "tool": {
            "expected_tool": "create_task",
            "predicted_tool": "create_task",
            "expected_arguments": {},
            "predicted_arguments": {},
            "success": True,
            "expected_hitl": True,
            "predicted_hitl": True,
        },
        "route": {
            "expected_task": "todo",
            "predicted_task": "todo",
            "expected_complexity": "retrieval",
            "predicted_complexity": "retrieval",
            "task_confidence": 0.9,
            "execution_mode": "deterministic",
        },
        "system": {"latency_ms": 100, "error": False, "tokens": 10, "cost": 0.01},
    }

    report = evaluate_records([record], top_k=5)

    assert set(["retrieval", "generation", "extraction", "tool", "route", "system"]).issubset(report)
    assert report["generation"]["citation_accuracy"] == 1.0
    assert report["system"]["p95_latency_ms"] == 100
    assert report["route_threshold_recommendation"]["status"] == "recommendation_only_not_applied"
