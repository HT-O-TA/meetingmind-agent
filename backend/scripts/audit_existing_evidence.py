"""Offline evaluation audit from frozen runs. No model calls."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from run_faithfulness_judge import contexts_of

BASE = Path(__file__).resolve().parents[1] / "evaluation"
REPORTS = BASE / "reports"
DATASET = BASE / "datasets" / "meetingmind_real_v1_evaluation.jsonl"
RUN = "meetingmind_real_v1_opus55_v2_100"
CONFIGS = {
    "qwen": "meetingmind_real_v1_cloud_100_scored",
    "opus": RUN + "_scored",
    "sonnet": "meetingmind_real_v1_sonnet5_100_scored",
}


def read(name, field):
    path = REPORTS / f"{name}.json"
    rows = json.loads(path.read_text(encoding="utf-8"))[field]
    indexed = {row["id"]: row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError(f"Duplicate IDs in {name}")
    return indexed


def judge_pass(row):
    labels = [claim["label"] for claim in row["claims"]["current"]]
    if not row["ok"] or not labels or set(labels) - {"supported", "unsupported"}:
        raise ValueError(f"Unscorable Judge output for {row['id']}")
    return all(label == "supported" for label in labels)


def pair(left, right):
    return dict(Counter(
        "both_pass" if a and b else "left_only" if a else "right_only" if b else "neither"
        for a, b in zip(left, right, strict=True)
    ))


def passes(row):
    if row["unit_type"] == "qa":
        return row["citation_precision"] == 1 and row["citation_recall"] > 0
    return row["decision_accuracy"] == 1 and row["f1"] == 1


def summarize(rows):
    return {"failed": len(rows), "by_primary_reason": dict(Counter(rows.values())), "per_id": rows}


def assess_tools(rows):
    failed = {}
    for key, row in rows.items():
        if not row["selection_ok"]:
            failed[key] = "missing_tool" if not row["predicted_tools"] else "tool_selection"
        elif row["parameter_score"] < 1:
            failed[key] = "tool_parameters"
        elif not row["hitl_ok"]:
            failed[key] = "confirmation"
    return {"total": len(rows), **summarize(failed)}


def compare_humans(rows, judges):
    human = {row["id"]: row["human_review"]["all_claims_supported"] for row in rows}
    if set(human) != set(next(iter(judges.values()))) or any(type(v) is not bool for v in human.values()):
        raise ValueError("Provide one boolean human judgment per frozen QA")
    out = {}
    for name, judge in judges.items():
        tp = sum(not human[key] and not judge[key] for key in human)
        fp = sum(human[key] and not judge[key] for key in human)
        fn = sum(not human[key] and judge[key] for key in human)
        tn = len(human) - tp - fp - fn
        out[name] = dict(tp=tp, fp=fp, fn=fn, tn=tn, agreement=(tp + tn) / len(human),
                         precision=tp / (tp + fp) if tp + fp else None,
                         recall=tp / (tp + fn) if tp + fn else None,
                         f1=2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
                         disagreements=[key for key in human if human[key] != judge[key]])
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--human", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    dataset = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines()]
    by_id = {row["id"]: row for row in dataset}
    assert len(by_id) == len(dataset) == 100
    qa = {key: row for key, row in by_id.items() if row["unit_type"] == "qa"}
    scored = {name: read(file, "per_record") for name, file in CONFIGS.items()}
    judges = {name: {key: judge_pass(row) for key, row in read(
        f"faithfulness_qa40_judge_{name}", "per_record").items()} for name in ("opus55", "sonnet5")}
    generation = read(RUN, "results")
    assert all(set(rows) == set(by_id) for rows in scored.values())
    assert all(set(rows) == set(qa) for rows in judges.values())
    audit = []
    qa_fail = {}
    missing_visible_evidence = {}
    for key, row in qa.items():
        output = generation[key]["output"]
        contexts = contexts_of(row)
        audit.append({"id": key, "question": row["question"], "evidence": contexts,
                      "answer": output["answer"],
                      "human_review": {"all_claims_supported": None, "evidence_ids": [], "rationale": ""}})
        visible = {line.split("]", 1)[0][1:] for line in contexts.splitlines() if line.startswith("[")}
        gold = set(row["retrieval"]["relevant_ids"])
        if gold - visible:
            missing_visible_evidence[key] = {
                "gold": len(gold), "visible_gold": len(gold & visible),
            }
        unsupported = sum(not judge[key] for judge in judges.values())
        if set(output.get("citation_ids", [])) - visible:
            qa_fail[key] = "citation_outside_review_context"
        elif unsupported:
            qa_fail[key] = "both_judges_flagged" if unsupported == 2 else "judge_disagreement"
        elif not passes(scored["opus"][key]):
            qa_fail[key] = "citation_acceptance_failure"
    report = {
        "dataset_sha256": hashlib.sha256(DATASET.read_bytes()).hexdigest(),
        "human_scope": "Reference review only; answer-level blind labels required",
        "pass_rules": {"qa": "All emitted citations are gold IDs and recall is positive",
                       "todo_or_constraint": "Correct decision and exact extraction F1 of 1"},
        "coverage": {},
        "qa": {"total": len(qa), "review_flags": summarize(qa_fail),
               "visible_gold_shortfall": missing_visible_evidence,
               "no_visible_gold": sum(not r["visible_gold"] for r in missing_visible_evidence.values())},
        "stability": {
            "paired_quality_runs_matching_current_qa_configuration": 1,
            "excluded": "Other recorded QA outputs use different models or prompts; tool replays are a different task",
        },
        "tools": {name: assess_tools(read("tool_eval_heldout_v1_" + name, "per_record"))
                  for name in ("opus55", "opus55_rerun2", "sonnet5")},
    }
    for kind in ("qa", "todo", "constraint"):
        ids = [key for key, row in by_id.items() if row["unit_type"] == kind]
        outcomes = {name: [passes(rows[key]) for key in ids] for name, rows in scored.items()}
        report["coverage"][kind] = {
            "count": len(ids), "meetings": len({by_id[key]["meeting_id"] for key in ids}),
            "source_counts": dict(Counter(by_id[key]["source_dataset"] for key in ids)),
            "pass_counts": {name: sum(labels) for name, labels in outcomes.items()},
            "paired": {f"{left}_vs_{right}": pair(outcomes[left], outcomes[right])
                       for left, right in (("qwen", "opus"), ("qwen", "sonnet"), ("opus", "sonnet"))},
        }
    if args.human:
        completed = [json.loads(line) for line in args.human.read_text(encoding="utf-8").splitlines()]
        if len(completed) != len(audit) or {row["id"]: {k: row[k] for k in ("answer", "question", "evidence")}
                for row in completed} != {row["id"]: {k: row[k] for k in ("answer", "question", "evidence")}
                                         for row in audit}:
            raise ValueError("Blind review inputs changed")
        report["judge_against_human"] = compare_humans(completed, judges)
    (args.output_dir / "evaluation-audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    review = args.output_dir / "qa40-human-blind.jsonl"
    if not review.exists():
        review.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in audit), encoding="utf-8")


if __name__ == "__main__":
    main()
