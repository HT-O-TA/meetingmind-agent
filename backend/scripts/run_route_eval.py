"""路由评测：在 route_eval_v1 上测 IntentRouter 的任务类型/工作流准确率与路由延迟。

--classifier local  使用本地 Qwen3 复杂度分类器（生产默认）
--classifier rules  不注入分类器，走 IntentRouter 规则兜底
--semantic          追加本地 bge-m3 语义任务识别（semantic_task_classifier）
云 LLM 语义多任务检测器统一不注入，各配置只差上述两个开关。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
DEFAULT_DATASET = BACKEND / "evaluation/datasets/route_eval_v1.jsonl"


async def run(classifier_mode: str, dataset: Path, semantic: bool = False):
    from app.services.intent_router import IntentRouter

    classifier = None
    if classifier_mode == "local":
        from app.services.complexity_classifier import get_complexity_classifier
        classifier = await get_complexity_classifier()
        await classifier.initialize()
    semantic_classifier = None
    if semantic:
        from app.services.semantic_task_classifier import get_semantic_task_classifier
        semantic_classifier = get_semantic_task_classifier()
        if semantic_classifier is None:
            raise RuntimeError("语义任务识别模型不可用")
    router = IntentRouter(
        complexity_classifier=classifier,
        multi_task_detector=None,
        semantic_task_classifier=semantic_classifier,
    )
    rows = [json.loads(x) for x in dataset.read_text(encoding="utf-8").splitlines() if x.strip()]
    results = []
    for row in rows:
        t0 = time.perf_counter()
        decision = await router.route(row["question"])
        latency = (time.perf_counter() - t0) * 1000
        results.append({
            "id": row["id"], "group": row["group"],
            "task_ok": decision.task_type.value == row["task_type"],
            "workflow_ok": decision.workflow_type.value == row["workflow_type"],
            "predicted": f"{decision.workflow_type.value}/{decision.task_type.value}",
            "expected": f"{row['workflow_type']}/{row['task_type']}",
            "latency_ms": round(latency, 1),
        })
    return results


def summarize(results):
    by_group = defaultdict(list)
    for r in results:
        by_group[r["group"]].append(r)
    lat = sorted(r["latency_ms"] for r in results)
    return {
        "count": len(results),
        "task_accuracy": round(sum(r["task_ok"] for r in results) / len(results), 4),
        "workflow_accuracy": round(sum(r["workflow_ok"] for r in results) / len(results), 4),
        "by_group": {g: {"n": len(v), "workflow_accuracy": round(sum(r["workflow_ok"] for r in v) / len(v), 3)}
                     for g, v in by_group.items()},
        "latency_ms": {"p50": lat[len(lat) // 2], "p95": lat[int(0.95 * (len(lat) - 1))], "max": lat[-1]},
        "confusions": Counter(f"{r['expected']} -> {r['predicted']}" for r in results if not r["workflow_ok"]).most_common(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--classifier", choices=["local", "rules"], default="rules")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--semantic", action="store_true", help="启用 bge-m3 语义任务识别")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    results = asyncio.run(run(args.classifier, args.dataset, args.semantic))
    summary = {"classifier": args.classifier, "semantic": args.semantic,
               "dataset": args.dataset.name, **summarize(results)}
    if args.output:
        args.output.write_text(json.dumps({**summary, "per_record": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
