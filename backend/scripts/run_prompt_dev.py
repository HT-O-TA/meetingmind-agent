"""在 prompt_dev_v1 开发集上比较 prompt 版本（不触碰冻结评测集）。

复用 run_cloud_eval_canary 的 prompt_for / call 与 score_cloud_eval 的 f1，保证调参口径与正式评测一致。
用法：EVAL_PROMPT_VERSION=v2 python run_prompt_dev.py --output ...
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_cloud_eval_canary as canary  # noqa: E402
from score_cloud_eval import f1  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]


def as_record(row):
    return {"id": row["id"], "unit_type": row["unit_type"], "extraction": {"predicted": [row["candidate"]]}}


def score(row, output):
    output = output if isinstance(output, dict) else {}
    accepted = output.get("decision") == "accept"
    if row["unit_type"] == "todo":
        predicted = output.get("todos", []) if accepted else []
    else:
        predicted = [output.get("constraint")] if accepted and output.get("constraint") else []
    return {**f1(row["expected"], predicted), "decision_ok": float(bool(row["expected"]) == accepted)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=BACKEND / "evaluation/datasets/prompt_dev_v1.jsonl")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    rows = [json.loads(l) for l in args.dataset.read_text(encoding="utf-8").splitlines() if l.strip()]
    base, key, model = os.environ["LLM_API_BASE"], os.environ["LLM_API_KEY"], os.environ["LLM_MODEL"]

    def run(row):
        try:
            resp = canary.call(base, key, model, canary.prompt_for(as_record(row)), 384, 90)
            text = resp["choices"][0]["message"]["content"]
            try:
                out = json.loads(text)
            except (TypeError, json.JSONDecodeError):
                out = text
            return {"id": row["id"], "unit_type": row["unit_type"], "source": row["source"], "output": out,
                    "latency_ms": resp.get("latency_ms"), "usage": resp.get("usage"), **score(row, out)}
        except Exception as exc:  # 单条失败计 0 分，不中断
            return {"id": row["id"], "unit_type": row["unit_type"], "source": row["source"], "error": str(exc)[:300],
                    "f1": 0.0, "precision": 0.0, "recall": 0.0, "decision_ok": 0.0}

    with ThreadPoolExecutor(args.workers) as pool:
        results = list(pool.map(run, rows))

    def agg(sel):
        return {"n": len(sel), "f1": round(mean(r["f1"] for r in sel), 4),
                "decision_acc": round(mean(r["decision_ok"] for r in sel), 4)} if sel else None

    summary = {"prompt_version": canary.PROMPT_VERSION, "model": model, "errors": sum("error" in r for r in results)}
    for t in ("todo", "constraint"):
        sel = [r for r in results if r["unit_type"] == t]
        summary[t] = agg(sel)
        summary[f"{t}_positive"] = agg([r for r, row in zip(results, rows) if row["unit_type"] == t and row["expected"]])
        summary[f"{t}_negative"] = agg([r for r, row in zip(results, rows) if row["unit_type"] == t and not row["expected"]])
    args.output.write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
