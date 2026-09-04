#!/usr/bin/env python3
"""测量真实 Agent API 的 P50/P95、失败率、Token 和单请求成本。

脚本只采集服务实际返回的预算账本；没有供应商 usage 或价格时，成本保持 null，
不把估算值伪装成真实费用。
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((q * len(ordered) + 0.999999)) - 1))
    return ordered[index]


def load_questions(path: Path) -> list[dict[str, Any]]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            records.append(json.loads(line))
    return [record for record in records if record.get("question")]


def ledger_usage(ledger: Any) -> tuple[int, str, bool, int, int]:
    if not isinstance(ledger, dict):
        return 0, "unavailable", False, 0, 0
    decisions = ledger.get("decisions") or []
    actual_total = 0
    actual_input_total = 0
    actual_output_total = 0
    projected_total = 0
    actual_count = 0
    decision_count = 0
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        decision_count += 1
        projected_total += int(decision.get("projected_call_tokens", 0) or 0)
        input_tokens = decision.get("actual_input_tokens")
        output_tokens = decision.get("actual_output_tokens")
        if input_tokens is not None and output_tokens is not None:
            input_value = int(input_tokens or 0)
            output_value = int(output_tokens or 0)
            actual_input_total += input_value
            actual_output_total += output_value
            actual_total += input_value + output_value
            actual_count += 1
    if decision_count and actual_count == decision_count:
        return actual_total, "provider_usage", True, actual_input_total, actual_output_total
    if actual_count:
        # 混合账本不拿来算成本；缺少 usage 的调用保留其预算上限，避免低估。
        return actual_total + max(0, projected_total - actual_total), "mixed_usage", False, actual_input_total, actual_output_total
    if projected_total:
        return projected_total, "reserved_upper_bound", False, 0, 0
    return 0, "unavailable", False, 0, 0


def main() -> int:
    parser = argparse.ArgumentParser(description="测量 Agent API 运行指标")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", default=os.getenv("MEETINGMIND_BEARER_TOKEN"))
    parser.add_argument("--dataset", type=Path, default=Path("backend/evaluation/datasets/meetingmind_deidentified_v1.jsonl"))
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--warmup", type=int, default=0)
    parser.add_argument("--meeting-id", type=int)
    parser.add_argument("--document-id", type=int, action="append")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input-price-per-1k", type=float, default=None)
    parser.add_argument("--output-price-per-1k", type=float, default=None)
    args = parser.parse_args()
    if not args.token:
        raise SystemExit("请通过 --token 或 MEETINGMIND_BEARER_TOKEN 提供登录后的 Bearer Token")
    if args.repeat < 1 or args.warmup < 0:
        raise SystemExit("repeat 必须大于 0，warmup 不能小于 0")

    records = load_questions(args.dataset)
    if not records:
        raise SystemExit("评测集没有可运行的问题")
    headers = {"Authorization": f"Bearer {args.token}"}
    latencies: list[float] = []
    all_latencies: list[float] = []
    errors: list[dict[str, Any]] = []
    total_tokens = 0
    total_input_tokens = 0
    total_output_tokens = 0
    token_sources: set[str] = set()
    provider_usage_complete_count = 0
    measured = []

    with httpx.Client(base_url=args.base_url, headers=headers, timeout=120.0) as client:
        for _ in range(args.warmup):
            client.post("/api/v1/agents/query", json={"question": records[0]["question"], "meeting_id": args.meeting_id})
        for repeat_index in range(args.repeat):
            for record in records:
                body: dict[str, Any] = {"question": record["question"], "session_id": f"runtime-{repeat_index}"}
                if args.meeting_id is not None:
                    body["meeting_id"] = args.meeting_id
                if args.document_id:
                    body["document_ids"] = args.document_id
                started = time.perf_counter()
                try:
                    response = client.post("/api/v1/agents/query", json=body)
                    elapsed_ms = (time.perf_counter() - started) * 1000
                    payload = response.json()
                    success = response.status_code == 200 and bool(payload.get("success", False))
                    ledger = payload.get("budget_ledger")
                    tokens, source, has_actual, input_tokens, output_tokens = ledger_usage(ledger)
                    total_tokens += tokens
                    total_input_tokens += input_tokens
                    total_output_tokens += output_tokens
                    token_sources.add(source)
                    provider_usage_complete_count += 1 if has_actual else 0
                    item = {
                        "id": record.get("id"),
                        "repeat": repeat_index,
                        "status_code": response.status_code,
                        "success": success,
                        "latency_ms": round(elapsed_ms, 3),
                        "tokens": tokens,
                        "token_source": source,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "error": payload.get("error"),
                    }
                    measured.append(item)
                    all_latencies.append(elapsed_ms)
                    if success:
                        latencies.append(elapsed_ms)
                    else:
                        errors.append(item)
                except Exception as exc:
                    elapsed_ms = (time.perf_counter() - started) * 1000
                    item = {"id": record.get("id"), "repeat": repeat_index, "success": False, "latency_ms": round(elapsed_ms, 3), "error": str(exc)}
                    measured.append(item)
                    all_latencies.append(elapsed_ms)
                    errors.append(item)

    cost = None
    cost_status = "unavailable_no_provider_usage_or_price"
    if provider_usage_complete_count == len(measured) and measured and args.input_price_per_1k is not None and args.output_price_per_1k is not None:
        cost = (
            total_input_tokens / 1000 * args.input_price_per_1k
            + total_output_tokens / 1000 * args.output_price_per_1k
        )
        cost_status = "estimated_from_provider_usage"

    report = {
        "schema_version": "meetingmind.runtime-benchmark.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(args.dataset),
        "sample_kind": "deidentified",
        "request_count": len(measured),
        "success_count": len(measured) - len(errors),
        "failure_rate": len(errors) / len(measured) if measured else 0.0,
        "latency_ms": {
            "p50": round(percentile(latencies, 0.50), 3),
            "p95": round(percentile(latencies, 0.95), 3),
            "mean": round(statistics.mean(latencies), 3) if latencies else 0.0,
            "successful_requests_only": True,
            "all_requests": {
                "p50": round(percentile(all_latencies, 0.50), 3),
                "p95": round(percentile(all_latencies, 0.95), 3),
                "mean": round(statistics.mean(all_latencies), 3) if all_latencies else 0.0,
            },
        },
        "tokens": {
            "total": total_tokens,
            "input": total_input_tokens,
            "output": total_output_tokens,
            "sources": sorted(token_sources),
        },
        "cost": {"total": cost, "per_successful_request": cost / len(latencies) if cost is not None and latencies else None, "status": cost_status},
        "requests": measured,
        "limitations": [
            "只有真实服务运行、真实请求返回和供应商 usage 才能形成真实系统指标。",
            "未提供输入/输出价格或没有 provider usage 时，成本保持 null。",
            "报告同时给出成功请求和 all_requests 两组 P50/P95；失败率单独统计。",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
