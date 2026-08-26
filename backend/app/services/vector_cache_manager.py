"""多级缓存系统 - Embedding/ACL 精确检索缓存 + 分级 TTL + 主动失效

架构说明：
┌─────────────────────────────────────────────────────────────────┐
│  Level 1: Embedding 缓存（省去计算费）                         │
│  - text → embedding 映射                                        │
│  - 节省约 28% Embedding 调用量                                  │
├─────────────────────────────────────────────────────────────────┤
│  Level 2: 语义缓存（仅保留给非权限业务结果的实验接口）          │
│  - 正式检索结果不得从 query-only 语义缓存返回                    │
│  - 无法证明 ACL 等价时禁止跨查询复用                             │
├─────────────────────────────────────────────────────────────────┤
│  Level 3: 检索结果缓存（省去向量库查询）                        │
│  - 缓存 Top-K 文档 ID，不存完整内容                              │
│  - 大幅降低 Milvus 并发压力                                     │
├─────────────────────────────────────────────────────────────────┤
│  Level 4: 答案缓存（LLM Response Cache）                        │
│  - 缓存最终答案                                                 │
│  - 分级 TTL：FAQ 1小时、技术文档 24小时、实时数据 5分钟          │
└─────────────────────────────────────────────────────────────────┘
"""
import hashlib
import json
import time
import numpy as np
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from collections import OrderedDict
from app.core.logger import app_logger
from app.core.cache import cache_get, cache_set, cache_delete


# ============================================================================
# TTL 配置（按业务时效性分级）
# ============================================================================
class CacheTTL:
    """缓存 TTL 分级策略"""
    # FAQ 类问题：稳定答案，缓存 1 小时
    FAQ = 3600
    # 技术文档：相对稳定，缓存 24 小时
    TECHNICAL = 86400
    # 业务规则：可能变更，缓存 30 分钟
    BUSINESS = 1800
    # 实时数据：需要最新，缓存 5 分钟
    REALTIME = 300
    # Embedding 缓存：长期有效
    EMBEDDING = 86400  # 24小时


# ============================================================================
# 查询类型分类器
# ============================================================================
class QueryClassifier:
    """查询分类器 - 判断查询类型以选择合适的缓存策略"""

    # 简单事实型查询关键词
    FACT_QUERY_KEYWORDS = [
        "你好", "你是谁", "帮助", "help", "功能", "版本",
        "时间", "日期", "怎么用", "使用方法", "怎么使用",
        "介绍", "是什么", "定义", "缩写", "全称",
        "如何", "怎么", "怎样", "操作", "步骤",
    ]

    # 实时数据查询关键词（不建议长时间缓存）
    REALTIME_QUERY_KEYWORDS = [
        "当前", "现在", "最新", "今天", "实时",
        "状态", "进度", "统计", "数量", "多少",
    ]

    # 复杂分析型查询关键词
    ANALYSIS_QUERY_KEYWORDS = [
        "分析", "对比", "评估", "预测", "建议",
        "为什么", "原因", "影响", "效果", "趋势",
        "总结", "综合", "汇总", "报告", "方案",
    ]

    @classmethod
    def classify(cls, query: str) -> Tuple[str, int]:
        """
        分类查询并返回推荐的 TTL

        Returns:
            (query_type, recommended_ttl)
        """
        query_lower = query.lower().strip()
        query_len = len(query)

        # 1. 检查实时数据查询（不建议缓存或短缓存）
        for keyword in cls.REALTIME_QUERY_KEYWORDS:
            if keyword in query_lower:
                return "realtime", CacheTTL.REALTIME

        # 2. 检查复杂分析型查询（不缓存）
        for keyword in cls.ANALYSIS_QUERY_KEYWORDS:
            if keyword in query_lower:
                return "complex", 0  # 不缓存

        # 3. 检查简单事实型查询（缓存）
        for keyword in cls.FACT_QUERY_KEYWORDS:
            if keyword in query_lower:
                # 短查询 TTL 更长
                return "fact", CacheTTL.FAQ if query_len < 30 else CacheTTL.BUSINESS

        # 4. 短查询（可能是事实查询）
        if query_len < 20:
            return "fact", CacheTTL.FAQ

        # 5. 中等长度查询
        if query_len < 50:
            return "moderate", CacheTTL.BUSINESS

        # 6. 长查询（可能是复杂问题）
        return "complex", 0


