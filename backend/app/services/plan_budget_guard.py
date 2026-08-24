"""规划 Token 预算保护 - 防止 LLM 输出截断导致 JSON 不完整

功能：
1. 输入预算评估：根据问题和上下文长度预估可用输出 token
2. 任务数动态限制：token 充足时最多 8 个任务，紧张时递减
3. 提示词引导压缩：在 prompt 中引导 LLM 输出精简计划
4. 输出完整性校验：JSON 可解析性、字段完整性、任务覆盖性
5. 渐进式规划：极端复杂场景下两阶段规划
"""
import json
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from app.core.logger import app_logger


@dataclass
class BudgetEstimate:
    """Token 预算评估结果"""
    available_output_tokens: int
    recommended_max_tasks: int
    is_tight: bool
    needs_progressive: bool
    guidance_hint: str


@dataclass
class ValidationResult:
    """计划完整性校验结果"""
    is_valid: bool
    is_complete: bool
    errors: List[str]
    warnings: List[str]
    missing_fields: List[str]


class PlanBudgetGuard:
    """规划 Token 预算保护器"""

    # Token 预估常数
    AVG_CHARS_PER_TOKEN = 1.5  # 中文约 1.5 字符/token
    SYSTEM_OVERHEAD_TOKENS = 200  # 系统提示词开销
    JSON_OVERHEAD_TOKENS = 50  # JSON 结构开销
    TASK_AVG_TOKENS = 80  # 每个任务平均 token
    SAFETY_MARGIN = 0.15  # 安全边际 15%

    def __init__(
        self,
        model_max_tokens: int = 4096,
        plan_max_tasks: int = 8,
        plan_min_tokens: int = 500,
        complexity_threshold: float = 0.7,
    ):
        self._model_max_tokens = model_max_tokens
        self._plan_max_tasks = plan_max_tasks
        self._plan_min_tokens = plan_min_tokens
        self._complexity_threshold = complexity_threshold

    def evaluate(
        self,
        question: str,
        context: str = "",
        complexity_score: float = 0.5,
    ) -> BudgetEstimate:
        """评估 Token 预算，返回任务数限制和引导提示

        Args:
            question: 用户问题
            context: 上下文文本
            complexity_score: 复杂度分数 (0-1)

        Returns:
            BudgetEstimate: 预算评估结果
        """
        # Step 1: 输入预算评估
        input_tokens = self._estimate_tokens(question) + self._estimate_tokens(context)
        total_overhead = self.SYSTEM_OVERHEAD_TOKENS + self.JSON_OVERHEAD_TOKENS
        available = int(
            (self._model_max_tokens - input_tokens - total_overhead) * (1 - self.SAFETY_MARGIN)
        )
        available = max(0, available)

        is_tight = available < self._plan_min_tokens
        needs_progressive = is_tight and complexity_score > self._complexity_threshold

        # Step 2: 任务数动态限制
        if available >= self._plan_min_tokens * 4:
            # token 充足
            recommended_max = min(self._plan_max_tasks, available // self.TASK_AVG_TOKENS)
            guidance = ""
        elif available >= self._plan_min_tokens * 2:
            # token 紧张
            recommended_max = min(4, available // self.TASK_AVG_TOKENS)
            guidance = "请仅输出必要的任务，每个任务描述不超过 20 字。优先执行核心任务，次要步骤合并。"
        elif available >= self._plan_min_tokens:
            # token 极端紧张
            recommended_max = min(2, available // self.TASK_AVG_TOKENS)
            guidance = (
                "Token 预算紧张，请只输出 2 个核心任务，描述精简到 15 字以内。"
                "省略 analysis 字段，直接输出 tasks 和 execution_order。"
            )
        else:
            # token 严重不足
            recommended_max = 1
            guidance = (
                "Token 预算严重不足，请只输出 1 个综合任务，合并所有操作。"
                "输出格式：{\"tasks\":[{\"task_id\":\"task_1\",\"task_type\":\"qa\","
                "\"description\":\"综合处理\"}],\"execution_order\":[\"task_1\"]}"
            )

        recommended_max = max(1, recommended_max)

        app_logger.debug(
            f"[PlanBudgetGuard] 预算评估: available={available}, "
            f"recommended_max_tasks={recommended_max}, "
            f"is_tight={is_tight}, needs_progressive={needs_progressive}"
        )

        return BudgetEstimate(
            available_output_tokens=available,
            recommended_max_tasks=recommended_max,
            is_tight=is_tight,
            needs_progressive=needs_progressive,
            guidance_hint=guidance,
        )

    def validate(self, plan: Dict[str, Any]) -> ValidationResult:
        """校验计划完整性

        Args:
            plan: 解析后的计划字典

        Returns:
            ValidationResult: 校验结果
        """
        errors: List[str] = []
        warnings: List[str] = []
        missing_fields: List[str] = []

        # 检查必需字段
        if "tasks" not in plan:
            errors.append("计划缺少 tasks 字段")
            missing_fields.append("tasks")
            return ValidationResult(False, False, errors, warnings, missing_fields)

        tasks = plan.get("tasks", [])
        if not tasks:
            errors.append("tasks 数组为空")
            return ValidationResult(False, False, errors, warnings, missing_fields)

        # 检查每个任务的完整性
        for i, task in enumerate(tasks):
            if not isinstance(task, dict):
                errors.append(f"task[{i}] 不是字典类型")
                continue
            if "task_id" not in task:
                errors.append(f"task[{i}] 缺少 task_id")
                missing_fields.append(f"tasks[{i}].task_id")
            if "task_type" not in task:
                warnings.append(f"task[{i}] 缺少 task_type，默认为 qa")
                task["task_type"] = "qa"
            if "description" not in task:
                warnings.append(f"task[{i}] 缺少 description")

        # 检查 execution_order
        execution_order = plan.get("execution_order", [])
        task_ids = {t.get("task_id") for t in tasks if isinstance(t, dict)}
        if execution_order:
            order_set = set(execution_order)
            if order_set != task_ids:
                missing_in_order = task_ids - order_set
                extra_in_order = order_set - task_ids
                if missing_in_order:
                    errors.append(f"execution_order 缺少任务: {missing_in_order}")
                if extra_in_order:
                    warnings.append(f"execution_order 包含不存在的任务: {extra_in_order}")
        else:
            warnings.append("缺少 execution_order，将按 tasks 顺序执行")
            plan["execution_order"] = list(task_ids)

        # 检查 parallel_groups
        parallel_groups = plan.get("parallel_groups", [])
        if parallel_groups:
            all_grouped = set()
            for group in parallel_groups:
                all_grouped.update(group)
            unknown_in_groups = all_grouped - task_ids
            if unknown_in_groups:
                warnings.append(f"parallel_groups 包含不存在的任务: {unknown_in_groups}")

        is_valid = len(errors) == 0
        is_complete = is_valid and len(warnings) == 0

        return ValidationResult(is_valid, is_complete, errors, warnings, missing_fields)

    def build_progressive_prompt(
        self,
        question: str,
        context: str,
        tools_info: str,
    ) -> Tuple[str, str]:
        """构建渐进式规划的提示词

        Returns:
            (skeleton_prompt, detail_prompt): 骨架规划提示词和子任务细化提示词
        """
        skeleton_prompt = f"""你是一个任务规划专家。由于问题复杂度较高，请先输出高层执行骨架。

{tools_info}

问题：{question}

请只输出 3-4 个高层步骤，不要细化子任务。格式：
{{
    "analysis": "问题分析（简短）",
    "phases": [
        {{"phase_id": "phase_1", "description": "阶段描述", "needs_detail": true}},
        ...
    ]
}}"""

        detail_prompt = """基于以下高层骨架，请细化每个需要细化的阶段：

骨架：{skeleton}

请为每个 needs_detail=true 的阶段输出具体任务。格式：
{{
    "tasks": [...],
    "execution_order": [...],
    "parallel_groups": [...]
}}"""

        return skeleton_prompt, detail_prompt

    def _estimate_tokens(self, text: str) -> int:
        """粗略估算文本的 token 数"""
        if not text:
            return 0
        return int(len(text) / self.AVG_CHARS_PER_TOKEN)


_guard_instance: Optional[PlanBudgetGuard] = None


def get_plan_budget_guard() -> PlanBudgetGuard:
    """获取全局 PlanBudgetGuard 实例"""
    global _guard_instance
    if _guard_instance is None:
        from app.core.config import settings
        _guard_instance = PlanBudgetGuard(
            model_max_tokens=getattr(settings, "LLM_MAX_TOKENS", 4096) * 4,  # 模型上限通常远大于输出上限
            plan_max_tasks=getattr(settings, "PLAN_MAX_TASKS", 8),
            plan_min_tokens=getattr(settings, "PLAN_MIN_TOKENS", 500),
            complexity_threshold=getattr(settings, "PLAN_COMPLEXITY_THRESHOLD", 0.7),
        )
    return _guard_instance
