"""按 corrected.needs_review 拆分真实会议 AI 初审结果。"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = REPO_ROOT / "backend/evaluation/datasets/meetingmind_real_v1_ai_reviews.jsonl"
DEFAULT_AUTO = REPO_ROOT / "backend/evaluation/datasets/meetingmind_real_v1_ai_accepted_silver.jsonl"
DEFAULT_QUEUE = REPO_ROOT / "backend/evaluation/datasets/meetingmind_real_v1_human_review_queue.jsonl"
DEFAULT_MANIFEST = REPO_ROOT / "backend/evaluation/datasets/meetingmind_real_v1_review_queue_manifest.json"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description="拆分机器初步通过项和人工重点审核队列")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--auto-output", type=Path, default=DEFAULT_AUTO)
    parser.add_argument("--queue-output", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    rows = read_jsonl(args.input)
    auto_accepted = [row for row in rows if isinstance(row.get("corrected"), dict) and row["corrected"].get("needs_review") is False]
    human_queue = [row for row in rows if row not in auto_accepted]
    if len(rows) != 580 or len(auto_accepted) != 71 or len(human_queue) != 509:
        raise RuntimeError(f"审核队列数量不符合预期：总数={len(rows)}，机器初步通过={len(auto_accepted)}，人工队列={len(human_queue)}")

    write_jsonl(args.auto_output, auto_accepted)
    write_jsonl(args.queue_output, human_queue)
    manifest = {
        "schema_version": "meetingmind.review-queue-manifest.v1",
        "dataset_version": "meetingmind-real-v1",
        "source": relative(args.input),
        "source_annotation_status": "ai_reviewed_silver",
        "auto_accepted_file": relative(args.auto_output),
        "human_review_queue_file": relative(args.queue_output),
        "counts": {
            "total": len(rows),
            "auto_accepted_needs_review_false": len(auto_accepted),
            "human_review_queue": len(human_queue),
        },
        "auto_accepted_breakdown": {
            ".".join(key): count
            for key, count in Counter((row["unit_type"], row["source_dataset"], row["decision"]) for row in auto_accepted).items()
        },
        "human_review_breakdown": {
            ".".join(key): count
            for key, count in Counter((row["unit_type"], row["source_dataset"], row["decision"]) for row in human_queue).items()
        },
        "rule": "只有 corrected.needs_review 严格等于 false 才进入机器初步通过区；该区仍不是人工 gold。",
        "human_sampling": "机器初步通过区至少抽检 5-10 条；人工重点队列优先审核问答、待办和 needs_review=true 的约束。",
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["counts"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
