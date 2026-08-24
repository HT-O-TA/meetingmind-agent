"""LLM深度评估服务 - 多维度回答质量评估"""
import asyncio
from typing import Dict, Any, List
from enum import Enum
from pydantic import BaseModel
from app.services.llm_service import LLMService


class EvaluationDimension(str, Enum):
    ACCURACY = "accuracy"
    RELEVANCE = "relevance"
    COMPLETENESS = "completeness"
    COHERENCE = "coherence"
    CONSISTENCY = "consistency"
    HALLUCINATION = "hallucination"


class EvaluationResult(BaseModel):
    dimension: EvaluationDimension
    score: float
    explanation: str
    passed: bool


class OverallEvaluation(BaseModel):
    scores: Dict[str, float]
    explanations: Dict[str, str]
    overall_score: float
    passed: bool
    suggestions: List[str]


class EvaluationService:
    def __init__(self):
        self.llm_service = LLMService()
        self.thresholds = {
            EvaluationDimension.ACCURACY: 0.7,
            EvaluationDimension.RELEVANCE: 0.7,
            EvaluationDimension.COMPLETENESS: 0.6,
            EvaluationDimension.COHERENCE: 0.7,
            EvaluationDimension.CONSISTENCY: 0.8,
            EvaluationDimension.HALLUCINATION: 0.7,
        }

    async def evaluate_answer(
        self,
        question: str,
        answer: str,
        contexts: List[str],
    ) -> OverallEvaluation:
        """
        多维度评估回答质量

        Args:
            question: 用户问题
            answer: 生成的回答
            contexts: 检索到的上下文文档列表

        Returns:
            综合评估结果
        """
        context_text = "\n\n".join([f"文档{i+1}:\n{c}" for i, c in enumerate(contexts)])

        evaluation_prompt = f"""
你是一个专业的问答系统评估专家，请根据以下标准对回答进行多维度评估：

**评估维度说明：**
1. **准确性(accuracy)**：回答是否与上下文事实一致，无错误信息
2. **相关性(relevance)**：回答是否直接针对用户问题，无无关内容
3. **完整性(completeness)**：回答是否覆盖了问题的所有关键点，无重要信息遗漏
4. **连贯性(coherence)**：回答逻辑是否清晰，语句是否通顺
5. **一致性(consistency)**：回答内部是否存在矛盾，前后表述是否一致
6. **抗幻觉(hallucination)**：回答是否包含上下文未提及的虚假信息

**评分标准**：0-1分，0表示最差，1表示最优

**输入数据：**
问题：{question}

回答：{answer}

上下文：
{context_text}

请按照JSON格式输出评估结果，格式如下：
{{
    "accuracy": {{"score": 0.0-1.0, "explanation": "评估理由"}},
    "relevance": {{"score": 0.0-1.0, "explanation": "评估理由"}},
    "completeness": {{"score": 0.0-1.0, "explanation": "评估理由"}},
    "coherence": {{"score": 0.0-1.0, "explanation": "评估理由"}},
    "consistency": {{"score": 0.0-1.0, "explanation": "评估理由"}},
    "hallucination": {{"score": 0.0-1.0, "explanation": "评估理由"}},
    "suggestions": ["改进建议1", "改进建议2"]
}}
"""

        response = await self.llm_service.generate_text(
            prompt=evaluation_prompt,
            max_tokens=2000,
            temperature=0,
        )

        try:
            import json
            result = json.loads(response)
        except:
            result = self._parse_fallback(response)

        scores = {}
        explanations = {}
        passed_dimensions = []

        for dim in EvaluationDimension:
            dim_key = dim.value
            if dim_key in result:
                scores[dim_key] = float(result[dim_key].get("score", 0))
                explanations[dim_key] = result[dim_key].get("explanation", "")
                if scores[dim_key] >= self.thresholds[dim]:
                    passed_dimensions.append(dim_key)

        overall_score = sum(scores.values()) / len(scores) if scores else 0
        passed = overall_score >= 0.7 and len(passed_dimensions) >= 4

        suggestions = result.get("suggestions", [])

        return OverallEvaluation(
            scores=scores,
            explanations=explanations,
            overall_score=overall_score,
            passed=passed,
            suggestions=suggestions,
        )

    def _parse_fallback(self, text: str) -> Dict[str, Any]:
        """解析失败时的降级处理"""
        return {
            "accuracy": {"score": 0.5, "explanation": "解析失败"},
            "relevance": {"score": 0.5, "explanation": "解析失败"},
            "completeness": {"score": 0.5, "explanation": "解析失败"},
            "coherence": {"score": 0.5, "explanation": "解析失败"},
            "consistency": {"score": 0.5, "explanation": "解析失败"},
            "hallucination": {"score": 0.5, "explanation": "解析失败"},
            "suggestions": ["评估解析失败，请检查输出格式"],
        }

    async def batch_evaluate(
        self,
        items: List[Dict[str, Any]],
    ) -> List[OverallEvaluation]:
        """批量评估"""
        tasks = [
            self.evaluate_answer(
                question=item["question"],
                answer=item["answer"],
                contexts=item["contexts"],
            )
            for item in items
        ]
        return await asyncio.gather(*tasks)


evaluation_service = EvaluationService()
