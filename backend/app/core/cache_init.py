"""
缓存初始化模块 - 混合缓存方案

功能说明：
- 集成三种缓存方案，统一管理 Redis 连接
- 支持 API 响应缓存、LLM 响应缓存、会话记忆持久化
- 提供分布式锁、限流等高级功能

配置来源：settings.REDIS_URL, settings.CACHE_ENABLED
"""
import json
import hashlib
from typing import Any, Optional, cast
import redis.asyncio as aioredis
from app.core.config import settings
from app.core.logger import app_logger


# ============================================================================
# 全局变量说明
# ============================================================================
# _redis: 原生 Redis 客户端（aioredis.Redis）
#   - 用于向量检索缓存、会话记忆持久化、LLM响应缓存
#   - 连接参数：encoding=utf-8, decode_responses=True
#
# _fastapi_cache_enabled: FastAPI-Cache 启用标志
#   - 用于 API 响应缓存
#   - 底层仍使用 _redis 作为后端
#
# _llm_cache_enabled: LLM 缓存启用标志
#   - 用于缓存 LLM API 调用结果
#   - 减少重复调用，降低成本
# ============================================================================
_redis: Optional[aioredis.Redis] = None  # 原生 Redis 客户端
_fastapi_cache_enabled: bool = False       # FastAPI-Cache 启用状态
_llm_cache_enabled: bool = False          # LLM 缓存启用状态

_cache_stats = {
    "total_hits": 0,
    "total_misses": 0,
    "api_cache_hits": 0,
    "api_cache_misses": 0,
    "llm_cache_hits": 0,
    "llm_cache_misses": 0,
    "total_sets": 0,
    "total_deletes": 0
}


# ============================================================================
# Redis 连接初始化 (init_redis)
# ============================================================================
# 参数说明：
#   - REDIS_URL: Redis 连接字符串，格式如：
#     redis://localhost:6379/0
#     redis://user:password@host:6379/1
#
#   - encoding="utf-8": 使用 UTF-8 编码存储字符串
#
#   - decode_responses=True: 自动将 bytes 解码为 str
#     便于直接操作字符串，无需手动解码
#
#   - socket_connect_timeout=3: 连接超时 3 秒
#     避免长时间等待不可达的 Redis
#
#   - socket_timeout=3: 操作超时 3 秒
#     防止单个操作阻塞过久
#
# 返回值：
#   - True: 连接成功
#   - False: 连接失败（缓存降级，不影响主流程）
# ============================================================================
async def init_redis() -> bool:
    """初始化 Redis 连接（原生 redis-py）"""
    global _redis
    if not settings.CACHE_ENABLED:
        app_logger.info("Redis cache disabled by config")
        return False
    try:
        _redis = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",  # UTF-8 编码
            decode_responses=True,  # 自动解码 bytes -> str
            socket_connect_timeout=3,  # 连接超时（秒）
            socket_timeout=3,  # 操作超时（秒）
        )
        # 确保 _redis 是 Redis 实例后再调用 ping
        assert isinstance(_redis, aioredis.Redis), "Redis connection should be aioredis.Redis instance"
        await _redis.ping()  # 测试连接
        app_logger.info(f"[Redis] 原生 Redis 连接成功: {settings.REDIS_URL}")
        return True
    except Exception as e:
        app_logger.warning(f"[Redis] 连接失败 (缓存已禁用): {e}")
        _redis = None
        return False


# ============================================================================
# FastAPI-Cache 初始化 (init_fastapi_cache)
# ============================================================================
# 用于 @cache decorator 自动缓存 API 响应
# 底层复用原生 Redis 连接
#
# 前缀说明：
#   prefix="api_cache:" - 所有 API 缓存的 key 前缀
#   避免与其他缓存类型冲突
# ============================================================================
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
            FastAPICache.init(backend, prefix="api_cache:")  # API 缓存前缀
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


