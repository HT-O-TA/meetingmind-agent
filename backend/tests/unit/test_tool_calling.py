"""单元测试 - 工具调用系统"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.agents.tools.base import (
    ToolCategory, ToolStatus, ToolParameter, ToolDefinition,
    ToolCall, ToolResult, BaseTool, ToolRegistry, ToolExecutor, ToolSelector
)


class TestToolCategory:
    def test_all_categories(self):
        categories = [cat.value for cat in ToolCategory]
        assert "search" in categories
        assert "retrieve" in categories
        assert "generate" in categories
        assert "extract" in categories
        assert "format" in categories
        assert "utility" in categories


class TestToolStatus:
    def test_all_statuses(self):
        statuses = [status.value for status in ToolStatus]
        assert "pending" in statuses
        assert "running" in statuses
        assert "success" in statuses
        assert "failed" in statuses
        assert "timeout" in statuses


class TestToolParameter:
    def test_parameter_creation(self):
        param = ToolParameter(
            name="query",
            description="搜索查询",
            type="string",
            required=True
        )
        assert param.name == "query"
        assert param.description == "搜索查询"
        assert param.type == "string"
        assert param.required is True

    def test_parameter_with_default(self):
        param = ToolParameter(
            name="limit",
            description="数量限制",
            type="number",
            required=False,
            default=10
        )
        assert param.default == 10
        assert param.required is False

    def test_parameter_with_enum(self):
        param = ToolParameter(
            name="sort_by",
            description="排序字段",
            type="string",
            required=False,
            enum=["date", "relevance", "score"]
        )
        assert param.enum == ["date", "relevance", "score"]


class TestToolDefinition:
    def test_definition_creation(self):
        params = [
            ToolParameter(name="query", description="查询词", type="string"),
            ToolParameter(name="limit", description="数量", type="number", required=False)
        ]
        tool_def = ToolDefinition(
            name="search_tool",
            description="搜索工具",
            category=ToolCategory.SEARCH,
            parameters=params,
            examples=["search_tool(query='会议记录')"],
            timeout=30
        )
        
        assert tool_def.name == "search_tool"
        assert tool_def.description == "搜索工具"
        assert tool_def.category == ToolCategory.SEARCH
        assert len(tool_def.parameters) == 2
        assert tool_def.timeout == 30

    def test_to_openai_format(self):
        params = [
            ToolParameter(name="query", description="查询词", type="string"),
            ToolParameter(name="limit", description="数量", type="number", required=False, default=10)
        ]
        tool_def = ToolDefinition(
            name="search_tool",
            description="搜索工具",
            category=ToolCategory.SEARCH,
            parameters=params
        )
        
        openai_format = tool_def.to_openai_format()
        
        assert openai_format["type"] == "function"
        assert openai_format["function"]["name"] == "search_tool"
        assert openai_format["function"]["description"] == "搜索工具"
        assert "query" in openai_format["function"]["parameters"]["properties"]
        assert "limit" in openai_format["function"]["parameters"]["properties"]
        assert openai_format["function"]["parameters"]["required"] == ["query"]


class MockTool(BaseTool):
    """用于测试的Mock工具"""
    def get_definition(self):
        return ToolDefinition(
            name="mock_tool",
            description="Mock工具",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter(name="input", description="输入", type="string")
            ]
        )
    
    async def execute(self, **kwargs):
        input_val = kwargs.get("input", "")
        return ToolResult(
            success=True,
            tool_name="mock_tool",
            result=f"processed: {input_val}"
        )


class TestBaseTool:
    @pytest.mark.asyncio
    async def test_run_success(self):
        tool = MockTool()
        result = await tool.run({"input": "test"})
        
        assert result.success is True
        assert result.tool_name == "mock_tool"
        assert result.result == "processed: test"
        assert result.execution_time >= 0

    @pytest.mark.asyncio
    async def test_run_with_exception(self):
        class FailingTool(BaseTool):
            def get_definition(self):
                return ToolDefinition(name="failing", description="失败工具", category=ToolCategory.UTILITY)
            
            async def execute(self, **kwargs):
                raise ValueError("测试错误")
        
        tool = FailingTool()
        result = await tool.run({})
        
        assert result.success is False
        assert result.error == "测试错误"


class TestToolRegistry:
    def test_register_and_get(self):
        registry = ToolRegistry()
        tool = MockTool()
        
        registry.register(tool)
        retrieved = registry.get("mock_tool")
        
        assert retrieved is not None
        assert retrieved.definition.name == "mock_tool"

    def test_get_nonexistent_tool(self):
        registry = ToolRegistry()
        result = registry.get("nonexistent")
        assert result is None

    def test_get_by_category(self):
        registry = ToolRegistry()
        tool = MockTool()
        registry.register(tool)
        
        tools = registry.get_by_category(ToolCategory.UTILITY)
        assert len(tools) == 1
        assert tools[0].definition.name == "mock_tool"

    def test_list_all(self):
        registry = ToolRegistry()
        tool = MockTool()
        registry.register(tool)
        
        definitions = registry.list_all()
        assert len(definitions) == 1
        assert definitions[0].name == "mock_tool"

    def test_get_openai_tools(self):
        registry = ToolRegistry()
        tool = MockTool()
        registry.register(tool)
        
        openai_tools = registry.get_openai_tools()
        assert len(openai_tools) == 1
        assert openai_tools[0]["function"]["name"] == "mock_tool"


class TestToolExecutor:
    @pytest.mark.asyncio
    async def test_execute_tool(self):
        registry = ToolRegistry()
        tool = MockTool()
        registry.register(tool)
        
        executor = ToolExecutor(registry)
        result = await executor.execute("mock_tool", {"input": "test input"})
        
        assert result.success is True
        assert result.result == "processed: test input"

    @pytest.mark.asyncio
    async def test_execute_nonexistent_tool(self):
        registry = ToolRegistry()
        executor = ToolExecutor(registry)
        
        result = await executor.execute("nonexistent", {})
        
        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_execute_multiple(self):
        registry = ToolRegistry()
        tool = MockTool()
        registry.register(tool)
        
        executor = ToolExecutor(registry)
        calls = [
            {"name": "mock_tool", "arguments": {"input": "a"}},
            {"name": "mock_tool", "arguments": {"input": "b"}}
        ]
        
        results = await executor.execute_multiple(calls)
        
        assert len(results) == 2
        assert results[0].success is True
        assert results[1].success is True

    def test_get_history(self):
        registry = ToolRegistry()
        tool = MockTool()
        registry.register(tool)
        
        executor = ToolExecutor(registry)
        
        # 执行多个调用
        import asyncio
        asyncio.run(executor.execute("mock_tool", {"input": "first"}))
        asyncio.run(executor.execute("mock_tool", {"input": "second"}))
        
        history = executor.get_history(limit=1)
        assert len(history) == 1
        assert history[0]["tool_name"] == "mock_tool"

    def test_clear_history(self):
        registry = ToolRegistry()
        tool = MockTool()
        registry.register(tool)
        
        executor = ToolExecutor(registry)
        
        import asyncio
        asyncio.run(executor.execute("mock_tool", {"input": "test"}))
        
        executor.clear_history()
        history = executor.get_history()
        assert len(history) == 0


class TestToolSelector:
    def test_select_by_intent(self):
        registry = ToolRegistry()
        search_tool = MockTool()
        registry.register(search_tool)
        
        selector = ToolSelector(registry)
        
        # 测试意图匹配
        result = selector.select_by_intent("请搜索会议记录")
        assert "mock_tool" in result

    def test_format_tools_for_prompt(self):
        registry = ToolRegistry()
        tool = MockTool()
        registry.register(tool)
        
        selector = ToolSelector(registry)
        prompt = selector.format_tools_for_prompt()
        
        assert "可用工具：" in prompt
        assert "mock_tool" in prompt
        assert "Mock工具" in prompt
