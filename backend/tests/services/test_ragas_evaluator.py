"""RAGAS 评估器测试"""
import pytest
from app.services.ragas_evaluator import (
    get_ragas_evaluator,
    evaluate_rag_response,
    evaluate_batch,
    get_evaluation_statistics
)


class TestRagasEvaluator:
    """RAGAS 评估器测试类"""

    @pytest.mark.asyncio
    async def test_evaluate_rag_response(self):
        """测试评估单个 RAG 响应"""
        result = await evaluate_rag_response(
            query="测试问题",
            answer="测试回答",
            contexts=["上下文1", "上下文2"],
            ground_truth="真实答案"
        )
        assert isinstance(result, dict)
        assert "metrics" in result
        assert "avg_score" in result

    @pytest.mark.asyncio
    async def test_evaluate_batch(self):
        """测试批量评估"""
        items = [
            {
                "query": "测试问题1",
                "answer": "测试回答1",
                "contexts": ["上下文1"],
                "ground_truth": "真实答案1"
            },
            {
                "query": "测试问题2",
                "answer": "测试回答2",
                "contexts": ["上下文2"],
                "ground_truth": "真实答案2"
            }
        ]
        result = await evaluate_batch(items)
        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_evaluation_statistics(self):
        """测试获取评估统计"""
        result = await get_evaluation_statistics()
        assert isinstance(result, dict)
        assert "total_evaluations" in result
        assert "average_scores" in result

    def test_get_ragas_evaluator(self):
        """测试获取评估器"""
        evaluator = get_ragas_evaluator()
        assert evaluator is not None
        assert hasattr(evaluator, 'evaluate')
