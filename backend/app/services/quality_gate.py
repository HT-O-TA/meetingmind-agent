"""统一质量门禁 - 合并 replan 和 reflection 的评估逻辑，消除双重 LLM 调用

功能：
1. Gate 1: 结构性检查（确定性，无 LLM）
2. Gate 2: 质量评估（单次 LLM 调用）
3. 决策分支：score < 0.5 → replan | 0.5-0.7 → polish | >= 0.7 → pass
4. 失败边界：评估器不可用时返回明确降级结果
"""
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from app.core.config import settings
from app.core.logger import app_logger


@dataclass
class QualityGateResult:
    """质量门禁评估结果"""
    quality_score: float = 0.0
    needs_replan: bool = False
    needs_polish: bool = False
    passed: bool = False
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    polishing_prompt: str = ""
    replan_prompt: str = ""
    dimensions: Dict[str, float] = field(default_factory=dict)
    structural_errors: List[str] = field(default_factory=list)
    evaluation_method: str = "unified"  # unified / legacy


QUALITY_GATE_PROMPT = """请从以下5个通用维度评估 Agent 执行结果的质量：

【评估标准】
1. 任务达成度 (task_completion): 用户的问题是否被有效解决，0.0-1.0
2. 正确性 (correctness): 内容是否准确，没有错误或误导性信息，0.0-1.0
3. 流程效率 (process_efficiency): 执行过程是否高效，是否有不必要的步骤，0.0-1.0
4. 表达 (expression): 表达是否清晰、通顺、易懂，0.0-1.0
5. 风险 (risk): 是否存在潜在风险（如信息泄露、错误引导、逻辑漏洞等），0.0-1.0（注意：风险越小，分数越高）

【权重配置】
- 任务达成度: 35%
- 正确性: 25%
- 流程效率: 15%
- 表达: 15%
- 风险: 10%

【特别注意】
- 如果问题是要求"总结"、"主要讲了什么"等摘要类问题，但回答只是直接复制原文而没有进行概括提炼，任务达成度应低于0.5
- 如果回答只是原文的简单重复，没有提取核心要点，任务达成度和表达应低于0.5

【用户问题】{question}

【执行结果】
- 回答：{answer_preview}
- 纪要：{minutes_preview}
- 待办：{todo_count} 个
- 争议点：{controversy_count} 个
- 当前重试次数：{retry_count}/{max_retries}

请输出 JSON，确保所有分数都在 0.0-1.0 之间：
{{
    "overall_score": 0.7,
    "metrics": {{
        "task_completion": 0.7,
        "correctness": 0.8,
        "process_efficiency": 0.6,
        "expression": 0.8,
        "risk": 0.9
    }},
    "confidence": 0.8,
    "issues": ["具体问题列表"],
    "suggestions": ["具体改进建议"],
    "needs_replan": false,
    "needs_polish": true,
    "polishing_prompt": "如果需要抛光，给出改进指令（不需要则为空）",
    "replan_prompt": "如果需要重规划，给出新计划方向（不需要则为空）"
}}"""


