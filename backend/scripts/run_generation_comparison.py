"""用同一 Qwen Prompt 比较四种本地检索上下文的端到端 QA 表现。"""
from __future__ import annotations

import argparse
import json
import time
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from openai import OpenAI

from app.evaluation.offline_metrics import lexical_overlap


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--retrieval", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--total-token-budget", type=int, default=50000)
    parser.add_argument("--limit-per-method", type=int, default=10)
    args = parser.parse_args()
    tasks = [json.loads(x) for x in args.tasks.read_text(encoding="utf-8").splitlines() if x.strip()]
    tasks = {x["id"]: x for x in tasks if x.get("unit_type") == "qa"}
    retrieval = json.loads(args.retrieval.read_text(encoding="utf-8"))["per_record"]
    retrieval = {name: rows[: args.limit_per_method] for name, rows in retrieval.items()}
    import os
    client = OpenAI(
        api_key=os.environ["LLM_API_KEY"],
        base_url=os.environ["LLM_API_BASE"],
        timeout=60.0,
        max_retries=0,
    )
    results = []
    total_tokens = 0
    started = time.perf_counter()
    for method, rows in retrieval.items():
        for row in rows:
            task = tasks[row["task_id"]]
            # top_ids 与 top_texts 必须严格一一对应；只把实际提供给模型的
            # 5 段上下文暴露给引用解析，避免模型引用不存在的第 6~20 段。
            top_ids = row.get("top_ids", [])[:5]
            contexts = [f"[{i + 1}] {text}" for i, text in enumerate(row.get("top_texts", [])[:5])]
            prompt = (
                "你是会议问答评测器。只能依据给出的会议片段回答，不要补充常识。"
                "输出严格 JSON：{answer:string,citation_indexes:[整数]}。"
                "如果片段不足，answer 写‘无法从会议片段确定’，citation_indexes 写空数组。\n"
                f"问题：{task['question']}\n会议片段：\n" + "\n".join(contexts)
            )
            t0 = time.perf_counter()
            item = {"method": method, "task_id": row["task_id"], "ok": False}
            try:
                response = client.chat.completions.create(
                    model=os.environ["LLM_MODEL"],
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    max_tokens=args.max_tokens,
                    response_format={"type": "json_object"},
                    extra_body={"enable_thinking": False},
                )
                text = response.choices[0].message.content or "{}"
                output = json.loads(text)
                usage = response.usage.model_dump() if response.usage else {}
                total_tokens += int(usage.get("total_tokens", 0) or 0)
                gold_ids = set(task.get("retrieval", {}).get("relevant_ids", []))
                cited_indexes = output.get("citation_indexes", [])
                cited_ids = {
                    top_ids[i - 1]
                    for i in cited_indexes
                    if isinstance(i, int) and 1 <= i <= len(top_ids)
                }
                item.update({
                    "ok": True,
                    "json_valid": True,
                    "answer": output.get("answer", ""),
                    "citation_ids": sorted(cited_ids),
                    "citation_precision": len(cited_ids & gold_ids) / len(cited_ids) if cited_ids else 0.0,
                    "citation_recall": len(cited_ids & gold_ids) / len(gold_ids) if gold_ids else 1.0,
                    "answer_lexical_overlap": lexical_overlap(output.get("answer", ""), task.get("generation", {}).get("answer", "")),
                    "usage": usage,
                    "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
                })
            except Exception as exc:
                item.update({"error": str(exc), "json_valid": False, "latency_ms": round((time.perf_counter() - t0) * 1000, 2)})
            results.append(item)
            total_expected = sum(len(rows) for rows in retrieval.values())
            print(f"[{len(results)}/{total_expected}] {method} {row['task_id']} tokens={total_tokens}", flush=True)
            if total_tokens > args.total_token_budget:
                raise RuntimeError(f"token budget exceeded: {total_tokens}")
    metrics = {}
    for method in retrieval:
        rows = [x for x in results if x["method"] == method and x.get("ok")]
        metrics[method] = {
            "count": len(rows),
            "json_valid_rate": len(rows) / args.limit_per_method,
            "citation_precision": mean(x["citation_precision"] for x in rows) if rows else 0.0,
            "citation_recall": mean(x["citation_recall"] for x in rows) if rows else 0.0,
            "answer_lexical_overlap": mean(x["answer_lexical_overlap"] for x in rows) if rows else 0.0,
            "p50_latency_ms": sorted(x["latency_ms"] for x in rows)[len(rows) // 2] if rows else None,
            "mean_tokens": mean(x.get("usage", {}).get("total_tokens", 0) for x in rows) if rows else 0.0,
        }
    output = {
        "schema_version": "evaluation.generation_comparison.v1",
        "task_count_per_method": args.limit_per_method,
        "retrieval_methods": list(retrieval),
        "total_tokens": total_tokens,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "metrics": metrics,
        "results": results,
        "limitations": ["答案词面重合度只是自动代理指标；引用 Recall 受细粒度多证据标注影响。"],
    }
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
