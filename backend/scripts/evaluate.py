#!/usr/bin/env python3
"""MeetingMind 唯一离线评估命令。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.evaluation.offline_metrics import evaluate_records, flatten_report


PROMPT_INJECTION_SCHEMA_VERSION = "meetingmind.prompt-injection-case.v1"


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


def check_thresholds(
    report: Dict[str, Any],
    path: Path,
    *,
    dataset_version: str | None = None,
) -> List[str]:
    config = json.loads(path.read_text(encoding="utf-8"))
    actual = flatten_report(report)
    failures = []
    threshold_dataset_version = config.get("dataset_version")
    if (
        threshold_dataset_version
        and dataset_version
        and str(threshold_dataset_version) != dataset_version
    ):
        failures.append(
            f"阈值数据版本 {threshold_dataset_version} 与数据集 {dataset_version} 不一致"
        )
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
        "",
    ]
    if payload["metadata"].get("top_k") is not None:
        lines.insert(-1, f"- Top-K：{payload['metadata']['top_k']}")
    if payload["metadata"]["sample_kind"] != "real":
        lines.extend([
            "> 此报告来自 synthetic 数据，仅验证数据、公式、规则或控制流的可复现回归，不得用于生产效果或简历结论。",
            "",
        ])
    for section, metrics in payload["metrics"].items():
        if not isinstance(metrics, dict) or not metrics:
            continue
        if all(isinstance(value, dict) for value in metrics.values()):
            metric_names = sorted({
                name
                for values in metrics.values()
                for name in values
            })
            lines.extend([
                f"## {section}",
                "",
                "| 分组 | " + " | ".join(metric_names) + " |",
                "|---|" + "---:|" * len(metric_names),
            ])
            for group, values in metrics.items():
                rendered_values = []
                for name in metric_names:
                    value = values.get(name, "")
                    rendered_values.append(
                        f"{value:.4f}" if isinstance(value, float) else str(value)
                    )
                lines.append(f"| {group} | " + " | ".join(rendered_values) + " |")
            lines.append("")
            continue
        lines.extend([f"## {section}", "", "| 指标 | 数值 |", "|---|---:|"])
        for name, value in metrics.items():
            if isinstance(value, dict):
                continue
            rendered = f"{value:.4f}" if isinstance(value, float) else str(value)
            lines.append(f"| {name} | {rendered} |")
        lines.append("")
    if payload.get("limitations"):
        lines.extend(["## 限制", ""])
        lines.extend(f"- {item}" for item in payload["limitations"])
        lines.append("")
    if payload.get("threshold_failures"):
        lines.extend(["## 回归阈值失败", ""])
        lines.extend(f"- {failure}" for failure in payload["threshold_failures"])
        lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="统一计算 RAG/抽取/工具/路由/系统/输入安全离线指标")
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
    dataset_versions = sorted({
        str(record["dataset_version"])
        for record in records
        if record.get("dataset_version") is not None
    })
    dataset_version = dataset_versions[0] if len(dataset_versions) == 1 else None
    if sample_kind != "real" and not args.allow_synthetic:
        raise ValueError("数据集不是 real；仅验证示例时请显式添加 --allow-synthetic")

    schemas = {str(record.get("schema_version", "")) for record in records}
    if schemas == {PROMPT_INJECTION_SCHEMA_VERSION}:
        from app.evaluation.prompt_injection_metrics import (
            evaluate_prompt_injection_cases,
            load_prompt_injection_cases,
        )

        cases = load_prompt_injection_cases(args.dataset)
        security_report = evaluate_prompt_injection_cases(cases)
        metrics = {
            "security": security_report["metrics"],
            "security_by_source": security_report["by_source"],
        }
        suite = "prompt_injection"
        limitations = security_report["limitations"]
        case_results = security_report["case_results"]
        top_k = None
    else:
        metrics = evaluate_records(records, top_k=args.top_k)
        suite = "general"
        limitations = []
        case_results = []
        top_k = args.top_k
    failures = (
        check_thresholds(
            metrics,
            args.thresholds,
            dataset_version=dataset_version,
        )
        if args.thresholds else []
    )
    payload = {
        "metadata": {
            "schema_version": "evaluation.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dataset": str(args.dataset),
            "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
            "dataset_version": dataset_version,
            "sample_kind": sample_kind,
            "record_count": len(records),
            "suite": suite,
            "top_k": top_k,
            "generation_metric_note": "faithfulness/relevancy are lexical proxies unless replaced by labeled evaluator outputs",
        },
        "metrics": metrics,
        "case_results": case_results,
        "limitations": limitations,
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
