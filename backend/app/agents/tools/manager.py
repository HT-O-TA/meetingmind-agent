"""工具管理器 - 管理工具注册和执行"""
from typing import Optional, Dict, Any
from app.agents.tools.executor import ToolExecutor
from app.agents.tools.registry import ToolRegistry, get_tool_registry
from app.services.llm_service import LLMService
from app.services.vector_search_service import VectorSearchService


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

    def get_available_tools(self):
        """获取所有可用工具"""
        return self.registry.get_all_tools()

    def get_tool_metadata(self, tool_id: str):
        """获取工具元数据"""
        return self.registry.get_tool(tool_id)

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]):
        """执行工具"""
        return await self.executor.execute(tool_name, arguments)

    def search_tools(self, query: str):
        """搜索工具"""
        return self.registry.search_tools(query)

    def get_tools_by_category(self, category: str):
        """按分类获取工具"""
        return self.registry.get_tools_by_category(category)
