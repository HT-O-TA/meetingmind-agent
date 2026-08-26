import pytest

from app.agents.human_in_the_loop import ConfirmationType, HumanInTheLoopService
from app.agents.nodes import AgentNodes
from app.agents.tools.enterprise_tools import get_enterprise_tools
from app.agents.tools.policy import ToolPolicy
from app.core.config import settings


@pytest.fixture
def jira_tools(monkeypatch):
    monkeypatch.setattr(settings, "JIRA_ENABLED", True)
    return {tool.metadata.tool_id: tool for tool in get_enterprise_tools()}


def test_external_jira_write_is_truthfully_marked_and_requires_confirmation(jira_tools):
    create = jira_tools["jira_create_issue"].metadata
    read = jira_tools["jira_get_issue"].metadata

    assert create.operation_type == "external"
    assert create.external_effect is True
    assert create.reversible is False
    assert create.idempotent is False
    assert create.requires_confirmation is True
    assert read.operation_type == "read"
    assert read.external_effect is False


def test_parameter_schema_runs_before_policy_and_rejects_unknown(jira_tools):
    tool = jira_tools["jira_create_issue"]
    errors = AgentNodes._validate_tool_parameters(
        None,
        tool,
        {"project_key": "MM", "summary": "ok", "surprise": True},
    )
    assert errors == ["未知参数: surprise"]

    errors = AgentNodes._validate_tool_parameters(
        None,
        tool,
        {"project_key": "MM", "summary": 123},
    )
    assert any("summary 类型错误" in error for error in errors)


def test_policy_precheck_exposes_hitl_without_allowing_unconfirmed_write(jira_tools):
    policy = ToolPolicy()
    tool = jira_tools["jira_create_issue"]
    state = {"question": "创建 Jira 任务", "confirmation_status": "not_required"}

    precheck = policy.validate_tool_call(tool, state, enforce_confirmation=False)
    blocked = policy.validate_tool_call(tool, state)
    approved = policy.validate_tool_call(tool, {**state, "confirmation_status": "approved"})

    assert precheck.allowed is True
    assert precheck.requires_confirmation is True
    assert blocked.allowed is False
    assert blocked.code == "confirmation_required"
    assert approved.allowed is True
    assert approved.retry_count == 1


@pytest.mark.asyncio
async def test_hitl_requests_are_visible_and_actionable_only_by_owner(fake_redis):
    hitl = HumanInTheLoopService()
    hitl.redis = fake_redis
    request_id = await hitl.request_confirmation(
        ConfirmationType.CRITICAL_ACTION,
        "外部写确认",
        "创建 Jira Issue？",
        details={"user_id": 7, "tool_name": "jira_create_issue"},
        resume_state={"question": "创建 Jira Issue"},
    )

    assert await hitl.get_request_status(request_id, expected_user_id=8) is None
    assert await hitl.list_pending_requests(expected_user_id=8) == []
    assert await hitl.respond_to_request(request_id, "approved", expected_user_id=8) is False

    owned = await hitl.get_request_status(request_id, expected_user_id=7)
    assert owned is not None
    assert await hitl.get_resume_state(request_id, expected_user_id=7) is not None
    assert await hitl.respond_to_request(request_id, "approved", expected_user_id=7) is True
