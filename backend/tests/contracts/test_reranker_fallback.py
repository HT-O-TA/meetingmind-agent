"""降级重排（无 BGE 模型）在中文上的行为。"""
from app.services.reranker import Reranker


def _fallback_reranker():
    reranker = Reranker.__new__(Reranker)
    reranker.model = None
    return reranker


def test_chinese_fallback_promotes_lexically_relevant_document():
    docs = [
        {"id": "a", "content": "今天午饭吃什么大家随便聊聊", "score": 0.9},
        {"id": "b", "content": "预算最后定为三十万元，下周提交", "score": 0.1},
    ]

    ranked = _fallback_reranker().rerank("预算最后定的是多少", docs, top_n=2)

    assert [d["id"] for d in ranked] == ["b", "a"]
    assert ranked[0]["rerank_score"] > 0


def test_fallback_keeps_retrieval_order_when_no_overlap():
    docs = [{"id": "x", "content": "甲乙丙", "score": 0.2}, {"id": "y", "content": "丁戊己", "score": 0.8}]

    ranked = _fallback_reranker().rerank("完全无关", docs, top_n=2)

    assert [d["id"] for d in ranked] == ["y", "x"]
