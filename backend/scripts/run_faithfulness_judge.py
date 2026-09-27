"""QA 生成忠实度评测：逐条论断判断是否被"生成时实际给出的会议片段"支持。

- 同一请求内盲评三份答案（标签随机打乱，映射记录在报告里）：
  baseline = qwen3.7-max 的答案（cloud_100），current = Opus 5.5 的答案（opus55_v2_100），
  probe = current 末尾拼接一句"其他会议的参考答案"——已知不忠实，用来测评判器的灵敏度。
- faithfulness = 被支持论断数 / 论断总数（按条目平均）；probe_detect = probe 中注入句被判为不支持的比例。
- 评判器经 CC-Switch 中转（Anthropic /v1/messages），模型由 LLM_MODEL 指定。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path
from statistics import mean

import httpx

BACKEND = Path(__file__).resolve().parents[1]
DATA = BACKEND / "evaluation/datasets/meetingmind_real_v1_evaluation.jsonl"
REPORTS = BACKEND / "evaluation/reports"
RUNS = {"baseline": REPORTS / "meetingmind_real_v1_cloud_100.json",
        "current": REPORTS / "meetingmind_real_v1_opus55_v2_100.json"}

SYSTEM = (
    "你是严格的事实核查员。只依据给出的会议片段判断，不使用常识补全。"
    "对每份答案：把它拆成原子论断（每条一个可核查的陈述），逐条标注 supported（片段中有明确依据）"
    "或 unsupported（片段中没有依据、与片段矛盾或属于臆测）。"
    "只输出一个合法 JSON，不要解释："
    '{"<答案标签>":[{"claim":"论断","label":"supported|unsupported"}],...}'
)


def contexts_of(record: dict) -> str:
    # 与 run_cloud_eval_canary.py 生成 QA 时的上下文拼法保持一致
    texts = record["generation"].get("contexts", [])[:6]
    ids = record.get("retrieval", {}).get("retrieved_ids", [])
    blocks = [f"[{ids[i] if i < len(ids) else f'context-{i + 1}'}] {str(t)[:800]}" for i, t in enumerate(texts)]
    return "\n".join(blocks)[:4800]


def first_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


async def judge_one(http, model, record, answers, rng, max_tokens):
    keys = list(answers)
    rng.shuffle(keys)
    labels = {k: f"答案{chr(65 + i)}" for i, k in enumerate(keys)}
    body_answers = "\n".join(f"{labels[k]}：{answers[k]}" for k in keys)
    user = f"问题：{record['question']}\n会议片段：\n{contexts_of(record)}\n\n待核查答案：\n{body_answers}"
    payload = {"model": model, "max_tokens": max_tokens, "temperature": 0,
               "system": SYSTEM, "messages": [{"role": "user", "content": user}]}
    t0 = time.perf_counter()
    item = {"id": record["id"], "labels": labels, "ok": False}
    try:
        resp = await http.post("/v1/messages", json=payload)
        item["status"] = resp.status_code
        data = resp.json()
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        parsed = first_json(text)
        item["claims"] = {k: parsed.get(labels[k], []) for k in keys}
        item["usage"] = data.get("usage", {})
        item["ok"] = all(isinstance(item["claims"][k], list) and item["claims"][k] for k in keys)
    except Exception as exc:  # 记录失败，不重试（节省额度）
        item["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    item["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return item

def score(claims: list) -> float:
    return sum(c.get("label") == "supported" for c in claims) / len(claims) if claims else 0.0


def unsupported(claims: list) -> int:
    return sum(c.get("label") != "supported" for c in claims)


async def main_async(args):
    records = [json.loads(x) for x in DATA.read_text(encoding="utf-8").splitlines() if x.strip()]
    records = [r for r in records if r.get("unit_type") == "qa"]
    runs = {name: {r["id"]: r for r in json.loads(p.read_text(encoding="utf-8"))["results"]} for name, p in RUNS.items()}
    rng = random.Random(args.seed)
    # probe 注入句：取另一场会议的人工参考答案首句，保证与本场片段无关
    gold_first = {r["meeting_id"]: str(r["generation"].get("answer", "")).split("。")[0] + "。" for r in records}
    jobs = []
    for record in records[: args.limit]:
        answers = {k: str((runs[k].get(record["id"], {}).get("output") or {}).get("answer", "")).strip() for k in RUNS}
        if not all(answers.values()):
            continue
        other = rng.choice([m for m in gold_first if m != record["meeting_id"]])
        answers["probe"] = answers["current"] + gold_first[other]
        jobs.append((record, answers))
    model = os.environ["LLM_MODEL"]
    root = os.environ["LLM_API_BASE"].rstrip("/").removesuffix("/v1")
    headers = {"x-api-key": os.environ["LLM_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json"}
    sem = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient(base_url=root, headers=headers, timeout=180.0) as http:
        async def run(job):
            async with sem:
                return await judge_one(http, model, job[0], job[1], random.Random(f"{args.seed}:{job[0]['id']}"), args.max_tokens)
        items = await asyncio.gather(*(run(j) for j in jobs))
    ok = [i for i in items if i["ok"]]
    metrics = {f"faithfulness.{k}": round(mean(score(i["claims"][k]) for i in ok), 4) for k in ("baseline", "current", "probe")} if ok else {}
    if ok:
        metrics["probe_detect_rate"] = round(mean(unsupported(i["claims"]["probe"]) > unsupported(i["claims"]["current"]) for i in ok), 4)
        for k in ("baseline", "current"):
            metrics[f"fully_faithful_rate.{k}"] = round(mean(unsupported(i["claims"][k]) == 0 for i in ok), 4)
    report = {"schema_version": "faithfulness-judge.v1", "judge_model": model, "seed": args.seed,
              "runs": {k: str(p.relative_to(BACKEND)) for k, p in RUNS.items()},
              "count": len(jobs), "ok_count": len(ok), "metrics": metrics,
              "input_tokens": sum(i.get("usage", {}).get("input_tokens", 0) for i in items),
              "output_tokens": sum(i.get("usage", {}).get("output_tokens", 0) for i in items),
              "limitations": ["评判器与 current 答案同为 Opus 系模型，可能偏袒自身输出；用 probe 注入句校验灵敏度",
                              "上下文为生成时实际给出的片段，不代表整场会议", "40 条 QA 来自 20 场 VCSUM 会议"],
              "per_record": items}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("count", "ok_count", "metrics", "input_tokens", "output_tokens")}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=REPORTS / "faithfulness_qa40.json")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--seed", type=int, default=20260927)
    asyncio.run(main_async(parser.parse_args()))
