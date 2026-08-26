"""真实 RabbitMQ 3.13 验证 confirm、延迟重试、manual ack 和 DLQ。"""
import asyncio
from uuid import uuid4

import pytest

from app.core.config import settings
from app.core.rabbitmq import RabbitMQManager


@pytest.mark.asyncio
async def test_poison_message_retries_then_enters_dead_letter_queue():
    manager = RabbitMQManager(settings.RABBITMQ_URL)
    manager.task_max_retries = 1
    manager.retry_delay_seconds = 1
    manager.task_timeout_seconds = 5
    queue_name = f"meetingmind.integration.{uuid4().hex}"
    attempts = []
    failures = []

    async def poison(body):
        attempts.append(body["task_id"])
        raise RuntimeError("injected poison message")

    async def record_failure(body, retry_count, error, dead_lettered):
        failures.append((retry_count, dead_lettered, error))

    handle = None
    try:
        handle = await manager.consume_messages(
            queue_name,
            poison,
            prefetch_count=1,
            failure_callback=record_failure,
        )
        await manager.publish_message(
            queue_name,
            {"task_id": f"task-{uuid4().hex}", "payload": {"kind": "poison"}},
        )

        dead_message = None
        async with manager.get_channel_context() as channel:
            topology = await manager.declare_topology(queue_name, channel=channel)
            for _ in range(60):
                dead_message = await topology.dead.get(fail=False)
                if dead_message:
                    break
                await asyncio.sleep(0.1)
            assert dead_message is not None
            await dead_message.ack()

        assert len(attempts) == 2
        assert failures[0][0:2] == (1, False)
        assert failures[-1][0:2] == (1, True)
        assert "injected poison message" in failures[-1][2]
    finally:
        if handle:
            await handle.close()
        try:
            await manager.delete_topology(queue_name)
        finally:
            await manager.close()
