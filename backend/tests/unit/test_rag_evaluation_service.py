from types import SimpleNamespace

from app.services.rag_evaluation_service import RAGEvaluationService


def test_generation_metrics_use_runtime_embedding_cosine_without_sklearn():
    service = RAGEvaluationService.__new__(RAGEvaluationService)
    service.embedding_service = SimpleNamespace(
        encode_batch=lambda _texts: [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]],
        cosine_similarity=lambda left, right: sum(a * b for a, b in zip(left, right)),
    )

    metrics = service._calculate_generation_metrics(
        answer="action item",
        expected_answer="action item",
        context=["unrelated"],
    )

    assert metrics["answer_similarity"] == 1.0
    assert metrics["context_relevance"] == 0.0
    assert metrics["answer_length"] == 11
