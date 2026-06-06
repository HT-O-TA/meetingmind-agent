from unittest.mock import MagicMock

import pytest

from app.services.document_service import DocumentService


@pytest.mark.asyncio
async def test_split_document_chunks_uses_basic_chunking_by_default(monkeypatch):
    service = DocumentService(MagicMock())
    service.text_process_service.split_chunks = MagicMock(return_value=["chunk-a", "chunk-b"])

    monkeypatch.setattr(
        service,
        "_get_runtime_config",
        lambda key, fallback: False if key == "processing.enable_semantic_chunking" else fallback,
    )

    chunks, metadatas = await service._split_document_chunks("content", document_id=1)

    assert chunks == ["chunk-a", "chunk-b"]
    assert metadatas == [{}, {}]
    service.text_process_service.split_chunks.assert_called_once_with("content")


@pytest.mark.asyncio
async def test_split_document_chunks_uses_semantic_chunking_when_enabled(monkeypatch):
    service = DocumentService(MagicMock())
    service.text_process_service.split_chunks = MagicMock(return_value=["fallback"])

    runtime_config = {
        "processing.enable_semantic_chunking": True,
        "processing.semantic_chunk_strategy": "paragraph",
        "processing.semantic_chunk_use_llm": False,
        "processing.semantic_chunk_preserve_structure": False,
        "processing.semantic_chunk_min_size": 10,
        "processing.semantic_chunk_max_size": 200,
        "processing.semantic_chunk_overlap": 20,
        "processing.semantic_chunk_build_hierarchy": True,
    }
    monkeypatch.setattr(
        service,
        "_get_runtime_config",
        lambda key, fallback: runtime_config.get(key, fallback),
    )

    content = "第一段内容。\n\n第二段内容。"
    chunks, metadatas = await service._split_document_chunks(content, document_id=7)

    assert chunks
    assert service.text_process_service.split_chunks.call_count == 0
    assert all(metadata["chunking"] == "semantic" for metadata in metadatas)
    assert all(metadata["strategy"] == "paragraph" for metadata in metadatas)
    assert all(metadata["use_llm"] is False for metadata in metadatas)
    assert all("chunk_id" in metadata for metadata in metadatas)
