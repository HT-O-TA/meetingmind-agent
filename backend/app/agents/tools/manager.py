"""工具管理器 - 管理工具注册和执行"""
from typing import Optional, Dict, Any
from app.agents.tools.executor import ToolExecutor
from app.agents.tools.registry import get_tool_registry
from app.agents.tools.meeting_tools import register_meeting_tools
from app.services.llm_service import LLMService
from app.services.vector_search_service import VectorSearchService
from app.core.logger import app_logger


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
        
        # 注册会议相关工具
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
        return self.registry.get_all()

    def get_tool_metadata(self, tool_id: str):
        """获取工具元数据"""
        return self.registry.get(tool_id)

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]):
        """执行工具"""
        return await self.executor.execute(tool_name, arguments, self.llm_service, self.vector_search_service)

    def search_tools(self, query: str):
        """搜索工具"""
        return self.registry.search(query)

    def get_tools_by_category(self, category: str):
        """按分类获取工具"""
        from app.agents.tools.tool_metadata import ToolCategory
        return self.registry.get_by_category(ToolCategory(category))

    def get_tools_info(self) -> Dict[str, Any]:
        """获取所有工具的信息"""
        return self.registry.get_all_metadata()
