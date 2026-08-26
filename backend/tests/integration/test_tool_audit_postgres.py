"""真实 PostgreSQL 验证持久审计、结果回放与幂等键冲突。"""
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.tool_execution import ToolExecutionAudit
from app.services.tool_audit_service import ToolAuditService


@pytest.mark.asyncio
async def test_tool_audit_is_persistent_and_idempotent():
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(ToolExecutionAudit.__table__.create, checkfirst=True)

    service = ToolAuditService(session_factory)
    suffix = uuid4().hex
    key = f"integration:{suffix}"
    arguments = {"project_key": "MM", "summary": "只创建一次", "api_token": "secret"}
    first = await service.begin(
        agent_run_id=suffix,
        thread_id=f"thread:{suffix}",
        user_id=1,
        tool_name="jira_create_issue",
        risk_level="medium",
        operation_type="external",
        confirmation_status="approved",
        policy_code="allowed",
        arguments=arguments,
        idempotency_key=key,
    )
    assert first.action == "execute"

    await service.finish(
        first.audit_id,
        status="succeeded",
        result={"success": True, "external_id": "MM-9"},
        external_id="MM-9",
    )

    replay = await service.begin(
        agent_run_id=suffix,
        thread_id=f"thread:{suffix}",
        user_id=1,
        tool_name="jira_create_issue",
        risk_level="medium",
        operation_type="external",
        confirmation_status="approved",
        policy_code="allowed",
        arguments=arguments,
        idempotency_key=key,
    )
    assert replay.action == "replay"
    assert replay.prior_result["external_id"] == "MM-9"

    conflict = await service.begin(
        agent_run_id=suffix,
        thread_id=f"thread:{suffix}",
        user_id=1,
        tool_name="jira_create_issue",
        risk_level="medium",
        operation_type="external",
        confirmation_status="approved",
        policy_code="allowed",
        arguments={**arguments, "summary": "不同请求"},
        idempotency_key=key,
    )
    assert conflict.action == "blocked"
    assert conflict.prior_status == "idempotency_key_conflict"

    async with session_factory() as session:
        record = await session.get(ToolExecutionAudit, first.audit_id)
        assert record.arguments_json["api_token"] == "[REDACTED]"
        assert record.status == "succeeded"
        await session.execute(delete(ToolExecutionAudit).where(ToolExecutionAudit.id == first.audit_id))
        await session.commit()
    await engine.dispose()
