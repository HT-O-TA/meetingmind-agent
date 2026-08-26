"""统一 RouteDecision 与双轴模型路由契约。"""
import pytest

from app.agents.state import ComplexityLevel, ExecutionMode, ModelTier, TaskType
from app.services.intent_router import IntentRouter


class FixedClassifier:
    def __init__(self, *, level, score, confidence, multi=False):
        self.result = {
            "level": level,
            "score": score,
            "confidence": confidence,
            "is_multi_task": multi,
            "requires_retrieval": level != ComplexityLevel.SIMPLE,
            "requires_reasoning": level in (ComplexityLevel.COT, ComplexityLevel.AGENT),
        }

    async def classify(self, question):
        return self.result


@pytest.mark.asyncio
async def test_greeting_also_produces_the_unified_route_schema():
    decision = await IntentRouter().route("你好")

    assert decision.schema_version == "route.v1"
    assert decision.rule_matched is True
    assert decision.model_tier == ModelTier.TURBO
    assert decision.execution_mode == ExecutionMode.DETERMINISTIC
    assert decision.requires_retrieval is False


@pytest.mark.asyncio
async def test_explicit_business_task_selects_model_tier_and_deterministic_mode():
    router = IntentRouter(
        complexity_classifier=FixedClassifier(
            level=ComplexityLevel.RETRIEVAL,
            score=0.4,
            confidence=0.9,
        )
    )

    decision = await router.route("请提取本次会议的待办事项")

    assert decision.task_type == TaskType.TODO
    assert decision.model_tier == ModelTier.PLUS
    assert decision.execution_mode == ExecutionMode.DETERMINISTIC
    assert decision.degradation_actions == []


@pytest.mark.asyncio
async def test_uncertain_complexity_degrades_without_changing_business_task():
    router = IntentRouter(
        complexity_classifier=FixedClassifier(
            level=ComplexityLevel.AGENT,
            score=0.82,
            confidence=0.4,
        ),
        complexity_confidence_threshold=0.65,
    )

    decision = await router.route("请提取本次会议的待办事项")

    assert decision.task_type == TaskType.TODO
    assert decision.complexity_level == ComplexityLevel.RETRIEVAL
    assert decision.model_tier == ModelTier.PLUS
    assert "complexity_degraded:agent->retrieval" in decision.degradation_actions
    assert decision.threshold_policy["source"] == "config_provisional_until_route_eval"


@pytest.mark.asyncio
async def test_uncertain_task_enters_safe_fallback():
    router = IntentRouter(
        complexity_classifier=FixedClassifier(
            level=ComplexityLevel.RETRIEVAL,
            score=0.4,
            confidence=0.8,
        ),
        task_confidence_threshold=0.65,
    )

    decision = await router.route("请处理一下这件事情")

    assert decision.execution_mode == ExecutionMode.FALLBACK
    assert decision.requires_retrieval is True
    assert "task_uncertain:external_write_disabled" in decision.degradation_actions


@pytest.mark.asyncio
async def test_multi_task_has_structured_subtasks_and_plan_execute_mode():
    router = IntentRouter(
        complexity_classifier=FixedClassifier(
            level=ComplexityLevel.AGENT,
            score=0.9,
            confidence=0.9,
            multi=True,
        )
    )

    decision = await router.route("请总结会议纪要并提取待办事项")

    assert decision.task_type == TaskType.MULTI
    assert decision.execution_mode == ExecutionMode.PLAN_EXECUTE
    assert decision.model_tier == ModelTier.MAX
    assert [task["task_type"] for task in decision.sub_tasks] == ["todo", "minutes"]
