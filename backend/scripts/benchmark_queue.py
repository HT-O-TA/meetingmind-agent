"""单机 RabbitMQ 轻量消息基线：publisher confirm 与端到端延迟。"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import platform
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit

from app.core.config import settings
from app.core.rabbitmq import RabbitMQManager


def percentile(values, percent):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percent / 100 * len(ordered)) - 1)
    return ordered[index]


def summary(values):
    return {
        "mean_ms": round(statistics.fmean(values), 3) if values else 0.0,
        "p50_ms": round(percentile(values, 50), 3),
        "p95_ms": round(percentile(values, 95), 3),
        "max_ms": round(max(values), 3) if values else 0.0,
    }


async def run(args):
    manager = RabbitMQManager(settings.RABBITMQ_URL)
    queue_name = f"meetingmind.benchmark.{uuid4().hex}"
    publish_latencies = []
    end_to_end_latencies = []
    completed = asyncio.Event()
    semaphore = asyncio.Semaphore(args.concurrency)
    padding = "x" * args.payload_bytes

    async def consume(body):
        end_to_end_latencies.append((time.perf_counter_ns() - body["sent_ns"]) / 1_000_000)
        if len(end_to_end_latencies) >= args.messages:
            completed.set()

    async def publish(index):
        async with semaphore:
            started = time.perf_counter_ns()
            await manager.publish_message(
                queue_name,
                {
                    "task_id": f"benchmark-{index}-{uuid4().hex}",
                    "sent_ns": time.perf_counter_ns(),
                    "payload": padding,
                },
            )
            publish_latencies.append((time.perf_counter_ns() - started) / 1_000_000)

    handle = None
    started = time.perf_counter()
    try:
        handle = await manager.consume_messages(
            queue_name,
            consume,
            prefetch_count=args.prefetch,
        )
        await asyncio.gather(*(publish(index) for index in range(args.messages)))
        await asyncio.wait_for(completed.wait(), timeout=args.timeout)
        duration = time.perf_counter() - started
        broker = await manager.get_server_properties()
        report = {
            "schema_version": "queue-benchmark.v1",
            "sample_kind": "local_single_node",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "rabbitmq_url_host": urlsplit(settings.RABBITMQ_URL).hostname,
                "broker": broker,
                "topology": "durable classic main/retry/dead",
            },
            "config": {
                "messages": args.messages,
                "concurrency": args.concurrency,
                "prefetch": args.prefetch,
                "payload_bytes": args.payload_bytes,
            },
            "metrics": {
                "duration_seconds": round(duration, 3),
                "throughput_messages_per_second": round(args.messages / duration, 3),
                "publisher_confirm": summary(publish_latencies),
                "end_to_end": summary(end_to_end_latencies),
                "received": len(end_to_end_latencies),
                "errors": args.messages - len(end_to_end_latencies),
            },
            "limitations": [
                "本报告只测单机本地 broker 和轻量回调，不代表文档解析、Embedding 或 LLM 吞吐。",
                "单节点 classic queue 不提供集群副本高可用；生产环境需单独验证 quorum queue。",
            ],
        }
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        print(rendered)
        if args.output:
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered + "\n", encoding="utf-8")
        return report
    finally:
        if handle:
            await handle.close()
        await manager.delete_topology(queue_name)
        await manager.close()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--messages", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--prefetch", type=int, default=20)
    parser.add_argument("--payload-bytes", type=int, default=1024)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--output")
    args = parser.parse_args()
    for field in ("messages", "concurrency", "prefetch"):
        if getattr(args, field) <= 0:
            parser.error(f"--{field.replace('_', '-')} 必须大于 0")
    if args.payload_bytes < 0:
        parser.error("--payload-bytes 不能小于 0")
    return args


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
