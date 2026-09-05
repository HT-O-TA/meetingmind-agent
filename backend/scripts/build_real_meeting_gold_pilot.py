"""从 580 条 AI 初审结果中抽取 100 条人工 gold-pilot。"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = REPO_ROOT / "backend/evaluation/datasets/meetingmind_real_v1_ai_reviews.jsonl"
DEFAULT_OUTPUT = REPO_ROOT / "backend/evaluation/datasets/meetingmind_real_v1_gold_pilot.jsonl"
DEFAULT_MANIFEST = REPO_ROOT / "backend/evaluation/datasets/meetingmind_real_v1_gold_pilot_manifest.json"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def round_robin(rows: list[dict[str, Any]], count: int, key: Callable[[dict[str, Any]], str]) -> list[dict[str, Any]]:
    """按 key 分层轮询，避免样本集中在单个会议或单个决定。"""
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in sorted(rows, key=lambda item: item["unit_id"]):
        groups.setdefault(key(row), []).append(row)
    selected: list[dict[str, Any]] = []
    while len(selected) < count and groups:
        for group_key in sorted(list(groups)):
            bucket = groups[group_key]
            if bucket:
                selected.append(bucket.pop(0))
                if len(selected) >= count:
                    break
            if not bucket:
                groups.pop(group_key, None)
    if len(selected) != count:
        raise ValueError(f"分层样本不足：需要 {count} 条，实际只有 {len(selected)} 条")
    return selected


def choose(rows: list[dict[str, Any]], unit_type: str, source: str, decision: str, count: int, group_field: str = "meeting_id") -> list[dict[str, Any]]:
    pool = [row for row in rows if row["unit_type"] == unit_type and row["source_dataset"] == source and row["decision"] == decision]
    return round_robin(pool, count, lambda row: str(row.get(group_field, "")))


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 100 条人工 gold-pilot 抽样集")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    rows = read_jsonl(args.input)

    selected: list[dict[str, Any]] = []
    selected += choose(rows, "todo", "AliMeeting-Eval", "edit", 10)
    selected += choose(rows, "todo", "AliMeeting-Eval", "reject", 10)
    selected += choose(rows, "todo", "VCSUM", "reject", 10)
    selected += choose([row for row in rows if row.get("candidate", {}).get("task") == "overall_summary_qa"], "qa", "VCSUM", "edit", 20)
    selected += choose([row for row in rows if row.get("candidate", {}).get("task") == "topic_qa"], "qa", "VCSUM", "accept", 10)
    selected += choose([row for row in rows if row.get("candidate", {}).get("task") == "topic_qa"], "qa", "VCSUM", "edit", 10)
    selected += choose(rows, "constraint", "AliMeeting-Eval", "accept", 8)
    selected += choose(rows, "constraint", "AliMeeting-Eval", "reject", 7)
    selected += choose(rows, "constraint", "VCSUM", "accept", 8)
    selected += choose(rows, "constraint", "VCSUM", "reject", 7)
    if len(selected) != 100 or len({row["unit_id"] for row in selected}) != 100:
        raise RuntimeError("gold-pilot 必须恰好包含 100 条唯一审核单元")

    pilot = []
    for index, row in enumerate(sorted(selected, key=lambda item: item["unit_id"]), start=1):
        pilot.append({
            "pilot_id": f"gold-pilot-{index:03d}",
            "review_status": "pending_human_review",
            "source_review": row,
            "human_review": {
                "decision": None,
                "corrected": None,
                "evidence_ids": [],
                "rationale": "",
                "reviewer": "",
                "reviewed_at": None,
            },
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in pilot) + "\n", encoding="utf-8")
    counts = Counter((row["source_review"]["unit_type"], row["source_review"]["source_dataset"], row["source_review"]["decision"]) for row in pilot)
    manifest = {
        "schema_version": "meetingmind.gold-pilot-manifest.v1",
        "dataset_version": "meetingmind-real-v1",
        "annotation_status": "pending_human_review",
        "gold": False,
        "source_ai_review": str(args.input.resolve().relative_to(REPO_ROOT)).replace("\\", "/"),
        "pilot_file": str(args.output.resolve().relative_to(REPO_ROOT)).replace("\\", "/"),
        "record_count": len(pilot),
        "sampling_rule": "固定分层抽样：问答 40、待办 30、约束 30；问答包含 20 条 VCSUM 整体问答和 20 条主题问答，覆盖 VCSUM/AliMeeting 和 accept/edit/reject。",
        "counts": {f"{unit}.{source}.{decision}": count for (unit, source, decision), count in sorted(counts.items())},
        "human_review_fields": ["decision", "corrected", "evidence_ids", "rationale", "reviewer", "reviewed_at"],
        "promotion_rule": "只有人工完成 100 条审核并通过质量检查，才能生成 gold-pilot.v1；不能把 AI decision 直接当作人工结论。",
    }
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"records": len(pilot), "output": str(args.output), "manifest": str(args.manifest), "counts": manifest["counts"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
