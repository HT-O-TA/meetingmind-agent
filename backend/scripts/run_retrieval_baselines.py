"""在完整会议原文上运行 BM25、Dense、Hybrid、Hybrid+Reranker 对比。"""
from __future__ import annotations

import argparse
import json
import math
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
DEFAULT_TASKS = ROOT / "backend/evaluation/datasets/meetingmind_real_v1_evaluation.jsonl"
DEFAULT_OUTPUT = ROOT / "backend/evaluation/reports/meetingmind_real_v1_retrieval_baselines.json"


def read_jsonl(path: Path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def add(pool, meeting, cid, text):
    text = " ".join(str(text).split())
    if text:
        pool[meeting].append({"id": cid, "text": text})


def deduplicate_by_text(pool):
    """按会议内规范化文本去重，并保留被合并的 citation ID 别名。

    会议转写常会把同一句话同时出现在 overall/short 视图中。只按
    citation_id 去重会让同一段内容占据多个 Top-K 位置，虚高检索结果。
    """
    result = {}
    aliases = {}
    duplicate_count = 0
    for meeting, docs in pool.items():
        seen = {}
        unique = []
        for doc in docs:
            key = " ".join(doc["text"].split()).casefold()
            if key in seen:
                aliases[doc["id"]] = seen[key]
                duplicate_count += 1
                continue
            seen[key] = doc["id"]
            aliases[doc["id"]] = doc["id"]
            unique.append(doc)
        result[meeting] = unique
    return result, aliases, duplicate_count


def build_corpus():
    pool = defaultdict(list)
    base = DATA / "VCSUM" / "vcsum_data"
    contexts = {str(r["av_num"]): r for r in read_jsonl(base / "overall_context.txt")}
    long_rows = read_jsonl(base / "long_test.txt")
    av_to_id = {str(r["av_num"]): str(r["id"]) for r in long_rows}
    for av, context in contexts.items():
        meeting = av_to_id.get(str(av))
        if meeting is None:
            continue
        for si, segment in enumerate(context.get("context", [])):
            for ui, text in enumerate(segment):
                add(pool, meeting, f"vcsum:{meeting}:seg:{si}:utt:{ui}", text)
    for row in read_jsonl(base / "short_test.txt"):
        meeting = str(row["id"]).split("_", 1)[0]
        for ui, text in enumerate(row.get("context", [])):
            if isinstance(text, list):
                for inner, value in enumerate(text):
                    add(pool, meeting, f"vcsum:{row['id']}:utt:{ui + inner}", value)
            else:
                add(pool, meeting, f"vcsum:{row['id']}:utt:{ui}", text)
    for row in read_jsonl(ROOT / "backend/evaluation/datasets/meetingmind_real_v1_sources.jsonl"):
        meeting = str(row["meeting_id"])
        for item in row.get("utterances", []):
            add(pool, meeting, item["citation_id"], item.get("text", ""))
    # 先按 ID 去重，再按文本去重并保持原始顺序。
    by_id = {k: list({x["id"]: x for x in v}.values()) for k, v in pool.items()}
    return deduplicate_by_text(by_id)


def ranks(ids, relevant):
    relevant = set(relevant)
    hits = [i for i, cid in enumerate(ids, 1) if cid in relevant]
    return hits


def score(ids, relevant, k=5):
    hits = ranks(ids, relevant)
    top = [x for x in hits if x <= k]
    recall = len(top) / len(set(relevant)) if relevant else 0.0
    precision = len(top) / k
    rr = 1 / hits[0] if hits else 0.0
    dcg = sum(1 / math.log2(pos + 1) for pos in top)
    ideal = sum(1 / math.log2(pos + 1) for pos in range(1, min(k, len(set(relevant))) + 1))
    return {"recall_at_5": recall, "precision_at_5": precision, "mrr": rr, "ndcg_at_5": dcg / ideal if ideal else 0.0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-qa", type=int, default=40)
    args = parser.parse_args()
    tasks = [r for r in read_jsonl(args.tasks) if r.get("unit_type") == "qa"][: args.max_qa]
    corpus, aliases, duplicate_count = build_corpus()
    missing = []
    for task in tasks:
        pool = corpus.get(str(task["meeting_id"]), [])
        relevant = {aliases.get(cid, cid) for cid in task.get("retrieval", {}).get("relevant_ids", [])}
        if not pool or not relevant.intersection({x["id"] for x in pool}):
            missing.append(task["id"])
    if missing:
        raise RuntimeError(f"无法把 {len(missing)} 条 QA 映射到完整会议语料，示例: {missing[:5]}")

    from sentence_transformers import SentenceTransformer
    from FlagEmbedding import FlagReranker

    embedder = SentenceTransformer(str(ROOT / "model/bge-m3"), device="cuda", local_files_only=True)
    reranker = FlagReranker(str(ROOT / "model/bge-reranker-v2-m3"), use_fp16=True, device="cuda")
    all_results = defaultdict(list)
    prepared = {}
    total_start = time.perf_counter()

    for task in tasks:
        meeting = str(task["meeting_id"])
        docs = corpus[meeting]
        query = task["question"]
        if meeting not in prepared:
            texts = [x["text"] for x in docs]
            vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 4), min_df=1)
            matrix = vectorizer.fit_transform(texts)
            dense = embedder.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
            prepared[meeting] = (texts, vectorizer, matrix, dense)
        texts, vectorizer, matrix, dense = prepared[meeting]
        qv = vectorizer.transform([query])
        bm25_scores = (matrix @ qv.T).toarray().ravel()
        q_dense = embedder.encode([query], normalize_embeddings=True)[0]
        dense_scores = np.asarray(dense) @ np.asarray(q_dense)
        bm_order = np.argsort(-bm25_scores)
        dense_order = np.argsort(-dense_scores)
        # 分数归一化后线性融合。
        def norm(x):
            x = np.asarray(x, dtype=float)
            span = x.max() - x.min()
            return (x - x.min()) / span if span else np.zeros_like(x)
        hybrid_scores = 0.3 * norm(bm25_scores) + 0.7 * norm(dense_scores)
        hybrid_order = np.argsort(-hybrid_scores)
        rerank_candidates = hybrid_order[: min(20, len(docs))]
        rerank_scores = reranker.compute_score([[query, texts[i]] for i in rerank_candidates])
        rerank_order = [i for _, i in sorted(zip(rerank_scores, rerank_candidates), reverse=True)]
        orders = {
            "bm25": bm_order,
            "dense": dense_order,
            "hybrid": hybrid_order,
            "hybrid_reranker": np.array(rerank_order),
        }
        # 相关证据可能是被文本去重合并掉的旧 citation ID，统一映射到保留 ID。
        relevant = [aliases.get(cid, cid) for cid in task["retrieval"].get("relevant_ids", [])]
        for name, order in orders.items():
            ids = [docs[int(i)]["id"] for i in order[:20]]
            all_results[name].append({
                "task_id": task["id"],
                "meeting_id": meeting,
                "top_ids": ids,
                "top_texts": [docs[int(i)]["text"] for i in order[:5]],
                **score(ids, relevant),
            })
        print(f"[{len(all_results['bm25'])}/{len(tasks)}] {task['id']}", flush=True)

    def avg(rows):
        return {k: mean([r[k] for r in rows]) for k in ("recall_at_5", "precision_at_5", "mrr", "ndcg_at_5")}

    payload = {
        "schema_version": "evaluation.retrieval_baselines.v1",
        "dataset": str(args.tasks.relative_to(ROOT)).replace("\\", "/"),
        "task_count": len(tasks),
        "meeting_count": len({r["meeting_id"] for r in tasks}),
        "corpus_meeting_count": len(corpus),
        "retrieval_scope": "within_meeting_oracle",
        "text_deduplicated_documents": duplicate_count,
        "embedding_model": "local://model/bge-m3",
        "reranker_model": "local://model/bge-reranker-v2-m3",
        "elapsed_seconds": round(time.perf_counter() - total_start, 3),
        "metrics": {name: avg(rows) for name, rows in all_results.items()},
        "per_record": {name: rows for name, rows in all_results.items()},
        "limitations": [
            "本轮是已知 meeting_id 后的会议内检索，不是把所有会议混在一起的全库检索；meeting_id 由评测任务提供。",
            "检索池已按规范化文本去重，并把被合并的旧 citation ID 映射到保留 ID。",
            "本轮只比较 QA 检索；待办和约束仍按候选规范化口径单独评测。",
            "BM25 使用字符 n-gram TF-IDF 作为可复现关键词基线，不依赖外部模型。",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
