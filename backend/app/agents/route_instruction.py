"""路由指令 - 意图理解层输出 / 规划编排层输入

设计原则：
    意图理解层只负责"分类和路由决策"，输出结构化路由指令，不做任何执行。
    规划编排层只负责"拿到指令后怎么执行"，不做分类，只关心执行逻辑。

指令结构：
    {
        task_type:    任务类型（QA/TODO/MINUTES/CONTROVERSY/MULTI）
        complexity:   复杂度（S/R/A，三级，无C——CoT降为提示词选项）
        model_tier:   模型档位（turbo/plus/max，双轴路由统一决策）
        confidence:   综合置信度（用于fallback判断）
        task_confidence:        任务分类置信度
        complexity_confidence:  复杂度分类置信度
        rule_matched:           规则是否命中（命中享有豁免权）
        sub_tasks:              子任务列表（仅MULTI时填充）
        execution_mode:         执行模式（确定性/REACT/PLAN_EXECUTE/FALLBACK）
        decision_trace:         决策链路（可观测性）
    }
"""
from dataclasses import dataclass, field
from typing import List, Optional, Any
from enum import Enum


class TaskTypeV2(str, Enum):
    """任务类型（五分类）"""
    QA = "qa"                    # 问答
    TODO = "todo"                # 待办提取
    MINUTES = "minutes"          # 会议纪要
    CONTROVERSY = "controversy"  # 争议观点
    MULTI = "multi"              # 多任务混合


class ComplexityV2(str, Enum):
    """复杂度（三级，去掉C——CoT降为提示词选项）

    S: Simple      - 直接回答，不需要检索
    R: Retrieval  - 需要检索或推理（原C级请求归入此级，由节点内部enable_cot区分）
    A: Agent      - 需要多步工具调用
    """
    S = "simple"
    R = "retrieval"
    A = "agent"


class ModelTier(str, Enum):
    """模型档位（双轴路由统一决策）"""
    TURBO = "turbo"   # qwen-turbo，最省成本
    PLUS = "plus"     # qwen3.6-plus，默认
    MAX = "max"       # qwen-max，最强能力


class ExecutionMode(str, Enum):
    """执行模式（规划编排层据此选择节点）"""
    FALLBACK = "fallback"          # 兜底（confidence不足）
    DETERMINISTIC = "deterministic"  # 确定性节点（S/R复杂度）
    REACT = "react"                # ReAct循环（A复杂度）
    PLAN_EXECUTE = "plan_execute"  # Plan-Execute（MULTI任务）


@dataclass
class SubTask:
    """子任务（仅MULTI时填充）"""
    task_id: str
    task_type: TaskTypeV2
    description: str
    priority: int = 1


@dataclass
class RouteInstruction:
    """路由指令 - 意图理解层输出

    核心字段：
        task_type:    做什么任务
        complexity:   用多复杂的方式做
        model_tier:   用哪档模型（双轴路由结果，节点直接使用，不重新判断）
        execution_mode: 走哪种执行模式

    置信度字段：
        confidence:              综合置信度（用于fallback判断）
        task_confidence:          任务分类置信度（低→fallback）
        complexity_confidence:    复杂度分类置信度（低→降级，不fallback）
        rule_matched:             规则是否命中（命中享有豁免权）

    分层置信度策略：
        if task_confidence < 0.65:      → FALLBACK（连做什么都不知道）
        elif complexity_confidence < 0.65: → 降一级复杂度（A→R，R→S），继续执行
        else:                           → 正常路由
    """
    # 核心路由字段
    task_type: TaskTypeV2
    complexity: ComplexityV2
    model_tier: ModelTier
    execution_mode: ExecutionMode

    # 置信度
    confidence: float = 0.5
    task_confidence: float = 0.5
    complexity_confidence: float = 0.5
    rule_matched: bool = False

    # 子任务（仅MULTI）
    sub_tasks: List[SubTask] = field(default_factory=list)

    # 可观测性
    decision_trace: List[str] = field(default_factory=list)
    original_question: str = ""

    def to_dict(self) -> dict:
        return {
            "task_type": self.task_type.value,
            "complexity": self.complexity.value,
            "model_tier": self.model_tier.value,
            "execution_mode": self.execution_mode.value,
            "confidence": self.confidence,
            "task_confidence": self.task_confidence,
            "complexity_confidence": self.complexity_confidence,
            "rule_matched": self.rule_matched,
            "sub_tasks": [
                {"task_id": t.task_id, "task_type": t.task_type.value,
                 "description": t.description, "priority": t.priority}
                for t in self.sub_tasks
            ],
            "decision_trace": self.decision_trace,
        }


# 双轴路由表： (task_type, complexity) -> model_tier
# 任务类型管"能不能省"（确定性任务锁plus下限），复杂度管"省多少"（A升max）
_DUAL_AXIS_ROUTING = {
    # ── QA类：S复杂度有turbo空间 ──
    (TaskTypeV2.QA, ComplexityV2.S): ModelTier.TURBO,
    (TaskTypeV2.QA, ComplexityV2.R): ModelTier.PLUS,
    (TaskTypeV2.QA, ComplexityV2.A): ModelTier.MAX,

    # ── 确定性任务：锁plus下限，A升max ──
    (TaskTypeV2.TODO, ComplexityV2.R): ModelTier.PLUS,
    (TaskTypeV2.TODO, ComplexityV2.A): ModelTier.MAX,

    (TaskTypeV2.MINUTES, ComplexityV2.R): ModelTier.PLUS,
    (TaskTypeV2.MINUTES, ComplexityV2.A): ModelTier.MAX,

    (TaskTypeV2.CONTROVERSY, ComplexityV2.R): ModelTier.PLUS,
    (TaskTypeV2.CONTROVERSY, ComplexityV2.A): ModelTier.MAX,

    # ── MULTI：恒走max（需要协调多步骤）──
    (TaskTypeV2.MULTI, ComplexityV2.A): ModelTier.MAX,
}


def select_model_tier(task_type: TaskTypeV2, complexity: ComplexityV2) -> ModelTier:
    """双轴模型路由 - 在意图理解层统一决策

    原则：
        任务类型管"能不能省"——确定性任务锁plus下限，QA+S允许turbo
        复杂度管"省多少"——A级别无论任务类型都升max
    """
    return _DUAL_AXIS_ROUTING.get((task_type, complexity), ModelTier.PLUS)
