"""按查询条件与 ACL 精确隔离的有界检索缓存。"""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional


class MultiLevelCacheManager:
    """保留兼容类名；当前只实现主链实际使用的精确检索缓存。"""

    _instance: Optional["MultiLevelCacheManager"] = None

    def __init__(self, max_size: int = 10_000, ttl_seconds: int = 1_800) -> None:
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._entries: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    @classmethod
    def get_instance(cls) -> "MultiLevelCacheManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def _key(query: str, top_k: int, filters: Optional[Dict[str, Any]]) -> str:
        payload = {
            "query": query.strip().lower(),
            "top_k": top_k,
            "filters": filters or {},
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    async def get_cached_result(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> Optional[List[Dict[str, Any]]]:
        key = self._key(query, top_k, filters)
        entry = self._entries.get(key)
        if entry is None or entry["expires_at"] <= time.monotonic():
            if entry is not None:
                del self._entries[key]
            self._misses += 1
            return None
        self._entries.move_to_end(key)
        self._hits += 1
        return [item.copy() for item in entry["results"]]

    async def cache_result(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> None:
        key = self._key(query, top_k, filters)
        compact = [
            {
                "chunk_id": item.get("chunk_id") or item.get("id"),
                "document_id": item.get("document_id"),
                "score": item.get("score", item.get("similarity", 0.0)),
            }
            for item in results
        ]
        self._entries[key] = {
            "results": compact,
            "expires_at": time.monotonic() + self.ttl_seconds,
        }
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_size:
            self._entries.popitem(last=False)

    async def invalidate_cache_for_document(self, document_id: int) -> int:
        keys = [
            key
            for key, entry in self._entries.items()
            if any(item.get("document_id") == document_id for item in entry["results"])
        ]
        for key in keys:
            del self._entries[key]
        return len(keys)

    async def invalidate_all_caches(self) -> Dict[str, int]:
        count = len(self._entries)
        self._entries.clear()
        return {"retrieval": count}

    def get_cache_stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "retrieval": {
                "size": len(self._entries),
                "max_size": self.max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self._hits / total if total else 0.0,
            }
        }


def get_cache_manager() -> MultiLevelCacheManager:
    return MultiLevelCacheManager.get_instance()


async def get_cached_result(query: str, **kwargs: Any) -> Optional[List[Dict[str, Any]]]:
    return await get_cache_manager().get_cached_result(query, **kwargs)


async def set_cached_result(query: str, results: List[Dict[str, Any]], **kwargs: Any) -> None:
    await get_cache_manager().cache_result(query, results, **kwargs)


async def invalidate_document_cache(document_id: int) -> int:
    return await get_cache_manager().invalidate_cache_for_document(document_id)


async def invalidate_all_caches() -> Dict[str, int]:
    return await get_cache_manager().invalidate_all_caches()
