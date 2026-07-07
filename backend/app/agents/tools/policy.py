"""工具执行策略校验"""
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class ToolPolicyDecision:
    """工具策略校验结果"""
    allowed: bool
    code: str = "allowed"
    reason: str = ""
    retry_count: int = 3


class ToolPolicy:
    """工具执行前策略层。"""

    HIGH_RISK_LEVELS = {"high", "critical"}

    def validate_tool_call(self, tool: Any, state: Dict[str, Any]) -> ToolPolicyDecision:
        if not tool:
            return ToolPolicyDecision(
                allowed=False,
                code="tool_not_found",
                reason="工具不存在或未注册",
                retry_count=0,
            )

        metadata = getattr(tool, "metadata", None)
        if not metadata:
            return ToolPolicyDecision(
                allowed=False,
                code="tool_not_found",
                reason="工具缺少元数据",
                retry_count=0,
            )

        workflow_type = state.get("workflow_type")
        workflow_value = workflow_type.value if hasattr(workflow_type, "value") else workflow_type
        allowed_workflows = getattr(metadata, "allowed_workflows", []) or []
        if allowed_workflows and workflow_value not in allowed_workflows:
            return ToolPolicyDecision(
                allowed=False,
                code="policy_denied",
                reason=f"工具不允许在当前工作流 {workflow_value} 中执行",
                retry_count=0,
            )

        risk_level = getattr(metadata, "risk_level", "low")
        risk_value = risk_level.value if hasattr(risk_level, "value") else str(risk_level).lower()
        requires_confirmation = bool(getattr(metadata, "requires_confirmation", False))
        if (requires_confirmation or risk_value in self.HIGH_RISK_LEVELS) and state.get("confirmation_status") != "approved":
            return ToolPolicyDecision(
                allowed=False,
                code="confirmation_required",
                reason="高风险工具未获得人工确认",
                retry_count=0,
            )

        idempotent = bool(getattr(metadata, "idempotent", True))
        retry_count = 3 if idempotent else 1
        return ToolPolicyDecision(allowed=True, retry_count=retry_count)
