"""规划验证器 - 验证LLM生成的执行计划"""
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from app.core.logger import app_logger

@dataclass
class ValidationIssue:
    """验证问题"""
    severity: str  # error, warning, info
    category: str  # syntax, logic, quality, executability
    message: str
    task_id: Optional[str] = None
    suggestion: Optional[str] = None

class PlanValidator:
    """
    规划验证器
    
    验证LLM生成的执行计划，包括：
    1. 语法验证：JSON格式、必需字段
    2. 逻辑验证：依赖关系无循环、输入输出匹配
    3. 质量验证：任务描述完整性、优先级合理性
    4. 可执行性验证：上下文是否充足、任务是否可执行
    """
    
    def __init__(self):
        self.validation_rules = {
            "syntax": self._validate_syntax,
            "logic": self._validate_logic,
            "quality": self._validate_quality,
            "executability": self._validate_executability,
        }
    
    def validate(self, plan: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Tuple[bool, List[ValidationIssue]]:
        """
        验证执行计划
        
        Args:
            plan: 执行计划
            context: 上下文信息（问题、已有上下文等）
            
        Returns:
            (是否有效, 问题列表)
        """
        all_issues = []
        
        # 1. 语法验证
        syntax_issues = self._validate_syntax(plan)
        all_issues.extend(syntax_issues)
        
        # 如果语法验证失败（严重错误），不再继续验证
        syntax_errors = [i for i in syntax_issues if i.severity == "error"]
        if syntax_errors:
            return False, all_issues
        
        # 2. 逻辑验证
        logic_issues = self._validate_logic(plan)
        all_issues.extend(logic_issues)
        
        # 3. 质量验证
        quality_issues = self._validate_quality(plan)
        all_issues.extend(quality_issues)
        
        # 4. 可执行性验证
        executability_issues = self._validate_executability(plan, context)
        all_issues.extend(executability_issues)
        
        # 判断是否有效：没有严重错误即可
        has_errors = any(issue.severity == "error" for issue in all_issues)
        
        return not has_errors, all_issues
    
    def _validate_syntax(self, plan: Dict[str, Any]) -> List[ValidationIssue]:
        """语法验证"""
        issues = []
        
        # 检查必需字段
        required_fields = ["analysis", "tasks", "parallel_groups"]
        for field in required_fields:
            if field not in plan:
                issues.append(ValidationIssue(
                    severity="error",
                    category="syntax",
                    message=f"缺少必需字段: {field}",
                    suggestion=f"在计划中添加 {field} 字段"
                ))
        
        # 检查 tasks 是否为列表
        if "tasks" in plan and not isinstance(plan["tasks"], list):
            issues.append(ValidationIssue(
                severity="error",
                category="syntax",
                message="tasks 必须是列表",
                suggestion="将 tasks 改为数组格式"
            ))
        
        # 检查每个任务的必需字段
        if "tasks" in plan and isinstance(plan["tasks"], list):
            for i, task in enumerate(plan["tasks"]):
                if not isinstance(task, dict):
                    issues.append(ValidationIssue(
                        severity="error",
                        category="syntax",
                        message=f"任务 {i} 格式错误，必须是对象",
                        suggestion="将任务改为对象格式"
                    ))
                    continue
                
                task_required_fields = ["task_id", "task_type", "description"]
                for field in task_required_fields:
                    if field not in task:
                        issues.append(ValidationIssue(
                            severity="warning",
                            category="syntax",
                            message=f"任务 {i} 缺少字段: {field}",
                            task_id=task.get("task_id"),
                            suggestion=f"为任务添加 {field} 字段"
                        ))
        
        return issues
    
    def _validate_logic(self, plan: Dict[str, Any]) -> List[ValidationIssue]:
        """逻辑验证"""
        issues = []
        
        if "tasks" not in plan or not isinstance(plan["tasks"], list):
            return issues
        
        tasks = {task.get("task_id"): task for task in plan["tasks"]}
        task_ids = set(tasks.keys())
        
        # 检查依赖关系是否形成循环
        for task_id, task in tasks.items():
            dependencies = task.get("dependencies", [])
            if not isinstance(dependencies, list):
                issues.append(ValidationIssue(
                    severity="error",
                    category="logic",
                    message=f"任务 {task_id} 的 dependencies 必须是列表",
                    task_id=task_id,
                    suggestion="将 dependencies 改为数组格式"
                ))
                continue
            
            # 检查依赖的任务是否存在
            for dep_id in dependencies:
                if dep_id not in task_ids:
                    issues.append(ValidationIssue(
                        severity="error",
                        category="logic",
                        message=f"任务 {task_id} 依赖了不存在的任务: {dep_id}",
                        task_id=task_id,
                        suggestion=f"移除对 {dep_id} 的依赖，或确保该任务存在"
                    ))
            
            # 检查自依赖
            if task_id in dependencies:
                issues.append(ValidationIssue(
                    severity="error",
                    category="logic",
                    message=f"任务 {task_id} 不能依赖自己",
                    task_id=task_id,
                    suggestion="移除 self 依赖"
                ))
        
        # 检查循环依赖（简单检查）
        cycle = self._detect_cycle(tasks)
        if cycle:
            issues.append(ValidationIssue(
                severity="error",
                category="logic",
                message=f"检测到循环依赖: {' -> '.join(cycle)}",
                suggestion="打破循环依赖，调整任务顺序"
            ))
        
        return issues
    
    def _detect_cycle(self, tasks: Dict[str, Dict[str, Any]]) -> Optional[List[str]]:
        """检测循环依赖"""
        def visit(task_id: str, visited: set, path: list) -> Optional[List[str]]:
            if task_id in path:
                cycle_start = path.index(task_id)
                return path[cycle_start:] + [task_id]
            
            if task_id in visited:
                return None
            
            visited.add(task_id)
            path.append(task_id)
            
            task = tasks.get(task_id, {})
            for dep_id in task.get("dependencies", []):
                cycle = visit(dep_id, visited, path.copy())
                if cycle:
                    return cycle
            
            return None
        
        visited = set()
        for task_id in tasks:
            if task_id not in visited:
                cycle = visit(task_id, visited, [])
                if cycle:
                    return cycle
        
        return None
    
    def _validate_quality(self, plan: Dict[str, Any]) -> List[ValidationIssue]:
        """质量验证"""
        issues = []
        
        if "tasks" not in plan or not isinstance(plan["tasks"], list):
            return issues
        
        tasks = plan["tasks"]
        
        # 检查任务描述是否完整
        for i, task in enumerate(tasks):
            if not isinstance(task, dict):
                continue
            
            task_id = task.get("task_id", f"task_{i}")
            description = task.get("description", "")
            
            # 描述太短
            if len(description) < 5:
                issues.append(ValidationIssue(
                    severity="warning",
                    category="quality",
                    message=f"任务 {task_id} 的描述太短，可能不够清晰",
                    task_id=task_id,
                    suggestion="提供更详细的任务描述"
                ))
            
            # 缺少优先级
            if "priority" not in task:
                issues.append(ValidationIssue(
                    severity="info",
                    category="quality",
                    message=f"任务 {task_id} 缺少优先级设置",
                    task_id=task_id,
                    suggestion="添加 priority 字段（1-5，1为最高）"
                ))
        
        # 检查任务数量
        if len(tasks) == 0:
            issues.append(ValidationIssue(
                severity="error",
                category="quality",
                message="计划中没有任务",
                suggestion="至少包含一个任务"
            ))
        elif len(tasks) > 10:
            issues.append(ValidationIssue(
                severity="warning",
                category="quality",
                message=f"任务数量过多（{len(tasks)}），可能影响执行效率",
                suggestion="考虑合并一些简单任务"
            ))
        
        # 检查 parallel_groups
        if "parallel_groups" in plan:
            if not isinstance(plan["parallel_groups"], list):
                issues.append(ValidationIssue(
                    severity="error",
                    category="quality",
                    message="parallel_groups 必须是列表",
                    suggestion="将 parallel_groups 改为数组格式"
                ))
            else:
                # 检查 parallel_groups 中的任务是否都在 tasks 中
                all_parallel_tasks = set()
                for group in plan["parallel_groups"]:
                    if isinstance(group, list):
                        all_parallel_tasks.update(group)
                
                task_ids = {task.get("task_id") for task in tasks}
                for task_id in all_parallel_tasks:
                    if task_id not in task_ids:
                        issues.append(ValidationIssue(
                            severity="error",
                            category="quality",
                            message=f"并行组中引用了不存在的任务: {task_id}",
                            suggestion="移除不存在的任务或添加该任务"
                        ))
        
        return issues
    
    def _validate_executability(self, plan: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> List[ValidationIssue]:
        """可执行性验证"""
        issues = []
        
        if "tasks" not in plan or not isinstance(plan["tasks"], list):
            return issues
        
        # 检查第一个任务是否有依赖
        tasks = plan["tasks"]
        if tasks:
            first_task = tasks[0]
            first_task_id = first_task.get("task_id", "")
            dependencies = first_task.get("dependencies", [])
            
            if dependencies and dependencies != [None]:
                issues.append(ValidationIssue(
                    severity="warning",
                    category="executability",
                    message=f"第一个任务 {first_task_id} 有依赖，可能无法开始执行",
                    task_id=first_task_id,
                    suggestion="确保第一个任务没有依赖，或其依赖的任务能够被正确初始化"
                ))
        
        # 检查是否有最终输出任务
        task_ids = {task.get("task_id") for task in tasks}
        has_final_output = False
        
        for task in tasks:
            task_type = task.get("task_type", "")
            if task_type in ["qa", "minutes", "todo", "controversy", "combine"]:
                has_final_output = True
                break
        
        if not has_final_output:
            issues.append(ValidationIssue(
                severity="warning",
                category="executability",
                message="计划中没有最终输出任务，可能无法生成结果",
                suggestion="添加一个 qa/minutes/todo/controversy/combine 类型的任务作为最终输出"
            ))
        
        # 检查上下文是否充足
        if context:
            has_context = context.get("has_context", False)
            context_length = context.get("context_length", 0)
            
            if not has_context:
                issues.append(ValidationIssue(
                    severity="warning",
                    category="executability",
                    message="缺少检索上下文，可能影响任务执行",
                    suggestion="确保有足够的文档上下文供任务使用"
                ))
            
            if context_length > 0 and context_length < 50:
                issues.append(ValidationIssue(
                    severity="info",
                    category="executability",
                    message=f"上下文较短（{context_length}字符），可能影响答案质量",
                    suggestion="考虑扩大检索范围，获取更多相关上下文"
                ))
        
        return issues
    
    def fix_common_issues(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        修复常见的计划问题
        
        Args:
            plan: 执行计划
            
        Returns:
            修复后的计划
        """
        fixed_plan = plan.copy()
        
        # 确保有必需字段
        if "tasks" not in fixed_plan:
            fixed_plan["tasks"] = []
        
        if "parallel_groups" not in fixed_plan:
            # 智能生成并行分组
            fixed_plan["parallel_groups"] = self._generate_parallel_groups(fixed_plan["tasks"])
        
        if "execution_order" not in fixed_plan:
            # 智能生成执行顺序
            fixed_plan["execution_order"] = self._generate_execution_order(fixed_plan["tasks"])
        
        # 修复任务
        if isinstance(fixed_plan.get("tasks"), list):
            fixed_tasks = []
            for task in fixed_plan["tasks"]:
                if not isinstance(task, dict):
                    continue
                
                # 确保有必需字段
                if "task_id" not in task:
                    task["task_id"] = f"task_{len(fixed_tasks) + 1}"
                if "task_type" not in task:
                    task["task_type"] = "qa"  # 默认类型
                if "description" not in task:
                    task["description"] = task.get("task_type", "未知任务")
                if "status" not in task:
                    task["status"] = "pending"
                if "dependencies" not in task:
                    task["dependencies"] = []
                if "can_parallel_with" not in task:
                    task["can_parallel_with"] = []
                if "priority" not in task:
                    task["priority"] = 1
                
                fixed_tasks.append(task)
            
            fixed_plan["tasks"] = fixed_tasks
        
        return fixed_plan
    
    def _generate_parallel_groups(self, tasks: List[Dict[str, Any]]) -> List[List[str]]:
        """生成并行分组"""
        if not tasks:
            return []
        
        groups = []
        processed = set()
        
        # 首先添加没有依赖的任务
        no_dep_tasks = [
            task.get("task_id") 
            for task in tasks 
            if not task.get("dependencies") or task.get("dependencies") == [None]
        ]
        
        if no_dep_tasks:
            groups.append(no_dep_tasks)
            processed.update(no_dep_tasks)
        
        # 然后添加可以并行的任务
        for task in tasks:
            task_id = task.get("task_id")
            if task_id in processed:
                continue
            
            can_parallel = task.get("can_parallel_with", [])
            if can_parallel:
                parallel_group = [task_id]
                for dep_id in can_parallel:
                    if dep_id not in processed:
                        parallel_group.append(dep_id)
                        processed.add(dep_id)
                
                if len(parallel_group) > 1:
                    groups.append(parallel_group)
                    processed.add(task_id)
        
        # 最后添加剩下的任务（按顺序）
        remaining = [task.get("task_id") for task in tasks if task.get("task_id") not in processed]
        if remaining:
            for task_id in remaining:
                groups.append([task_id])
        
        return groups
    
    def _generate_execution_order(self, tasks: List[Dict[str, Any]]) -> List[str]:
        """生成执行顺序"""
        if not tasks:
            return []
        
        # 简单的拓扑排序
        task_map = {task.get("task_id"): task for task in tasks}
        in_degree = {task.get("task_id"): 0 for task in tasks}
        
        # 计算入度
        for task in tasks:
            for dep_id in task.get("dependencies", []):
                if dep_id in in_degree:
                    in_degree[task.get("task_id")] += 1
        
        # 执行拓扑排序
        queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
        order = []
        
        while queue:
            task_id = queue.pop(0)
            order.append(task_id)
            
            for task in tasks:
                if task_id in task.get("dependencies", []):
                    in_degree[task.get("task_id")] -= 1
                    if in_degree[task.get("task_id")] == 0:
                        queue.append(task.get("task_id"))
        
        return order


# 全局验证器实例
_validator = None

def get_plan_validator() -> PlanValidator:
    """获取全局规划验证器实例"""
    global _validator
    if _validator is None:
        _validator = PlanValidator()
    return _validator
