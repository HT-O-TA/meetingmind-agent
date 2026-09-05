"""用 OpenAI 兼容接口运行受限 token 的云端 canary 评测。"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "backend/evaluation/datasets/meetingmind_real_v1_evaluation.jsonl"
DEFAULT_OUTPUT = ROOT / "backend/evaluation/reports/meetingmind_real_v1_cloud_canary.json"


def load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def prompt_for(record: dict[str, Any]) -> list[dict[str, str]]:
    if record.get("unit_type") == "todo":
        candidate = (record.get("extraction", {}).get("predicted") or [{}])[0]
        return [
            {"role": "system", "content": "你是会议待办审核器。只输出合法 JSON，不要解释。格式：{\"decision\":\"accept或reject\",\"todos\":[{\"content\":\"\",\"assignee\":\"\",\"deadline\":\"\"}]}。只保留明确行动，不要把讨论或建议当待办。"},
            {"role": "user", "content": f"候选待办：{json.dumps(candidate, ensure_ascii=False)}\n请判断并输出规范化结果。"},
        ]
    if record.get("unit_type") == "constraint":
        candidate = (record.get("extraction", {}).get("predicted") or [{}])[0]
        return [
            {"role": "system", "content": "你是会议约束审核器。只输出合法 JSON，不要解释。格式：{\"decision\":\"accept或reject\",\"constraint\":{\"kind\":\"\",\"text\":\"\"}}。只有明确的否定、阈值、范围或条件才接受。"},
            {"role": "user", "content": f"候选约束：{json.dumps(candidate, ensure_ascii=False)}\n请判断并输出规范化结果。"},
        ]
    generation = record.get("generation", {})
    context_texts = generation.get("contexts", [])
    citation_ids = record.get("retrieval", {}).get("retrieved_ids", [])
    citation_blocks = []
    for index, text in enumerate(context_texts[:6]):
        citation_id = citation_ids[index] if index < len(citation_ids) else f"context-{index + 1}"
        citation_blocks.append(f"[{citation_id}] {str(text)[:800]}")
    contexts = "\n".join(citation_blocks)[:4800]
    question = generation.get("question", record.get("question", ""))
    return [
        {"role": "system", "content": "你是会议助手。只输出一个合法 JSON 对象，不要 Markdown，不要解释。格式：{\"answer\":\"简短回答\",\"citation_ids\":[]}。只能依据上下文回答。citation_ids 只能填写上下文方括号中的 ID，不能填写引用原文。"},
        {"role": "user", "content": f"问题：{question}\n引用候选：\n{contexts}\n请用不超过两句话回答，并只返回实际支持答案的引用 ID。"},
    ]


def call(api_base: str, api_key: str, model: str, messages: list[dict[str, str]], max_tokens: int, timeout: int) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
        "enable_thinking": False,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        api_base.rstrip("/") + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        body["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        return body
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:500]}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--record-id", help="只运行指定记录，用于最重样本预估")
    parser.add_argument("--max-tokens", type=int, default=768)
    parser.add_argument("--total-token-budget", type=int, default=10000)
    parser.add_argument("--per-record-token-budget", type=int, default=2000)
    args = parser.parse_args()
    api_key = os.environ.get("LLM_API_KEY", "")
    api_base = os.environ.get("LLM_API_BASE", "")
    model = os.environ.get("LLM_MODEL", "qwen3.7-max-2026-06-08")
    if not api_key or not api_base:
        raise ValueError("请通过 LLM_API_KEY 和 LLM_API_BASE 环境变量提供云端配置")
    all_records = load(args.dataset)
    records = ([record for record in all_records if record.get("id") == args.record_id]
               if args.record_id else all_records[:args.count])
    if not records:
        raise ValueError("没有可用 QA 样本")
    results: list[dict[str, Any]] = []
    used_tokens = 0
    pause_reason: str | None = None
    paused_at_id: str | None = None
    for record in records:
        if used_tokens >= args.total_token_budget:
            pause_reason = "total_token_budget_exceeded"
            paused_at_id = record["id"]
            break
        print(f"progress {len(results) + 1}/{len(records)} start id={record['id']}", flush=True)
        try:
            record_max_tokens = args.max_tokens if record.get("unit_type") == "qa" else min(args.max_tokens, 384)
            response = call(api_base, api_key, model, prompt_for(record), record_max_tokens, 60)
            usage = response.get("usage") or {}
            record_tokens = int(usage.get("total_tokens", 0) or 0)
            used_tokens += record_tokens
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            try:
                parsed = json.loads(content)
                json_valid = True
            except (TypeError, json.JSONDecodeError):
                parsed = None
                json_valid = False
            finish_reason = response.get("choices", [{}])[0].get("finish_reason")
            anomaly = []
            if record_tokens > args.per_record_token_budget:
                anomaly.append("per_record_token_budget_exceeded")
            if finish_reason == "length":
                anomaly.append("finish_reason_length")
            if not json_valid:
                anomaly.append("invalid_json")
            results.append({"id": record["id"], "ok": not anomaly, "json_valid": json_valid, "output": parsed or content, "usage": usage, "finish_reason": finish_reason, "latency_ms": response.get("latency_ms"), "anomalies": anomaly})
            print(f"progress {len(results)}/{len(records)} done id={record['id']} json_valid={json_valid} total_tokens={record_tokens}", flush=True)
            if anomaly:
                pause_reason = ",".join(anomaly)
                paused_at_id = record["id"]
                print(f"PAUSED id={record['id']} reason={pause_reason}", flush=True)
                break
        except Exception as exc:
            results.append({"id": record["id"], "ok": False, "error": str(exc)})
            print(f"progress {len(results)}/{len(records)} failed id={record['id']} error={exc}", flush=True)
            pause_reason = "request_exception"
            paused_at_id = record["id"]
            print(f"PAUSED id={record['id']} reason={pause_reason}", flush=True)
            break
        if used_tokens >= args.total_token_budget:
            break
    payload = {
        "schema_version": "meetingmind.cloud-canary.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "count_requested": args.count,
        "count_completed": len(results),
        "max_tokens": args.max_tokens,
        "total_token_budget": args.total_token_budget,
        "per_record_token_budget": args.per_record_token_budget,
        "total_tokens_observed": used_tokens,
        "paused": pause_reason is not None,
        "pause_reason": pause_reason,
        "paused_at_id": paused_at_id,
        "results": results,
        "limitations": ["待办和约束当前使用冻结候选文本做规范化审核，不等同于从完整会议转写中重新抽取。", "模型供应商可能将隐藏思考 token 计入 completion_tokens。"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
