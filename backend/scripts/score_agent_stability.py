"""Compare independent QA generation replays against one set of frozen inputs."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from run_cloud_eval_canary import DEFAULT_DATASET, load, prompt_for


def read_run(path, ids):
    rows = load(path)
    by_id = {row["id"]: row for row in rows}
    if len(rows) != len(ids) or set(by_id) != set(ids):
        raise ValueError(f"{path.name}: incomplete or duplicate IDs")
    for key, row in by_id.items():
        citations = row["citation_ids"]
        if not isinstance(row["answer"], str) or not row["answer"].strip():
            raise ValueError(f"{path.name}: empty or invalid answer for {key}")
        if not isinstance(citations, list) or any(not isinstance(item, str) for item in citations):
            raise ValueError(f"{path.name}: invalid citations for {key}")
    return by_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, nargs="+", required=True)
    parser.add_argument("--runs", type=Path, nargs=2, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    dataset = {row["id"]: row for row in load(DEFAULT_DATASET) if row["unit_type"] == "qa"}
    ids = []
    for file in args.input:
        for row in load(file):
            key = row["id"]
            if row["messages"] != prompt_for(dataset[key]):
                raise ValueError(f"Frozen QA prompt mismatch for {key}")
            ids.append(key)
    if len(ids) != len(dataset) or set(ids) != set(dataset):
        raise ValueError("Frozen QA inputs must cover all QA rows once")
    left, right = [read_run(path, ids) for path in args.runs]

    def score(key, row):
        allowed = set(re.findall(r"(?m)^\[([^]]+)] ", prompt_for(dataset[key])[1]["content"]))
        gold = set(dataset[key]["retrieval"]["relevant_ids"])
        citations = set(row["citation_ids"])
        return bool(citations & gold) and citations <= (allowed & gold), sorted(citations - allowed)

    details = []
    for key in ids:
        first, second = left[key], right[key]
        pass1, invalid1 = score(key, first)
        pass2, invalid2 = score(key, second)
        details.append({
            "id": key, "pass_round_1": pass1, "pass_round_2": pass2,
            "outside_context_round_1": invalid1, "outside_context_round_2": invalid2,
            "same_citation_set": set(first["citation_ids"]) == set(second["citation_ids"]),
            "same_answer_after_whitespace_normalization":
                " ".join(first["answer"].split()) == " ".join(second["answer"].split()),
        })
    result = {
        "schema_version": "qa_agent_citation_stability.v1",
        "model": "gpt-6.1-sol", "execution": "two independent Codex agent sessions",
        "limitations": "Generation controls unavailable; no per-record API isolation or semantic faithfulness scoring.",
        "input_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in args.input},
        "n": len(details),
        "pass_round_1": sum(r["pass_round_1"] for r in details),
        "pass_round_2": sum(r["pass_round_2"] for r in details),
        "same_pass_status": sum(r["pass_round_1"] == r["pass_round_2"] for r in details),
        "flips": [r["id"] for r in details if r["pass_round_1"] != r["pass_round_2"]],
        "same_citation_set": sum(r["same_citation_set"] for r in details),
        "same_answer_after_whitespace_normalization":
            sum(r["same_answer_after_whitespace_normalization"] for r in details),
        "per_id": details,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({key: value for key, value in result.items() if key != "per_id"})


if __name__ == "__main__":
    main()
