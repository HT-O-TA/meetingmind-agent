"""把完成复核的 100 条 pilot 冻结为 evaluation.v1，并保留可追溯来源。"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "backend/evaluation/datasets/meetingmind_real_v1_gold_pilot.jsonl"
DEFAULT_OUTPUT = ROOT / "backend/evaluation/datasets/meetingmind_real_v1_evaluation.jsonl"
DEFAULT_MANIFEST = ROOT / "backend/evaluation/datasets/meetingmind_real_v1_evaluation_manifest.json"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def citation_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict) and item.get("citation_id"):
                result.append(str(item["citation_id"]))
        return list(dict.fromkeys(result))
    return []


def citation_texts(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item["text"]) for item in value if isinstance(item, dict) and item.get("text")]


def todo_fields(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [
            {key: item.get(key, "") for key in ("content", "assignee", "deadline")}
            for item in value
            if isinstance(item, dict)
        ]
    if not isinstance(value, dict):
        return []
    return [{key: value.get(key, "") for key in ("content", "assignee", "deadline")}]


def constraint_fields(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    return [{key: value.get(key, "") for key in ("kind", "text")}]


def selected_gold(source: dict[str, Any], human: dict[str, Any]) -> Any:
    if human.get("decision") == "edit" and human.get("corrected") is not None:
        return human["corrected"]
    return source.get("corrected") or source.get("candidate")


def convert(row: dict[str, Any]) -> dict[str, Any]:
    source = row["source_review"]
    human = row["human_review"]
    candidate = source.get("candidate") or {}
    gold = selected_gold(source, human)
    unit_type = source["unit_type"]
    common = {
        "id": row["pilot_id"],
        "dataset_version": "meetingmind-real-v1-evaluation.v1",
        "sample_kind": "real",
        "split": "test",
        "meeting_id": source.get("meeting_id"),
        "unit_type": unit_type,
        "source_dataset": source.get("source_dataset"),
        "source_unit_id": source.get("unit_id"),
        "review_decision": human["decision"],
        "reviewer": human.get("reviewer"),
    }
    if unit_type == "qa":
        candidate_citations = citation_ids(candidate.get("citation_ids"))
        gold_citations = citation_ids((gold or {}).get("citations")) or human.get("evidence_ids", [])
        contexts = citation_texts((gold or {}).get("citations"))
        if not contexts:
            contexts = citation_texts((source.get("corrected") or {}).get("citations"))
        common.update({
            "question": (gold or candidate).get("question", ""),
            "retrieval": {"relevant_ids": gold_citations, "retrieved_ids": candidate_citations},
            "generation": {
                "question": (gold or candidate).get("question", ""),
                "answer": candidate.get("answer", ""),
                "contexts": contexts,
                "citation_ids": candidate_citations,
            },
        })
    elif unit_type == "todo":
        common["extraction"] = {
            "expected": [] if human["decision"] == "reject" else todo_fields(gold),
            "predicted": todo_fields(candidate),
            "raw_output": json.dumps(todo_fields(candidate), ensure_ascii=False),
        }
    elif unit_type == "constraint":
        common["extraction"] = {
            "expected": [] if human["decision"] == "reject" else constraint_fields(gold),
            "predicted": constraint_fields(candidate),
            "raw_output": json.dumps(constraint_fields(candidate), ensure_ascii=False),
        }
    return common


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    rows = load_jsonl(args.input)
    if len(rows) != 100 or len({row.get("pilot_id") for row in rows}) != 100:
        raise ValueError("输入必须是 100 条且 pilot_id 唯一")
    missing = [row["pilot_id"] for row in rows if row.get("human_review", {}).get("decision") not in {"accept", "edit", "reject"}]
    if missing:
        raise ValueError(f"仍有未完成人工决定：{missing[:5]}")
    records = [convert(row) for row in rows]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n", encoding="utf-8")
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    counts: dict[str, int] = {}
    for record in records:
        key = f"{record['unit_type']}.{record['review_decision']}"
        counts[key] = counts.get(key, 0) + 1
    manifest = {
        "schema_version": "evaluation.v1",
        "dataset_version": "meetingmind-real-v1-evaluation.v1",
        "annotation_status": "frozen_reviewed_pilot",
        "sample_kind": "real",
        "gold": False,
        "source_pilot": str(args.input.relative_to(ROOT)).replace("\\", "/"),
        "evaluation_file": str(args.output.relative_to(ROOT)).replace("\\", "/"),
        "sha256": digest,
        "record_count": len(records),
        "counts": counts,
        "reviewer_counts": {reviewer: sum(record.get("reviewer") == reviewer for record in records) for reviewer in sorted({record.get("reviewer") for record in records})},
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "limitations": [
            "这是 100 条分层试点评测集，不代表全部 580 条候选或生产泛化效果。",
            "100 条记录均已由 reviewer=ht 完成人工审核；此前的 AI 初审只作为人工复核参考。",
            "系统延迟、失败率和成本需要真实服务运行，本文件只提供质量评测标签。",
        ],
    }
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