class QualityGate:
    """统一质量门禁 - 单次 LLM 评估替代 replan+reflection 双重评估"""

    def __init__(
        self,
        replan_threshold: float = 0.5,
        polish_threshold: float = 0.7,
        max_retries: int = 2,
    ):
        self._replan_threshold = replan_threshold
        self._polish_threshold = polish_threshold
        self._max_retries = max_retries

    async def evaluate(
        self,
        state: Dict[str, Any],
        llm_service: Optional[Any] = None,
    ) -> QualityGateResult:
        """执行统一质量评估

        Args:
            state: AgentState
            llm_service: LLM 服务实例

        Returns:
            QualityGateResult: 评估结果
        """
        question = state.get("question", "")
        answer = state.get("answer", "")
        minutes = state.get("minutes", "")
        todos = state.get("todos", [])
        controversies = state.get("controversies", [])

        if not isinstance(answer, str):
            answer = ""
        if not isinstance(minutes, str):
            minutes = ""
        if not isinstance(todos, list):
            todos = []
        if not isinstance(controversies, list):
            controversies = []

        # Gate 1: 结构性检查（确定性，无 LLM）
        structural_errors = self._structural_check(state)
        if structural_errors:
            app_logger.warning(
                f"[QualityGate] 结构性检查失败: {structural_errors}"
            )

        # 获取重试计数
        reflection = state.get("reflection") or {}
        retry_count = int(reflection.get("retry_count", 0)) if reflection else 0

        # 如果已达最大重试次数，不再触发 replan
        can_retry = retry_count < self._max_retries

        # Gate 2: LLM 质量评估
        if llm_service and answer:
            result = await self._llm_evaluate(
                question=question,
                answer=answer,
                minutes=minutes,
                todos=todos,
                controversies=controversies,
                retry_count=retry_count,
                llm_service=llm_service,
                structural_errors=structural_errors,
                can_retry=can_retry,
            )
        else:
            # 无 LLM 或无 answer，走降级评估
            result = self._fallback_evaluate(
                answer=answer,
                structural_errors=structural_errors,
                can_retry=can_retry,
            )

        return result

    async def _llm_evaluate(
        self,
        question: str,
        answer: str,
        minutes: str,
        todos: list,
        controversies: list,
        retry_count: int,
        llm_service: Any,
        structural_errors: List[str],
        can_retry: bool,
    ) -> QualityGateResult:
        """LLM 质量评估"""
        prompt = QUALITY_GATE_PROMPT.format(
            question=question,
            answer_preview=answer[:500] if answer else "无",
            minutes_preview=minutes[:500] if minutes else "无",
            todo_count=len(todos),
            controversy_count=len(controversies),
            retry_count=retry_count,
            max_retries=self._max_retries,
        )

        messages = [
            {
                "role": "system",
                "content": "你是专业的质量评估专家，擅长从多个维度评估 AI 输出质量，并决定后续操作（重规划/抛光/通过）。",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            response = await llm_service.chat(
                messages=messages,
                model=settings.QUALITY_GATE_MODEL,
                temperature=0.3,
            )
            return self._parse_llm_result(
                response, structural_errors, can_retry, retry_count
            )
        except Exception as e:
            app_logger.error(f"[QualityGate] LLM 评估失败: {e}")
            return self._fallback_evaluate(answer, structural_errors, can_retry)

    def _parse_llm_result(
        self,
        response: str,
        structural_errors: List[str],
        can_retry: bool,
        retry_count: int,
    ) -> QualityGateResult:
        """解析 LLM 返回结果"""
        try:
            # 尝试提取 JSON
            json_str = response.strip()
            if json_str.startswith("```"):
                json_str = json_str.split("\n", 1)[-1]
                if json_str.endswith("```"):
                    json_str = json_str[:-3]
            data = json.loads(json_str.strip())
        except (json.JSONDecodeError, IndexError):
            app_logger.warning("[QualityGate] LLM 返回解析失败，走降级评估")
            return self._fallback_evaluate(response, structural_errors, can_retry)

        weights = {
            "task_completion": 0.35,
            "correctness": 0.25,
            "process_efficiency": 0.15,
            "expression": 0.15,
            "risk": 0.10,
        }
        raw_dimensions = data.get("metrics", {})
        dimensions = {}
        if isinstance(raw_dimensions, dict):
            for name in weights:
                value = raw_dimensions.get(name, 0.0)
                try:
                    dimensions[name] = max(0.0, min(1.0, float(value)))
                except (TypeError, ValueError):
                    dimensions[name] = 0.0

        has_all_dimensions = isinstance(raw_dimensions, dict) and all(
            name in raw_dimensions for name in weights
        )
        if has_all_dimensions:
            score = sum(dimensions[name] * weight for name, weight in weights.items())
        else:
            try:
                score = max(0.0, min(1.0, float(data.get("overall_score", 0.5))))
            except (TypeError, ValueError):
                score = 0.5
        needs_replan_flag = bool(data.get("needs_replan", False))
        needs_polish_flag = bool(data.get("needs_polish", False))

        # 结构性错误影响评分
        if structural_errors:
            score = min(score, 0.6)
            needs_replan_flag = needs_replan_flag or can_retry

        # 根据阈值确定最终决策
        if score < self._replan_threshold and can_retry:
            needs_replan_flag = True
            needs_polish_flag = False
        elif score < self._polish_threshold:
            needs_polish_flag = True
            needs_replan_flag = False
        else:
            needs_replan_flag = False
            needs_polish_flag = False

        result = QualityGateResult(
            quality_score=score,
            needs_replan=needs_replan_flag,
            needs_polish=needs_polish_flag,
            passed=not needs_replan_flag and not needs_polish_flag,
            issues=data.get("issues", []),
            suggestions=data.get("suggestions", []),
            polishing_prompt=data.get("polishing_prompt", ""),
            replan_prompt=data.get("replan_prompt", ""),
            dimensions=dimensions,
            structural_errors=structural_errors,
            evaluation_method="unified",
        )

        app_logger.info(
            f"[QualityGate] 评估完成: score={score:.2f}, "
            f"replan={result.needs_replan}, polish={result.needs_polish}, "
            f"passed={result.passed}, retry={retry_count}/{self._max_retries}"
        )

        return result

    def _structural_check(self, state: Dict[str, Any]) -> List[str]:
        """结构性检查（确定性，无 LLM）"""
        errors: List[str] = []
        task_type = state.get("task_type")
        answer = state.get("answer", "")
        minutes = state.get("minutes", "")
        todos = state.get("todos", [])
        controversies = state.get("controversies", [])

        # 答案非空检查
        if not answer or not answer.strip():
            errors.append("answer 为空")

        # 根据任务类型做结构校验
        from app.agents.state import TaskType
        task_type_str = task_type.value if hasattr(task_type, "value") else str(task_type)

        if task_type_str == "minutes" or "minutes" in task_type_str:
            if not minutes or not minutes.strip():
                errors.append("minutes 为空但任务类型为会议纪要")

        if task_type_str == "todo" or "todo" in task_type_str:
            if not todos:
                errors.append("todos 为空但任务类型为待办提取")

        if task_type_str == "controversy" or "controversy" in task_type_str:
            if not controversies:
                errors.append("controversies 为空但任务类型为争议识别")

        return errors

    def _fallback_evaluate(
        self,
        answer: str,
        structural_errors: List[str],
        can_retry: bool,
    ) -> QualityGateResult:
        """降级评估（无 LLM 时）"""
        if structural_errors and can_retry:
            return QualityGateResult(
                quality_score=0.3,
                needs_replan=True,
                needs_polish=False,
                passed=False,
                issues=structural_errors,
                suggestions=["请修复结构性问题后重试"],
                structural_errors=structural_errors,
                evaluation_method="fallback",
            )

        if answer and len(answer) > 50:
            return QualityGateResult(
                quality_score=0.6,
                needs_replan=False,
                needs_polish=True,
                passed=False,
                issues=structural_errors,
                structural_errors=structural_errors,
                evaluation_method="fallback",
            )

        return QualityGateResult(
            quality_score=0.5,
            needs_replan=False,
            needs_polish=False,
            passed=True,
            structural_errors=structural_errors,
            evaluation_method="fallback",
        )


_gate_instance: Optional[QualityGate] = None


def get_quality_gate() -> QualityGate:
    """获取全局 QualityGate 实例"""
    global _gate_instance
    if _gate_instance is None:
        _gate_instance = QualityGate(
            replan_threshold=getattr(settings, "QUALITY_GATE_REPLAN_THRESHOLD", 0.5),
            polish_threshold=getattr(settings, "QUALITY_GATE_POLISH_THRESHOLD", 0.7),
            max_retries=1,
        )
    return _gate_instance
