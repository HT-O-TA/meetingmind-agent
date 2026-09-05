"""运行冻结的真实会议 100 条试点评测，并输出离线基线报告。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.evaluation.offline_metrics import precision_recall_f1, retrieval_metrics  # noqa: E402


DEFAULT_DATASET = ROOT / "backend/evaluation/datasets/meetingmind_real_v1_evaluation.jsonl"
DEFAULT_OUTPUT = ROOT / "backend/evaluation/reports/meetingmind_real_v1_baseline.json"


def load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def avg(values: list[float]) -> float | None:
    return mean(values) if values else None


def evaluate(records: list[dict[str, Any]], dataset: Path) -> dict[str, Any]:
    retrieval: list[dict[str, float]] = []
    generation: list[dict[str, float]] = []
    extraction: dict[str, list[dict[str, float]]] = {}
    for record in records:
        if record.get("retrieval"):
            block = record["retrieval"]
            retrieval.append(retrieval_metrics(block.get("relevant_ids", []), block.get("retrieved_ids", []), 5))
        if record.get("generation"):
            block = record["generation"]
            citations = set(block.get("citation_ids", []))
            relevant = set(record.get("retrieval", {}).get("relevant_ids", []))
            generation.append({"citation_accuracy": len(citations & relevant) / len(citations) if citations else (1.0 if not relevant else 0.0)})
        if record.get("extraction"):
            kind = record.get("unit_type", "unknown")
            extraction.setdefault(kind, []).append(precision_recall_f1(record["extraction"].get("expected", []), record["extraction"].get("predicted", [])))

    def average_dict(items: list[dict[str, float]]) -> dict[str, float | None]:
        keys = sorted(set().union(*(item.keys() for item in items))) if items else []
        return {key: avg([float(item.get(key, 0.0)) for item in items]) for key in keys}

    extraction_report = {kind: average_dict(items) for kind, items in extraction.items()}
    todo = extraction_report.get("todo", {})
    return {
        "metadata": {
            "schema_version": "evaluation.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dataset": str(dataset.relative_to(ROOT)).replace("\\", "/"),
            "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
            "dataset_version": "meetingmind-real-v1-evaluation.v1",
            "sample_kind": "real",
            "record_count": len(records),
            "suite": "real_meeting_frozen_pilot_baseline",
            "baseline_type": "candidate_vs_reviewed_labels",
        },
        "metrics": {
            "retrieval": average_dict(retrieval),
            "generation": average_dict(generation),
            "extraction_by_unit_type": extraction_report,
            "todo": {"todo_f1": todo.get("f1"), "precision": todo.get("precision"), "recall": todo.get("recall")},
        },
        "system": {
            "status": "not_measured",
            "p50_latency_ms": None,
            "p95_latency_ms": None,
            "failure_rate": None,
            "single_request_cost": None,
        },
        "limitations": [
            "质量基线比较的是已生成候选与复核标签，不是模型重新推理结果。",
            "当前冻结集只有 100 条，覆盖 28 场会议；100 条均已由 reviewer=ht 完成人工审核。",
            "未连接真实模型、数据库或队列，因此不报告端到端延迟、失败率和成本。",
        ],
    }


def markdown(payload: dict[str, Any]) -> str:
    lines = ["# MeetingMind 真实会议 100 条离线基线", "", f"- 数据集：`{payload['metadata']['dataset']}`", f"- 数据集哈希：`{payload['metadata']['dataset_sha256']}`", f"- 样本数：{payload['metadata']['record_count']}", "", "> 这是候选结果对照复核标签的离线基线，不是端到端线上性能结论。", ""]
    for section, values in payload["metrics"].items():
        lines.extend([f"## {section}", ""])
        if isinstance(values, dict):
            for key, value in values.items():
                if isinstance(value, dict):
                    lines.append(f"- {key}：{json.dumps(value, ensure_ascii=False)}")
                else:
                    lines.append(f"- {key}：{value if value is not None else '未测量'}")
        lines.append("")
    lines.extend(["## 系统性能", "", "- P50/P95 延迟：未测量", "- 失败率：未测量", "- 单请求成本：未测量", ""])
    lines.extend(["## 限制", "", *[f"- {item}" for item in payload["limitations"]], ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    records = load(args.dataset)
    if len(records) != 100:
        raise ValueError(f"冻结评测集应为 100 条，实际 {len(records)} 条")
    payload = evaluate(records, args.dataset)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
