import json
from typing import Any, Optional, cast
import redis.asyncio as aioredis
from app.core.config import settings
from app.core.logger import app_logger

# 全局 Redis 连接池
_redis: Optional[aioredis.Redis] = None


async def init_redis() -> bool:
    global _redis
    if not settings.CACHE_ENABLED:
        app_logger.info("Redis cache disabled by config")
        return False
    try:
        _redis = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        await cast(aioredis.Redis, _redis).ping()
        app_logger.info(f"Redis connected: {settings.REDIS_URL}")
        return True
    except Exception as e:
        app_logger.warning(f"Redis connection failed (cache disabled): {e}")
        _redis = None
        return False


async def close_redis():
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None
        app_logger.info("Redis connection closed")


def get_redis() -> Optional[aioredis.Redis]:
    return _redis


async def cache_get(key: str) -> Optional[Any]:
    if not _redis:
        return None
    try:
        value = await _redis.get(key)
        if value is None:
            return None
        return json.loads(value)
    except Exception as e:
        app_logger.warning(f"cache_get error key={key}: {e}")
        return None


async def cache_set(key: str, value: Any, ttl: int = None) -> bool:
    if not _redis:
        return False
    try:
        ttl = ttl or settings.CACHE_TTL
        await _redis.setex(key, ttl, json.dumps(value, ensure_ascii=False, default=str))
        return True
    except Exception as e:
        app_logger.warning(f"cache_set error key={key}: {e}")
        return False


async def cache_delete(key: str) -> bool:
    if not _redis:
        return False
    try:
        await _redis.delete(key)
        return True
    except Exception as e:
        app_logger.warning(f"cache_delete error key={key}: {e}")
        return False


async def cache_delete_pattern(pattern: str) -> int:
    """删除匹配 pattern 的所有 key，返回删除数量"""
    if not _redis:
        return 0
    try:
        keys = await _redis.keys(pattern)
        if keys:
            return await _redis.delete(*keys)
        return 0
    except Exception as e:
        app_logger.warning(f"cache_delete_pattern error pattern={pattern}: {e}")
        return 0


async def redis_health() -> dict:
    if not _redis:
        return {"status": "disabled"}
    try:
        await cast(aioredis.Redis, _redis).ping()
        info = await cast(aioredis.Redis, _redis).info("memory")
        return {
            "status": "ok",
            "used_memory_human": info.get("used_memory_human", "N/A"),
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}
