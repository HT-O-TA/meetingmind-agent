"""块级检索评测：把会议内连续发言按字符预算合并为块，再做 Hybrid/Reranker 检索。

与 run_retrieval_baselines.py 共用语料与去重逻辑，区别只在检索单元：
- 基线按单条发言（中位数约 36 字）检索，Top-5 只能覆盖 5 条发言；
- 生产链路的 SemanticChunker 按 50-300 字成块，本脚本用相同字符预算模拟。
指标同时报告块级命中与发言级证据召回，并按问题类型（主题 QA / 整体总结 QA）分层。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_retrieval_baselines import DEFAULT_TASKS, ROOT, build_corpus, read_jsonl  # noqa: E402

DEFAULT_OUTPUT = ROOT / "backend/evaluation/reports/meetingmind_real_v1_chunk_retrieval.json"


def make_chunks(docs, max_chars):
    """按原始顺序贪心合并连续发言，单块不超过 max_chars（单条超长发言独立成块）。"""
    chunks, current, size = [], [], 0
    for doc in docs:
        if current and size + len(doc["text"]) > max_chars:
            chunks.append(current)
            current, size = [], 0
        current.append(doc)
        size += len(doc["text"])
    if current:
        chunks.append(current)
    return [{"ids": [d["id"] for d in c], "text": "".join(d["text"] for d in c)} for c in chunks]


def norm(x):
    x = np.asarray(x, dtype=float)
    span = x.max() - x.min()
    return (x - x.min()) / span if span else np.zeros_like(x)


def score(order, chunks, relevant, k):
    """块级 MRR/nDCG（块相关度=块内 gold 发言占比）+ 发言级证据召回。"""
    gains = [len(relevant.intersection(chunks[i]["ids"])) / len(chunks[i]["ids"]) for i in order]
    hits = [pos for pos, g in enumerate(gains, 1) if g > 0]
    covered = set().union(*(set(chunks[i]["ids"]) for i in order[:k])) & relevant
    dcg = sum(g / math.log2(pos + 1) for pos, g in enumerate(gains[:k], 1))
    ideal = sorted((len(relevant.intersection(c["ids"])) / len(c["ids"]) for c in chunks), reverse=True)[:k]
    idcg = sum(g / math.log2(pos + 1) for pos, g in enumerate(ideal, 1))
    ceiling = set().union(*(set(c["ids"]) for c in sorted(
        chunks, key=lambda c: -len(relevant.intersection(c["ids"])))[:k])) & relevant
    return {
        "evidence_recall_at_k": len(covered) / len(relevant),
        "evidence_recall_ceiling_at_k": len(ceiling) / len(relevant),
        "chunk_hit_at_k": float(bool(hits and hits[0] <= k)),
        "chunk_precision_at_k": sum(1 for g in gains[:k] if g > 0) / k,
        "mrr": 1 / hits[0] if hits else 0.0,
        "ndcg_at_k": dcg / idcg if idcg else 0.0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sizes", type=int, nargs="+", default=[1, 150, 300])
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    tasks = [r for r in read_jsonl(args.tasks) if r.get("unit_type") == "qa"]
    corpus, aliases, _ = build_corpus()

    from sentence_transformers import SentenceTransformer
    from FlagEmbedding import FlagReranker

    embedder = SentenceTransformer(str(ROOT / "model/bge-m3"), device="cuda", local_files_only=True)
    reranker = FlagReranker(str(ROOT / "model/bge-reranker-v2-m3"), use_fp16=True, device="cuda")
    started = time.perf_counter()
    per_record = defaultdict(list)
    query_latency = defaultdict(list)
    cache = {}
    for size in args.sizes:
        for task in tasks:
            meeting = str(task["meeting_id"])
            key = (meeting, size)
            if key not in cache:
                chunks = make_chunks(corpus[meeting], size)
                texts = [c["text"] for c in chunks]
                vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 4)).fit(texts)
                dense = embedder.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
                cache[key] = (chunks, texts, vec, vec.transform(texts), np.asarray(dense))
            chunks, texts, vec, matrix, dense = cache[key]
            query = task["question"]
            relevant = {aliases.get(c, c) for c in task["retrieval"]["relevant_ids"]}
            t0 = time.perf_counter()
            bm = (matrix @ vec.transform([query]).T).toarray().ravel()
            dn = dense @ embedder.encode([query], normalize_embeddings=True)[0]
            hybrid = list(np.argsort(-(0.3 * norm(bm) + 0.7 * norm(dn))))
            t_hybrid = time.perf_counter() - t0
            cand = hybrid[: min(20, len(chunks))]
            rs = reranker.compute_score([[query, texts[i]] for i in cand])
            reranked = [i for _, i in sorted(zip(rs, cand), key=lambda x: -x[0])] + hybrid[len(cand):]
            query_latency[f"{size}:hybrid"].append(t_hybrid * 1000)
            query_latency[f"{size}:hybrid_reranker"].append((time.perf_counter() - t0) * 1000)
            kind = "summary" if "overall_summary" in task["source_unit_id"] else "topic"
            for name, order in (("hybrid", hybrid), ("hybrid_reranker", reranked)):
                per_record[f"{size}:{name}"].append({"task_id": task["id"], "kind": kind,
                    "chunk_count": len(chunks), **score(order, chunks, relevant, args.k)})
        print(f"size={size} done", flush=True)

    metric_keys = [k for k in next(iter(per_record.values()))[0] if k not in ("task_id", "kind", "chunk_count")]

    def avg(rows):
        return {k: round(mean(r[k] for r in rows), 4) for k in metric_keys}

    metrics = {}
    for name, rows in per_record.items():
        lat = sorted(query_latency[name])
        metrics[name] = {"all": avg(rows),
            "topic": avg([r for r in rows if r["kind"] == "topic"]),
            "summary": avg([r for r in rows if r["kind"] == "summary"]),
            "chunk_count_median": sorted(r["chunk_count"] for r in rows)[len(rows) // 2],
            "query_latency_ms": {"p50": round(lat[len(lat) // 2], 1), "p95": round(lat[int(0.95 * (len(lat) - 1))], 1)}}
    payload = {
        "schema_version": "evaluation.chunk_retrieval.v1",
        "dataset": str(args.tasks.relative_to(ROOT)).replace("\\", "/"),
        "task_count": len(tasks), "k": args.k, "chunk_sizes_chars": args.sizes,
        "retrieval_scope": "within_meeting_oracle",
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "metrics": metrics, "per_record": per_record,
        "definitions": {
            "size=1": "每条发言单独成块，等价于 run_retrieval_baselines.py 的发言级检索",
            "evidence_recall_at_k": "Top-k 块覆盖的 gold 发言数 / gold 发言总数",
            "evidence_recall_ceiling_at_k": "同一分块下任意选 k 块能达到的最大证据召回（按块内 gold 数贪心取前 k）",
            "chunk_hit_at_k": "Top-k 中至少一块含 gold 发言",
            "mrr/ndcg_at_k": "块级；nDCG 的块增益=块内 gold 发言占比",
        },
        "limitations": [
            "会议内检索（已知 meeting_id），不是全库检索。",
            "分块为按字符预算的连续合并，模拟生产 SemanticChunker 的 50-300 字预算，未复用其说话人切分。",
            "整体总结类问题的 gold 覆盖整场会议（中位 27 条发言），Top-k 检索的证据召回有结构性上限，见 ceiling 字段。",
        ],
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
