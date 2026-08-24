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

    @staticmethod
    def _medium_authorized(metadata: Any, state: Dict[str, Any]) -> bool:
        """MEDIUM 自动放行的保守条件：本轮明确授权、范围受限、可撤销且无外部副作用。"""
        explicit = bool(state.get("explicit_write_authorization", False))
        if not explicit:
            question = str(state.get("question", "")).lower()
            explicit = any(word in question for word in ("创建", "新增", "保存", "更新", "修改", "写入", "create", "save", "update"))
        return (
            explicit
            and bool(getattr(metadata, "reversible", True))
            and not bool(getattr(metadata, "external_effect", False))
            and not bool(getattr(metadata, "bulk_operation", False))
        )

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
        if risk_value in self.HIGH_RISK_LEVELS:
            requires_confirmation = True
        elif risk_value == "medium":
            requires_confirmation = not self._medium_authorized(metadata, state)
        if requires_confirmation and state.get("confirmation_status") != "approved":
            return ToolPolicyDecision(
                allowed=False,
                code="confirmation_required",
                reason=getattr(metadata, "risk_reason", "工具风险需要人工确认"),
                retry_count=0,
            )

        idempotent = bool(getattr(metadata, "idempotent", True))
        retry_count = 3 if idempotent else 1
        return ToolPolicyDecision(allowed=True, retry_count=retry_count)
