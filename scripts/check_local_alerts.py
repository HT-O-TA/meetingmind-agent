"""Evaluate a local observation window and report alert transitions as JSON."""

import argparse
import json
import time
from itertools import count
from pathlib import Path

from summarize_http_logs import summarize
from sample_local_queues import sample as sample_queue


def evaluate(http, baseline, samples, *, min_requests=20, error_rate=.05,
             p95_ms=2000, ready_depth=10):
    alerts = set()
    for route, metrics in http.items():
        count = metrics["requests"]
        if count < min_requests:
            continue
        errors = sum(n for code, n in metrics["status_counts"].items() if code.startswith("5"))
        if errors / count >= error_rate:
            alerts.add(f"http_errors:{route}")
        if metrics["p95_ms"] >= p95_ms:
            alerts.add(f"http_latency:{route}")
    for name, queue in samples[-1]["queues"].items():
        if name.endswith(".dead"):
            if queue["ready"] > baseline["queues"][name]["ready"]:
                alerts.add(f"new_dead_letter:{name}")
        elif not name.endswith(".retry") and len(samples) >= 2:
            if all(sample["queues"][name]["ready"] >= ready_depth for sample in samples[-2:]):
                alerts.add(f"queue_backlog:{name}")
    return alerts


def transitions(http, baseline, samples, previous, *, min_requests=20):
    active = evaluate(http, baseline, samples, min_requests=min_requests)
    # An empty or undersized window cannot establish HTTP recovery.
    for alert in previous:
        kind, route = alert.split(":", 1)
        if kind in {"http_errors", "http_latency"} and (
            http.get(route, {}).get("requests", 0) < min_requests
        ):
            active.add(alert)
        if kind == "queue_backlog" and len(samples) < 2:
            active.add(alert)
    return {"active": sorted(active), "triggered": sorted(active - previous),
            "recovered": sorted(previous - active)}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("access_log", type=Path)
    cli.add_argument("queue_samples", type=Path, nargs="?")
    cli.add_argument("--previous", type=Path)
    cli.add_argument("--watch", action="store_true", help="sample live local queues and follow an append-only access log")
    cli.add_argument("--interval", type=float, default=10)
    cli.add_argument("--windows", type=int, default=0, help="stop after this many windows; 0 runs until interrupted")
    cli.add_argument("--queue", action="append", help="select isolated queues in watch mode")
    args = cli.parse_args()
    if args.watch:
        if args.queue_samples or args.previous or args.interval < 2 or args.windows < 0:
            cli.error("--watch requires an interval of at least 2 seconds and no saved state inputs")
        watch(args.access_log, args.interval, args.windows, args.queue)
        return
    if not args.queue_samples:
        cli.error("provide saved queue samples or use --watch")
    with args.access_log.open(encoding="utf-8-sig") as log:
        http = summarize(log)
    samples = [json.loads(line) for line in args.queue_samples.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if len(samples) < 2:
        cli.error("queue input requires a baseline and at least one current sample")
    previous = set(json.loads(args.previous.read_text(encoding="utf-8-sig"))["active"]) if args.previous else set()
    print(json.dumps(transitions(http, samples[0], samples[1:], previous), ensure_ascii=False))


def watch(path, interval, windows, queue_names=None):
    baseline = sample_queue(queue_names)
    samples = []
    previous = set()
    with path.open(encoding="utf-8-sig", errors="replace") as log:
        log.seek(0, 2)
        for _ in range(windows) if windows else count():
            time.sleep(interval)
            samples = [*samples[-1:], sample_queue(queue_names)]
            # Keep a partial record for the next window if the writer has not
            # finished appending this line.
            lines = []
            while True:
                offset = log.tell()
                line = log.readline()
                if not line.endswith("\n"):
                    log.seek(offset)
                    break
                lines.append(line)
            state = transitions(summarize(lines), baseline, samples, previous)
            previous = set(state["active"])
            print(json.dumps({"sampled_at": samples[-1]["sampled_at"], **state}), flush=True)


if __name__ == "__main__":
    main()
