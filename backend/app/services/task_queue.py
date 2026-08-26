"""Redis 任务状态 + RabbitMQ 发布、幂等和消费声明。"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from app.core.cache_init import get_redis
from app.core.config import settings
from app.core.rabbitmq import rabbitmq_manager

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEAD_LETTER = "dead_letter"
    PUBLISH_FAILED = "publish_failed"


class TaskType(str, Enum):
    DOCUMENT_PROCESS = "document_process"
    VECTOR_EMBED = "vector_embed"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    AGENT_EXECUTE = "agent_execute"
    AUDIO_TRANSCRIBE = "audio_transcribe"


@dataclass
class TaskInfo:
    task_id: str
    task_type: str
    status: str
    progress: int = 0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    metadata: Optional[Dict[str, Any]] = None
    user_id: Optional[int] = None
    idempotency_key: Optional[str] = None
    attempt_count: int = 0
    max_attempts: int = 1
    error_category: Optional[str] = None
    published_at: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


TERMINAL_STATUSES = {
    TaskStatus.COMPLETED.value,
    TaskStatus.CANCELLED.value,
    TaskStatus.DEAD_LETTER.value,
    TaskStatus.PUBLISH_FAILED.value,
}


class TaskQueueService:
    def __init__(self, *, redis_client=None, publisher=None) -> None:
        self.redis = redis_client
        self.publisher = publisher or rabbitmq_manager

    async def _get_redis(self):
        if self.redis is None:
            self.redis = get_redis()
        return self.redis

    @staticmethod
    def _get_task_key(task_id: str) -> str:
        return f"task:{task_id}"

    @staticmethod
    def _get_claim_key(task_id: str) -> str:
        return f"task:claim:{task_id}"

    @staticmethod
    def _get_idempotency_key(user_id: Optional[int], task_type: TaskType, key: str) -> str:
        owner = user_id if user_id is not None else "system"
        return f"task:idempotency:{owner}:{task_type.value}:{key}"

    def _get_task_queue(self, task_type: TaskType | str) -> str:
        try:
            normalized = task_type if isinstance(task_type, TaskType) else TaskType(task_type)
        except ValueError as exc:
            raise ValueError(f"未知任务类型: {task_type}") from exc
        return {
            TaskType.DOCUMENT_PROCESS: settings.QUEUE_DOCUMENT_PROCESS,
            TaskType.VECTOR_EMBED: settings.QUEUE_VECTOR_EMBED,
            TaskType.KNOWLEDGE_GRAPH: settings.QUEUE_KNOWLEDGE_GRAPH,
            TaskType.AGENT_EXECUTE: settings.QUEUE_AGENT_EXECUTE,
            TaskType.AUDIO_TRANSCRIBE: settings.QUEUE_AUDIO_TRANSCRIBE,
        }[normalized]

    async def _save_task(self, task: TaskInfo) -> None:
        redis = await self._get_redis()
        await redis.set(
            self._get_task_key(task.task_id),
            json.dumps(asdict(task), ensure_ascii=False),
            ex=settings.QUEUE_TASK_RETENTION_SECONDS,
        )

    async def create_task(
        self,
        task_type: TaskType,
        payload: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        *,
        user_id: Optional[int] = None,
        idempotency_key: Optional[str] = None,
    ) -> TaskInfo:
        """相同用户、任务类型和幂等键只创建并发布一次。"""
        if idempotency_key and len(idempotency_key) > 128:
            raise ValueError("idempotency_key 长度不能超过 128")

        task_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        task = TaskInfo(
            task_id=task_id,
            task_type=task_type.value,
            status=TaskStatus.PENDING.value,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
            user_id=user_id,
            idempotency_key=idempotency_key,
            max_attempts=settings.QUEUE_MAX_RETRIES + 1,
            payload=payload,
        )
        redis = await self._get_redis()
        await self._save_task(task)

        if idempotency_key:
            index_key = self._get_idempotency_key(user_id, task_type, idempotency_key)
            acquired = await redis.set(
                index_key,
                task_id,
                ex=settings.QUEUE_TASK_RETENTION_SECONDS,
                nx=True,
            )
            if not acquired:
                await redis.delete(self._get_task_key(task_id))
                existing_id = await redis.get(index_key)
                if isinstance(existing_id, bytes):
                    existing_id = existing_id.decode("utf-8")
                for _ in range(10):
                    existing = await self.get_task_status(str(existing_id)) if existing_id else None
                    if existing:
                        if existing.status == TaskStatus.PUBLISH_FAILED.value:
                            return await self.republish_task(existing.task_id)
                        return existing
                    await asyncio.sleep(0.01)
                raise RuntimeError("幂等索引存在但任务状态不可用")

        message = {
            "task_id": task_id,
            "task_type": task_type.value,
            "payload": payload,
            "metadata": metadata or {},
            "user_id": user_id,
            "created_at": now,
        }
        try:
            await self.publisher.publish_message(
                queue_name=self._get_task_queue(task_type),
                message_body=message,
                headers={
                    "task_id": task_id,
                    "idempotency_key": idempotency_key or task_id,
                },
            )
        except Exception as exc:
            task.status = TaskStatus.PUBLISH_FAILED.value
            task.error_category = "publish_failed"
            task.error = f"{exc.__class__.__name__}: {exc}"[:2000]
            task.updated_at = datetime.now().isoformat()
            await self._save_task(task)
            logger.error("Task publish failed task_id=%s: %s", task_id, exc)
            return task

        task.published_at = datetime.now().isoformat()
        await self._save_task(task)
        logger.info("Task published task_id=%s type=%s", task_id, task_type.value)
        return task

    async def republish_task(
        self,
        task_id: str,
        user_id: Optional[int] = None,
    ) -> TaskInfo:
        """仅重发 broker 未确认的同一 task_id，消费者仍可按 task_id 去重。"""
        task = await self.get_task_status(task_id, user_id)
        if not task:
            raise LookupError("Task not found")
        if task.status != TaskStatus.PUBLISH_FAILED.value:
            raise ValueError("只有 publish_failed 任务允许重新发布")
        message = {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "payload": task.payload or {},
            "metadata": task.metadata or {},
            "user_id": task.user_id,
            "created_at": task.created_at,
        }
        try:
            await self.publisher.publish_message(
                queue_name=self._get_task_queue(task.task_type),
                message_body=message,
                headers={
                    "task_id": task.task_id,
                    "idempotency_key": task.idempotency_key or task.task_id,
                },
            )
        except Exception as exc:
            task.error = f"{exc.__class__.__name__}: {exc}"[:2000]
            task.updated_at = datetime.now().isoformat()
            await self._save_task(task)
            return task
        task.status = TaskStatus.PENDING.value
        task.error = None
        task.error_category = None
        task.published_at = datetime.now().isoformat()
        task.updated_at = task.published_at
        await self._save_task(task)
        return task

    async def get_task_status(
        self,
        task_id: str,
        user_id: Optional[int] = None,
    ) -> Optional[TaskInfo]:
        redis = await self._get_redis()
        raw = await redis.get(self._get_task_key(task_id))
        if not raw:
            return None
        task = TaskInfo(**json.loads(raw))
        if user_id is not None and task.user_id != user_id:
            return None
        return task

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        progress: Optional[int] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        error_category: Optional[str] = None,
    ) -> Optional[TaskInfo]:
        task = await self.get_task_status(task_id)
        if not task:
            logger.warning("Task not found: %s", task_id)
            return None
        if task.status in TERMINAL_STATUSES and task.status != status.value:
            logger.warning(
                "Ignored terminal task transition task=%s from=%s to=%s",
                task_id,
                task.status,
                status.value,
            )
            return task

        task.status = status.value
        task.updated_at = datetime.now().isoformat()
        if progress is not None:
            task.progress = max(0, min(100, progress))
        if result is not None:
            task.result = result
        if error is not None:
            task.error = error[:2000]
        if error_category is not None:
            task.error_category = error_category
        await self._save_task(task)
        return task

    async def cancel_task(self, task_id: str, user_id: Optional[int] = None) -> bool:
        if not await self.get_task_status(task_id, user_id):
            return False
        return await self.update_task_status(task_id, TaskStatus.CANCELLED) is not None

    async def list_tasks(
        self,
        task_type: Optional[TaskType] = None,
        status: Optional[TaskStatus] = None,
        limit: int = 100,
        user_id: Optional[int] = None,
    ) -> List[TaskInfo]:
        redis = await self._get_redis()
        tasks: List[TaskInfo] = []
        async for key in redis.scan_iter(match="task:*", count=limit):
            key_text = key.decode("utf-8") if isinstance(key, bytes) else str(key)
            if key_text.startswith("task:claim:") or key_text.startswith("task:idempotency:"):
                continue
            raw = await redis.get(key)
            if not raw:
                continue
            task = TaskInfo(**json.loads(raw))
            if user_id is not None and task.user_id != user_id:
                continue
            if task_type and task.task_type != task_type.value:
                continue
            if status and task.status != status.value:
                continue
            tasks.append(task)
        tasks.sort(key=lambda item: item.created_at, reverse=True)
        return tasks[:limit]

    async def delete_task(self, task_id: str, user_id: Optional[int] = None) -> bool:
        task = await self.get_task_status(task_id, user_id)
        if not task:
            return False
        redis = await self._get_redis()
        deleted = await redis.delete(self._get_task_key(task_id))
        if task.idempotency_key:
            await redis.delete(
                self._get_idempotency_key(
                    task.user_id,
                    TaskType(task.task_type),
                    task.idempotency_key,
                )
            )
        return bool(deleted)

    async def claim_task(self, task_id: str, worker_id: Optional[str] = None) -> str:
        """返回 claimed:<worker_id>、busy、terminal 或 missing。"""
        task = await self.get_task_status(task_id)
        if not task:
            return "missing"
        if task.status in TERMINAL_STATUSES:
            return "terminal"

        worker_id = worker_id or str(uuid.uuid4())
        redis = await self._get_redis()
        acquired = await redis.set(
            self._get_claim_key(task_id),
            worker_id,
            ex=settings.QUEUE_CLAIM_TTL_SECONDS,
            nx=True,
        )
        if not acquired:
            return "busy"

        latest = await self.get_task_status(task_id)
        if not latest or latest.status in TERMINAL_STATUSES:
            await self.release_claim(task_id, worker_id)
            return "terminal" if latest else "missing"
        latest.status = TaskStatus.PROCESSING.value
        latest.attempt_count += 1
        latest.updated_at = datetime.now().isoformat()
        await self._save_task(latest)
        return f"claimed:{worker_id}"

    async def release_claim(self, task_id: str, worker_id: str) -> None:
        redis = await self._get_redis()
        key = self._get_claim_key(task_id)
        current = await redis.get(key)
        if isinstance(current, bytes):
            current = current.decode("utf-8")
        if current == worker_id:
            await redis.delete(key)

    async def record_delivery_failure(
        self,
        body: Dict[str, Any],
        retry_count: int,
        error: str,
        dead_lettered: bool,
    ) -> None:
        task_id = body.get("task_id")
        task = await self.get_task_status(task_id) if task_id else None
        if not task or task.status == TaskStatus.CANCELLED.value:
            return
        task.status = (
            TaskStatus.DEAD_LETTER.value
            if dead_lettered
            else TaskStatus.RETRYING.value
        )
        task.error_category = error.split(":", 1)[0] if error else "worker_error"
        task.error = error[:2000]
        task.updated_at = datetime.now().isoformat()
        task.attempt_count = max(
            task.attempt_count,
            retry_count + (1 if dead_lettered else 0),
        )
        await self._save_task(task)


task_queue_service = TaskQueueService()


async def create_document_process_task(
    document_id: int,
    file_path: str,
    user_id: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
    idempotency_key: Optional[str] = None,
) -> TaskInfo:
    return await task_queue_service.create_task(
        TaskType.DOCUMENT_PROCESS,
        {"document_id": document_id, "file_path": file_path, "user_id": user_id},
        metadata,
        user_id=user_id,
        idempotency_key=idempotency_key,
    )


async def create_vector_embed_task(
    document_id: int,
    chunk_ids: List[int],
    metadata: Optional[Dict[str, Any]] = None,
    *,
    user_id: Optional[int] = None,
    idempotency_key: Optional[str] = None,
) -> TaskInfo:
    return await task_queue_service.create_task(
        TaskType.VECTOR_EMBED,
        {"document_id": document_id, "chunk_ids": chunk_ids, "user_id": user_id},
        metadata,
        user_id=user_id,
        idempotency_key=idempotency_key,
    )


async def create_knowledge_graph_task(
    document_id: int,
    chunk_ids: List[int],
    metadata: Optional[Dict[str, Any]] = None,
    *,
    user_id: Optional[int] = None,
    idempotency_key: Optional[str] = None,
) -> TaskInfo:
    return await task_queue_service.create_task(
        TaskType.KNOWLEDGE_GRAPH,
        {"document_id": document_id, "chunk_ids": chunk_ids, "user_id": user_id},
        metadata,
        user_id=user_id,
        idempotency_key=idempotency_key,
    )


async def create_audio_transcribe_task(
    meeting_id: int,
    file_path: str,
    original_filename: str,
    user_id: int,
    *,
    metadata: Optional[Dict[str, Any]] = None,
    idempotency_key: Optional[str] = None,
) -> TaskInfo:
    return await task_queue_service.create_task(
        TaskType.AUDIO_TRANSCRIBE,
        {
            "meeting_id": meeting_id,
            "file_path": file_path,
            "original_filename": original_filename,
            "user_id": user_id,
        },
        metadata,
        user_id=user_id,
        idempotency_key=idempotency_key,
    )
