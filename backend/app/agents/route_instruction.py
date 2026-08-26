"""统一路由契约的兼容入口。

正式定义只有 ``app.agents.state.RouteDecision``；本模块保留旧导入名，避免再维护
一套不接线的枚举、路由表和数据类。
"""
from app.agents.state import (
    ComplexityLevel,
    ExecutionMode,
    ModelTier,
    RouteDecision,
    TaskType,
)
from app.services.model_router import get_model_router


RouteInstruction = RouteDecision
TaskTypeV2 = TaskType
ComplexityV2 = ComplexityLevel


def select_model_tier(task_type: TaskType, complexity: ComplexityLevel) -> ModelTier:
    """兼容旧调用；实际选择统一委托给 ModelRouter。"""
    return get_model_router().select(task_type, complexity)[0]


__all__ = [
    "ComplexityLevel",
    "ComplexityV2",
    "ExecutionMode",
    "ModelTier",
    "RouteDecision",
    "RouteInstruction",
    "TaskType",
    "TaskTypeV2",
    "select_model_tier",
]
