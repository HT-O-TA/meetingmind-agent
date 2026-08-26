import json
import asyncio
from unittest.mock import AsyncMock

import pytest

from app.core.rabbitmq import RabbitMQManager
from app.services.task_queue import TaskQueueService, TaskStatus, TaskType


class FakePublisher:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    async def publish_message(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return kwargs["queue_name"]


class CompletingPublisher:
    """模拟 consumer 在 publisher confirm 返回前已经完成任务。"""

    def __init__(self):
        self.service = None

    async def publish_message(self, **kwargs):
        assert self.service is not None
        await self.service.update_task_status(
            kwargs["headers"]["task_id"],
            TaskStatus.COMPLETED,
            progress=100,
        )
        return kwargs["queue_name"]


class FakeIncomingMessage:
    def __init__(self, body, headers=None):
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.headers = headers or {}
        self.acked = 0
        self.nacked = []
        self.rejected = []

    async def ack(self):
        self.acked += 1

    async def nack(self, requeue=False):
        self.nacked.append(requeue)

    async def reject(self, requeue=False):
        self.rejected.append(requeue)


@pytest.mark.asyncio
async def test_create_task_idempotency_publishes_once(fake_redis):
    publisher = FakePublisher()
    service = TaskQueueService(redis_client=fake_redis, publisher=publisher)

    first = await service.create_task(
        TaskType.DOCUMENT_PROCESS,
        {"document_id": 1},
        user_id=7,
        idempotency_key="upload-1",
    )
    second = await service.create_task(
        TaskType.DOCUMENT_PROCESS,
        {"document_id": 1},
        user_id=7,
        idempotency_key="upload-1",
    )

    assert second.task_id == first.task_id
    assert len(publisher.calls) == 1
    assert first.published_at is not None


@pytest.mark.asyncio
async def test_publish_failure_is_visible_in_task_state(fake_redis):
    publisher = FakePublisher(ConnectionError("broker down"))
    service = TaskQueueService(redis_client=fake_redis, publisher=publisher)
    task = await service.create_task(TaskType.DOCUMENT_PROCESS, {"document_id": 1}, user_id=7)

    assert task.status == TaskStatus.PUBLISH_FAILED.value
    assert task.error_category == "publish_failed"
    stored = await service.get_task_status(task.task_id, user_id=7)
    assert stored.status == TaskStatus.PUBLISH_FAILED.value

    publisher.error = None
    republished = await service.republish_task(task.task_id, user_id=7)
    assert republished.task_id == task.task_id
    assert republished.status == TaskStatus.PENDING.value
    assert len(publisher.calls) == 2


@pytest.mark.asyncio
async def test_fast_consumer_completion_is_not_overwritten_by_publisher(fake_redis):
    publisher = CompletingPublisher()
    service = TaskQueueService(redis_client=fake_redis, publisher=publisher)
    publisher.service = service

    task = await service.create_task(
        TaskType.VECTOR_EMBED,
        {"document_id": 1, "chunk_ids": [1]},
        user_id=7,
    )

    assert task.status == TaskStatus.COMPLETED.value
    stored = await service.get_task_status(task.task_id)
    assert stored.status == TaskStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_fast_consumer_completion_is_not_overwritten_on_republish(fake_redis):
    service = TaskQueueService(
        redis_client=fake_redis,
        publisher=FakePublisher(ConnectionError("broker down")),
    )
    failed = await service.create_task(TaskType.VECTOR_EMBED, {}, user_id=7)
    publisher = CompletingPublisher()
    publisher.service = service
    service.publisher = publisher

    task = await service.republish_task(failed.task_id, user_id=7)

    assert task.status == TaskStatus.COMPLETED.value
    stored = await service.get_task_status(task.task_id)
    assert stored.status == TaskStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_task_status_and_listing_are_owner_scoped(fake_redis):
    service = TaskQueueService(redis_client=fake_redis, publisher=FakePublisher())
    task = await service.create_task(TaskType.DOCUMENT_PROCESS, {}, user_id=7)

    assert await service.get_task_status(task.task_id, user_id=8) is None
    assert await service.list_tasks(user_id=8) == []
    assert await service.cancel_task(task.task_id, user_id=8) is False
    assert len(await service.list_tasks(user_id=7)) == 1


@pytest.mark.asyncio
async def test_task_queue_fails_clearly_without_initialized_redis(monkeypatch):
    monkeypatch.setattr("app.services.task_queue.get_redis", lambda: None)
    service = TaskQueueService(publisher=FakePublisher())

    with pytest.raises(RuntimeError, match="Redis is not initialized"):
        await service.get_task_status("missing")


@pytest.mark.asyncio
async def test_claim_prevents_parallel_duplicate_and_terminal_replay(fake_redis):
    service = TaskQueueService(redis_client=fake_redis, publisher=FakePublisher())
    task = await service.create_task(TaskType.VECTOR_EMBED, {}, user_id=7)

    claim = await service.claim_task(task.task_id, "worker-a")
    assert claim == "claimed:worker-a"
    assert await service.claim_task(task.task_id, "worker-b") == "busy"
    await service.update_task_status(task.task_id, TaskStatus.COMPLETED, progress=100)
    await service.release_claim(task.task_id, "worker-a")
    assert await service.claim_task(task.task_id, "worker-b") == "terminal"


@pytest.mark.asyncio
async def test_consumer_success_acks_only_after_callback():
    manager = RabbitMQManager()
    message = FakeIncomingMessage({"task_id": "t1"})
    callback = AsyncMock(return_value={"ok": True})

    await manager._process_delivery("test.queue", message, callback, None)

    callback.assert_awaited_once()
    assert message.acked == 1
    assert message.nacked == []
    assert message.rejected == []


@pytest.mark.asyncio
async def test_consumer_failure_republishes_then_acks_original():
    manager = RabbitMQManager()
    manager.task_max_retries = 2
    manager._publish_retry = AsyncMock()
    failure_callback = AsyncMock()
    message = FakeIncomingMessage({"task_id": "t1"}, {"x-retry-count": 0})

    async def fail(body):
        raise RuntimeError("boom")

    await manager._process_delivery("test.queue", message, fail, failure_callback)

    manager._publish_retry.assert_awaited_once()
    retry_headers = manager._publish_retry.await_args.args[2]
    assert retry_headers["x-retry-count"] == 1
    assert message.acked == 1
    failure_callback.assert_awaited_once_with(
        {"task_id": "t1"}, 1, "RuntimeError: boom", False
    )


@pytest.mark.asyncio
async def test_consumer_exhaustion_confirms_dead_queue_before_ack():
    manager = RabbitMQManager()
    manager.task_max_retries = 2
    manager._publish_dead = AsyncMock()
    failure_callback = AsyncMock()
    message = FakeIncomingMessage({"task_id": "t1"}, {"x-retry-count": 2})

    async def fail(body):
        raise RuntimeError("poison")

    await manager._process_delivery("test.queue", message, fail, failure_callback)

    manager._publish_dead.assert_awaited_once()
    assert message.rejected == []
    assert message.acked == 1
    failure_callback.assert_awaited_once_with(
        {"task_id": "t1"}, 2, "RuntimeError: poison", True
    )


@pytest.mark.asyncio
async def test_failure_callback_error_does_not_break_confirmed_retry():
    manager = RabbitMQManager()
    manager._publish_retry = AsyncMock()
    failure_callback = AsyncMock(side_effect=RuntimeError("state store down"))
    message = FakeIncomingMessage({"task_id": "t1"})

    async def fail(body):
        raise RuntimeError("boom")

    await manager._process_delivery("test.queue", message, fail, failure_callback)

    assert message.acked == 1
    assert message.nacked == []


@pytest.mark.asyncio
async def test_retry_publish_failure_keeps_original_message():
    manager = RabbitMQManager()
    manager._publish_retry = AsyncMock(side_effect=ConnectionError("confirm lost"))
    message = FakeIncomingMessage({"task_id": "t1"})

    async def fail(body):
        raise RuntimeError("boom")

    with pytest.raises(ConnectionError):
        await manager._process_delivery("test.queue", message, fail, None)
    assert message.nacked == [True]
    assert message.acked == 0


@pytest.mark.asyncio
async def test_malformed_message_is_dead_lettered_without_callback():
    manager = RabbitMQManager()
    message = FakeIncomingMessage(b"not-json")
    callback = AsyncMock()

    await manager._process_delivery("test.queue", message, callback, None)

    callback.assert_not_awaited()
    assert message.rejected == [False]


@pytest.mark.asyncio
async def test_consumer_timeout_enters_bounded_retry():
    manager = RabbitMQManager()
    manager.task_timeout_seconds = 0.01
    manager._publish_retry = AsyncMock()
    failure_callback = AsyncMock()
    message = FakeIncomingMessage({"task_id": "slow"})

    async def slow(body):
        await asyncio.sleep(1)

    await manager._process_delivery("test.queue", message, slow, failure_callback)

    assert message.acked == 1
    failure = failure_callback.await_args.args
    assert failure[0] == {"task_id": "slow"}
    assert failure[1] == 1
    assert "TimeoutError" in failure[2]
    assert failure[3] is False
