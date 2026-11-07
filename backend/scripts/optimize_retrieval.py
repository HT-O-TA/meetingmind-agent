"""Local operator workflow. Files are created exclusively (never overwritten).

Run from backend: python scripts/optimize_retrieval.py --help
No network requests, model calls, or production activation are performed.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.evaluation.controlled_optimization import approve, freeze_reviewed_feedback, optimize
from app.evaluation.retrieval_policy import RetrievalPolicy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["freeze", "experiment", "approve", "rollback"])
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--reviewer")
    parser.add_argument("--expected-hash")
    parser.add_argument("--baseline-bm25", type=float, default=.3)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--min-gain", type=float, default=.01)
    args = parser.parse_args()
    value = json.loads(args.input.read_text(encoding="utf-8"))
    if args.action == "freeze":
        result = freeze_reviewed_feedback(value)
    elif args.action == "experiment":
        result = optimize(value, RetrievalPolicy(args.baseline_bm25, 1 - args.baseline_bm25),
                          [RetrievalPolicy(weight, 1 - weight) for weight in (.0, .25, .5, .75, 1.)],
                          k=args.k, min_gain=args.min_gain)
    elif args.action == "approve":
        result = approve(value, approved_by=args.reviewer, expected_hash=args.expected_hash)
    else:
        from app.evaluation.controlled_optimization import digest
        from app.evaluation.retrieval_policy import load_policy
        load_policy(str(args.input))
        if not args.reviewer or digest(value) != args.expected_hash:
            raise ValueError("rollback requires operator and hash of current policy file")
        previous = RetrievalPolicy.parse(value["previous_policy"])
        result = {**value, "policy": previous.to_dict(), "previous_policy": value["policy"],
                  "approved_by": args.reviewer, "rollback_of": args.expected_hash}
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({"output": str(args.output), "status": result.get("status", "written")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
