import hashlib
import json
from typing import Any


def make_cache_key(*parts: Any) -> str:
    """将多个参数拼接成缓存 key，None 值会被过滤"""
    segments = [str(p) for p in parts if p is not None]
    return ":".join(segments)


def hash_params(**kwargs) -> str:
    """将查询参数字典哈希为短字符串，用于列表缓存 key"""
    filtered = {k: v for k, v in sorted(kwargs.items()) if v is not None}
    raw = json.dumps(filtered, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()[:8]
