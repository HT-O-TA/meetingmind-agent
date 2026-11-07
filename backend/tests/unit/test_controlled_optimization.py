"""Synthetic contracts, not evidence of real meeting quality gains."""
import copy
import unittest
import json
from pathlib import Path
import tempfile

from app.evaluation.controlled_optimization import approve, digest, freeze_reviewed_feedback, optimize
from app.evaluation.retrieval_policy import RetrievalPolicy, load_policy, weighted_fusion


def cases():
    return [{"case_id": split, "source_group_id": split, "split": split,
             "review_status": "approved", "reviewed_by": "test-reviewer", "source_run_id": "test-run",
             "question": "synthetic question", "sample_kind": "synthetic",
             "relevant_ids": ["good"], "allowed_ids": ["good", "bad"],
             "bm25_results": [{"chunk_id": "bad", "score": 1}],
             "dense_results": [{"chunk_id": "good", "score": 1}]}
            for split in ("development", "validation", "holdout")]


class ControlledOptimizationTest(unittest.TestCase):
    def test_approval_and_no_holdout_scoring(self):
        dataset = freeze_reviewed_feedback(cases())
        result = optimize(dataset, RetrievalPolicy(1, 0), [RetrievalPolicy(0, 1)], k=1)
        self.assertEqual(result["status"], "awaiting_approval")
        self.assertNotIn("holdout", result["baseline"])
        policy = approve(result, approved_by="human", expected_hash=result["experiment_hash"])
        self.assertEqual(policy["policy"]["vector_weight"], 1)

    def test_tampered_experiment_rejected(self):
        result = optimize(freeze_reviewed_feedback(cases()), RetrievalPolicy(1, 0), [RetrievalPolicy(0, 1)], k=1)
        result["selected_policy"] = RetrievalPolicy(1, 0).to_dict()
        with self.assertRaises(ValueError):
            approve(result, approved_by="human", expected_hash=result["experiment_hash"])

    def test_dataset_tampering(self):
        dataset = freeze_reviewed_feedback(cases())
        dataset["cases"][0]["relevant_ids"] = []
        with self.assertRaises(ValueError):
            optimize(dataset, RetrievalPolicy(1, 0), [RetrievalPolicy(0, 1)])

    def test_source_leakage(self):
        rows = cases()
        rows[1]["source_group_id"] = rows[0]["source_group_id"]
        with self.assertRaises(ValueError):
            freeze_reviewed_feedback(rows)

    def test_unreviewed_feedback_excluded(self):
        rows = cases()
        rows[0]["review_status"] = "rejected"
        dataset = freeze_reviewed_feedback(rows)
        self.assertEqual(dataset["rejected_case_ids"], ["development"])
        with self.assertRaises(ValueError):
            optimize(dataset, RetrievalPolicy(1, 0), [RetrievalPolicy(0, 1)])

    def test_no_improvement_rejected(self):
        result = optimize(freeze_reviewed_feedback(cases()), RetrievalPolicy(0, 1), [RetrievalPolicy(1, 0)], k=1)
        self.assertEqual(result["status"], "rejected")
        with self.assertRaises(ValueError):
            approve(result, approved_by="human", expected_hash=result["experiment_hash"])

    def test_restricted_policy_and_numbers(self):
        for value in [float("nan"), float("inf"), -1, True]:
            with self.assertRaises(ValueError):
                RetrievalPolicy(value, 1)
        with self.assertRaises(ValueError):
            RetrievalPolicy.parse({"acl": False})

    def test_unauthorized_label(self):
        rows = cases()
        rows[0]["allowed_ids"] = []
        with self.assertRaises(ValueError):
            freeze_reviewed_feedback(rows)

    def test_pool_acl_filter(self):
        rows = cases()
        for row in rows:
            row["bm25_results"].append({"chunk_id": "private", "score": 100})
        result = optimize(freeze_reviewed_feedback(rows), RetrievalPolicy(1, 0), [RetrievalPolicy(0, 1)], k=1)
        self.assertNotIn("private", str(result))

    def test_candidate_budget_and_gain(self):
        dataset = freeze_reviewed_feedback(cases())
        for candidates, gain in [([], .01), ([RetrievalPolicy(1, 0)] * 21, .01), ([RetrievalPolicy(1, 0)], float("nan"))]:
            with self.assertRaises(ValueError):
                optimize(dataset, RetrievalPolicy(1, 0), candidates, min_gain=gain)

    def test_duplicate_and_missing_ids(self):
        for rows in [[{"score": 1}], [{"chunk_id": 1}, {"chunk_id": 1}]]:
            with self.assertRaises(ValueError):
                weighted_fusion(rows, [], RetrievalPolicy(1, 0))

    def test_provenance_required(self):
        rows = cases()
        rows[0]["source_run_id"] = ""
        with self.assertRaises(ValueError):
            freeze_reviewed_feedback(rows)

    def test_approved_policy_is_runtime_loadable(self):
        result = optimize(freeze_reviewed_feedback(cases()), RetrievalPolicy(1, 0), [RetrievalPolicy(0, 1)], k=1)
        policy = approve(result, approved_by="human", expected_hash=result["experiment_hash"])
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3] / "artifacts") as directory:
            path = Path(directory) / "policy.json"
            path.write_text(json.dumps(policy), encoding="utf-8")
            self.assertEqual(load_policy(str(path)), RetrievalPolicy(0, 1))
            policy["approved_by"] = ""
            path.write_text(json.dumps(policy), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_policy(str(path))

    def test_one_regression_blocks_aggregate_gain(self):
        rows = cases()
        extra = copy.deepcopy(rows[1])
        extra.update(case_id="validation-regression", source_group_id="other-meeting")
        extra["bm25_results"], extra["dense_results"] = extra["dense_results"], extra["bm25_results"]
        rows.append(extra)
        extra2 = copy.deepcopy(rows[1])
        extra2.update(case_id="validation-gain", source_group_id="another-meeting")
        rows.append(extra2)
        result = optimize(freeze_reviewed_feedback(rows), RetrievalPolicy(1, 0), [RetrievalPolicy(0, 1)], k=1)
        self.assertGreater(result["gate"]["gain"], 0)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["gate"]["regressions"], ["validation-regression"])

    def test_duplicate_case_rejected(self):
        rows = cases()
        rows.append(copy.deepcopy(rows[0]))
        with self.assertRaises(ValueError):
            freeze_reviewed_feedback(rows)


if __name__ == "__main__":
    unittest.main()
