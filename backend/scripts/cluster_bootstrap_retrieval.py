"""对检索基线按会议做 cluster bootstrap。"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from statistics import mean


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260905)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    rng = random.Random(args.seed)
    result = {}
    for method, rows in payload["per_record"].items():
        groups = {}
        for row in rows:
            groups.setdefault(str(row["meeting_id"]), []).append(row)
        keys = list(groups)
        draws = {field: [] for field in ("recall_at_5", "mrr", "ndcg_at_5")}
        for _ in range(args.iterations):
            sample = [rng.choice(keys) for _ in keys]
            sampled = [row for key in sample for row in groups[key]]
            for field in draws:
                draws[field].append(mean(row[field] for row in sampled))
        def interval(values):
            ordered = sorted(values)
            return {
                "mean": mean(values),
                "lower_95": ordered[int(0.025 * (len(values) - 1))],
                "upper_95": ordered[int(0.975 * (len(values) - 1))],
            }
        result[method] = {field: interval(values) for field, values in draws.items()}
    output = {
        "schema_version": "evaluation.retrieval_cluster_bootstrap.v1",
        "source": str(args.input),
        "meeting_count": payload["meeting_count"],
        "task_count": payload["task_count"],
        "iterations": args.iterations,
        "seed": args.seed,
        "metrics": result,
        "note": "以会议为单位重采样，不能把任务数当作独立样本数。",
    }
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
