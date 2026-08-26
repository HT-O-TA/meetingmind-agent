from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.document_service import DocumentService
from app.services.semantic_chunker import ChunkingStrategy, SemanticChunker


@pytest.mark.asyncio
async def test_split_document_chunks_uses_the_single_formal_strategy(monkeypatch):
    service = DocumentService(MagicMock())
    chunk_document = AsyncMock(return_value=[
        SimpleNamespace(
            content="会议正文",
            chunk_id="doc-7-0",
            metadata={"speaker": "speaker_0"},
        )
    ])
    monkeypatch.setattr(SemanticChunker, "chunk_document", chunk_document)

    chunks, metadatas = await service._split_document_chunks("content", document_id=7)

    assert chunks == ["会议正文"]
    assert metadatas[0]["strategy"] == "speaker_aware_hybrid"
    assert metadatas[0]["speaker"] == "speaker_0"
    assert chunk_document.await_args.args == ("content",)
    assert chunk_document.await_args.kwargs["doc_id"] == "7"


@pytest.mark.asyncio
async def test_split_document_chunks_has_an_explicit_fixed_fallback(monkeypatch):
    service = DocumentService(MagicMock())
    service.text_process_service.split_chunks = MagicMock(return_value=["fallback"])
    monkeypatch.setattr(
        SemanticChunker,
        "chunk_document",
        AsyncMock(side_effect=RuntimeError("semantic unavailable")),
    )

    chunks, metadatas = await service._split_document_chunks("content", document_id=8)

    assert chunks == ["fallback"]
    assert metadatas == [{"chunking": "fixed_fallback"}]
    service.text_process_service.split_chunks.assert_called_once_with("content")


def test_formal_chunking_enum_is_speaker_aware_hybrid():
    assert ChunkingStrategy.SPEAKER_AWARE_HYBRID.value == "speaker_aware_hybrid"
