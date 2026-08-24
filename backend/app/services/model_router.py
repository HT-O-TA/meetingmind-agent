"""双轴模型路由器 - 任务类型 × 复杂度 联合决定模型档位

设计原则（对应 docs/总结.md 意图理解层描述）：
    任务类型管"能不能省" —— 确定性任务（TODO/MINUTES/CONTROVERSY）锁 plus 档位，
                          只有 QA 类在 S 复杂度下有 turbo 空间。
    复杂度管"省多少"      —— C/A 级别无论任务类型都用 max 档位，确保推理能力上限。

档位映射：
    turbo = qwen-turbo      # 最省成本，用于简单 QA
    plus  = qwen3.6-plus    # 默认档位，平衡成本与能力
    max   = qwen-max        # 最强能力，用于复杂推理

成本对比（相对 plus）：
    turbo ≈ 1/8  plus
    plus  = 1.0
    max   ≈ 2.5  plus

路由矩阵：
    ┌─────────┬───────┬───────┬───────┬───────┐
    │ task/com │   S   │   R   │   C   │   A   │
    ├─────────┼───────┼───────┼───────┼───────┤
    │   QA     │ turbo │ plus  │ max   │ max   │
    │   TODO   │  -    │ plus  │ max   │ max   │  ← 确定性任务锁 plus 下限
    │ MINUTES  │  -    │ plus  │ max   │ max   │
    │CONTROVERSY│ -    │ plus  │ max   │ max   │
    │ MULTI    │  -    │  -    │ max   │ max   │  ← 多任务恒走 max
    └─────────┴───────┴───────┴───────┴───────┘
"""
from typing import Optional, Tuple
from enum import Enum
from app.core.config import settings
from app.core.logger import app_logger
from app.agents.state import TaskType, ComplexityLevel


class ModelTier(str, Enum):
    """模型档位枚举"""
    TURBO = "turbo"
    PLUS = "plus"
    MAX = "max"


# 档位 → 实际模型名映射（从 settings 读取，便于配置覆盖）
_TIER_MODEL_MAP = {
    ModelTier.TURBO: "qwen-turbo",
    ModelTier.PLUS: "qwen3.6-plus",
    ModelTier.MAX: "qwen-max",
}


