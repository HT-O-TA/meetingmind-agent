"""真实 Redis 验证任务幂等索引、用户隔离和消费 claim。"""
from uuid import uuid4

import pytest
from redis.asyncio import from_url

from app.core.config import settings
from app.services.task_queue import TaskQueueService, TaskStatus, TaskType


class RecordingPublisher:
    def __init__(self):
        self.calls = []

    async def publish_message(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs["queue_name"]


@pytest.mark.asyncio
async def test_redis_idempotency_owner_scope_and_claim():
    redis = from_url(settings.REDIS_URL, decode_responses=True)
    publisher = RecordingPublisher()
    service = TaskQueueService(redis_client=redis, publisher=publisher)
    unique = uuid4().hex

    try:
        first = await service.create_task(
            TaskType.DOCUMENT_PROCESS,
            {"document_id": 1},
            user_id=7,
            idempotency_key=unique,
        )
        replay = await service.create_task(
            TaskType.DOCUMENT_PROCESS,
            {"document_id": 1},
            user_id=7,
            idempotency_key=unique,
        )
        assert replay.task_id == first.task_id
        assert len(publisher.calls) == 1
        assert await service.get_task_status(first.task_id, user_id=8) is None

        claim = await service.claim_task(first.task_id, "worker-a")
        assert claim == "claimed:worker-a"
        assert await service.claim_task(first.task_id, "worker-b") == "busy"
        await service.update_task_status(first.task_id, TaskStatus.COMPLETED, progress=100)
        await service.release_claim(first.task_id, "worker-a")
        assert await service.claim_task(first.task_id, "worker-b") == "terminal"
    finally:
        if "first" in locals():
            await service.delete_task(first.task_id, user_id=7)
        await redis.aclose()
