import pytest

from app.workers.memory_index_worker import MemoryIndexProjector


class Sink:
    def __init__(self):
        self.calls = []

    async def upsert(self, payload):
        self.calls.append(payload)


@pytest.mark.asyncio
async def test_projector_requires_at_least_one_real_sink():
    with pytest.raises(RuntimeError):
        await MemoryIndexProjector()({"operation": "upsert", "text": "事实"})


@pytest.mark.asyncio
async def test_projector_forwards_event_to_configured_sink():
    sink = Sink()
    result = await MemoryIndexProjector(milvus=sink)({"operation": "upsert", "text": "事实"})

    assert result["projected"] is True
    assert sink.calls == [{"operation": "upsert", "text": "事实"}]
