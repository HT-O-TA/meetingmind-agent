"""工具管理器测试"""
import pytest
from app.agents.tools.manager import ToolManager
from app.agents.tools.meeting_tools import register_meeting_tools


class TestToolManager:
    """工具管理器测试类"""

    def test_get_available_tools(self, mock_llm_service, mock_vector_search_service):
        """测试获取可用工具"""
        manager = ToolManager(mock_llm_service, mock_vector_search_service)
        tools = manager.get_available_tools()
        assert isinstance(tools, list)

    def test_get_tool_metadata(self, mock_llm_service, mock_vector_search_service):
        """测试获取工具元数据"""
        manager = ToolManager(mock_llm_service, mock_vector_search_service)
        metadata = manager.get_tool_metadata("search_meeting")
        assert metadata is not None

    @pytest.mark.asyncio
    async def test_execute_tool(self, mock_llm_service, mock_vector_search_service):
        """测试执行工具"""
        manager = ToolManager(mock_llm_service, mock_vector_search_service)
        result = await manager.execute_tool("search_meeting", {"query": "测试"})
        assert result is not None

    def test_search_tools(self, mock_llm_service, mock_vector_search_service):
        """测试搜索工具"""
        manager = ToolManager(mock_llm_service, mock_vector_search_service)
        results = manager.search_tools("搜索")
        assert isinstance(results, list)

    def test_get_tools_by_category(self, mock_llm_service, mock_vector_search_service):
        """测试按分类获取工具"""
        manager = ToolManager(mock_llm_service, mock_vector_search_service)
        tools = manager.get_tools_by_category("SEARCH")
        assert isinstance(tools, list)
