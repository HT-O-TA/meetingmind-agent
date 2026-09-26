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


PROMPT_VERSION = os.environ.get("EVAL_PROMPT_VERSION", "v1")

# v2 只依据 prompt_dev_v1（非评测单元）制定：约束 accept 时原文与 kind 保持不变；
# 待办内容规范化为简短祈使句，说话人代号不当作负责人；判定标准写成可操作的正反例。
TODO_SYSTEM_V2 = (
    "你是会议待办审核器。输入是一句会议转写中的候选句，判断其中是否包含已经明确要做的具体行动。\n"
    "accept 条件（满足任一即可）：有人被要求、承诺或被安排去做一件具体的事，例如\"你去确认一下\"\"会后把X整理出来\"\"回头联系供应商\"。"
    "口语、语气词、无主语都不影响判断。\n"
    "reject 条件：寒暄、主持串场、介绍嘉宾、观点讨论、泛泛建议（\"应该多学习\"）、提问、描述已发生的事。\n"
    "accept 时每个独立行动写一条，content 用不超过 20 字的简短中文祈使句概括动作与对象（不照抄口语），"
    "assignee 与 deadline 只在原句明确点名真实人名或日期时填写，说话人代号（如 speaker_1、N_SPK8013）一律留空字符串。\n"
    "只输出一个合法 JSON，不要解释：{\"decision\":\"accept或reject\",\"todos\":[{\"content\":\"\",\"assignee\":\"\",\"deadline\":\"\"}]}；reject 时 todos 为 []。"
)
# v3（仅依据 prompt_dev_v1 的错误分析）：content 以句号结尾、时间状语并入 content、负责人与截止时间一律留空；
# 约束判定对齐银标口径——表达"应当/不应当"的规范性否定即算约束，不要求针对具体方案。
TODO_SYSTEM_V3 = TODO_SYSTEM_V2.split("accept 时每个独立行动")[0] + (
    "accept 时每个独立行动写一条：content 是不超过 20 字、以中文句号\"。\"结尾的祈使句，概括动作与对象，"
    "原句中的时间要求（如\"周五前\"）直接写进 content；assignee 和 deadline 始终为空字符串。"
    "连续的两个动作若围绕同一对象（如\"整理X并发到群里\"），合并为一条。\n"
    "只输出一个合法 JSON，不要解释：{\"decision\":\"accept或reject\",\"todos\":[{\"content\":\"\",\"assignee\":\"\",\"deadline\":\"\"}]}；reject 时 todos 为 []。"
)
CONSTRAINT_SYSTEM_V3 = (
    "你是会议约束审核器。输入是一句会议转写中的候选句及其预标注类型 kind，判断它是否表达了规范性限制。\n"
    "accept：句子表达\"应当/不应当、必须/不能、不要、除非、不超过、至少\"这类规范性要求或判断，"
    "包括对做法的原则性要求（\"不能因为X就认定Y\"\"恶搞并不能长期吸引粉丝\"这类否定某种做法的判断也算）。\n"
    "reject：否定词只描述个人状态或客观事实（\"我不能理解\"\"那个人不在\"）、纯提问、寒暄、"
    "对某事物重要性的肯定（\"这是最不能丢的\"）、以商量口吻提出的提议（\"……不要太长，十分钟怎么样？\"）。\n"
    "accept 时 constraint.kind 原样沿用输入的 kind，constraint.text 原样照抄输入的完整候选句，不改写、不截断。\n"
    "只输出一个合法 JSON，不要解释：{\"decision\":\"accept或reject\",\"constraint\":{\"kind\":\"\",\"text\":\"\"}}；reject 时 constraint 为 {}。"
)
CONSTRAINT_SYSTEM_V2 = (
    "你是会议约束审核器。输入是一句会议转写中的候选句及其预标注类型 kind，判断它是否表达了对方案或行为的明确限制。\n"
    "accept 条件：句中有明确的否定要求（不要/不能/不得/不应/禁止）、数量或预算阈值（不超过/至少/上限）、或范围/条件限定（除非/只在/仅限），"
    "且该限制针对要做的事，而不是在陈述事实、举例或反问。\n"
    "reject 条件：否定词只用于陈述事实或观点（\"这个不太好说\"\"我不能理解\"）、客套、疑问句、没有约束对象。\n"
    "accept 时 constraint.kind 原样沿用输入的 kind，constraint.text 原样照抄输入的完整候选句，不改写、不截断。\n"
    "只输出一个合法 JSON，不要解释：{\"decision\":\"accept或reject\",\"constraint\":{\"kind\":\"\",\"text\":\"\"}}；reject 时 constraint 为 {}。"
)


