"""固定的工具确认门禁演示。

只验证本项目的策略层：高风险 Jira 写操作在未确认时被拦截，确认后才放行。
演示不会向 Jira 发起真实写请求，避免把演示误当成外部系统成功证据。
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from app.agents.tools.enterprise_tools import get_enterprise_tools
from app.agents.tools.policy import ToolPolicy
from app.core.config import settings


def main() -> int:
    parser = argparse.ArgumentParser(description="运行工具确认门禁固定演示")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    # 仅在演示进程内打开工具注册；不代表已经配置或执行了 Jira。
    settings.JIRA_ENABLED = True
    tools = {tool.metadata.tool_id: tool for tool in get_enterprise_tools()}
    tool = tools.get("jira_create_issue")
    if tool is None:
        result = {
            "schema_version": "meetingmind.tool-confirmation-demo.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "skipped",
            "reason": "jira_create_issue 未注册",
            "external_write_executed": False,
        }
    else:
        policy = ToolPolicy()
        state = {"question": "创建 Jira 任务", "confirmation_status": "not_required"}
        precheck = policy.validate_tool_call(tool, state, enforce_confirmation=False)
        blocked = policy.validate_tool_call(tool, state)
        approved = policy.validate_tool_call(
            tool, {**state, "confirmation_status": "approved"}
        )
        passed = (
            precheck.allowed
            and precheck.requires_confirmation
            and not blocked.allowed
            and blocked.code == "confirmation_required"
            and approved.allowed
        )
        result = {
            "schema_version": "meetingmind.tool-confirmation-demo.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "passed" if passed else "failed",
            "sample_kind": "local_policy",
            "tool_id": tool.metadata.tool_id,
            "tool_risk_level": str(getattr(tool.metadata.risk_level, "value", tool.metadata.risk_level)),
            "before_confirmation": {
                "allowed": precheck.allowed,
                "requires_confirmation": precheck.requires_confirmation,
                "code": precheck.code,
            },
            "blocked_without_confirmation": {
                "allowed": blocked.allowed,
                "requires_confirmation": blocked.requires_confirmation,
                "code": blocked.code,
            },
            "after_confirmation": {
                "allowed": approved.allowed,
                "code": approved.code,
                "retry_count": approved.retry_count,
            },
            "external_write_executed": False,
            "limitations": [
                "这是策略门禁演示，没有调用 Jira 网络接口。",
                "真实 Jira 成功率、权限和延迟需要在隔离租户中单独测量。",
            ],
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
