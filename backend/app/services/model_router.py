"""任务类型 × 复杂度的唯一模型档位路由。"""

from __future__ import annotations

from typing import Optional, Tuple

from app.agents.state import ComplexityLevel, ModelTier, TaskType
from app.core.config import settings
from app.core.logger import app_logger


class ModelRouter:
    """规则路由只决定模型档位；效果和成本必须由真实评测另行证明。"""

    _ROUTING_TABLE = {
        (TaskType.QA, ComplexityLevel.SIMPLE): ModelTier.TURBO,
        (TaskType.QA, ComplexityLevel.RETRIEVAL): ModelTier.PLUS,
        (TaskType.QA, ComplexityLevel.COT): ModelTier.MAX,
        (TaskType.QA, ComplexityLevel.AGENT): ModelTier.MAX,
        (TaskType.TODO, ComplexityLevel.RETRIEVAL): ModelTier.PLUS,
        (TaskType.TODO, ComplexityLevel.COT): ModelTier.MAX,
        (TaskType.TODO, ComplexityLevel.AGENT): ModelTier.MAX,
        (TaskType.MINUTES, ComplexityLevel.RETRIEVAL): ModelTier.PLUS,
        (TaskType.MINUTES, ComplexityLevel.COT): ModelTier.MAX,
        (TaskType.MINUTES, ComplexityLevel.AGENT): ModelTier.MAX,
        (TaskType.CONTROVERSY, ComplexityLevel.RETRIEVAL): ModelTier.PLUS,
        (TaskType.CONTROVERSY, ComplexityLevel.COT): ModelTier.MAX,
        (TaskType.CONTROVERSY, ComplexityLevel.AGENT): ModelTier.MAX,
        (TaskType.MULTI, ComplexityLevel.COT): ModelTier.MAX,
        (TaskType.MULTI, ComplexityLevel.AGENT): ModelTier.MAX,
    }

    def select(
        self,
        task_type: Optional[TaskType],
        complexity_level: Optional[ComplexityLevel],
    ) -> Tuple[ModelTier, str]:
        tier = self._ROUTING_TABLE.get((task_type, complexity_level), ModelTier.PLUS)
        model = self._tier_to_model(tier)
        app_logger.info(
            "[ModelRouter] task=%s complexity=%s tier=%s model=%s",
            getattr(task_type, "value", None),
            getattr(complexity_level, "value", None),
            tier.value,
            model,
        )
        return tier, model

    def select_for_planning(self, complexity_level: Optional[ComplexityLevel]) -> str:
        tier = (
            ModelTier.MAX
            if complexity_level in (ComplexityLevel.COT, ComplexityLevel.AGENT)
            else ModelTier.PLUS
        )
        return self._tier_to_model(tier)

    @staticmethod
    def _tier_to_model(tier: ModelTier) -> str:
        return {
            ModelTier.TURBO: settings.MODEL_TURBO_NAME,
            ModelTier.PLUS: settings.MODEL_PLUS_NAME,
            ModelTier.MAX: settings.MODEL_MAX_NAME,
        }[tier]


_model_router: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    global _model_router
    if _model_router is None:
        _model_router = ModelRouter()
    return _model_router