# ============================================================================
# 全部缓存初始化 (init_all_caches)
# ============================================================================
# 启动时调用，初始化所有缓存系统
# 返回各缓存组件的初始化状态
# ============================================================================
async def init_all_caches() -> dict:
    """初始化所有缓存系统"""
    global _llm_cache_enabled
    results = {
        "redis": False,  # 原生 Redis
        "llm_cache": False,  # LLM 响应缓存
        "fastapi_cache": False,  # API 响应缓存
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


# ============================================================================
# 缓存操作函数
# ============================================================================
# 说明：
#   - 所有函数自动检查 Redis 连接状态
#   - Redis 不可用时返回安全默认值，不影响主流程
#   - TTL（Time To Live）：缓存过期时间（秒）
# ============================================================================

def get_redis() -> Optional[aioredis.Redis]:
    """获取 Redis 客户端实例"""
    return _redis


async def cache_get(key: str) -> Optional[Any]:
    """
    获取缓存值
    
    参数：
        key: 缓存键（需包含前缀，如 "meetings:detail:123"）
    
    返回：
        缓存值（JSON 反序列化后的 Python 对象）
        None（key 不存在或 Redis 不可用）
    """
    if not _redis:
        _cache_stats["total_misses"] += 1
        if key.startswith("api_cache:"):
            _cache_stats["api_cache_misses"] += 1
        return None
    try:
        value = await _redis.get(key)
        if value is None:
            _cache_stats["total_misses"] += 1
            if key.startswith("api_cache:"):
                _cache_stats["api_cache_misses"] += 1
            return None
        _cache_stats["total_hits"] += 1
        if key.startswith("api_cache:"):
            _cache_stats["api_cache_hits"] += 1
        return json.loads(value)  # JSON 反序列化
    except Exception as e:
        _cache_stats["total_misses"] += 1
        if key.startswith("api_cache:"):
            _cache_stats["api_cache_misses"] += 1
        app_logger.warning(f"cache_get error key={key}: {e}")
        return None


async def cache_set(key: str, value: Any, ttl: int = None) -> bool:
    """
    设置缓存值
    
    参数：
        key: 缓存键
        value: 缓存值（会被 JSON 序列化）
        ttl: 过期时间（秒），默认使用 settings.CACHE_TTL
    
    返回：
        True（设置成功）
        False（Redis 不可用或设置失败）
    """
    if not _redis:
        return False
    try:
        ttl = ttl or settings.CACHE_TTL  # 默认 TTL
        await _redis.setex(key, ttl, json.dumps(value, ensure_ascii=False, default=str))
        _cache_stats["total_sets"] += 1
        return True
    except Exception as e:
        app_logger.warning(f"cache_set error key={key}: {e}")
        return False


async def cache_delete(key: str) -> bool:
    """
    删除单个缓存
    
    参数：
        key: 缓存键
    
    返回：
        True（删除成功或 key 不存在）
        False（Redis 不可用）
    """
    if not _redis:
        return False
    try:
        await _redis.delete(key)
        _cache_stats["total_deletes"] += 1
        return True
    except Exception as e:
        app_logger.warning(f"cache_delete error key={key}: {e}")
        return False


async def cache_delete_pattern(pattern: str) -> int:
    """
    批量删除匹配 pattern 的缓存
    
    参数：
        pattern: 通配符模式，如 "meetings:list:*"
    
    返回：
        删除的 key 数量
    """
    if not _redis:
        return 0
    try:
        keys = await _redis.keys(pattern)  # 匹配所有 key
        if keys:
            return await _redis.delete(*keys)  # 批量删除
        return 0
    except Exception as e:
        app_logger.warning(f"cache_delete_pattern error pattern={pattern}: {e}")
        return 0


# ============================================================================
# LLM 响应缓存
# ============================================================================
# 功能：对相同 prompt + config 的 LLM 调用进行缓存
# 原理：
#   1. 对 prompt 和 config 生成 MD5 哈希作为缓存键
#   2. 相同请求直接返回缓存，避免重复调用 LLM API
#   3. 节省成本，提高响应速度
#
# 缓存键格式：llm_cache:{md5_hash}
# ============================================================================

def _llm_cache_key(prompt: str, llm_config: dict = None) -> str:
    """
    生成 LLM 缓存键
    
    参数：
        prompt: 用户输入的提示词
        llm_config: LLM 配置（如 model, temperature 等）
    
    返回：
        缓存键（格式：llm_cache:{md5_hash}）
    """
    key_str = f"prompt:{prompt}:config:{json.dumps(llm_config or {})}",
    return f"llm_cache:{hashlib.md5(str(key_str).encode()).hexdigest()}"


async def llm_cache_get(prompt: str, llm_config: dict = None) -> Optional[str]:
    """
    获取 LLM 响应缓存
    
    参数：
        prompt: 提示词
        llm_config: LLM 配置
    
    返回：
        缓存的 LLM 响应字符串
        None（未命中或不可用）
    """
    if not _redis or not _llm_cache_enabled:
        _cache_stats["total_misses"] += 1
        _cache_stats["llm_cache_misses"] += 1
        return None
    try:
        key = _llm_cache_key(prompt, llm_config)
        value = await _redis.get(key)
        if value:
            _cache_stats["total_hits"] += 1
            _cache_stats["llm_cache_hits"] += 1
            app_logger.debug(f"[LLM Cache] 命中缓存: {key[:32]}...")
            return value
        _cache_stats["total_misses"] += 1
        _cache_stats["llm_cache_misses"] += 1
        return None
    except Exception as e:
        _cache_stats["total_misses"] += 1
        _cache_stats["llm_cache_misses"] += 1
        app_logger.warning(f"llm_cache_get error: {e}")
        return None


async def llm_cache_set(prompt: str, response: str, llm_config: dict = None, ttl: int = None) -> bool:
    """
    设置 LLM 响应缓存
    
    参数：
        prompt: 提示词
        response: LLM 响应内容
        llm_config: LLM 配置
        ttl: 过期时间，默认 LLM_CACHE_TTL (1小时)
    """
    if not _redis or not _llm_cache_enabled:
        return False
    try:
        key = _llm_cache_key(prompt, llm_config)
        ttl = ttl or settings.LLM_CACHE_TTL if hasattr(settings, 'LLM_CACHE_TTL') else 3600
        await _redis.setex(key, ttl, response)
        _cache_stats["total_sets"] += 1
        app_logger.debug(f"[LLM Cache] 缓存已设置: {key[:32]}...")
        return True
    except Exception as e:
        app_logger.warning(f"llm_cache_set error: {e}")
        return False


async def llm_cache_clear() -> int:
    """清空所有 LLM 缓存"""
    return await cache_delete_pattern("llm_cache:*")


def get_cache_stats() -> dict:
    """
    获取缓存统计信息
    
    返回：
        {
            "total_hits": int,
            "total_misses": int,
            "hit_rate": float,
            "api_cache_hits": int,
            "api_cache_misses": int,
            "api_cache_hit_rate": float,
            "llm_cache_hits": int,
            "llm_cache_misses": int,
            "llm_cache_hit_rate": float,
            "total_sets": int,
            "total_deletes": int,
            "enabled": bool
        }
    """
    stats = _cache_stats.copy()
    
    total = stats["total_hits"] + stats["total_misses"]
    stats["hit_rate"] = stats["total_hits"] / total if total > 0 else 0.0
    
    api_total = stats["api_cache_hits"] + stats["api_cache_misses"]
    stats["api_cache_hit_rate"] = stats["api_cache_hits"] / api_total if api_total > 0 else 0.0
    
    llm_total = stats["llm_cache_hits"] + stats["llm_cache_misses"]
    stats["llm_cache_hit_rate"] = stats["llm_cache_hits"] / llm_total if llm_total > 0 else 0.0
    
    stats["enabled"] = _redis is not None
    
    return stats


def reset_cache_stats():
    """重置缓存统计信息"""
    global _cache_stats
    _cache_stats = {
        "total_hits": 0,
        "total_misses": 0,
        "api_cache_hits": 0,
        "api_cache_misses": 0,
        "llm_cache_hits": 0,
        "llm_cache_misses": 0,
        "total_sets": 0,
        "total_deletes": 0
    }


# ============================================================================
# Redis 连接关闭 (close_redis)
# ============================================================================
# 应用关闭时调用，确保释放 Redis 连接
# ============================================================================
async def close_redis():
    """关闭 Redis 连接"""
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None
        app_logger.info("[Redis] 连接已关闭")


# ============================================================================
# 健康检查 (redis_health)
# ============================================================================
# 用于 /api/health 或运维监控系统
# ============================================================================
async def redis_health() -> dict:
    """
    Redis 健康检查
    
    返回：
        {
            "status": "ok" | "disabled" | "error",
            "used_memory_human": "1.5M",
            "llm_cache": True,
            "fastapi_cache": True
        }
    """
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


# ============================================================================
# 高级功能：分布式锁 & 限流
# ============================================================================
# 分布式锁：用于多实例部署时的资源竞争控制
# 限流：用于 API 调用频率控制
# ============================================================================

async def acquire_lock(key: str, ttl: int = 10) -> bool:
    """
    获取分布式锁
    
    参数：
        key: 锁名称
        ttl: 锁自动过期时间（秒），防止死锁
    
    返回：
        True（获取成功）
        False（锁已被占用或 Redis 不可用）
    
    实现原理：
        SET key "1" NX EX ttl
        NX: key 不存在时才设置
        EX: 设置过期时间
    """
    if not _redis:
        return False
    try:
        result = await _redis.set(key, "1", nx=True, ex=ttl)
        return result is not None
    except Exception as e:
        app_logger.warning(f"acquire_lock error key={key}: {e}")
        return False


async def release_lock(key: str) -> bool:
    """释放分布式锁（删除 key）"""
    return await cache_delete(key)


async def rate_limit(key: str, limit: int, window: int) -> tuple[bool, int]:
    """
    限流检查（滑动窗口计数器算法）
    
    参数：
        key: 限流键（如 "ip:192.168.1.1" 或 "user:123"）
        limit: 时间窗口内允许的最大请求数
        window: 时间窗口大小（秒）
    
    返回：
        (是否允许, 当前计数)
    
    示例：
        # 限制每分钟最多 60 次请求
        allowed, count = await rate_limit("ip:192.168.1.1", limit=60, window=60)
        if not allowed:
            return {"error": "请求过于频繁"}
    """
    if not _redis:
        return True, 0
    try:
        count = await _redis.incr(key)  # 原子递增
        if count == 1:
            # 首次请求，设置过期时间
            await _redis.expire(key, window)
        return count <= limit, count
    except Exception as e:
        app_logger.warning(f"rate_limit error key={key}: {e}")
        return True, 0
