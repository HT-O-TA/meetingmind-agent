"""把各独立评测报告汇总成扁平指标，并对 regression_thresholds.json 做门禁检查。

evaluate.py 只覆盖单一报告；路由、块级检索、云评测分别由不同脚本产出，这里统一收口。
缺少报告的指标计为失败（而不是静默通过）；阈值为 null 的指标跳过。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPORTS = BACKEND / "evaluation/reports"


def _load(name):
    path = REPORTS / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def collect(cloud_report: str = "meetingmind_real_v1_cloud_100_scored.json",
            tool_report: str = "tool_eval_heldout_v1_opus55.json") -> dict:
    actual = {}
    inj = _load("prompt_injection_synthetic_v1.json")
    if inj:
        sec = inj["metrics"]["security"]
        actual.update({"security.false_negative_rate": sec["false_negative_rate"],
                       "security.false_positive_rate": sec["false_positive_rate"]})
    tool = _load(tool_report)
    if tool:
        t = tool["summary"]
        actual.update({k: t[k] for k in ("tool.selection_accuracy", "tool.parameter_accuracy",
                                         "tool.hitl_trigger_accuracy", "tool.hitl_recall_on_writes",
                                         "tool.unsafe_write_count") if t.get(k) is not None})
    base = _load("meetingmind_real_v1_retrieval_baselines.json")
    if base:
        h = base["metrics"]["hybrid"]
        actual.update({"retrieval.recall_at_k": h["recall_at_5"], "retrieval.mrr": h["mrr"], "retrieval.ndcg_at_k": h["ndcg_at_5"]})
    chunk = _load("meetingmind_real_v1_chunk_retrieval.json")
    if chunk and "300:hybrid" in chunk["metrics"]:
        c = chunk["metrics"]["300:hybrid"]["all"]
        actual.update({"retrieval_chunk.evidence_recall_at_k": c["evidence_recall_at_k"], "retrieval_chunk.mrr": c["mrr"]})
    scored = _load(cloud_report)
    if scored:
        s = scored["metrics"]
        actual.update({
            "generation.citation_accuracy": s["qa"]["citation_precision"],
            "extraction.f1": min(s["todo"]["f1"], s["constraint"]["f1"]),
            "extraction.json_valid_rate": s["json_valid_rate"],
            "system.error_rate": s["failure_rate"],
            "system.p95_latency_ms": s["latency_ms"]["p95"],
        })
    route = _load("route_eval_test_v4_rules_semantic_head.json")
    if route:
        actual.update({"route.task_accuracy": route["task_accuracy"], "route.p95_latency_ms": route["latency_ms"]["p95"]})
    return actual


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cloud-report", default="meetingmind_real_v1_cloud_100_scored.json", help="reports/ 下的云评测评分报告")
    parser.add_argument("--tool-report", default="tool_eval_heldout_v1_opus55.json", help="reports/ 下的工具调用评测报告")
    args = parser.parse_args()
    config = json.loads((BACKEND / "evaluation/regression_thresholds.json").read_text(encoding="utf-8"))
    actual = collect(args.cloud_report, args.tool_report)
    print(f"云评测报告: {args.cloud_report}；工具评测报告: {args.tool_report}\n")
    rows, failures = [], []
    for kind, op in (("minimum", ">="), ("maximum", "<=")):
        for metric, threshold in config.get(kind, {}).items():
            if threshold is None:
                rows.append((metric, "—", op, "null", "SKIP"))
                continue
            value = actual.get(metric)
            ok = value is not None and (value >= threshold if kind == "minimum" else value <= threshold)
            rows.append((metric, "缺失" if value is None else f"{value:.4f}", op, threshold, "PASS" if ok else "FAIL"))
            if not ok:
                failures.append(metric)
    for row in rows:
        print("{:<40} {:>10} {:>2} {:<8} {}".format(*map(str, row)))
    print(f"\n{len(rows) - len(failures)}/{len(rows)} 通过（含 SKIP），失败: {failures or '无'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
