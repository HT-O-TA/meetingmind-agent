"""全库检索评测：不给 meeting_id，把所有会议的 300 字块放进同一个池子里检索。

与 run_chunk_retrieval.py（会议内检索，已知 meeting_id）同分块、同混合权重、同 k，
只改检索范围，用来回答"不告诉系统是哪场会议时还能不能找到证据"。
- meeting_hit@k：Top-k 中至少一块来自正确会议
- evidence_recall@k：Top-k 块覆盖的 gold 发言数 / gold 发言总数（与会议内口径相同）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_chunk_retrieval import make_chunks, norm  # noqa: E402
from run_retrieval_baselines import DEFAULT_TASKS, ROOT, build_corpus, read_jsonl  # noqa: E402

DEFAULT_OUTPUT = ROOT / "backend/evaluation/reports/meetingmind_real_v1_corpus_retrieval.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--size", type=int, default=300)
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    tasks = [r for r in read_jsonl(args.tasks) if r.get("unit_type") == "qa"]
    corpus, aliases, _ = build_corpus()

    from sentence_transformers import SentenceTransformer
    from FlagEmbedding import FlagReranker

    embedder = SentenceTransformer(str(ROOT / "model/bge-m3"), device="cuda", local_files_only=True)
    reranker = FlagReranker(str(ROOT / "model/bge-reranker-v2-m3"), use_fp16=True, device="cuda")
    chunks, owner = [], []
    for meeting, docs in corpus.items():
        for c in make_chunks(docs, args.size):
            chunks.append(c)
            owner.append(str(meeting))
    texts = [c["text"] for c in chunks]
    vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 4)).fit(texts)
    matrix = vec.transform(texts)
    dense = np.asarray(embedder.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False))

    rows = defaultdict(list)
    started = time.perf_counter()
    for task in tasks:
        query, meeting = task["question"], str(task["meeting_id"])
        relevant = {aliases.get(c, c) for c in task["retrieval"]["relevant_ids"]}
        bm = (matrix @ vec.transform([query]).T).toarray().ravel()
        dn = dense @ embedder.encode([query], normalize_embeddings=True)[0]
        hybrid = list(np.argsort(-(0.3 * norm(bm) + 0.7 * norm(dn))))
        cand = hybrid[:20]
        rs = reranker.compute_score([[query, texts[i]] for i in cand])
        reranked = [i for _, i in sorted(zip(rs, cand), key=lambda x: -x[0])]
        kind = "summary" if "overall_summary" in task["source_unit_id"] else "topic"
        for name, order in (("hybrid", hybrid), ("hybrid_reranker", reranked)):
            top = order[: args.k]
            covered = set().union(*(set(chunks[i]["ids"]) for i in top)) & relevant
            rows[name].append({"task_id": task["id"], "kind": kind,
                               "meeting_hit_at_k": float(any(owner[i] == meeting for i in top)),
                               "top1_meeting_ok": float(owner[top[0]] == meeting),
                               "evidence_recall_at_k": len(covered) / len(relevant)})

    def avg(rs):
        return {m: round(mean(r[m] for r in rs), 4) for m in ("meeting_hit_at_k", "top1_meeting_ok", "evidence_recall_at_k")}

    metrics = {name: {"all": avg(rs), "topic": avg([r for r in rs if r["kind"] == "topic"]),
                      "summary": avg([r for r in rs if r["kind"] == "summary"])} for name, rs in rows.items()}
    payload = {"schema_version": "evaluation.corpus_retrieval.v1", "retrieval_scope": "full_corpus",
               "task_count": len(tasks), "meeting_count": len(corpus), "chunk_count": len(chunks),
               "chunk_size_chars": args.size, "k": args.k, "elapsed_seconds": round(time.perf_counter() - started, 2),
               "metrics": metrics, "per_record": rows,
               "limitations": ["与会议内口径同分块、同权重，只改检索范围。",
                               "20 条是同一问题'这场会议主要讲了什么'，全库下天然无法定位会议，单列 summary。"]}
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("meeting_count", "chunk_count")}, ensure_ascii=False))
    print(json.dumps(metrics, ensure_ascii=False))


if __name__ == "__main__":
    main()