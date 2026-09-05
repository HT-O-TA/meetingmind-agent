from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATASETS = BACKEND_ROOT / "evaluation" / "datasets"
SOURCE_PATH = DATASETS / "meetingmind_real_v1_sources.jsonl"
CANDIDATE_PATH = DATASETS / "meetingmind_real_v1_candidates.jsonl"
REVIEW_PATH = DATASETS / "meetingmind_real_v1_ai_reviews.jsonl"
SOURCE_MANIFEST_PATH = DATASETS / "meetingmind_real_v1_review_manifest.json"
REVIEW_MANIFEST_PATH = DATASETS / "meetingmind_real_v1_ai_review_manifest.json"

EXPECTED_SOURCE_HASH = "c32dc4a90a288cee2d15891167fd8652ec1cc71b61e09883c06cf62f82a387ca"
EXPECTED_CANDIDATE_HASH = "4ee50cef10ef88ddac183d5af2b822e87065f6f372f214d66045c83fa4f5aa9c"


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _stable_hash(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    normalized = text.rstrip("\n") + "\n" if text else ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _manifest_hash(manifest: dict) -> str:
    payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def test_real_meeting_source_hash_contract_is_cross_platform_stable() -> None:
    manifest = json.loads(SOURCE_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert _stable_hash(SOURCE_PATH) == EXPECTED_SOURCE_HASH
    assert _stable_hash(CANDIDATE_PATH) == EXPECTED_CANDIDATE_HASH
    assert manifest["files"]["sources"]["sha256"] == EXPECTED_SOURCE_HASH
    assert manifest["files"]["candidates"]["sha256"] == EXPECTED_CANDIDATE_HASH
    assert manifest["hash_contract"]["sha256"].startswith("UTF-8 JSONL")
    assert manifest["manifest_sha256"] == _manifest_hash(manifest)


def test_ai_review_covers_all_580_units_without_claiming_gold() -> None:
    reviews = _read_jsonl(REVIEW_PATH)
    manifest = json.loads(REVIEW_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert len(reviews) == 580
    assert len({row["unit_id"] for row in reviews}) == 580
    assert Counter(row["unit_type"] for row in reviews) == Counter({"qa": 158, "todo": 194, "constraint": 228})
    assert {row["annotation_status"] for row in reviews} == {"ai_reviewed_silver"}
    assert all(row["human_review_required"] is True for row in reviews)
    assert manifest["gold"] is False
    assert manifest["human_review_required"] is True
    assert manifest["human_sampling_plan"]["minimum_units"] >= 20
    assert manifest["files"]["reviews"]["sha256"] == _stable_hash(REVIEW_PATH)
    assert manifest["manifest_sha256"] == _manifest_hash(manifest)


def test_ai_review_corrections_are_evidence_linked_and_do_not_infer_assignees() -> None:
    reviews = _read_jsonl(REVIEW_PATH)
    for row in reviews:
        assert row["decision"] in {"accept", "edit", "reject"}
        assert row["evidence_ids"]
        if row["decision"] == "reject":
            assert row["corrected"] is None
        if row["unit_type"] == "qa":
            citations = row["corrected"]["citations"]
            assert citations
            assert row["evidence_ids"] == [citation["citation_id"] for citation in citations]
            assert row["corrected"]["answer"]
        if row["unit_type"] == "todo" and row["corrected"]:
            for todo in row["corrected"]:
                assert todo["content"]
                assert todo["assignee"] == ""
                assert todo["deadline"] == ""
                assert todo["evidence_id"] in row["evidence_ids"]
