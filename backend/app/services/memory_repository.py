"""PostgreSQL 长期事实记忆仓库。

这个仓库只负责权威写入、范围过滤和 outbox 事件；向量/图索引由异步消费者
根据事件构建，不能反过来决定事实是否存在。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.database import AsyncSessionLocal
from app.models.memory import MemoryIndexEventModel, MemoryRecordModel, utcnow_naive
from app.core.config import settings


def _clean(value: Any, max_chars: int) -> str:
    return " ".join(str(value or "").split())[:max_chars]


def _record_id(namespace: str, key: str, value: str, now: datetime) -> str:
    raw = f"{namespace}|{key}|{value}|{now.isoformat()}".encode("utf-8")
    return "fact_" + hashlib.sha256(raw).hexdigest()[:32]


class MemoryRepository:
    """可注入 session 工厂，便于生产连接池和单元测试分别使用。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal):
        self.session_factory = session_factory

    async def write_fact(
        self,
        *,
        namespace: str,
        key: str,
        value: str,
        user_id: Optional[int] = None,
        thread_id: Optional[str] = None,
        meeting_id: Optional[int] = None,
        document_id: Optional[int] = None,
        source: str = "user",
        source_ref: Optional[str] = None,
        confidence: float = 0.8,
        importance: float = 0.7,
        metadata: Optional[Dict[str, Any]] = None,
        embedding_model: Optional[str] = None,
        embedding_version: Optional[str] = None,
        conflict_group_id: Optional[str] = None,
        supersede_previous: bool = True,
    ) -> Optional[MemoryRecordModel]:
        namespace = _clean(namespace, 128)
        key = _clean(key, 256)
        value = _clean(value, 2000)
        if not namespace or not key or not value:
            return None
        if not (0 <= confidence <= 1 and 0 <= importance <= 1):
            raise ValueError("confidence/importance 必须位于 [0,1]")

        now = utcnow_naive()
        async with self.session_factory() as session:
            async with session.begin():
                scope = [
                    MemoryRecordModel.task_namespace == namespace,
                    MemoryRecordModel.record_key == key,
                    MemoryRecordModel.status == "active",
                ]
                if user_id is not None:
                    scope.append(MemoryRecordModel.user_id == user_id)
                if thread_id is not None:
                    scope.append(MemoryRecordModel.thread_id == thread_id)
                previous = (
                    await session.execute(
                        select(MemoryRecordModel)
                        .where(and_(*scope))
                        .order_by(MemoryRecordModel.created_at.desc())
                        .limit(1)
                        .with_for_update()
                    )
                ).scalar_one_or_none()
                if previous and previous.value == value:
                    return previous
                if previous and supersede_previous:
                    previous.status = "superseded"
                    previous.valid_until = now

                memory_id = _record_id(namespace, key, value, now)
                record = MemoryRecordModel(
                    id=memory_id,
                    user_id=user_id,
                    thread_id=thread_id,
                    task_namespace=namespace,
                    meeting_id=meeting_id,
                    document_id=document_id,
                    kind="fact",
                    record_key=key,
                    value=value,
                    text=f"{key}: {value}",
                    source=_clean(source, 32) or "user",
                    source_ref=_clean(source_ref, 255) or None,
                    confidence=confidence,
                    importance=importance,
                    valid_from=now,
                    status="active",
                    supersedes_id=previous.id if previous and supersede_previous else None,
                    conflict_group_id=_clean(conflict_group_id, 64) or None,
                    embedding_model=_clean(embedding_model, 128) or None,
                    embedding_version=_clean(embedding_version, 64) or None,
                    content_hash=hashlib.sha256(value.encode("utf-8")).hexdigest(),
                    metadata_json=metadata if isinstance(metadata, dict) else {},
                    created_at=now,
                )
                session.add(record)
                await session.flush()
                event_id = f"{memory_id}:upsert"
                session.add(
                    MemoryIndexEventModel(
                        id=event_id,
                        memory_id=memory_id,
                        operation="upsert",
                        payload_json={"memory_id": memory_id, "text": record.text, "namespace": namespace},
                        status="pending",
                        created_at=now,
                        available_at=now,
                    )
                )
                return record

    async def search(
        self,
        query: str,
        *,
        namespace: str,
        user_id: Optional[int] = None,
        thread_id: Optional[str] = None,
        meeting_id: Optional[int] = None,
        document_id: Optional[int] = None,
        kinds: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[MemoryRecordModel]:
        """先做严格范围过滤，再做轻量词面召回；dense/rerank 由索引层补分。"""

        terms = re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]", _clean(query, 500).casefold())[:32]
        filters = [
            MemoryRecordModel.task_namespace == _clean(namespace, 128),
            MemoryRecordModel.status == "active",
        ]
        if user_id is not None:
            filters.append(MemoryRecordModel.user_id == user_id)
        if thread_id is not None:
            filters.append(MemoryRecordModel.thread_id == thread_id)
        if meeting_id is not None:
            filters.append(MemoryRecordModel.meeting_id == meeting_id)
        if document_id is not None:
            filters.append(MemoryRecordModel.document_id == document_id)
        if kinds:
            filters.append(MemoryRecordModel.kind.in_(kinds))
        lexical = [
            or_(MemoryRecordModel.text.ilike(f"%{term}%"), MemoryRecordModel.record_key.ilike(f"%{term}%"))
            for term in terms
        ]
        if lexical:
            filters.append(or_(*lexical))
        async with self.session_factory() as session:
            result = await session.execute(
                select(MemoryRecordModel)
                .where(and_(*filters))
                .order_by(MemoryRecordModel.importance.desc(), MemoryRecordModel.confidence.desc(), MemoryRecordModel.created_at.desc())
                .limit(max(1, min(limit, 100)))
            )
            return list(result.scalars().all())

    async def forget(self, *, max_age_days: int = 30, namespace: Optional[str] = None) -> int:
        """软删除过期/被覆盖事实；保留审计记录，避免直接物理删除无法追责。"""

        now = utcnow_naive()
        cutoff = now - timedelta(days=max(1, max_age_days))
        filters = [
            MemoryRecordModel.status.in_(["superseded", "active"]),
            or_(
                MemoryRecordModel.status == "superseded",
                MemoryRecordModel.valid_until <= now,
                and_(MemoryRecordModel.kind == "conversation", MemoryRecordModel.created_at < cutoff),
            ),
        ]
        if namespace:
            filters.append(MemoryRecordModel.task_namespace == namespace)
        async with self.session_factory() as session:
            async with session.begin():
                result = await session.execute(update(MemoryRecordModel).where(and_(*filters)).values(status="deleted", deleted_at=now))
                return int(result.rowcount or 0)

    async def publish_pending_events(
        self,
        *,
        limit: Optional[int] = None,
        queue_name: Optional[str] = None,
        publisher: Optional[Any] = None,
    ) -> int:
        """发布 outbox 事件；先 claim 再发消息，重复执行不会重复 claim 同一批。"""

        if publisher is None:
            from app.core.rabbitmq import rabbitmq_manager

            publisher = rabbitmq_manager
        batch_size = max(1, min(int(limit or settings.MEMORY_OUTBOX_BATCH_SIZE), 200))
        queue = queue_name or settings.QUEUE_MEMORY_INDEX
        now = utcnow_naive()
        async with self.session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(MemoryIndexEventModel)
                    .where(
                        or_(
                            and_(MemoryIndexEventModel.status == "pending", MemoryIndexEventModel.available_at <= now),
                            and_(MemoryIndexEventModel.status == "publishing", MemoryIndexEventModel.available_at <= now),
                        ),
                    )
                    .order_by(MemoryIndexEventModel.created_at)
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )
                events = list(result.scalars().all())
                for event in events:
                    event.status = "publishing"
                    event.attempts = int(event.attempts or 0) + 1
                    event.claimed_at = now
                    event.available_at = now + timedelta(seconds=max(5, int(settings.MEMORY_OUTBOX_CLAIM_LEASE_SECONDS)))
        published = 0
        for event in events:
            body = dict(event.payload_json or {})
            body.update({"task_id": event.id, "event_id": event.id, "operation": event.operation, "memory_id": event.memory_id})
            try:
                await publisher.publish_message(queue, body)
            except Exception:
                await self._mark_event_failed(event.id)
            else:
                await self._mark_event_published(event.id)
                published += 1
        return published

    async def _mark_event_published(self, event_id: str) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(MemoryIndexEventModel)
                    .where(MemoryIndexEventModel.id == event_id)
                    .values(status="published", processed_at=utcnow_naive())
                )

    async def _mark_event_failed(self, event_id: str) -> None:
        now = utcnow_naive()
        async with self.session_factory() as session:
            async with session.begin():
                event = (
                    await session.execute(
                        select(MemoryIndexEventModel).where(MemoryIndexEventModel.id == event_id).with_for_update()
                    )
                ).scalar_one_or_none()
                if event is None:
                    return
                max_attempts = max(1, int(settings.QUEUE_MAX_RETRIES) + 1)
                if int(event.attempts or 0) >= max_attempts:
                    event.status = "dead"
                else:
                    event.status = "pending"
                    event.available_at = now + timedelta(seconds=max(1, int(settings.QUEUE_RETRY_DELAY_SECONDS)))

    async def delete_scope(
        self,
        *,
        user_id: int,
        thread_id: Optional[str] = None,
        namespace: Optional[str] = None,
        meeting_id: Optional[int] = None,
        document_id: Optional[int] = None,
    ) -> int:
        """按用户归属软删除记忆，并为索引生成 delete 事件。"""

        filters = [MemoryRecordModel.user_id == user_id, MemoryRecordModel.status != "deleted"]
        if thread_id:
            filters.append(MemoryRecordModel.thread_id == thread_id)
        if namespace:
            filters.append(MemoryRecordModel.task_namespace == namespace)
        if meeting_id is not None:
            filters.append(MemoryRecordModel.meeting_id == meeting_id)
        if document_id is not None:
            filters.append(MemoryRecordModel.document_id == document_id)
        now = utcnow_naive()
        async with self.session_factory() as session:
            async with session.begin():
                records = list((await session.execute(select(MemoryRecordModel).where(and_(*filters)).with_for_update())).scalars().all())
                for record in records:
                    record.status = "deleted"
                    record.deleted_at = now
                    session.add(
                        MemoryIndexEventModel(
                            id=f"{record.id}:delete:{now.timestamp()}",
                            memory_id=record.id,
                            operation="delete",
                            payload_json={"memory_id": record.id, "namespace": record.task_namespace},
                            status="pending",
                            created_at=now,
                            available_at=now,
                        )
                    )
                return len(records)


__all__ = ["MemoryRepository"]