class ModelRouter:
    """双轴模型路由器

    联合 task_type 和 complexity_level 决定使用哪档模型。
    路由规则可被 settings.MODEL_ROUTING_OVERRIDE 覆盖（用于 A/B 实验）。
    """

    # 路由矩阵： (task_type, complexity_level) -> ModelTier
    # None 表示不存在的组合（如 TODO + S 不会发生，TODO 至少需要 R）
    _ROUTING_TABLE = {
        # ── QA 类：S 复杂度有 turbo 空间，其他递进 ──
        (TaskType.QA, ComplexityLevel.SIMPLE):    ModelTier.TURBO,
        (TaskType.QA, ComplexityLevel.RETRIEVAL): ModelTier.PLUS,
        (TaskType.QA, ComplexityLevel.COT):       ModelTier.MAX,
        (TaskType.QA, ComplexityLevel.AGENT):     ModelTier.MAX,

        # ── 确定性任务：锁 plus 下限，C/A 升 max ──
        # "任务类型管能不能省" —— 确定性任务不允许走 turbo，保证输出质量稳定
        (TaskType.TODO,        ComplexityLevel.RETRIEVAL): ModelTier.PLUS,
        (TaskType.TODO,        ComplexityLevel.COT):       ModelTier.MAX,
        (TaskType.TODO,        ComplexityLevel.AGENT):     ModelTier.MAX,

        (TaskType.MINUTES,     ComplexityLevel.RETRIEVAL): ModelTier.PLUS,
        (TaskType.MINUTES,     ComplexityLevel.COT):       ModelTier.MAX,
        (TaskType.MINUTES,     ComplexityLevel.AGENT):     ModelTier.MAX,

        (TaskType.CONTROVERSY, ComplexityLevel.RETRIEVAL): ModelTier.PLUS,
        (TaskType.CONTROVERSY, ComplexityLevel.COT):       ModelTier.MAX,
        (TaskType.CONTROVERSY, ComplexityLevel.AGENT):     ModelTier.MAX,

        # ── 多任务：恒走 max，因为需要协调多步骤 ──
        (TaskType.MULTI, ComplexityLevel.COT):   ModelTier.MAX,
        (TaskType.MULTI, ComplexityLevel.AGENT): ModelTier.MAX,
    }

    def select(
        self,
        task_type: Optional[TaskType],
        complexity_level: Optional[ComplexityLevel],
    ) -> Tuple[ModelTier, str]:
        """根据任务类型和复杂度选择模型档位

        Args:
            task_type: 任务类型（QA/TODO/MINUTES/CONTROVERSY/MULTI）
            complexity_level: 复杂度级别（S/R/C/A）

        Returns:
            (ModelTier, model_name) 档位枚举与实际模型名
        """
        # 兜底：缺任一轴时用 plus（安全默认）
        if task_type is None or complexity_level is None:
            return ModelTier.PLUS, self._tier_to_model(ModelTier.PLUS)

        tier = self._ROUTING_TABLE.get((task_type, complexity_level))
        if tier is None:
            # 未定义组合（如 TODO+SIMPLE 不应出现），回退到 plus
            tier = ModelTier.PLUS

        model_name = self._tier_to_model(tier)

        app_logger.info(
            f"[ModelRouter] task={task_type.value} complexity={complexity_level.value} "
            f"→ tier={tier.value} model={model_name}"
        )
        return tier, model_name

    def select_for_planning(self, complexity_level: Optional[ComplexityLevel]) -> str:
        """规划阶段专用模型选择

        规划是高价值环节，按复杂度递进：
            S/R → plus（简单规划够用）
            C/A → max（复杂规划需要强能力）

        Args:
            complexity_level: 复杂度级别

        Returns:
            模型名
        """
        if complexity_level in (ComplexityLevel.COT, ComplexityLevel.AGENT):
            tier = ModelTier.MAX
        else:
            tier = ModelTier.PLUS
        return self._tier_to_model(tier)

    def select_for_evaluation(self) -> str:
        """评估阶段专用模型（reflection/quality_gate）

        评估任务对推理深度要求低，但调用频繁，统一用 turbo 降本。

        Returns:
            模型名（默认 qwen-turbo，可通过 settings.EVAL_LLM_MODEL 覆盖）
        """
        return settings.EVAL_LLM_MODEL or self._tier_to_model(ModelTier.TURBO)

    def estimate_cost_factor(self, tier: ModelTier) -> float:
        """估算档位的相对成本系数（以 plus=1.0 为基准）

        用于 cost_manager 统计和面试讲解时的量化说明。

        Args:
            tier: 模型档位

        Returns:
            相对成本系数：turbo≈0.125, plus=1.0, max≈2.5
        """
        return {
            ModelTier.TURBO: 0.125,  # turbo 约为 plus 的 1/8
            ModelTier.PLUS:  1.0,
            ModelTier.MAX:   2.5,
        }.get(tier, 1.0)

    def explain_routing(
        self,
        task_type: Optional[TaskType],
        complexity_level: Optional[ComplexityLevel],
    ) -> str:
        """生成人类可读的路由解释（用于 trace/调试/面试讲解）

        Args:
            task_type: 任务类型
            complexity_level: 复杂度级别

        Returns:
            路由解释字符串
        """
        tier, model = self.select(task_type, complexity_level)

        if task_type is None or complexity_level is None:
            return f"路由兜底 → {tier.value}（{model}）: 缺少任务类型或复杂度信息"

        # 任务类型维度解释
        if task_type == TaskType.QA:
            if tier == ModelTier.TURBO:
                task_explain = "QA + 简单复杂度，允许降级到 turbo 省成本"
            else:
                task_explain = f"QA 类，按复杂度升档到 {tier.value}"
        elif task_type == TaskType.MULTI:
            task_explain = "多任务请求，恒走 max 保证协调能力"
        else:
            # 确定性任务（TODO/MINUTES/CONTROVERSY）
            if tier == ModelTier.PLUS:
                task_explain = f"{task_type.value} 确定性任务锁 plus 下限，不走 turbo"
            else:
                task_explain = f"{task_type.value} 确定性任务，复杂度 C/A 升 max"

        # 复杂度维度解释
        if complexity_level in (ComplexityLevel.COT, ComplexityLevel.AGENT):
            comp_explain = f"复杂度 {complexity_level.value} 需要强推理，升 max"
        else:
            comp_explain = f"复杂度 {complexity_level.value}，无需升档"

        return f"{task_explain}；{comp_explain} → 最终 {tier.value}（{model}）"

    def _tier_to_model(self, tier: ModelTier) -> str:
        """档位转模型名，支持 settings 覆盖"""
        # 允许通过环境变量覆盖默认映射
        override_map = {
            ModelTier.TURBO: getattr(settings, "MODEL_TURBO_NAME", None),
            ModelTier.PLUS:  getattr(settings, "MODEL_PLUS_NAME", None),
            ModelTier.MAX:   getattr(settings, "MODEL_MAX_NAME", None),
        }
        return override_map.get(tier) or _TIER_MODEL_MAP[tier]


# 单例
_model_router: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    """获取 ModelRouter 单例"""
    global _model_router
    if _model_router is None:
        _model_router = ModelRouter()
    return _model_router