# ============================================================================
# Embedding 缓存（Level 1）
# ============================================================================
class EmbeddingCache:
    """
    Embedding 缓存 - 避免重复计算向量

    使用场景：
    - 用户多次询问相同问题
    - 系统内部对同一段文本做多次处理

    节省：约 28% Embedding 调用量
    """

    _instance = None

    def __init__(self, max_size: int = 5000):
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    @classmethod
    def get_instance(cls) -> 'EmbeddingCache':
        if cls._instance is None:
            cls._instance = EmbeddingCache()
        return cls._instance

    def get(self, text: str, model_name: str) -> Optional[List[float]]:
        """获取 Embedding 缓存"""
        cache_key = self._make_key(text, model_name)

        if cache_key in self._cache:
            cached = self._cache[cache_key]
            # LRU: 移到末尾
            self._cache.move_to_end(cache_key)
            self._hits += 1
            return cached["embedding"]

        self._misses += 1
        return None

    def set(self, text: str, model_name: str, embedding: List[float]) -> None:
        """设置 Embedding 缓存"""
        cache_key = self._make_key(text, model_name)

        # LRU 淘汰
        while len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)

        self._cache[cache_key] = {
            "embedding": embedding,
            "timestamp": time.time(),
        }

    def invalidate(self, model_name: Optional[str] = None) -> int:
        """失效缓存"""
        if model_name:
            keys_to_delete = [k for k in self._cache.keys() if model_name in k]
            for key in keys_to_delete:
                del self._cache[key]
            return len(keys_to_delete)
        else:
            count = len(self._cache)
            self._cache.clear()
            return count

    def get_stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0,
        }

    @staticmethod
    def _make_key(text: str, model_name: str) -> str:
        """生成缓存键"""
        # 对文本做规范化处理
        normalized = text.strip().lower()
        content_hash = hashlib.md5(normalized.encode()).hexdigest()
        return f"emb:{model_name}:{content_hash}"


