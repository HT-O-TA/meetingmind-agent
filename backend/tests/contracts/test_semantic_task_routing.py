"""语义任务识别接入 IntentRouter 的契约（假编码器，不加载模型）。"""
import numpy as np
import pytest

from app.agents.state import TaskType, WorkflowType
from app.services.intent_router import IntentRouter
from app.services.semantic_task_classifier import PROTOTYPES, SemanticTaskClassifier

# 把文本映射到"所属任务类型"的 one-hot；未登记文本映射为零向量（不命中任何类型）。
_AXIS = {TaskType.TODO: 0, TaskType.MINUTES: 1, TaskType.CONTROVERSY: 2, TaskType.QA: 3}
_LEXICON = {text: label for label, texts in PROTOTYPES.items() for text in texts}
_LEXICON.update({"各自分一下工": TaskType.TODO, "recap一下": TaskType.MINUTES, "哪里没谈拢": TaskType.CONTROVERSY})


class FakeEncoder:
    def encode(self, texts, **kwargs):
        rows = []
        for text in texts:
            vec = np.zeros(4)
            if text in _LEXICON:
                vec[_AXIS[_LEXICON[text]]] = 1.0
            rows.append(vec)
        return np.array(rows)


@pytest.fixture
def router():
    return IntentRouter(semantic_task_classifier=SemanticTaskClassifier(FakeEncoder()))


@pytest.mark.asyncio
async def test_semantic_synonym_routes_to_business_workflow(router):
    decision = await router.route("各自分一下工")
    assert (decision.workflow_type, decision.task_type) == (WorkflowType.TODO, TaskType.TODO)


@pytest.mark.asyncio
async def test_implicit_multi_task_across_clauses(router):
    decision = await router.route("recap一下，然后哪里没谈拢")
    assert decision.workflow_type == WorkflowType.COMPLEX
    assert decision.task_type == TaskType.MULTI


@pytest.mark.asyncio
async def test_question_phrase_does_not_turn_single_task_into_multi(router):
    # "是什么"命中 QA 关键词，但与业务任务同句时不构成独立子任务
    decision = await router.route("有哪些争议，反对的理由都是什么")
    assert decision.workflow_type == WorkflowType.CONTROVERSY


@pytest.mark.asyncio
async def test_single_ordinal_word_is_not_parallel_multi_task():
    decision = await IntentRouter().route("为什么最后决定不用那个外包团队了")
    assert decision.workflow_type == WorkflowType.SIMPLE_QA


def _head_router(label_for_axis):
    """意图头：4 维假向量上每个轴对应一个整句类别。"""
    classes = np.array(label_for_axis)
    coef = np.eye(4, dtype=np.float32)
    return IntentRouter(semantic_task_classifier=SemanticTaskClassifier(
        FakeEncoder(), head=(coef, np.zeros(4, dtype=np.float32), classes)))


@pytest.mark.asyncio
async def test_intent_head_qa_overrides_task_keyword():
    # "纪要"关键词会命中 MINUTES；意图头判为 qa（问具体事实）时应走 QA
    router = _head_router(["todo", "minutes", "controversy", "qa"])
    _LEXICON["纪要里写的预算是多少"] = TaskType.QA
    decision = await router.route("纪要里写的预算是多少")
    assert decision.workflow_type == WorkflowType.SIMPLE_QA


@pytest.mark.asyncio
async def test_intent_head_multi_routes_to_complex():
    router = _head_router(["multi", "minutes", "controversy", "qa"])
    _LEXICON["tldr + action items"] = TaskType.TODO  # 映射到轴 0 → 头判 multi
    decision = await router.route("tldr + action items")
    assert (decision.workflow_type, decision.task_type) == (WorkflowType.COMPLEX, TaskType.MULTI)
