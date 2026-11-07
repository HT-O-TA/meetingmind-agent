"""Offline, human-reviewed policy optimization; not recursive model training.

Consumes exported authorized candidate pools, not arbitrary network endpoints.
No model can alter labels, scoring rules, ACLs, or activate a policy here.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from statistics import mean

from app.evaluation.offline_metrics import retrieval_metrics
from app.evaluation.retrieval_policy import RetrievalPolicy, weighted_fusion


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode("utf-8")).hexdigest()


def freeze_reviewed_feedback(rows):
    """Explicit review only; never infer truth from a low rating."""
    accepted, rejected, ids, groups = [], [], set(), {}
    for original in rows:
        row = dict(original)
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in ids:
            raise ValueError("case IDs must be unique nonempty strings")
        ids.add(case_id)
        if row.get("review_status") != "approved":
            rejected.append(case_id)
            continue
        required = ("reviewed_by", "source_run_id", "source_group_id", "question")
        if any(not isinstance(row.get(key), str) or not row[key].strip() for key in required):
            raise ValueError("approved feedback requires review and source provenance")
        if row.get("split") not in {"development", "validation", "holdout"}:
            raise ValueError("explicit split required")
        if row.get("sample_kind") not in {"synthetic", "public", "deidentified"}:
            raise ValueError("explicit data origin required")
        group = row["source_group_id"]
        if group in groups and groups[group] != row["split"]:
            raise ValueError("source group crosses dataset splits")
        groups[group] = row["split"]
        for key in ("relevant_ids", "allowed_ids", "bm25_results", "dense_results"):
            if not isinstance(row.get(key), list):
                raise ValueError(f"{key} must be an explicit list")
        allowed = set(map(str, row["allowed_ids"]))
        if not set(map(str, row["relevant_ids"])) <= allowed:
            raise ValueError("labels include unauthorized IDs")
        # Validate pool shape, but do not send excluded text to an external scorer.
        weighted_fusion(row["bm25_results"], row["dense_results"], RetrievalPolicy(.5, .5))
        accepted.append(row)
    if not accepted:
        raise ValueError("no approved feedback")
    payload = {"schema_version": "meetingmind.reviewed-retrieval.v1", "cases": accepted,
               "rejected_case_ids": rejected}
    return {**payload, "dataset_hash": digest(payload)}


def verify_dataset(dataset):
    payload = {key: value for key, value in dataset.items() if key != "dataset_hash"}
    if digest(payload) != dataset.get("dataset_hash"):
        raise ValueError("dataset hash mismatch")
    rebuilt = freeze_reviewed_feedback(dataset["cases"])
    if rebuilt["cases"] != dataset["cases"]:
        raise ValueError("dataset contains unreviewed rows")


def score_policy(cases, policy, k):
    results = []
    for case in cases:
        allowed = set(map(str, case["allowed_ids"]))
        pools = [[row for row in case[key]
                  if str(row.get("chunk_id", row.get("doc_id", row.get("document_id")))) in allowed]
                 for key in ("bm25_results", "dense_results")]
        ranked = [row["chunk_id"] for row in weighted_fusion(*pools, policy)[:k]]
        relevant = list(map(str, case["relevant_ids"]))
        # Empty-label cases are abstention checks, not ordinary recall samples.
        quality = (retrieval_metrics(relevant, list(map(str, ranked)), k)["ndcg_at_k"]
                   if relevant else float(not ranked))
        results.append({"case_id": case["case_id"], "quality": quality,
                        "ranked_ids": ranked, "source_run_id": case["source_run_id"]})
    return {"mean_quality": mean(row["quality"] for row in results), "cases": results}


def optimize(dataset, baseline, candidates, *, k=5, min_gain=.01):
    verify_dataset(dataset)
    if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= 100:
        raise ValueError("k outside budget")
    if not math.isfinite(min_gain) or min_gain <= 0:
        raise ValueError("positive finite gain required")
    if not 1 <= len(candidates) <= 20:
        raise ValueError("candidate budget is 1..20")
    splits = {split: [case for case in dataset["cases"] if case["split"] == split]
              for split in ("development", "validation")}
    if any(not rows for rows in splits.values()):
        raise ValueError("development and validation groups required")
    baseline_scores = {split: score_policy(rows, baseline, k) for split, rows in splits.items()}
    # Candidate selection uses development only; holdout is never inspected/scored.
    trials = [{"policy": policy.to_dict(), "development": score_policy(splits["development"], policy, k)}
              for policy in candidates]
    best = max(trials, key=lambda trial: trial["development"]["mean_quality"])
    validation = score_policy(splits["validation"], RetrievalPolicy.parse(best["policy"]), k)
    gain = validation["mean_quality"] - baseline_scores["validation"]["mean_quality"]
    regressions = [new["case_id"] for old, new in zip(baseline_scores["validation"]["cases"], validation["cases"])
                   if new["quality"] < old["quality"]]
    development_gain = best["development"]["mean_quality"] - baseline_scores["development"]["mean_quality"]
    passed = gain >= min_gain and development_gain > 0 and not regressions
    result = {"schema_version": "meetingmind.policy-experiment.v1", "dataset_hash": dataset["dataset_hash"],
              "implementation_hashes": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                        for name in ("controlled_optimization.py", "retrieval_policy.py", "offline_metrics.py")},
              "scorer_version": "cached-ranking-ndcg-no-regressions.v1",
              "sample_kinds": sorted({case["sample_kind"] for case in dataset["cases"]}),
              "baseline_policy": baseline.to_dict(), "selected_policy": best["policy"],
              "baseline": baseline_scores, "trials": trials, "validation": validation,
              "gate": {"passed": passed, "gain": gain, "development_gain": development_gain,
                       "min_gain": min_gain, "regressions": regressions},
              "k": k, "status": "awaiting_approval" if passed else "rejected",
              "scope": "cached candidate ranking only; no generation, reranker, or production quality claim"}
    return {**result, "experiment_hash": digest(result)}


def approve(experiment, *, approved_by, expected_hash):
    payload = {key: value for key, value in experiment.items() if key != "experiment_hash"}
    if digest(payload) != expected_hash or experiment.get("experiment_hash") != expected_hash:
        raise ValueError("experiment changed since review")
    if not isinstance(approved_by, str) or not approved_by.strip():
        raise ValueError("operator identity required")
    if experiment.get("status") != "awaiting_approval" or experiment["gate"]["passed"] is not True:
        raise ValueError("candidate failed gate")
    policy = RetrievalPolicy.parse(experiment["selected_policy"])
    return {"schema_version": "meetingmind.retrieval-policy.v1", "policy": policy.to_dict(),
            "previous_policy": experiment["baseline_policy"], "approved_by": approved_by,
            "experiment_hash": expected_hash, "dataset_hash": experiment["dataset_hash"]}
