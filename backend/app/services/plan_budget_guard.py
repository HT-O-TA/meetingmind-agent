"""规划 Token 预算保护 - 防止 LLM 输出截断导致 JSON 不完整

功能：
1. 输入预算评估：根据问题和上下文长度预估可用输出 token
2. 任务数动态限制：token 充足时最多 8 个任务，紧张时递减
3. 提示词引导压缩：在 prompt 中引导 LLM 输出精简计划
4. 输出完整性校验：JSON 可解析性、字段完整性、任务覆盖性
5. 渐进式规划：极端复杂场景下两阶段规划
"""
import json
from typing import Dict, List, Optional, Tuple, Any, Iterable, Set
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

    def validate(
        self,
        plan: Dict[str, Any],
        *,
        available_tools: Optional[Iterable[str]] = None,
        max_tasks: Optional[int] = None,
    ) -> ValidationResult:
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
        if not isinstance(plan, dict):
            return ValidationResult(False, False, ["计划必须是对象"], warnings, missing_fields)
        if "tasks" not in plan:
            errors.append("计划缺少 tasks 字段")
            missing_fields.append("tasks")
            return ValidationResult(False, False, errors, warnings, missing_fields)

        tasks = plan.get("tasks", [])
        if not isinstance(tasks, list):
            errors.append("tasks 必须是数组")
            return ValidationResult(False, False, errors, warnings, missing_fields)
        if not tasks:
            errors.append("tasks 数组为空")
            return ValidationResult(False, False, errors, warnings, missing_fields)

        limit = int(max_tasks or self._plan_max_tasks)
        if len(tasks) > limit:
            errors.append(f"任务数 {len(tasks)} 超过当前上限 {limit}")

        # 检查每个任务的完整性、ID 唯一性和依赖引用
        task_ids: List[str] = []
        for i, task in enumerate(tasks):
            if not isinstance(task, dict):
                errors.append(f"task[{i}] 不是字典类型")
                continue
            task_id = str(task.get("task_id") or "").strip()
            if not task_id:
                errors.append(f"task[{i}] 缺少 task_id")
                missing_fields.append(f"tasks[{i}].task_id")
            elif task_id in task_ids:
                errors.append(f"task_id 重复: {task_id}")
            else:
                task_ids.append(task_id)
            if "task_type" not in task:
                warnings.append(f"task[{i}] 缺少 task_type，默认为 qa")
                task["task_type"] = "qa"
            if "description" not in task:
                warnings.append(f"task[{i}] 缺少 description")
            dependencies = task.get("dependencies", [])
            if dependencies is None:
                dependencies = []
                task["dependencies"] = dependencies
            if not isinstance(dependencies, list):
                errors.append(f"任务 {task_id or i} 的 dependencies 必须是数组")
            else:
                for dependency in dependencies:
                    if str(dependency) not in task_ids and not any(
                        isinstance(candidate, dict) and str(candidate.get("task_id") or "") == str(dependency)
                        for candidate in tasks
                    ):
                        errors.append(f"任务 {task_id or i} 依赖不存在: {dependency}")

        # 检查 execution_order
        task_id_set: Set[str] = set(task_ids)
        execution_order = plan.get("execution_order", [])
        if execution_order is None:
            execution_order = []
        if not isinstance(execution_order, list):
            errors.append("execution_order 必须是数组")
            execution_order = []
        if execution_order:
            order_values = [str(value) for value in execution_order]
            if len(order_values) != len(set(order_values)):
                errors.append("execution_order 包含重复任务")
            order_set = set(order_values)
            missing_in_order = task_id_set - order_set
            extra_in_order = order_set - task_id_set
            if missing_in_order:
                errors.append(f"execution_order 缺少任务: {sorted(missing_in_order)}")
            if extra_in_order:
                errors.append(f"execution_order 包含不存在的任务: {sorted(extra_in_order)}")
            position = {task_id: index for index, task_id in enumerate(order_values)}
            for task in tasks:
                if not isinstance(task, dict):
                    continue
                task_id = str(task.get("task_id") or "")
                for dependency in task.get("dependencies", []) or []:
                    dep_id = str(dependency)
                    if dep_id in position and task_id in position and position[dep_id] > position[task_id]:
                        errors.append(f"依赖顺序错误: {task_id} 必须排在 {dep_id} 之后")
        else:
            warnings.append("缺少 execution_order，将按 tasks 顺序执行")
            plan["execution_order"] = list(task_ids)
        errors.extend(self._dependency_cycle_errors(tasks))

        # 检查 parallel_groups
        parallel_groups = plan.get("parallel_groups", [])
        if parallel_groups is None:
            parallel_groups = []
        if not isinstance(parallel_groups, list):
            errors.append("parallel_groups 必须是数组")
            parallel_groups = []
        if parallel_groups:
            all_grouped = set()
            for group in parallel_groups:
                if not isinstance(group, list):
                    errors.append("parallel_groups 中的每一组必须是数组")
                    continue
                group_ids = [str(item) for item in group]
                if len(group_ids) != len(set(group_ids)):
                    errors.append("parallel_groups 中存在重复任务")
                all_grouped.update(group_ids)
            unknown_in_groups = all_grouped - task_id_set
            if unknown_in_groups:
                errors.append(f"parallel_groups 包含不存在的任务: {sorted(unknown_in_groups)}")

        tool_calls = plan.get("tool_calls", [])
        if tool_calls is None:
            tool_calls = []
        if not isinstance(tool_calls, list):
            errors.append("tool_calls 必须是数组")
            tool_calls = []
        known_tools = {str(name) for name in available_tools} if available_tools is not None else None
        for index, call in enumerate(tool_calls):
            if not isinstance(call, dict):
                errors.append(f"tool_calls[{index}] 不是对象")
                continue
            tool_name = str(call.get("tool_name") or call.get("name") or "").strip()
            if not tool_name:
                errors.append(f"tool_calls[{index}] 缺少 tool_name")
            elif known_tools is not None and tool_name not in known_tools:
                errors.append(f"tool_calls[{index}] 使用了未注册工具: {tool_name}")
            arguments = call.get("arguments", {})
            if not isinstance(arguments, dict):
                errors.append(f"tool_calls[{index}].arguments 必须是对象")

        is_valid = len(errors) == 0
        is_complete = is_valid and len(warnings) == 0

        return ValidationResult(is_valid, is_complete, errors, warnings, missing_fields)

    @staticmethod
    def _dependency_cycle_errors(tasks: List[Any]) -> List[str]:
        """用 DFS 拦住依赖环，避免执行器在两个任务之间来回等待。"""
        graph: Dict[str, List[str]] = {}
        for task in tasks:
            if not isinstance(task, dict):
                continue
            task_id = str(task.get("task_id") or "")
            graph[task_id] = [str(dep) for dep in (task.get("dependencies") or [])]
        visiting: Set[str] = set()
        visited: Set[str] = set()
        errors: List[str] = []

        def visit(node: str, path: List[str]) -> None:
            if node in visiting:
                cycle = path[path.index(node):] + [node] if node in path else path + [node]
                errors.append("任务依赖存在循环: " + " -> ".join(cycle))
                return
            if node in visited or node not in graph:
                return
            visiting.add(node)
            for dependency in graph[node]:
                visit(dependency, path + [node])
            visiting.remove(node)
            visited.add(node)

        for node in graph:
            visit(node, [])
        return list(dict.fromkeys(errors))

    @staticmethod
    def fingerprint(plan: Dict[str, Any]) -> str:
        """生成不含运行结果的稳定指纹，用于识别重复计划。"""
        normalized = {
            "tasks": [
                {
                    key: task.get(key)
                    for key in ("task_id", "task_type", "description", "dependencies")
                }
                for task in (plan.get("tasks", []) if isinstance(plan, dict) else [])
                if isinstance(task, dict)
            ],
            "execution_order": plan.get("execution_order", []) if isinstance(plan, dict) else [],
            "tool_calls": plan.get("tool_calls", []) if isinstance(plan, dict) else [],
        }
        return __import__("hashlib").sha256(
            json.dumps(normalized, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:20]

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
