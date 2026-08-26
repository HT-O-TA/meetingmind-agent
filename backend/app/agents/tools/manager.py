"""工具管理器 - 管理工具注册和执行"""
from typing import Optional, Dict, Any
from app.agents.tools.executor import ToolExecutor
from app.agents.tools.registry import get_tool_registry
from app.agents.tools.selector import ToolSelector
from app.agents.tools.meeting_tools import register_meeting_tools
from app.services.llm_service import LLMService
from app.services.vector_search_service import VectorSearchService
from app.core.logger import app_logger
from app.agents.tools.tool_metadata import ToolExecutionResult
from app.services.tool_audit_service import get_tool_audit_service


class ToolManager:
    """工具管理器 - 整合注册表和执行器"""

    def __init__(
        self,
        llm_service: LLMService,
        vector_search_service: Optional[VectorSearchService] = None
    ):
        self.llm_service = llm_service
        self.vector_search_service = vector_search_service
        self.registry = get_tool_registry()
        self.executor = ToolExecutor()
        self.audit_service = get_tool_audit_service()
        self.selector = ToolSelector(allowed_tool_ids=self.executor.get_supported_tool_ids())
        
        self._register_meeting_tools()

    def _register_meeting_tools(self):
        """注册会议相关工具"""
        try:
            register_meeting_tools(self.llm_service, self.vector_search_service)
            app_logger.info("会议工具注册成功")
        except Exception as e:
            app_logger.warning(f"注册会议工具失败: {e}")

    def get_available_tools(self):
        """获取所有可用工具"""
        supported_ids = set(self.executor.get_supported_tool_ids())
        return [tool for tool in self.registry.get_all() if tool.metadata.tool_id in supported_ids]

    def get_tool_metadata(self, tool_id: str):
        """获取工具元数据"""
        return self.registry.get(tool_id)

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        *,
        audit_context: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """执行并持久审计工具；外部写在审计不可用时关闭执行。"""
        tool = self.registry.get(tool_name) or self.registry.get_by_name(tool_name)
        metadata = getattr(tool, "metadata", None)
        is_external_write = bool(metadata and metadata.external_effect)
        audit_context = audit_context or {}
        audit_id = None

        if is_external_write and not audit_context.get("idempotency_key"):
            return ToolExecutionResult(
                tool_id=tool_name,
                success=False,
                error="外部写缺少 idempotency_key，已阻止执行",
                metadata={"error_category": "idempotency_key_missing"},
            )

        should_audit = bool(metadata and (is_external_write or audit_context.get("agent_run_id")))
        if should_audit:
            risk = metadata.risk_level.value if hasattr(metadata.risk_level, "value") else str(metadata.risk_level)
            try:
                begin = await self.audit_service.begin(
                    agent_run_id=audit_context.get("agent_run_id"),
                    thread_id=audit_context.get("thread_id"),
                    user_id=audit_context.get("user_id"),
                    tool_name=metadata.tool_id,
                    risk_level=risk,
                    operation_type=metadata.operation_type,
                    confirmation_status=audit_context.get("confirmation_status", "not_required"),
                    policy_code=audit_context.get("policy_code", "allowed"),
                    arguments=arguments,
                    idempotency_key=audit_context.get("idempotency_key"),
                )
                audit_id = begin.audit_id
                if begin.action == "replay":
                    return ToolExecutionResult(
                        tool_id=metadata.tool_id,
                        success=True,
                        result=begin.prior_result,
                        cached=True,
                        metadata={"audit_id": audit_id, "idempotent_replay": True},
                    )
                if begin.action == "blocked":
                    return ToolExecutionResult(
                        tool_id=metadata.tool_id,
                        success=False,
                        error=f"幂等门禁阻止重复执行，历史状态: {begin.prior_status}",
                        metadata={
                            "audit_id": audit_id,
                            "error_category": "idempotency_blocked",
                            "prior_status": begin.prior_status,
                        },
                    )
            except Exception as exc:
                app_logger.error("[ToolAudit] 创建审计记录失败: %s", exc)
                if is_external_write:
                    return ToolExecutionResult(
                        tool_id=metadata.tool_id,
                        success=False,
                        error="持久审计不可用，外部写已关闭",
                        metadata={"error_category": "audit_unavailable"},
                    )

        result = await self.executor.execute(
            tool_name,
            arguments,
            self.llm_service,
            self.vector_search_service,
            context={"access_scope": audit_context.get("access_scope")},
            **kwargs,
        )

        if audit_id:
            try:
                error_category = result.metadata.get("error_category") if result.metadata else None
                status = "succeeded" if result.success else "failed"
                if (
                    not result.success
                    and is_external_write
                    and not bool(getattr(metadata, "idempotent", True))
                    and error_category in {"timeout", "network", "upstream"}
                ):
                    status = "unknown"
                payload = result.result if isinstance(result.result, dict) else {"value": result.result}
                external_id = payload.get("external_id") if result.success else None
                await self.audit_service.finish(
                    audit_id,
                    status=status,
                    result=payload if result.success else None,
                    external_id=external_id,
                    error_category=error_category,
                    error_message=result.error or None,
                )
                result.metadata["audit_id"] = audit_id
                result.metadata["audit_status"] = status
            except Exception as exc:
                app_logger.error("[ToolAudit] 完成审计记录失败: %s", exc)
                if is_external_write and result.success:
                    result.metadata["audit_completion_error"] = True
        return result

    def search_tools(self, query: str):
        """搜索工具"""
        supported_ids = set(self.executor.get_supported_tool_ids())
        return [tool for tool in self.registry.search(query) if tool.metadata.tool_id in supported_ids]

    def get_tools_by_category(self, category: str):
        """按分类获取工具"""
        from app.agents.tools.tool_metadata import ToolCategory
        supported_ids = set(self.executor.get_supported_tool_ids())
        return [tool for tool in self.registry.get_by_category(ToolCategory(category)) if tool.metadata.tool_id in supported_ids]

    def get_tools_info(self) -> Dict[str, Any]:
        """获取所有工具的信息"""
        return [tool.metadata.to_dict() for tool in self.get_available_tools()]
