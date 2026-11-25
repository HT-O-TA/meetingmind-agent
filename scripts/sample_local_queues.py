"""Sample the local MeetingMind RabbitMQ queues without consuming messages."""

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone


QUEUES = {
    "document_process", "document_process.retry", "document_process.dead",
    "vector_embed", "vector_embed.retry", "vector_embed.dead",
}


def sample(queue_names=None):
    selected = set(queue_names or QUEUES)
    started = time.monotonic()
    result = subprocess.run(
        ["docker", "exec", "meetingmind-rabbitmq", "rabbitmqctl", "-q",
         "list_queues", "name", "messages_ready", "messages_unacknowledged"],
        check=True, capture_output=True, text=True, timeout=8,
    )
    queues = {}
    for line in result.stdout.splitlines():
        name, *values = line.split("\t")
        if name in selected and len(values) == 2:
            queues[name] = {"ready": int(values[0]), "unacknowledged": int(values[1])}
    if missing := selected - queues.keys():
        raise RuntimeError(f"Missing RabbitMQ queues: {', '.join(sorted(missing))}")
    return {
        "sampled_at": datetime.now(timezone.utc).isoformat(),
        "query_seconds": round(time.monotonic() - started, 3),
        "queues": queues,
    }


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--seconds", type=float, default=10)
    cli.add_argument("--interval", type=float, default=1)
    cli.add_argument("--queue", action="append", help="sample only these queues")
    args = cli.parse_args()
    if not 0 < args.seconds <= 600 or not 0.5 <= args.interval <= 60:
        cli.error("seconds must be in (0, 600] and interval in [0.5, 60]")
    deadline = time.monotonic() + args.seconds
    while True:
        started = time.monotonic()
        print(json.dumps(sample(args.queue)), flush=True)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(remaining, max(0, args.interval - (time.monotonic() - started))))


if __name__ == "__main__":
    main()
