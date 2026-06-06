"""会议工具测试"""
import pytest
from app.agents.tools.meeting_tools import (
    MeetingSearchTool,
    TodoExtractionTool,
    MinutesGenerationTool,
    ControversyDetectionTool,
    QAAnswerTool,
    register_meeting_tools
)


class TestMeetingSearchTool:
    """会议搜索工具测试"""

    @pytest.mark.asyncio
    async def test_execute(self, mock_vector_search_service):
        """测试执行搜索"""
        tool = MeetingSearchTool(mock_vector_search_service)
        result = await tool.execute("测试查询", top_k=3)
        assert result.success
        assert isinstance(result.result, list)


class TestTodoExtractionTool:
    """待办抽取工具测试"""

    @pytest.mark.asyncio
    async def test_execute(self, mock_llm_service):
        """测试执行待办抽取"""
        tool = TodoExtractionTool(mock_llm_service)
        result = await tool.execute("会议内容")
        assert result.success
        assert isinstance(result.result, list)


class TestMinutesGenerationTool:
    """会议纪要生成工具测试"""

    @pytest.mark.asyncio
    async def test_execute(self, mock_llm_service):
        """测试执行纪要生成"""
        tool = MinutesGenerationTool(mock_llm_service)
        result = await tool.execute("会议内容", format="简略")
        assert result.success
        assert result.result is not None


class TestControversyDetectionTool:
    """争议点检测工具测试"""

    @pytest.mark.asyncio
    async def test_execute(self, mock_llm_service):
        """测试执行争议点检测"""
        tool = ControversyDetectionTool(mock_llm_service)
        result = await tool.execute("会议内容")
        assert result.success
        assert isinstance(result.result, list)


class TestQAAnswerTool:
    """问答工具测试"""

    @pytest.mark.asyncio
    async def test_execute(self, mock_llm_service):
        """测试执行问答"""
        tool = QAAnswerTool(mock_llm_service)
        result = await tool.execute("问题", "上下文")
        assert result.success
        assert result.result is not None


class TestRegisterMeetingTools:
    """会议工具注册测试"""

    def test_register_tools(self, mock_llm_service, mock_vector_search_service):
        """测试注册会议工具"""
        register_meeting_tools(mock_llm_service, mock_vector_search_service)
        from app.agents.tools.registry import get_tool_registry
        registry = get_tool_registry()
        tools = registry.get_all()
        assert len(tools) > 0
