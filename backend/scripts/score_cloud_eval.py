"""将云端 100 条输出与 evaluation.v1 人工标签对齐并计算可复现指标。"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any
import sys
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))
from app.evaluation.offline_metrics import lexical_overlap

DEFAULT_DATASET = ROOT / "backend/evaluation/datasets/meetingmind_real_v1_evaluation.jsonl"
DEFAULT_RUN = ROOT / "backend/evaluation/reports/meetingmind_real_v1_cloud_100.json"
DEFAULT_OUTPUT = ROOT / "backend/evaluation/reports/meetingmind_real_v1_cloud_100_scored.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def flatten(value: Any, prefix: str = "") -> set[tuple[str, str]]:
    if isinstance(value, dict):
        result: set[tuple[str, str]] = set()
        for key, child in value.items():
            result |= flatten(child, f"{prefix}.{key}" if prefix else str(key))
        return result
    if isinstance(value, list):
        result: set[tuple[str, str]] = set()
        for index, child in enumerate(value):
            result |= flatten(child, f"{prefix}[{index}]")
        return result
    return {(prefix, json.dumps(value, ensure_ascii=False, sort_keys=True))}


def f1(expected: Any, predicted: Any) -> dict[str, float]:
    gold, output = flatten(expected), flatten(predicted)
    tp = len(gold & output)
    precision = tp / len(output) if output else (1.0 if not gold else 0.0)
    recall = tp / len(gold) if gold else (1.0 if not output else 0.0)
    score = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": score}


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    dataset_records = [
        json.loads(line)
        for line in args.dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    records = {record["id"]: record for record in dataset_records}
    run = load_json(args.run)
    result_by_id = {result["id"]: result for result in run.get("results", [])}
    qa, todo, constraint = [], [], []
    per_record = []
    latencies, tokens = [], []
    valid = failed = 0
    for record_id, record in records.items():
        result = result_by_id.get(record_id)
        if not result:
            failed += 1
            continue
        usage = result.get("usage", {})
        latencies.append(float(result.get("latency_ms", 0) or 0))
        tokens.append(int(usage.get("total_tokens", 0) or 0))
        valid += int(bool(result.get("json_valid")))
        if not result.get("ok"):
            failed += 1
        output = result.get("output") if isinstance(result.get("output"), dict) else {}
        kind = record.get("unit_type")
        if kind == "qa":
            gold_ids = set(record.get("retrieval", {}).get("relevant_ids", []))
            predicted_ids = set(output.get("citation_ids", []))
            metrics = {
                "citation_precision": len(predicted_ids & gold_ids) / len(predicted_ids) if predicted_ids else (1.0 if not gold_ids else 0.0),
                "citation_recall": len(predicted_ids & gold_ids) / len(gold_ids) if gold_ids else 1.0,
                "answer_lexical_overlap": lexical_overlap(output.get("answer", ""), record.get("generation", {}).get("answer", "")),
            }
            qa.append(metrics)
        elif kind == "todo":
            gold = record.get("extraction", {}).get("expected", [])
            predicted = output.get("todos", []) if output.get("decision") != "reject" else []
            metrics = {**f1(gold, predicted), "decision_accuracy": float((bool(gold)) == (output.get("decision") == "accept"))}
            todo.append(metrics)
        elif kind == "constraint":
            gold = record.get("extraction", {}).get("expected", [])
            predicted = [output.get("constraint")] if output.get("decision") == "accept" and output.get("constraint") else []
            metrics = {**f1(gold, predicted), "decision_accuracy": float((bool(gold)) == (output.get("decision") == "accept"))}
            constraint.append(metrics)
        else:
            metrics = {}
        per_record.append({
            "id": record_id,
            "meeting_key": record.get("source", {}).get("meeting_id") or record.get("meeting_id"),
            "unit_type": kind,
            **metrics,
        })

    def avg(items: list[dict[str, float]]) -> dict[str, float | None]:
        keys = sorted(set().union(*(item.keys() for item in items))) if items else []
        return {key: mean([item[key] for item in items]) for key in keys}

    payload = {
        "schema_version": "evaluation.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "run_file": str(args.run.relative_to(ROOT)).replace("\\", "/"),
        "record_count": len(records),
        "completed_count": len(result_by_id),
        "per_record": per_record,
        "metrics": {
            "qa": avg(qa),
            "todo": avg(todo),
            "constraint": avg(constraint),
            "json_valid_rate": valid / len(records) if records else 0.0,
            "failure_rate": failed / len(records) if records else 0.0,
            "latency_ms": {"p50": percentile(latencies, 0.50), "p95": percentile(latencies, 0.95), "mean": mean(latencies) if latencies else None},
            "tokens": {"total": sum(tokens), "mean_per_record": mean(tokens) if tokens else None, "max_per_record": max(tokens) if tokens else None},
        },
        "limitations": [
            "QA 的答案指标使用词面 F1 代理，不能替代人工语义评分。",
            "待办和约束使用候选文本规范化口径，不等同于从完整会议转写重新抽取。",
            "本次 100 条来自 28 场会议，不能表述为 100 场会议。",
        ],
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
