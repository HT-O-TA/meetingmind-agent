import json
from pathlib import Path

from app.schemas.structured_output import TodoOutput
from finetuning.build_dataset import build_records, lint_records
from finetuning.common import extract_json_array, score_predictions, sha256_file, validate_todos


ROOT = Path(__file__).parents[2]
DATASET = ROOT / "finetuning" / "data" / "meeting_todo_synthetic_v1.jsonl"
MANIFEST = ROOT / "finetuning" / "data" / "meeting_todo_synthetic_v1.manifest.json"


def test_synthetic_dataset_is_frozen_private_safe_and_split_by_meeting():
    records = build_records()
    lint = lint_records(records)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert lint["valid"] is True
    assert lint["counts"] == {"train": 48, "validation": 12, "test": 16}
    assert lint["real_user_record_count"] == 0
    assert lint["human_reviewed_record_count"] == 0
    assert manifest["dataset_sha256"] == sha256_file(DATASET)


def test_dataset_outputs_are_compatible_with_formal_todo_schema():
    for record in build_records():
        for item in validate_todos(record["expected"]):
            formal = TodoOutput.model_validate(item)
            assert formal.content == item["content"]
            assert formal.source_id == record["sample_id"]


def test_strict_output_parser_accepts_fences_but_rejects_missing_fields():
    expected = build_records()[0]["expected"]
    parsed = extract_json_array("```json\n" + json.dumps(expected, ensure_ascii=False) + "\n```")
    assert validate_todos(parsed) == expected

    incomplete = [{"content": "整理发布清单"}]
    try:
        validate_todos(incomplete)
    except ValueError as exc:
        assert "fields mismatch" in str(exc)
    else:
        raise AssertionError("strict schema should reject missing fields")


def test_invalid_output_cannot_count_as_exact_empty_prediction():
    row = {
        "expected": [],
        "predicted_validated": [],
        "json_valid": False,
        "schema_valid": False,
    }
    assert score_predictions([row])["sample_exact_match"] == 0.0