def prompt_for(record: dict[str, Any]) -> list[dict[str, str]]:
    if PROMPT_VERSION in ("v2", "v3") and record.get("unit_type") in ("todo", "constraint"):
        candidate = (record.get("extraction", {}).get("predicted") or [{}])[0]
        prompts = {("v2", "todo"): TODO_SYSTEM_V2, ("v2", "constraint"): CONSTRAINT_SYSTEM_V2,
                   ("v3", "todo"): TODO_SYSTEM_V3, ("v3", "constraint"): CONSTRAINT_SYSTEM_V3}
        system = prompts[(PROMPT_VERSION, record["unit_type"])]
        label = "候选待办" if record["unit_type"] == "todo" else "候选约束"
        return [{"role": "system", "content": system},
                {"role": "user", "content": f"{label}：{json.dumps(candidate, ensure_ascii=False)}"}]
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


def _first_json_object(text: str) -> str:
    """截取第一个配平的 {...}（容忍 Markdown 代码块和前后说明）；找不到则原样返回，交给 json_valid 判定。"""
    start = text.find("{")
    depth, in_str, escaped = 0, False, False
    for index in range(max(start, 0), len(text)) if start != -1 else ():
        char = text[index]
        if in_str:
            escaped = (char == "\\") and not escaped
            if char == '"' and not escaped:
                in_str = False
            continue
        if char == '"':
            in_str = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return text


def call_anthropic(api_base: str, api_key: str, model: str, messages: list[dict[str, str]], max_tokens: int, timeout: int) -> dict[str, Any]:
    """Anthropic Messages API；响应归一化为 chat/completions 形状，下游评分不变。

    Anthropic 没有 json_object 模式。实测中转层对 assistant 预填不生效（模型会重复 "{"），
    因此不预填，改为从文本中截取第一个完整 JSON 对象。
    """
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    turns = [m for m in messages if m["role"] != "system"]
    payload = {"model": model, "max_tokens": max_tokens, "temperature": 0, "system": system, "messages": turns}
    root = api_base.rstrip("/").removesuffix("/v1")
    request = urllib.request.Request(
        root + "/v1/messages",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')[:500]}") from exc
    latency = round((time.perf_counter() - started) * 1000, 2)
    text = _first_json_object("".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text"))
    usage = body.get("usage") or {}
    prompt, completion = int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
    finish = {"max_tokens": "length", "end_turn": "stop"}.get(body.get("stop_reason"), body.get("stop_reason"))
    return {"choices": [{"message": {"content": text}, "finish_reason": finish}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion},
            "latency_ms": latency}


def call(api_base: str, api_key: str, model: str, messages: list[dict[str, str]], max_tokens: int, timeout: int) -> dict[str, Any]:
    if os.environ.get("LLM_PROVIDER", "openai") == "anthropic":
        return call_anthropic(api_base, api_key, model, messages, max_tokens, timeout)
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
    parser.add_argument("--offset", type=int, default=0, help="跳过前 N 条，用于断点续跑")
    parser.add_argument("--record-id", help="只运行指定记录，用于最重样本预估")
    parser.add_argument("--max-tokens", type=int, default=768)
    parser.add_argument("--total-token-budget", type=int, default=10000)
    parser.add_argument("--per-record-token-budget", type=int, default=2000)
    parser.add_argument("--continue-on-invalid-json", action="store_true",
                        help="invalid_json 只记录不暂停（全量评测用，json_valid_rate 如实统计）")
    parser.add_argument("--proxy-overhead-tokens", type=int, default=0,
                        help="中转层每次固定注入的输入 token，从单条预算检查中扣除（总量仍如实累计）")
    args = parser.parse_args()
    api_key = os.environ.get("LLM_API_KEY", "")
    api_base = os.environ.get("LLM_API_BASE", "")
    model = os.environ.get("LLM_MODEL", "qwen3.7-max-2026-06-08")
    if not api_key or not api_base:
        raise ValueError("请通过 LLM_API_KEY 和 LLM_API_BASE 环境变量提供云端配置")
    all_records = load(args.dataset)
    records = ([record for record in all_records if record.get("id") == args.record_id]
               if args.record_id else all_records[args.offset:args.offset + args.count])
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
            if record_tokens - args.proxy_overhead_tokens > args.per_record_token_budget:
                anomaly.append("per_record_token_budget_exceeded")
            if finish_reason == "length":
                anomaly.append("finish_reason_length")
            if not json_valid:
                anomaly.append("invalid_json")
            results.append({"id": record["id"], "ok": not anomaly, "json_valid": json_valid, "output": parsed or content, "usage": usage, "finish_reason": finish_reason, "latency_ms": response.get("latency_ms"), "anomalies": anomaly})
            print(f"progress {len(results)}/{len(records)} done id={record['id']} json_valid={json_valid} total_tokens={record_tokens}", flush=True)
            blocking = [a for a in anomaly if not (args.continue_on_invalid_json and a == "invalid_json")]
            if blocking:
                pause_reason = ",".join(blocking)
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
        "provider": os.environ.get("LLM_PROVIDER", "openai"),
        "prompt_version": PROMPT_VERSION,
        "proxy_overhead_tokens": args.proxy_overhead_tokens,
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
