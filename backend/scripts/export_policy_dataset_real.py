"""Export reviewed Gold Pilot QA pools and summarize a frozen policy experiment."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
from statistics import mean
import subprocess
import sys

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from run_chunk_retrieval import ROOT, build_corpus, make_chunks, read_jsonl

sys.path.insert(0, str(ROOT / "backend"))
from app.evaluation.controlled_optimization import digest, verify_dataset
from app.evaluation.retrieval_policy import RetrievalPolicy, weighted_fusion


GOLD = ROOT / "backend/evaluation/datasets/meetingmind_real_v1_gold_pilot.jsonl"
CHUNK_CHARS = 300
SPLIT_SEED = 20261107
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 20260905


def export_cases():
    from sentence_transformers import SentenceTransformer

    tasks = [row for row in read_jsonl(GOLD) if row["source_review"]["unit_type"] == "qa"]
    if len(tasks) != 40:
        raise ValueError(f"expected 40 Gold Pilot QA rows, found {len(tasks)}")
    meetings = sorted({str(row["source_review"]["meeting_id"]) for row in tasks})
    random.Random(SPLIT_SEED).shuffle(meetings)
    development = set(meetings[:len(meetings) * 7 // 10])

    corpus, aliases, _ = build_corpus()
    embedder = SentenceTransformer(str(ROOT / "model/bge-m3"), device="cuda", local_files_only=True)
    cache = {}
    cases = []
    for row in tasks:
        source = row["source_review"]
        review = row["human_review"]
        if (row["review_status"] != "human_review_completed"
                or review["decision"] not in {"accept", "edit"}):
            raise ValueError(f"expected an accepted or edited human review for {row['pilot_id']}")
        annotation = (review["corrected"] if review["decision"] == "edit"
                      else source.get("corrected") or source["candidate"])
        meeting = str(source["meeting_id"])
        if meeting not in cache:
            chunks = make_chunks(corpus[meeting], CHUNK_CHARS)
            ids = [f"{meeting}:{i:04d}" for i in range(len(chunks))]
            texts = [chunk["text"] for chunk in chunks]
            vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 4))
            matrix = vectorizer.fit_transform(texts)
            vectors = embedder.encode(texts, normalize_embeddings=True, batch_size=32,
                                      show_progress_bar=False)
            chunk_by_evidence = {cid: chunk_id for chunk_id, chunk in zip(ids, chunks)
                                 for cid in chunk["ids"]}
            cache[meeting] = ids, vectorizer, matrix, np.asarray(vectors), chunk_by_evidence

        ids, vectorizer, matrix, vectors, chunk_by_evidence = cache[meeting]
        evidence = {aliases.get(cid, cid) for cid in review["evidence_ids"]}
        if not evidence or evidence - chunk_by_evidence.keys():
            raise ValueError(f"missing reviewed evidence in meeting corpus for {row['pilot_id']}")
        evidence_by_chunk = defaultdict(list)
        for cid in sorted(evidence):
            evidence_by_chunk[chunk_by_evidence[cid]].append(cid)
        question = annotation["question"]
        sparse_scores = (matrix @ vectorizer.transform([question]).T).toarray().ravel()
        dense_scores = vectors @ embedder.encode([question], normalize_embeddings=True)[0]
        cases.append({
            "case_id": source["unit_id"],
            "review_status": "approved",
            "reviewed_by": review["reviewer"],
            "source_run_id": row["pilot_id"],
            "source_group_id": meeting,
            "sample_kind": "public",
            "split": "development" if meeting in development else "validation",
            "question": question,
            "relevant_ids": sorted(evidence_by_chunk),
            "gold_evidence_by_chunk": dict(evidence_by_chunk),
            "allowed_ids": ids,
            "bm25_results": [{"chunk_id": cid, "score": float(s)} for cid, s in zip(ids, sparse_scores)],
            "dense_results": [{"chunk_id": cid, "score": float(s)} for cid, s in zip(ids, dense_scores)],
        })
    return cases


def summarize_scores(cases, weights, scores, k):
    policy = RetrievalPolicy.parse(weights)
    per_case = {}
    for scored in scores["cases"]:
        case = cases[scored["case_id"]]
        ranked = [row["chunk_id"] for row in weighted_fusion(
            case["bm25_results"], case["dense_results"], policy)]
        top = scored["ranked_ids"]
        if ranked[:k] != top:
            raise ValueError(f"ranking mismatch for {case['case_id']}")
        evidence = case["gold_evidence_by_chunk"]
        gold_count = sum(len(ids) for ids in evidence.values())
        first_hit = next(i for i, cid in enumerate(ranked, 1) if cid in evidence)
        per_case[case["case_id"]] = {
            "ndcg_at_k": scored["quality"],
            "evidence_recall_at_k": sum(len(evidence.get(cid, [])) for cid in top) / gold_count,
            "mrr": 1 / first_hit,
        }
    metrics = {key: mean(row[key] for row in per_case.values())
               for key in next(iter(per_case.values()))}
    return metrics, per_case


def bootstrap_gains(groups):
    rng = random.Random(BOOTSTRAP_SEED)
    meetings = sorted(groups)
    samples = {key: [] for key in groups[meetings[0]][0]}
    for _ in range(BOOTSTRAP_DRAWS):
        drawn = rng.choices(meetings, k=len(meetings))
        rows = [row for meeting in drawn for row in groups[meeting]]
        for key, values in samples.items():
            values.append(mean(row[key] for row in rows))
    intervals = {}
    for key, values in samples.items():
        values.sort()
        intervals[key] = [values[int(p * (len(values) - 1))] for p in (.025, .975)]
    return {"seed": BOOTSTRAP_SEED, "draws": BOOTSTRAP_DRAWS, "percentile_95": intervals}


def build_report(dataset, experiment):
    verify_dataset(dataset)
    payload = {key: value for key, value in experiment.items() if key != "experiment_hash"}
    if (digest(payload) != experiment["experiment_hash"]
            or dataset["dataset_hash"] != experiment["dataset_hash"]):
        raise ValueError("experiment hash or dataset hash mismatch")
    cases = {case["case_id"]: case for case in dataset["cases"]}
    k = experiment["k"]
    baseline = experiment["baseline_policy"]
    selected = experiment["selected_policy"]
    trials = []
    selected_dev = None
    for trial in experiment["trials"]:
        metrics, rows = summarize_scores(cases, trial["policy"], trial["development"], k)
        trials.append({"policy": trial["policy"], "development": metrics})
        if trial["policy"] == selected:
            selected_dev = metrics, rows

    splits = {}
    validation_groups = defaultdict(list)
    for split in ("development", "validation"):
        base_metrics, base_rows = summarize_scores(cases, baseline, experiment["baseline"][split], k)
        new_metrics, new_rows = (selected_dev if split == "development" else
                                 summarize_scores(cases, selected, experiment["validation"], k))
        meeting_ids = sorted({cases[cid]["source_group_id"] for cid in base_rows})
        deltas = {cid: {key: new_rows[cid][key] - old[key] for key in old}
                  for cid, old in base_rows.items()}
        regressions = {key: [cid for cid, delta in deltas.items() if delta[key] < 0]
                       for key in base_metrics}
        splits[split] = {
            "task_count": len(base_rows),
            "meeting_count": len(meeting_ids),
            "meeting_ids": meeting_ids,
            "baseline": base_metrics,
            "selected": new_metrics,
            "gain": {key: new_metrics[key] - base_metrics[key] for key in base_metrics},
            "regression_counts": {key: len(ids) for key, ids in regressions.items()},
            "regression_case_ids": regressions,
        }
        if split == "validation":
            for cid, delta in deltas.items():
                validation_groups[cases[cid]["source_group_id"]].append(delta)

    return {
        "schema_version": "evaluation.policy_optimization_real.v1",
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "dataset": GOLD.relative_to(ROOT).as_posix(),
        "gold_pilot_sha256": hashlib.sha256(GOLD.read_bytes()).hexdigest(),
        "dataset_hash": dataset["dataset_hash"],
        "experiment_hash": experiment["experiment_hash"],
        "implementation_hashes": experiment["implementation_hashes"],
        "split_rule": {"seed": SPLIT_SEED, "method": "sort meeting IDs, shuffle, first floor(70%) to development"},
        "chunk_chars": CHUNK_CHARS,
        "k": k,
        "baseline_policy": baseline,
        "candidates": trials,
        "selected_policy": selected,
        "splits": splits,
        "gate": {**experiment["gate"], "regression_count": len(experiment["gate"]["regressions"])},
        "status": experiment["status"],
        "validation_paired_meeting_bootstrap": bootstrap_gains(validation_groups),
        "definitions": {
            "candidate_pool": "会议内全部块。稀疏通道复用字符 2–4 gram TF-IDF 点积，写入 bm25_results；Dense 使用本地 BGE-M3 归一化向量点积。",
            "fusion": "受控优化器使用非负分数除以各通道最大值再加权，同分按块 ID 排序。",
            "evidence_recall_at_k": "Top-k 块覆盖的去重 gold 发言数 / 去重 gold 发言总数，按 QA 宏平均。",
            "mrr": "按完整块排序计算首个含 gold 发言的块的倒数排名，再按 QA 宏平均。",
            "ndcg_at_k": "块级二元相关性。开发集最大 nDCG 选权重；门禁要求开发增益 > 0、验证增益 >= 0.01、验证逐样本零退化。",
        },
        "limitations": [
            "仅 40 条 VCSUM QA、20 场会议。验证集仅 6 场，按会议重采样的区间可能很宽，覆盖率也不稳定。",
            "已知 meeting_id，仅比较缓存候选池的融合排序；范围限于会议内检索，未评估全库、重排、生成或线上 ACL。",
            "稀疏通道用字符 TF-IDF，融合使用最大值归一化；旧分块报告使用 min-max，基线数值口径有差异。",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    export = actions.add_parser("export")
    export.add_argument("output", type=Path)
    report = actions.add_parser("report")
    report.add_argument("dataset", type=Path)
    report.add_argument("experiment", type=Path)
    report.add_argument("output", type=Path)
    args = parser.parse_args()

    if args.action == "export":
        value = export_cases()
    else:
        dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
        experiment = json.loads(args.experiment.read_text(encoding="utf-8"))
        value = build_report(dataset, experiment)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
