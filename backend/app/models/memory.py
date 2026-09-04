"""长期事实记忆的权威表和索引同步 outbox。

PostgreSQL 保存“到底记住了什么”的唯一事实；Milvus、Neo4j 以及缓存只保存
可重建的派生数据。这样即使索引服务短暂不可用，也不会丢失事实本身。
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Float, Index, Integer, String, Text

from app.db.database import Base


def utcnow_naive() -> datetime:
    """项目现有表使用无时区 DateTime，统一写入 UTC 的无时区时间。"""

    return datetime.now(timezone.utc).replace(tzinfo=None)


class MemoryRecordModel(Base):
    """长期事实/决定记录；同一命名空间内的旧事实不会被物理覆盖。"""

    __tablename__ = "memory_records"

    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, nullable=True, index=True)
    thread_id = Column(String(255), nullable=True, index=True)
    task_namespace = Column(String(128), nullable=False, index=True)
    meeting_id = Column(Integer, nullable=True, index=True)
    document_id = Column(Integer, nullable=True, index=True)
    kind = Column(String(32), nullable=False, index=True)  # fact/decision/conversation
    record_key = Column(String(256), nullable=True)
    value = Column(Text, nullable=True)
    text = Column(Text, nullable=False)
    source = Column(String(32), nullable=False, default="user")
    source_ref = Column(String(255), nullable=True)
    confidence = Column(Float, nullable=False, default=0.5)
    importance = Column(Float, nullable=False, default=0.5)
    valid_from = Column(DateTime, nullable=False, default=utcnow_naive)
    valid_until = Column(DateTime, nullable=True)
    status = Column(String(24), nullable=False, default="active", index=True)
    supersedes_id = Column(String(64), nullable=True, index=True)
    conflict_group_id = Column(String(64), nullable=True, index=True)
    embedding_model = Column(String(128), nullable=True)
    embedding_version = Column(String(64), nullable=True)
    content_hash = Column(String(64), nullable=True, index=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=utcnow_naive, index=True)
    deleted_at = Column(DateTime, nullable=True, index=True)

    __table_args__ = (
        Index(
            "ix_memory_scope_key_status",
            "user_id",
            "thread_id",
            "task_namespace",
            "record_key",
            "status",
        ),
        Index("ix_memory_retrieval_scope", "user_id", "task_namespace", "kind", "status"),
    )


class MemoryIndexEventModel(Base):
    """写入事实后投递给 Milvus/Neo4j 的可靠 outbox 事件。"""

    __tablename__ = "memory_index_events"

    id = Column(String(96), primary_key=True)
    memory_id = Column(String(64), nullable=False, index=True)
    operation = Column(String(24), nullable=False)  # upsert/delete
    payload_json = Column(JSON, nullable=False, default=dict)
    status = Column(String(24), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime, nullable=False, default=utcnow_naive, index=True)
    claimed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow_naive, index=True)
    processed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_memory_event_pending", "status", "available_at"),
    )


__all__ = ["MemoryRecordModel", "MemoryIndexEventModel", "utcnow_naive"]