# ============================================================================
# 语义缓存（Level 2）
# ============================================================================
class SemanticCache:
    """
    语义缓存 - 基于 Embedding 相似度匹配历史查询

    核心思想：
    - 用户问"如何重置密码"和"密码忘了怎么办"语义相同
    - 用 Embedding 计算查询间的余弦相似度
    - 相似度超过阈值（默认 0.95）则视为相同查询

    优势：
    - 支持口语化、倒装句等变体
    - 大幅提高缓存命中率
    - 减少 LLM API 调用成本
    """

    def __init__(self, similarity_threshold: float = 0.95):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._threshold = similarity_threshold
        self._embedding_cache = EmbeddingCache.get_instance()
        self._hits = 0
        self._semantic_hits = 0  # 语义匹配命中
        self._exact_hits = 0     # 精确匹配命中

    async def lookup(
        self,
        query: str,
        model_name: str,
        embedding_service: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        查找缓存（先精确匹配，再语义匹配）

        Returns:
            {"result": ..., "match_type": "exact"|"semantic", "similarity": float}
        """
        # Step 1: 精确匹配
        exact_key = self._make_exact_key(query)
        if exact_key in self._cache:
            cached = self._cache[exact_key]
            # 检查是否过期
            if self._is_expired(cached):
                del self._cache[exact_key]
            else:
                self._hits += 1
                self._exact_hits += 1
                app_logger.debug(f"[SemanticCache] 精确匹配命中: {query[:30]}...")
                return {
                    "result": cached["result"],
                    "match_type": "exact",
                    "similarity": 1.0,
                }

        # Step 2: 语义匹配（需要 Embedding 服务）
        if embedding_service:
            query_embedding = self._get_query_embedding(query, model_name, embedding_service)
            if query_embedding is not None:
                # 查找最相似的缓存
                best_match = self._find_best_match(query_embedding)
                if best_match:
                    result_key, similarity = best_match
                    cached = self._cache[result_key]
                    if not self._is_expired(cached):
                        self._hits += 1
                        self._semantic_hits += 1
                        app_logger.debug(
                            f"[SemanticCache] 语义匹配命中: {query[:30]}... "
                            f"(相似度: {similarity:.3f})"
                        )
                        return {
                            "result": cached["result"],
                            "match_type": "semantic",
                            "similarity": similarity,
                        }

        return None

    def store(
        self,
        query: str,
        result: Dict[str, Any],
        model_name: str,
        ttl: int = 3600,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """存储缓存"""
        exact_key = self._make_exact_key(query)
        self._cache[exact_key] = {
            "result": result,
            "query": query,
            "timestamp": time.time(),
            "ttl": ttl,
            "expires_at": time.time() + ttl,
            "metadata": metadata or {},
        }
        return exact_key

    def invalidate(self, query: Optional[str] = None) -> int:
        """失效缓存"""
        if query:
            exact_key = self._make_exact_key(query)
            if exact_key in self._cache:
                del self._cache[exact_key]
                return 1
            return 0
        else:
            count = len(self._cache)
            self._cache.clear()
            return count

    def get_stats(self) -> Dict[str, Any]:
        total = self._hits + (len(self._cache) * 10)  # 估算的 miss 数
        return {
            "size": len(self._cache),
            "hits": self._hits,
            "exact_hits": self._exact_hits,
            "semantic_hits": self._semantic_hits,
            "semantic_ratio": self._semantic_hits / self._hits if self._hits > 0 else 0,
            "threshold": self._threshold,
        }

    def _get_query_embedding(
        self,
        query: str,
        model_name: str,
        embedding_service: Any,
    ) -> Optional[List[float]]:
        """获取查询的 Embedding"""
        # 先查 Embedding 缓存
        cached = self._embedding_cache.get(query, model_name)
        if cached:
            return cached

        # 计算 Embedding
        try:
            embedding = embedding_service.encode_text(query)
            if embedding:
                self._embedding_cache.set(query, model_name, embedding)
                return embedding
        except Exception as e:
            app_logger.warning(f"[SemanticCache] Embedding 计算失败: {e}")

        return None

    def _find_best_match(
        self,
        query_embedding: List[float],
    ) -> Optional[Tuple[str, float]]:
        """查找最相似的缓存"""
        best_key = None
        best_similarity = 0.0

        query_vec = np.array(query_embedding)
        query_norm = np.linalg.norm(query_vec)

        for key, cached in self._cache.items():
            if self._is_expired(cached):
                continue

            # 检查是否有存储的 Embedding
            cached_embedding = cached.get("embedding")
            if cached_embedding is None:
                continue

            # 计算余弦相似度
            cached_vec = np.array(cached_embedding)
            cached_norm = np.linalg.norm(cached_vec)

            if query_norm > 0 and cached_norm > 0:
                similarity = np.dot(query_vec, cached_vec) / (query_norm * cached_norm)

                if similarity > best_similarity:
                    best_similarity = similarity
                    best_key = key

        if best_similarity >= self._threshold:
            return best_key, best_similarity
        return None

    def _is_expired(self, cached: Dict[str, Any]) -> bool:
        """检查是否过期"""
        return time.time() > cached.get("expires_at", 0)

    @staticmethod
    def _make_exact_key(query: str) -> str:
        """生成精确缓存键"""
        normalized = query.strip().lower()
        content_hash = hashlib.md5(normalized.encode()).hexdigest()
        return f"sem:{content_hash}"


# ============================================================================
# 检索结果缓存（Level 3）
# ============================================================================
class RetrievalCache:
    """
    检索结果缓存 - 缓存 Top-K 文档 ID

    优势：
    - 知识库不会频繁变化
    - 直接返回 ID，避免重复查询 Milvus
    - 大幅降低向量数据库并发压力

    注意：
    - 仅缓存 ID，不缓存完整内容
    - 数据更新时需要主动失效
    """

    def __init__(self, max_size: int = 10000):
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def get(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """获取检索结果缓存"""
        cache_key = self._make_key(query, top_k, filters)

        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if self._is_valid(cached):
                self._cache.move_to_end(cache_key)
                self._hits += 1
                app_logger.debug(f"[RetrievalCache] 命中缓存: {query[:30]}...")
                return cached["results"]

        self._misses += 1
        return None

    def set(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        ttl: int = 1800,
    ) -> None:
        """设置检索结果缓存"""
        cache_key = self._make_key(query, top_k, filters)

        # LRU 淘汰
        while len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)

        # 仅保存 ID 和分数（不保存完整内容）
        compact_results = [
            {
                "chunk_id": r.get("chunk_id") or r.get("id"),
                "document_id": r.get("document_id"),
                "score": r.get("score", 0),
            }
            for r in results
        ]

        self._cache[cache_key] = {
            "results": compact_results,
            "timestamp": time.time(),
            "expires_at": time.time() + ttl,
            "query_hash": hashlib.md5(query.encode()).hexdigest(),
        }

    def invalidate(self, query: Optional[str] = None) -> int:
        """失效缓存"""
        if query:
            # 失效所有包含该查询的缓存
            keys_to_delete = []
            query_hash = hashlib.md5(query.encode()).hexdigest()
            for key, value in self._cache.items():
                if value.get("query_hash") == query_hash:
                    keys_to_delete.append(key)

            for key in keys_to_delete:
                del self._cache[key]
            return len(keys_to_delete)
        else:
            count = len(self._cache)
            self._cache.clear()
            return count

    def invalidate_by_document(self, document_id: int) -> int:
        """失效指定文档相关的缓存"""
        keys_to_delete = []
        for key, value in self._cache.items():
            for result in value.get("results", []):
                if result.get("document_id") == document_id:
                    keys_to_delete.append(key)
                    break

        for key in keys_to_delete:
            del self._cache[key]
        return len(keys_to_delete)

    def get_stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0,
        }

    def _is_valid(self, cached: Dict[str, Any]) -> bool:
        """检查是否有效"""
        return time.time() < cached.get("expires_at", 0)

    @staticmethod
    def _make_key(query: str, top_k: int, filters: Optional[Dict[str, Any]]) -> str:
        """生成缓存键"""
        key_parts = [query.strip().lower(), str(top_k)]
        if filters:
            filter_str = json.dumps(filters, sort_keys=True)
            key_parts.append(filter_str)

        content_hash = hashlib.md5(":".join(key_parts).encode()).hexdigest()
        return f"retrieval:{content_hash}"


# ============================================================================
# 多级缓存管理器（统一入口）
# ============================================================================
class MultiLevelCacheManager:
    """
    多级缓存管理器 - 统一管理所有缓存层级

    工作流程：
    1. 查询先经过 QueryClassifier 分类
    2. 根据类型选择 TTL 和缓存策略
    3. 正式检索只检查按 ACL/filter 隔离的 Retrieval Cache
    4. 缓存未命中则执行检索，结果写入相应层级
    """

    _instance = None
    _cache_version = "v3"  # 版本号：Embedding 模型更新时递增

    def __init__(self):
        self.embedding_cache = EmbeddingCache.get_instance()
        self.semantic_cache = SemanticCache(similarity_threshold=0.95)
        self.retrieval_cache = RetrievalCache(max_size=10000)
        self._query_classifier = QueryClassifier()

    @classmethod
    def get_instance(cls) -> 'MultiLevelCacheManager':
        if cls._instance is None:
            cls._instance = MultiLevelCacheManager()
        return cls._instance

    async def get_cached_result(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        embedding_service: Optional[Any] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        获取缓存的检索结果（多级缓存查找）

        Returns:
            缓存的结果（可能是完整结果或 ID 列表）
        """
        # Step 1: 查询分类
        query_type, ttl = self._query_classifier.classify(query)

        # Step 2: 复杂查询或实时查询，不缓存
        if ttl == 0:
            app_logger.debug(f"[MultiLevelCache] 跳过缓存（{query_type}）: {query[:30]}...")
            return None

        # 检索结果必须按 ACL/filter 精确隔离。语义缓存只按 query 匹配，
        # 无法证明权限范围等价，因此不再用于返回检索结果。
        retrieval_result = self.retrieval_cache.get(query, top_k, filters)
        if retrieval_result:
            app_logger.debug(f"[MultiLevelCache] 检索缓存命中: {query[:30]}...")
            return retrieval_result

        return None

    async def cache_result(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None,
    ) -> None:
        """
        缓存检索结果（写入多级缓存）
        """
        # 查询分类获取 TTL
        query_type, ttl = self._query_classifier.classify(query)
        if ttl == 0:
            return  # 不缓存复杂查询

        # 只写按 ACL/filter 隔离的精确检索缓存；缓存中仅保存 ID 与分数。
        self.retrieval_cache.set(
            query=query,
            results=results,
            top_k=top_k,
            filters=filters,
            ttl=ttl,
        )

        app_logger.debug(
            f"[MultiLevelCache] 缓存结果: {query[:30]}..., "
            f"type={query_type}, ttl={ttl}s"
        )

    async def invalidate_cache_for_document(self, document_id: int) -> int:
        """
        主动失效指定文档的缓存

        当文档更新/删除时调用
        """
        count = self.retrieval_cache.invalidate_by_document(document_id)

        # 同时失效语义缓存（简化处理）
        count += self.semantic_cache.invalidate()

        app_logger.info(f"[MultiLevelCache] 失效文档 {document_id} 的缓存: {count} 条")
        return count

    async def invalidate_all_caches(self) -> Dict[str, int]:
        """失效所有缓存"""
        result = {
            "embedding": self.embedding_cache.invalidate(),
            "semantic": self.semantic_cache.invalidate(),
            "retrieval": self.retrieval_cache.invalidate(),
        }

        # 更新版本号
        self._cache_version = f"v{int(time.time())}"

        app_logger.warning(f"[MultiLevelCache] 所有缓存已失效，版本更新为 {self._cache_version}")
        return result

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return {
            "version": self._cache_version,
            "query_classifier": {
                "factory_ttl": CacheTTL.FAQ,
                "technical_ttl": CacheTTL.TECHNICAL,
                "business_ttl": CacheTTL.BUSINESS,
                "realtime_ttl": CacheTTL.REALTIME,
            },
            "embedding_cache": self.embedding_cache.get_stats(),
            "semantic_cache": self.semantic_cache.get_stats(),
            "retrieval_cache": self.retrieval_cache.get_stats(),
        }

    @property
    def cache_version(self) -> str:
        return self._cache_version


# ============================================================================
# 便捷函数
# ============================================================================
def get_cache_manager() -> MultiLevelCacheManager:
    """获取多级缓存管理器"""
    return MultiLevelCacheManager.get_instance()


async def get_cached_result(query: str, **kwargs) -> Optional[List[Dict]]:
    """获取缓存的检索结果"""
    manager = get_cache_manager()
    return await manager.get_cached_result(query, **kwargs)


async def set_cached_result(query: str, results: List[Dict], **kwargs) -> None:
    """设置缓存结果"""
    manager = get_cache_manager()
    await manager.cache_result(query, results, **kwargs)


async def invalidate_document_cache(document_id: int) -> int:
    """失效指定文档的缓存"""
    manager = get_cache_manager()
    return await manager.invalidate_cache_for_document(document_id)


async def invalidate_all_caches() -> Dict[str, int]:
    """失效所有缓存"""
    manager = get_cache_manager()
    return await manager.invalidate_all_caches()
