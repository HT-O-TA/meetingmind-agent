"""等字数预算对照：发言级 hybrid 按排序累加到与 300 字块 Top-5 相同的字数，比较证据召回。

回答"分块召回提升是方法增益还是上下文预算增益"。结果写入独立报告，供简历口径引用。
"""
import json
import sys
from pathlib import Path
from statistics import mean

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_chunk_retrieval import make_chunks, norm  # noqa: E402
from run_retrieval_baselines import DEFAULT_TASKS, ROOT, build_corpus, read_jsonl  # noqa: E402

OUTPUT = ROOT / "backend/evaluation/reports/meetingmind_real_v1_chunk_budget_control.json"


def main(chunk_chars=300, k=5):
    from sentence_transformers import SentenceTransformer

    emb = SentenceTransformer(str(ROOT / "model/bge-m3"), device="cuda", local_files_only=True)
    corpus, aliases, _ = build_corpus()
    tasks = [r for r in read_jsonl(DEFAULT_TASKS) if r["unit_type"] == "qa"]

    def rank(texts, query):
        vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 4)).fit(texts)
        bm = (vec.transform(texts) @ vec.transform([query]).T).toarray().ravel()
        dn = np.asarray(emb.encode(texts, normalize_embeddings=True)) @ emb.encode([query], normalize_embeddings=True)[0]
        return list(np.argsort(-(0.3 * norm(bm) + 0.7 * norm(dn))))

    rows = []
    for task in tasks:
        docs = corpus[str(task["meeting_id"])]
        relevant = {aliases.get(c, c) for c in task["retrieval"]["relevant_ids"]}
        chunks = make_chunks(docs, chunk_chars)
        top = rank([c["text"] for c in chunks], task["question"])[:k]
        budget = sum(len(chunks[i]["text"]) for i in top)
        chunk_ids = set().union(*(set(chunks[i]["ids"]) for i in top))
        selected, used = set(), 0
        for i in rank([d["text"] for d in docs], task["question"]):
            if used >= budget:
                break
            selected.add(docs[i]["id"])
            used += len(docs[i]["text"])
        rows.append({"task_id": task["id"], "char_budget": budget,
                     "chunk_recall": len(chunk_ids & relevant) / len(relevant),
                     "utterance_same_budget_recall": len(selected & relevant) / len(relevant)})
    payload = {
        "schema_version": "evaluation.chunk_budget_control.v1",
        "chunk_chars": chunk_chars, "k": k, "task_count": len(rows),
        "mean_char_budget": round(mean(r["char_budget"] for r in rows), 1),
        "chunk_recall": round(mean(r["chunk_recall"] for r in rows), 4),
        "utterance_same_budget_recall": round(mean(r["utterance_same_budget_recall"] for r in rows), 4),
        "per_record": rows,
        "limitations": ["会议内检索（已知 meeting_id），40 条 QA，不外推为全库检索。"],
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({k: v for k, v in payload.items() if k != "per_record"})


if __name__ == "__main__":
    main()
