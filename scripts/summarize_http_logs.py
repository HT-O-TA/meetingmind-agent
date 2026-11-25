"""Summarize MeetingMind access logs read from standard input."""

import json
import math
import re
import sys
from collections import Counter, defaultdict


ACCESS = re.compile(
    r"\[(?:RESPONSE|ERROR)\] (?P<method>[A-Z]+) .*? "
    r"\[(?P<status>\d{3})\] (?P<ms>\d+(?:\.\d+)?)ms .* route=(?P<route>\S+)$"
)


def summarize(lines):
    counts = defaultdict(Counter)
    latencies = defaultdict(list)
    for line in lines:
        match = ACCESS.search(line.strip())
        if not match:
            continue
        key = f"{match['method']} {match['route']}"
        counts[key][match["status"]] += 1
        latencies[key].append(float(match["ms"]))
    return {
        key: {
            "requests": len(values),
            "status_counts": dict(sorted(counts[key].items())),
            "p95_ms": sorted(values)[math.ceil(0.95 * len(values)) - 1],
        }
        for key, values in sorted(latencies.items())
    }


if __name__ == "__main__":
    print(json.dumps(summarize(sys.stdin), indent=2))
