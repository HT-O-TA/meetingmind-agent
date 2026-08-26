from types import SimpleNamespace

import pytest

from app.services.embedding_service import EmbeddingService


class FakeSession:
    def __init__(self, chunk):
        self.chunk = chunk
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, model, chunk_id):
        return self.chunk if chunk_id == self.chunk.id else None

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_vector_worker_embedding_entrypoint_persists_chunk(monkeypatch):
    from app.db import database

    chunk = SimpleNamespace(
        id=7,
        chunk_text="会议决定周五发布",
        deleted_at=None,
        embedding=None,
        embedding_array=None,
        embedding_model=None,
    )
    session = FakeSession(chunk)
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: session)
    service = EmbeddingService.__new__(EmbeddingService)
    service.use_fallback = True
    service.encode_text = lambda text: [0.25, 0.75]

    await service.embed_chunk(7)

    assert chunk.embedding == "[0.25, 0.75]"
    assert chunk.embedding_array == [0.25, 0.75]
    assert chunk.embedding_model == "fallback-word-frequency-v1"
    assert session.committed is True


@pytest.mark.asyncio
async def test_vector_worker_embedding_fails_for_missing_chunk(monkeypatch):
    from app.db import database

    session = FakeSession(SimpleNamespace(id=8))
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: session)
    service = EmbeddingService.__new__(EmbeddingService)
    service.use_fallback = True
    service.encode_text = lambda text: [1.0]

    with pytest.raises(LookupError, match="not found"):
        await service.embed_chunk(7)
