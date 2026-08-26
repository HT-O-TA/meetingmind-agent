"""会议工具测试"""
import pytest
from app.agents.tools.meeting_tools import (
    MeetingSearchTool,
    TodoExtractionTool,
    MinutesGenerationTool,
    ControversyDetectionTool,
    DocumentContentTool,
    DocumentSearchTool,
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

    @pytest.mark.asyncio
    async def test_acl_scope_is_forwarded_to_formal_retrieval(self, mock_vector_search_service):
        tool = MeetingSearchTool(mock_vector_search_service)

        result = await tool.execute(
            "私有会议",
            access_scope={"user_id": 7, "department": "AI", "document_scope": [3, 5]},
        )

        assert result.success
        access_context = mock_vector_search_service.search_with_multi_retrieval.await_args.kwargs[
            "access_context"
        ]
        assert access_context.user_id == 7
        assert access_context.department == "AI"
        assert access_context.document_scope == [3, 5]


class TestDocumentReadTools:
    @pytest.mark.asyncio
    async def test_content_read_cannot_bypass_acl(self, mock_vector_search_service):
        tool = DocumentContentTool(mock_vector_search_service)

        result = await tool.execute(
            3,
            access_scope={"user_id": 9, "document_scope": [3], "allow_public": False},
        )

        assert result.success
        access_context = mock_vector_search_service.get_document_chunks.await_args.kwargs[
            "access_context"
        ]
        assert access_context.user_id == 9
        assert access_context.document_scope == [3]
        assert access_context.allow_public is False

    @pytest.mark.asyncio
    async def test_document_search_forwards_acl_and_requested_scope(self, mock_vector_search_service):
        tool = DocumentSearchTool(mock_vector_search_service)

        result = await tool.execute(
            "评审结论",
            document_ids=[3],
            access_scope={"user_id": 9, "document_scope": [3]},
        )

        assert result.success
        call = mock_vector_search_service.search_with_multi_retrieval.await_args
        assert call.kwargs["document_ids"] == [3]
        assert call.kwargs["access_context"].user_id == 9


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
