"""按会议而非按任务计算云端评测指标的 cluster bootstrap 区间。"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from statistics import mean


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scored", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260905)
    args = parser.parse_args()
    payload = json.loads(args.scored.read_text(encoding="utf-8"))
    groups: dict[str, list[dict]] = {}
    for row in payload.get("per_record", []):
        groups.setdefault(str(row.get("meeting_key") or "unknown"), []).append(row)
    keys = list(groups)
    rng = random.Random(args.seed)

    def metric(rows: list[dict], unit: str, field: str) -> float | None:
        values = [float(r[field]) for r in rows if r.get("unit_type") == unit and field in r]
        return mean(values) if values else None

    draws: dict[str, list[float]] = {"qa_citation_recall": [], "todo_f1": [], "constraint_f1": []}
    for _ in range(args.iterations):
        sample_keys = [rng.choice(keys) for _ in keys]
        rows = [row for key in sample_keys for row in groups[key]]
        for name, unit, field in (
            ("qa_citation_recall", "qa", "citation_recall"),
            ("todo_f1", "todo", "f1"),
            ("constraint_f1", "constraint", "f1"),
        ):
            value = metric(rows, unit, field)
            if value is not None:
                draws[name].append(value)

    def interval(values: list[float]) -> dict[str, float | None]:
        if not values:
            return {"mean": None, "lower_95": None, "upper_95": None}
        ordered = sorted(values)
        return {
            "mean": mean(values),
            "lower_95": ordered[int(0.025 * (len(ordered) - 1))],
            "upper_95": ordered[int(0.975 * (len(ordered) - 1))],
        }

    result = {
        "schema_version": "evaluation.cluster_bootstrap.v1",
        "source": str(args.scored),
        "meeting_count": len(keys),
        "task_count": len(payload.get("per_record", [])),
        "iterations": args.iterations,
        "seed": args.seed,
        "metrics": {name: interval(values) for name, values in draws.items()},
        "note": "每次重采样整场会议及其全部任务，不能解读为 100 个独立样本。",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
