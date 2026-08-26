"""工具调用持久审计与幂等记录。"""
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, Text

from app.db.database import Base


class ToolExecutionAudit(Base):
    __tablename__ = "tool_execution_audits"

    id = Column(String(36), primary_key=True)
    agent_run_id = Column(String(64), nullable=True, index=True)
    thread_id = Column(String(255), nullable=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    tool_name = Column(String(128), nullable=False, index=True)
    risk_level = Column(String(20), nullable=False)
    operation_type = Column(String(20), nullable=False)
    confirmation_status = Column(String(32), nullable=False)
    policy_code = Column(String(64), nullable=False, default="allowed")
    idempotency_key = Column(String(128), nullable=True, unique=True)
    request_hash = Column(String(64), nullable=False)
    arguments_json = Column(JSON, nullable=False)
    status = Column(String(32), nullable=False, index=True)
    result_json = Column(JSON, nullable=True)
    external_id = Column(String(255), nullable=True)
    error_category = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=1)
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_tool_audit_tool_status", "tool_name", "status"),
        Index("ix_tool_audit_user_created", "user_id", "created_at"),
    )
