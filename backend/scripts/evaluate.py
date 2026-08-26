#!/usr/bin/env python3
"""MeetingMind 唯一离线评估命令。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.evaluation.offline_metrics import evaluate_records, flatten_report


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number} 必须是 JSON 对象")
        records.append(value)
    return records


def check_thresholds(report: Dict[str, Any], path: Path) -> List[str]:
    config = json.loads(path.read_text(encoding="utf-8"))
    actual = flatten_report(report)
    failures = []
    for metric, threshold in config.get("minimum", {}).items():
        if metric not in actual:
            failures.append(f"缺少指标 {metric}")
        elif actual[metric] < float(threshold):
            failures.append(f"{metric}={actual[metric]:.4f} < {float(threshold):.4f}")
    for metric, threshold in config.get("maximum", {}).items():
        if metric not in actual:
            failures.append(f"缺少指标 {metric}")
        elif actual[metric] > float(threshold):
            failures.append(f"{metric}={actual[metric]:.4f} > {float(threshold):.4f}")
    return failures


def markdown_report(payload: Dict[str, Any]) -> str:
    lines = [
        "# MeetingMind 离线评估报告",
        "",
        f"- 生成时间：{payload['metadata']['generated_at']}",
        f"- 数据集：`{payload['metadata']['dataset']}`",
        f"- 数据类型：`{payload['metadata']['sample_kind']}`",
        f"- 样本数：{payload['metadata']['record_count']}",
        f"- Top-K：{payload['metadata']['top_k']}",
        "",
    ]
    if payload["metadata"]["sample_kind"] != "real":
        lines.extend([
            "> 此报告来自 synthetic 示例，仅验证评估代码可运行，不得用于 README、简历或性能结论。",
            "",
        ])
    for section, metrics in payload["metrics"].items():
        if not isinstance(metrics, dict) or not metrics:
            continue
        lines.extend([f"## {section}", "", "| 指标 | 数值 |", "|---|---:|"])
        for name, value in metrics.items():
            rendered = f"{value:.4f}" if isinstance(value, float) else str(value)
            lines.append(f"| {name} | {rendered} |")
        lines.append("")
    if payload.get("threshold_failures"):
        lines.extend(["## 回归阈值失败", ""])
        lines.extend(f"- {failure}" for failure in payload["threshold_failures"])
        lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="统一计算 RAG/抽取/工具/路由/系统离线指标")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=BACKEND_ROOT / "evaluation/datasets/sample_eval.jsonl",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--output",
        type=Path,
        default=BACKEND_ROOT / "evaluation/reports/latest.json",
    )
    parser.add_argument("--thresholds", type=Path)
    parser.add_argument("--enforce-thresholds", action="store_true")
    parser.add_argument("--allow-synthetic", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = load_jsonl(args.dataset)
    if not records:
        raise ValueError("评估数据集为空")
    kinds = sorted({str(record.get("sample_kind", "unknown")) for record in records})
    sample_kind = kinds[0] if len(kinds) == 1 else "mixed"
    if sample_kind != "real" and not args.allow_synthetic:
        raise ValueError("数据集不是 real；仅验证示例时请显式添加 --allow-synthetic")

    metrics = evaluate_records(records, top_k=args.top_k)
    failures = check_thresholds(metrics, args.thresholds) if args.thresholds else []
    payload = {
        "metadata": {
            "schema_version": "evaluation.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dataset": str(args.dataset),
            "sample_kind": sample_kind,
            "record_count": len(records),
            "top_k": args.top_k,
            "generation_metric_note": "faithfulness/relevancy are lexical proxies unless replaced by labeled evaluator outputs",
        },
        "metrics": metrics,
        "threshold_failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path = args.output.with_suffix(".md")
    markdown_path.write_text(markdown_report(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.enforce_thresholds and failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
