from unittest.mock import AsyncMock

import pytest

from app.core import cache_init


@pytest.mark.asyncio
async def test_invalid_json_counts_as_one_cache_miss(monkeypatch):
    redis = AsyncMock()
    redis.get.return_value = "invalid-json"
    monkeypatch.setattr(cache_init, "_redis", redis)
    monkeypatch.setattr(cache_init, "_cache_stats", dict.fromkeys(cache_init._cache_stats, 0))

    assert await cache_init.cache_get("api_cache:test") is None
    stats = cache_init.get_cache_stats()
    assert stats["api_cache_hits"] == stats["total_hits"] == 0
    assert stats["api_cache_misses"] == stats["total_misses"] == 1
