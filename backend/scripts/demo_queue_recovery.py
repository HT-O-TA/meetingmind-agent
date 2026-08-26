"""真实 RabbitMQ 毒消息恢复 Demo：一次重试后进入死信队列。"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.core.config import settings
from app.core.rabbitmq import RabbitMQManager


async def run() -> dict:
    manager = RabbitMQManager(settings.RABBITMQ_URL)
    manager.task_max_retries = 1
    manager.retry_delay_seconds = 1
    manager.task_timeout_seconds = 5
    queue_name = f"meetingmind.demo.recovery.{uuid4().hex}"
    task_id = f"demo-poison-{uuid4().hex}"
    attempts: list[str] = []
    failures: list[dict] = []
    handle = None
    started = time.perf_counter()

    async def poison(body: dict) -> None:
        attempts.append(body["task_id"])
        raise RuntimeError("injected poison message for recovery demo")

    async def record_failure(
        body: dict, retry_count: int, error: str, dead_lettered: bool
    ) -> None:
        failures.append(
            {
                "task_id_matches": body.get("task_id") == task_id,
                "retry_count": retry_count,
                "dead_lettered": dead_lettered,
                "error_category": "injected_demo_failure",
            }
        )

    try:
        handle = await manager.consume_messages(
            queue_name,
            poison,
            prefetch_count=1,
            failure_callback=record_failure,
        )
        await manager.publish_message(
            queue_name,
            {"task_id": task_id, "payload": {"kind": "poison_demo"}},
        )

        dead_message = None
        async with manager.get_channel_context() as channel:
            topology = await manager.declare_topology(queue_name, channel=channel)
            for _ in range(100):
                dead_message = await topology.dead.get(fail=False)
                if dead_message:
                    break
                await asyncio.sleep(0.1)
            if dead_message is None:
                raise TimeoutError("毒消息未在 10 秒内进入死信队列")
            dead_body = json.loads(dead_message.body)
            await dead_message.ack()

        passed = (
            len(attempts) == 2
            and len(failures) == 2
            and failures[0]["dead_lettered"] is False
            and failures[-1]["dead_lettered"] is True
            and dead_body.get("task_id") == task_id
        )
        if not passed:
            raise AssertionError("重试/死信生命周期与预期不一致")
        return {
            "schema_version": "meetingmind.queue-recovery-demo.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sample_kind": "local_single_node",
            "status": "passed",
            "topology": "durable classic main/retry/dead",
            "publisher_confirm": "publish_message returned without error",
            "prefetch": 1,
            "configured_extra_retries": 1,
            "attempt_count": len(attempts),
            "retry_event_count": sum(not item["dead_lettered"] for item in failures),
            "dead_letter_event_count": sum(item["dead_lettered"] for item in failures),
            "dead_message_task_id_matches": dead_body.get("task_id") == task_id,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "cleanup": "temporary topology deleted in finally",
            "limitations": [
                "故障由 Demo 确定性注入，只证明恢复机制，不代表真实业务成功率。",
                "本机单节点 classic queue 不等于多节点 quorum 高可用。",
            ],
        }
    finally:
        if handle:
            await handle.close()
        try:
            await manager.delete_topology(queue_name)
        finally:
            await manager.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(run())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
