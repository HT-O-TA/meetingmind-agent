from unittest.mock import AsyncMock

import pytest

from app.workers import run


@pytest.mark.asyncio
async def test_worker_requires_redis(monkeypatch):
    init_redis = AsyncMock(return_value=False)
    monkeypatch.setattr(run, "init_redis", init_redis)

    with pytest.raises(RuntimeError, match="Redis is unavailable"):
        await run.initialize_worker_dependencies()


@pytest.mark.asyncio
async def test_worker_accepts_initialized_redis(monkeypatch):
    init_redis = AsyncMock(return_value=True)
    monkeypatch.setattr(run, "init_redis", init_redis)

    await run.initialize_worker_dependencies()

    init_redis.assert_awaited_once_with()
