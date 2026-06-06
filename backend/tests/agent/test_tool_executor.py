"""工具执行器测试"""
import pytest
from app.agents.tools.executor import ToolExecutor


class TestToolExecutor:
    """工具执行器测试类"""

    def test_initialization(self):
        """测试初始化"""
        executor = ToolExecutor()
        assert executor is not None

    @pytest.mark.asyncio
    async def test_execute_nonexistent_tool(self):
        """测试执行不存在的工具"""
        executor = ToolExecutor()
        result = await executor.execute("nonexistent_tool", {})
        assert not result.success
        assert "不存在" in result.error

    @pytest.mark.asyncio
    async def test_execute_batch(self):
        """测试批量执行"""
        executor = ToolExecutor()
        tasks = [
            {"tool_id": "search_meeting", "params": {"query": "test1"}},
            {"tool_id": "search_meeting", "params": {"query": "test2"}}
        ]
        results = await executor.execute_batch(tasks)
        assert isinstance(results, list)
        assert len(results) == 2

    def test_generate_cache_key(self):
        """测试生成缓存键"""
        executor = ToolExecutor()
        key1 = executor._generate_cache_key("tool1", {"a": 1, "b": 2})
        key2 = executor._generate_cache_key("tool1", {"b": 2, "a": 1})
        assert key1 == key2

    def test_clear_cache(self):
        """测试清除缓存"""
        executor = ToolExecutor()
        executor._cache = {"key1": "value1", "key2": "value2"}
        executor.clear_cache()
        assert len(executor._cache) == 0

    def test_get_statistics(self):
        """测试获取统计信息"""
        executor = ToolExecutor()
        stats = executor.get_statistics()
        assert isinstance(stats, dict)
        assert "total_executions" in stats
        assert "success_rate" in stats
