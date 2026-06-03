"""缓存初始化模块 - 混合缓存方案

集成三种缓存方案：
1. 原生 redis-py：向量检索缓存、会话记忆持久化、LLM响应缓存
2. FastAPI-Cache：API 响应缓存
"""
import json
import hashlib
from typing import Any, Optional, cast
import redis.asyncio as aioredis
from app.core.config import settings
from app.core.logger import app_logger

# ==================== 原生 Redis 客户端 ====================
_redis: Optional[aioredis.Redis] = None

# ==================== FastAPI-Cache ====================
_fastapi_cache_enabled: bool = False

# ==================== LLM 缓存 ====================
_llm_cache_enabled: bool = False


async def init_redis() -> bool:
    """初始化 Redis 连接（原生 redis-py）"""
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
        app_logger.info(f"[Redis] 原生 Redis 连接成功: {settings.REDIS_URL}")
        return True
    except Exception as e:
        app_logger.warning(f"[Redis] 连接失败 (缓存已禁用): {e}")
        _redis = None
        return False


async def init_fastapi_cache() -> bool:
    """初始化 FastAPI-Cache（用于 API 响应缓存）"""
    global _fastapi_cache_enabled
    
    if not settings.CACHE_ENABLED:
        return False
    
    try:
        from fastapi_cache import FastAPICache
        from fastapi_cache.backends.redis import RedisBackend
        
        # 使用已有的异步 Redis 客户端
        if _redis:
            backend = RedisBackend(_redis)
            FastAPICache.init(backend, prefix="api_cache:")
            _fastapi_cache_enabled = True
            app_logger.info("[Redis] FastAPI-Cache 已启用")
            return True
        return False
    except ImportError:
        app_logger.warning("[Redis] fastapi-cache 未安装，跳过 API 缓存初始化")
        return False
    except Exception as e:
        app_logger.warning(f"[Redis] FastAPI-Cache 初始化失败: {e}")
        return False


async def init_all_caches() -> dict:
    """初始化所有缓存系统"""
    global _llm_cache_enabled
    results = {
        "redis": False,
        "llm_cache": False,
        "fastapi_cache": False,
    }
    
    # 1. 初始化原生 Redis
    results["redis"] = await init_redis()
    
    # 2. LLM 缓存（基于原生 Redis，无需额外初始化）
    if results["redis"]:
        _llm_cache_enabled = True
        results["llm_cache"] = True
    
    # 3. 初始化 FastAPI-Cache
    results["fastapi_cache"] = await init_fastapi_cache()
    
    app_logger.info(f"[Redis] 缓存初始化完成: {results}")
    return results


async def close_redis():
    """关闭 Redis 连接"""
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None
        app_logger.info("[Redis] 连接已关闭")


# ==================== 原生 Redis 操作函数 ====================

def get_redis() -> Optional[aioredis.Redis]:
    """获取 Redis 客户端"""
    return _redis


async def cache_get(key: str) -> Optional[Any]:
    """获取缓存值"""
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
    """设置缓存值"""
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
    """删除缓存"""
    if not _redis:
        return False
    try:
        await _redis.delete(key)
        return True
    except Exception as e:
        app_logger.warning(f"cache_delete error key={key}: {e}")
        return False


async def cache_delete_pattern(pattern: str) -> int:
    """删除匹配 pattern 的所有 key"""
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


# ==================== LLM 缓存实现（替代 LangChain RedisCache） ====================

def _llm_cache_key(prompt: str, llm_config: dict = None) -> str:
    """生成 LLM 缓存键"""
    key_str = f"prompt:{prompt}:config:{json.dumps(llm_config or {})}"
    return f"llm_cache:{hashlib.md5(key_str.encode()).hexdigest()}"


async def llm_cache_get(prompt: str, llm_config: dict = None) -> Optional[str]:
    """获取 LLM 响应缓存"""
    if not _redis or not _llm_cache_enabled:
        return None
    try:
        key = _llm_cache_key(prompt, llm_config)
        value = await _redis.get(key)
        if value:
            app_logger.debug(f"[LLM Cache] 命中缓存: {key[:32]}...")
            return value
        return None
    except Exception as e:
        app_logger.warning(f"llm_cache_get error: {e}")
        return None


async def llm_cache_set(prompt: str, response: str, llm_config: dict = None, ttl: int = None) -> bool:
    """设置 LLM 响应缓存"""
    if not _redis or not _llm_cache_enabled:
        return False
    try:
        key = _llm_cache_key(prompt, llm_config)
        ttl = ttl or settings.LLM_CACHE_TTL if hasattr(settings, 'LLM_CACHE_TTL') else 3600
        await _redis.setex(key, ttl, response)
        app_logger.debug(f"[LLM Cache] 缓存已设置: {key[:32]}...")
        return True
    except Exception as e:
        app_logger.warning(f"llm_cache_set error: {e}")
        return False


async def llm_cache_clear() -> int:
    """清空所有 LLM 缓存"""
    return await cache_delete_pattern("llm_cache:*")


# ==================== 健康检查 ====================

async def redis_health() -> dict:
    """Redis 健康检查"""
    if not _redis:
        return {"status": "disabled"}
    try:
        await cast(aioredis.Redis, _redis).ping()
        info = await cast(aioredis.Redis, _redis).info("memory")
        return {
            "status": "ok",
            "used_memory_human": info.get("used_memory_human", "N/A"),
            "llm_cache": _llm_cache_enabled,
            "fastapi_cache": _fastapi_cache_enabled,
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


# ==================== 高级功能 ====================

async def acquire_lock(key: str, ttl: int = 10) -> bool:
    """获取分布式锁"""
    if not _redis:
        return False
    try:
        result = await _redis.set(key, "1", nx=True, ex=ttl)
        return result is not None
    except Exception as e:
        app_logger.warning(f"acquire_lock error key={key}: {e}")
        return False


async def release_lock(key: str) -> bool:
    """释放分布式锁"""
    return await cache_delete(key)


async def rate_limit(key: str, limit: int, window: int) -> tuple[bool, int]:
    """限流检查
    
    Args:
        key: 限流键
        limit: 限制次数
        window: 时间窗口（秒）
    
    Returns:
        (是否允许, 当前计数)
    """
    if not _redis:
        return True, 0
    try:
        count = await _redis.incr(key)
        if count == 1:
            await _redis.expire(key, window)
        return count <= limit, count
    except Exception as e:
        app_logger.warning(f"rate_limit error key={key}: {e}")
        return True, 0
