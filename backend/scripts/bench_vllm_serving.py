"""本地 vLLM 服务压测：对 OpenAI 兼容 /v1/chat/completions 做流式请求，记录 TTFT、端到端延迟、吞吐。

- 负载：真实会议 QA 的问题 + 生成时给出的片段（meetingmind_real_v1_evaluation.jsonl），不是随机文本。
- 每个并发档位跑固定条数，百分位用 nearest-rank（与 run_tool_eval.py 一致）。
- 只打本机端口，不涉及外部服务与密钥。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1]
DATA = BACKEND / "evaluation/datasets/meetingmind_real_v1_evaluation.jsonl"


def pct(values, q):
    values = sorted(values)
    return round(values[max(0, math.ceil(q / 100 * len(values)) - 1)], 1) if values else None


def build_prompts(limit_chars: int) -> list[str]:
    rows = [json.loads(x) for x in DATA.read_text(encoding="utf-8").splitlines() if x.strip()]
    prompts = []
    for r in rows:
        if r.get("unit_type") != "qa":
            continue
        ctx = "\n".join(str(t)[:400] for t in r["generation"].get("contexts", [])[:6])[:limit_chars]
        prompts.append(f"只依据会议片段，用两句话回答。\n问题：{r['question']}\n片段：\n{ctx}")
    return prompts


async def one(http, model, prompt, max_tokens):
    body = {"model": model, "stream": True, "max_tokens": max_tokens, "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
            "stream_options": {"include_usage": True},
            "chat_template_kwargs": {"enable_thinking": False}}
    t0 = time.perf_counter()
    ttft, out_tokens = None, 0
    async with http.stream("POST", "/v1/chat/completions", json=body) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line.startswith("data: ") or line.endswith("[DONE]"):
                continue
            chunk = json.loads(line[6:])
            if ttft is None and chunk.get("choices") and chunk["choices"][0].get("delta", {}).get("content"):
                ttft = time.perf_counter() - t0
            if chunk.get("usage"):
                out_tokens = chunk["usage"].get("completion_tokens", 0)
    return {"ttft_ms": (ttft or 0) * 1000, "e2e_ms": (time.perf_counter() - t0) * 1000, "out_tokens": out_tokens}


async def level(http, model, prompts, concurrency, n, max_tokens):
    sem = asyncio.Semaphore(concurrency)
    jobs = [prompts[i % len(prompts)] for i in range(n)]

    async def run(p):
        async with sem:
            return await one(http, model, p, max_tokens)

    t0 = time.perf_counter()
    rows = await asyncio.gather(*(run(p) for p in jobs), return_exceptions=True)
    wall = time.perf_counter() - t0
    ok = [r for r in rows if isinstance(r, dict)]
    return {"concurrency": concurrency, "requests": n, "ok": len(ok),
            "ttft_p50_ms": pct([r["ttft_ms"] for r in ok], 50), "ttft_p95_ms": pct([r["ttft_ms"] for r in ok], 95),
            "e2e_p50_ms": pct([r["e2e_ms"] for r in ok], 50), "e2e_p95_ms": pct([r["e2e_ms"] for r in ok], 95),
            "output_tok_per_s": round(sum(r["out_tokens"] for r in ok) / wall, 1),
            "req_per_s": round(len(ok) / wall, 2), "wall_s": round(wall, 1)}


async def main_async(args):
    prompts = build_prompts(args.context_chars)
    async with httpx.AsyncClient(base_url=args.base_url, timeout=300.0) as http:
        await one(http, args.model, prompts[0], 8)  # 预热
        results = [await level(http, args.model, prompts, c, args.requests, args.max_tokens) for c in args.concurrency]
    report = {"schema_version": "vllm-bench.v1", "model": args.model, "server_args": args.server_args,
              "max_tokens": args.max_tokens, "context_chars": args.context_chars, "results": results}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in results:
        print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--model", default="qwen3-1.7b")
    ap.add_argument("--concurrency", type=int, nargs="+", default=[1, 4, 8, 16, 32])
    ap.add_argument("--requests", type=int, default=64)
    ap.add_argument("--max-tokens", type=int, default=128)
    ap.add_argument("--context-chars", type=int, default=1600)
    ap.add_argument("--server-args", default="")
    ap.add_argument("--output", type=Path, required=True)
    asyncio.run(main_async(ap.parse_args()))