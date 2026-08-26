"""无模型、无外部服务依赖的统一离线指标实现。"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from statistics import mean
from typing import Any, Dict, Iterable, List, Sequence, Set, Tuple


def _unique(values: Iterable[Any]) -> List[str]:
    return list(dict.fromkeys(str(value) for value in values if value is not None))


def retrieval_metrics(relevant: Sequence[Any], retrieved: Sequence[Any], k: int) -> Dict[str, float]:
    relevant_ids = set(_unique(relevant))
    ranked = _unique(retrieved)[:k]
    if not relevant_ids:
        return {"recall_at_k": 0.0, "mrr": 0.0, "ndcg_at_k": 0.0}

    hits = [1 if item in relevant_ids else 0 for item in ranked]
    recall = sum(hits) / len(relevant_ids)
    reciprocal_rank = next((1.0 / rank for rank, hit in enumerate(hits, 1) if hit), 0.0)
    dcg = sum(hit / math.log2(rank + 1) for rank, hit in enumerate(hits, 1))
    ideal_hits = min(len(relevant_ids), k)
    ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return {
        "recall_at_k": recall,
        "mrr": reciprocal_rank,
        "ndcg_at_k": dcg / ideal_dcg if ideal_dcg else 0.0,
    }


def _lexical_units(text: str) -> Set[str]:
    normalized = re.sub(r"\s+", "", str(text).lower())
    latin = re.findall(r"[a-z0-9_]+", normalized)
    chinese = re.findall(r"[\u4e00-\u9fff]", normalized)
    chinese_bigrams = ["".join(chinese[index:index + 2]) for index in range(max(0, len(chinese) - 1))]
    return set(latin + chinese_bigrams)


def lexical_overlap(source: str, target: str) -> float:
    source_units = _lexical_units(source)
    target_units = _lexical_units(target)
    if not target_units:
        return 0.0
    return len(source_units & target_units) / len(target_units)


def generation_metrics(record: Dict[str, Any], relevant_ids: Sequence[Any]) -> Dict[str, float]:
    answer = str(record.get("answer", ""))
    contexts = "\n".join(str(item) for item in record.get("contexts", []))
    question = str(record.get("question", ""))
    citations = set(_unique(record.get("citation_ids", [])))
    relevant = set(_unique(relevant_ids))
    citation_precision = (
        len(citations & relevant) / len(citations)
        if citations
        else (1.0 if not relevant else 0.0)
    )
    return {
        # 这是透明的词面代理指标，不冒充需要评判模型的 RAGAS 指标。
        "faithfulness_lexical_proxy": lexical_overlap(contexts, answer),
        "answer_relevancy_lexical_proxy": lexical_overlap(question, answer),
        "citation_accuracy": citation_precision,
    }


def _flatten(value: Any, prefix: str = "") -> Set[Tuple[str, str]]:
    flattened: Set[Tuple[str, str]] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            flattened |= _flatten(child, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            flattened |= _flatten(child, f"{prefix}[{index}]")
    else:
        flattened.add((prefix, json.dumps(value, ensure_ascii=False, sort_keys=True)))
    return flattened


def precision_recall_f1(expected: Any, predicted: Any) -> Dict[str, float]:
    expected_fields = _flatten(expected)
    predicted_fields = _flatten(predicted)
    true_positive = len(expected_fields & predicted_fields)
    precision = true_positive / len(predicted_fields) if predicted_fields else (1.0 if not expected_fields else 0.0)
    recall = true_positive / len(expected_fields) if expected_fields else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def json_is_valid(raw_output: Any) -> float:
    if not isinstance(raw_output, str):
        return 1.0 if raw_output is not None else 0.0
    try:
        json.loads(raw_output)
        return 1.0
    except (json.JSONDecodeError, TypeError):
        return 0.0


def percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return ordered[index]


def _average_metric(records: List[Dict[str, float]]) -> Dict[str, float]:
    if not records:
        return {}
    keys = set().union(*(record.keys() for record in records))
    return {key: mean(record.get(key, 0.0) for record in records) for key in sorted(keys)}


def _route_threshold(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    labeled = [record for record in records if record.get("task_confidence") is not None]
    if not labeled:
        return {}
    best = {"threshold": 0.0, "f1": -1.0, "coverage": 1.0}
    for step in range(21):
        threshold = step / 20
        tp = fp = fn = accepted = 0
        for record in labeled:
            correct = record.get("expected_task") == record.get("predicted_task")
            predicted_correct = float(record["task_confidence"]) >= threshold
            accepted += int(predicted_correct)
            tp += int(predicted_correct and correct)
            fp += int(predicted_correct and not correct)
            fn += int((not predicted_correct) and correct)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        coverage = accepted / len(labeled)
        if (f1, coverage) > (best["f1"], best["coverage"]):
            best = {"threshold": threshold, "f1": f1, "coverage": coverage}
    best["status"] = "recommendation_only_not_applied"
    return best


def evaluate_records(records: List[Dict[str, Any]], top_k: int = 5) -> Dict[str, Any]:
    buckets: Dict[str, List[Dict[str, float]]] = defaultdict(list)
    latencies: List[float] = []
    route_records: List[Dict[str, Any]] = []
    errors = tokens = 0
    cost = 0.0

    for record in records:
        retrieval = record.get("retrieval") or {}
        relevant = retrieval.get("relevant_ids", [])
        if retrieval:
            buckets["retrieval"].append(
                retrieval_metrics(relevant, retrieval.get("retrieved_ids", []), top_k)
            )

        generation = record.get("generation") or {}
        if generation:
            buckets["generation"].append(generation_metrics(generation, relevant))

        extraction = record.get("extraction") or {}
        if extraction:
            metrics = precision_recall_f1(
                extraction.get("expected", []), extraction.get("predicted", [])
            )
            metrics["json_valid_rate"] = json_is_valid(extraction.get("raw_output"))
            buckets["extraction"].append(metrics)

        tool = record.get("tool") or {}
        if tool:
            parameter_metrics = precision_recall_f1(
                tool.get("expected_arguments", {}), tool.get("predicted_arguments", {})
            )
            buckets["tool"].append({
                "selection_accuracy": float(tool.get("expected_tool") == tool.get("predicted_tool")),
                "parameter_accuracy": parameter_metrics["f1"],
                "success_rate": float(bool(tool.get("success"))),
                "hitl_trigger_accuracy": float(tool.get("expected_hitl") == tool.get("predicted_hitl")),
            })

        route = record.get("route") or {}
        if route:
            route_records.append(route)
            buckets["route"].append({
                "task_accuracy": float(route.get("expected_task") == route.get("predicted_task")),
                "complexity_accuracy": float(
                    route.get("expected_complexity") == route.get("predicted_complexity")
                ),
                "fallback_rate": float(route.get("execution_mode") == "fallback"),
            })

        system = record.get("system") or {}
        if system:
            latencies.append(float(system.get("latency_ms", 0.0)))
            errors += int(bool(system.get("error")))
            tokens += int(system.get("tokens", 0) or 0)
            cost += float(system.get("cost", 0.0) or 0.0)

    report = {name: _average_metric(items) for name, items in buckets.items()}
    if latencies:
        total_seconds = sum(latencies) / 1000
        report["system"] = {
            "mean_latency_ms": mean(latencies),
            "p95_latency_ms": percentile(latencies, 0.95),
            "sequential_throughput_proxy_rps": len(latencies) / total_seconds if total_seconds else 0.0,
            "error_rate": errors / len(latencies),
            "total_tokens": tokens,
            "total_cost": cost,
        }
    report["route_threshold_recommendation"] = _route_threshold(route_records)
    return report


def flatten_report(report: Dict[str, Any]) -> Dict[str, float]:
    flattened: Dict[str, float] = {}
    for section, metrics in report.items():
        if isinstance(metrics, dict):
            for key, value in metrics.items():
                if isinstance(value, (int, float)):
                    flattened[f"{section}.{key}"] = float(value)
    return flattened
