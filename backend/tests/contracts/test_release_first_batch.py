from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.services.document_service import DocumentService
from app.services.rag_service import RAGService


@pytest.mark.asyncio
@pytest.mark.parametrize("indexed, expected", [(True, "parsed"), (False, "index_failed")])
async def test_document_status_exposes_indexing_result(monkeypatch, indexed, expected):
    db = AsyncMock()
    service = DocumentService(db)
    monkeypatch.setattr(service, "_create_vector_chunks", AsyncMock(return_value=indexed))
    doc = SimpleNamespace(id=1, meeting_id=2, department="Docs", status="parsed")

    await service._index_document(doc, "parsed content")

    assert doc.status == expected
    assert db.commit.await_count == int(not indexed)


@pytest.mark.asyncio
@pytest.mark.parametrize("answer, rejected, ids", [
    ("Supported [1]", False, ["[1]"]),
    ("Unseen [2]", True, ["[1]", "[2]"]),
    ("Out of range [99]", True, ["[1]", "[2]"]),
    ("No explicit reference", False, []),
])
async def test_rag_citations_must_reference_evidence_seen_by_model(monkeypatch, answer, rejected, ids):
    monkeypatch.setattr(settings, "ENABLE_RERANK", False)
    vector = SimpleNamespace(search_with_multi_retrieval=AsyncMock(return_value=[
        {"chunk_id": 1, "chunk_text": "First evidence"},
        {"chunk_id": 2, "chunk_text": "Second evidence"},
    ]))
    llm = SimpleNamespace(
        generate_answer=AsyncMock(return_value=answer),
        last_context_manifest={"included": [{"content_ref": "retrieval:0"}]},
    )

    result = await RAGService(vector, llm).ask("question")

    assert len(result["citations"]) == 2
    assert ("invalid_answer_citations" in result["degradation"]["reasons"]) is rejected
    assert [item["citation_id"] for item in result["answer_citations"]] == ids
    assert (result["answer"] != answer) is rejected
