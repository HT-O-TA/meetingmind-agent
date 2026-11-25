"""Measure response-level agreement from the two frozen judge reports."""
import json
from collections import Counter
from pathlib import Path


def read_judgments(path):
    report = json.loads(path.read_text(encoding="utf-8"))
    rows = report["per_record"]
    judgments = {row["id"]: row["claims"] for row in rows if row["ok"]}
    if not len(judgments) == len(rows) == report["count"]:
        raise ValueError(f"Incomplete or duplicate judgments in {path.name}")
    return judgments


def supported(claims):
    return bool(claims) and all(claim["label"] == "supported" for claim in claims)


def agreement(left, right, variant):
    counts = Counter((supported(left[key][variant]), supported(right[key][variant]))
                     for key in left)
    both, left_only, right_only, neither = (
        counts[True, True], counts[True, False], counts[False, True], counts[False, False]
    )
    count = len(left)
    observed = (both + neither) / count
    expected = ((both + left_only) * (both + right_only)
                + (neither + left_only) * (neither + right_only)) / count**2
    return {
        "both_supported": both,
        "opus_only": left_only,
        "sonnet_only": right_only,
        "neither_supported": neither,
        "agreement": round(observed, 4),
        "cohen_kappa": round((observed - expected) / (1 - expected), 4) if expected < 1 else None,
    }


def main():
    reports = Path(__file__).resolve().parents[1] / "evaluation" / "reports"
    left, right = [
        read_judgments(reports / f"faithfulness_qa40_judge_{name}.json")
        for name in ("opus55", "sonnet5")
    ]
    if not left or left.keys() != right.keys():
        raise ValueError("Judge reports must contain matching, nonempty QA identifiers")
    print(json.dumps({
        "schema_version": "evaluation.paired_judge_agreement.v1",
        "paired_qa": len(left),
        "criterion": "Nonempty claims, all labeled supported by the respective judge",
        "variants": {name: agreement(left, right, name) for name in ("baseline", "current", "probe")},
    }, indent=2))


if __name__ == "__main__":
    main()
