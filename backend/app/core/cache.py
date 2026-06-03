"""缓存模块 - 兼容层（重导出 cache_init 中的函数）"""
# 从新的缓存初始化模块重导出所有函数
from app.core.cache_init import (
    init_redis,
    init_all_caches,
    close_redis,
    get_redis,
    cache_get,
    cache_set,
    cache_delete,
    cache_delete_pattern,
    redis_health,
    acquire_lock,
    release_lock,
    rate_limit,
    llm_cache_get,
    llm_cache_set,
    llm_cache_clear,
)

__all__ = [
    "init_redis",
    "init_all_caches",
    "close_redis",
    "get_redis",
    "cache_get",
    "cache_set",
    "cache_delete",
    "cache_delete_pattern",
    "redis_health",
    "acquire_lock",
    "release_lock",
    "rate_limit",
    "llm_cache_get",
    "llm_cache_set",
    "llm_cache_clear",
]
