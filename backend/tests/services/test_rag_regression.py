"""RAG 回归测试模块测试"""
import pytest
from app.services.rag_regression import (
    get_rag_regression_tester,
    run_regression_test,
    run_single_test,
    establish_baseline
)


class TestRagRegression:
    """RAG 回归测试类"""

    @pytest.mark.asyncio
    async def test_run_regression_test(self):
        """测试运行回归测试"""
        result = await run_regression_test()
        assert isinstance(result, dict)
        assert "overall" in result
        assert "tests" in result

    @pytest.mark.asyncio
    async def test_run_single_test(self):
        """测试运行单个测试用例"""
        result = await run_single_test("test_rag_response")
        assert isinstance(result, dict)
        assert "passed" in result

    @pytest.mark.asyncio
    async def test_establish_baseline(self):
        """测试建立基线"""
        result = await establish_baseline()
        assert isinstance(result, dict)
        assert "baseline_id" in result

    def test_get_rag_regression_tester(self):
        """测试获取回归测试器"""
        tester = get_rag_regression_tester()
        assert tester is not None
        assert hasattr(tester, 'run_regression')
