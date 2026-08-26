"""工具执行持久审计与幂等门禁。"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.database import AsyncSessionLocal
from app.models.tool_execution import ToolExecutionAudit


SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "api_token",
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
}


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in SENSITIVE_KEYS else redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    return value


def stable_request_hash(arguments: Dict[str, Any]) -> str:
    canonical = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class AuditBeginResult:
    audit_id: str
    action: str  # execute / replay / blocked
    prior_result: Optional[Dict[str, Any]] = None
    prior_status: Optional[str] = None


class ToolAuditService:
    """每次方法调用使用独立事务，避免提交 Agent 业务会话中的其他修改。"""

    def __init__(self, session_factory=AsyncSessionLocal) -> None:
        self.session_factory = session_factory

    async def begin(
        self,
        *,
        agent_run_id: Optional[str],
        thread_id: Optional[str],
        user_id: Optional[int],
        tool_name: str,
        risk_level: str,
        operation_type: str,
        confirmation_status: str,
        policy_code: str,
        arguments: Dict[str, Any],
        idempotency_key: Optional[str],
    ) -> AuditBeginResult:
        request_hash = stable_request_hash(arguments)
        async with self.session_factory() as session:
            if idempotency_key:
                existing = await session.scalar(
                    select(ToolExecutionAudit).where(
                        ToolExecutionAudit.idempotency_key == idempotency_key
                    )
                )
                if existing:
                    return self._existing_result(existing, request_hash)

            audit_id = str(uuid.uuid4())
            record = ToolExecutionAudit(
                id=audit_id,
                agent_run_id=agent_run_id,
                thread_id=thread_id,
                user_id=user_id,
                tool_name=tool_name,
                risk_level=risk_level,
                operation_type=operation_type,
                confirmation_status=confirmation_status,
                policy_code=policy_code,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                arguments_json=redact_sensitive(arguments),
                status="started",
            )
            session.add(record)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(
                    select(ToolExecutionAudit).where(
                        ToolExecutionAudit.idempotency_key == idempotency_key
                    )
                )
                if not existing:
                    raise
                return self._existing_result(existing, request_hash)
            return AuditBeginResult(audit_id=audit_id, action="execute")

    @staticmethod
    def _existing_result(record: ToolExecutionAudit, request_hash: str) -> AuditBeginResult:
        if record.request_hash != request_hash:
            return AuditBeginResult(
                audit_id=record.id,
                action="blocked",
                prior_status="idempotency_key_conflict",
            )
        if record.status == "succeeded":
            return AuditBeginResult(
                audit_id=record.id,
                action="replay",
                prior_result=record.result_json,
                prior_status=record.status,
            )
        return AuditBeginResult(
            audit_id=record.id,
            action="blocked",
            prior_status=record.status,
        )

    async def finish(
        self,
        audit_id: str,
        *,
        status: str,
        result: Any = None,
        external_id: Optional[str] = None,
        error_category: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        async with self.session_factory() as session:
            record = await session.get(ToolExecutionAudit, audit_id)
            if not record:
                raise LookupError(f"工具审计记录不存在: {audit_id}")
            record.status = status
            record.result_json = redact_sensitive(result) if result is not None else None
            record.external_id = external_id
            record.error_category = error_category
            record.error_message = error_message[:2000] if error_message else None
            record.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await session.commit()


_tool_audit_service: Optional[ToolAuditService] = None


def get_tool_audit_service() -> ToolAuditService:
    global _tool_audit_service
    if _tool_audit_service is None:
        _tool_audit_service = ToolAuditService()
    return _tool_audit_service
