"""反思记忆服务 - 持久化反思评估结果，形成反馈闭环

功能：
1. 异步保存反思结果（不阻塞主流程）
2. 查询相似历史反思（用于评估参考）
3. 用户错误模式统计（用于个性化调优）
4. 与长期记忆系统集成

存储架构：
- 内存 LRU 缓存（快速访问，大小/TTL 从配置读取）
- Redis 热缓存（TTL 从 REFLECTION_MEMORY_CACHE_TTL 配置读取）
- 后续可扩展 PostgreSQL 持久化
"""
import json
import hashlib
import time
from typing import Dict, List, Optional, Any
from collections import OrderedDict
from dataclasses import dataclass, field
from app.core.logger import app_logger
from app.core.config import settings


@dataclass
class ReflectionRecord:
    """反思记忆记录"""
    question_summary: str
    quality_score: float
    error_types: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    retry_count: int = 0
    final_answer_hash: str = ""
    timestamp: float = 0.0
    user_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question_summary": self.question_summary,
            "quality_score": self.quality_score,
            "error_types": self.error_types,
            "suggestions": self.suggestions,
            "retry_count": self.retry_count,
            "final_answer_hash": self.final_answer_hash,
            "timestamp": self.timestamp,
            "user_id": self.user_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReflectionRecord":
        return cls(
            question_summary=data.get("question_summary", ""),
            quality_score=data.get("quality_score", 0.0),
            error_types=data.get("error_types", []),
            suggestions=data.get("suggestions", []),
            retry_count=data.get("retry_count", 0),
            final_answer_hash=data.get("final_answer_hash", ""),
            timestamp=data.get("timestamp", 0.0),
            user_id=data.get("user_id"),
        )


class ReflectionMemoryService:
    """反思记忆服务"""

    def __init__(
        self,
        max_cache_size: int = 0,  # 0 表示从配置读取
        cache_ttl: float = 0,     # 0 表示从配置读取
    ):
        # 从配置读取，允许外部覆盖（方便测试）
        _max_cache_size = max_cache_size or getattr(settings, "REFLECTION_MEMORY_CACHE_SIZE", 500)
        _cache_ttl = cache_ttl or float(getattr(settings, "REFLECTION_MEMORY_CACHE_TTL", 3600))
        self._cache: OrderedDict = OrderedDict()
        self._max_cache_size = _max_cache_size
        self._cache_ttl = _cache_ttl
        self._redis_prefix = "reflection_memory:"

    async def save_reflection(
        self,
        question: str,
        quality_score: float,
        error_types: List[str],
        suggestions: List[str],
        retry_count: int,
        final_answer: str = "",
        user_id: Optional[int] = None,
    ) -> bool:
        """异步保存反思结果

        Args:
            question: 用户问题
            quality_score: 质量分数
            error_types: 错误类型列表
            suggestions: 改进建议
            retry_count: 重试次数
            final_answer: 最终答案
            user_id: 用户 ID

        Returns:
            bool: 是否保存成功
        """
        try:
            # 创建摘要（取问题前 100 字）
            question_summary = question[:100] if question else ""

            # 计算答案哈希
            final_answer_hash = ""
            if final_answer:
                final_answer_hash = hashlib.sha256(
                    final_answer.encode("utf-8")
                ).hexdigest()[:16]

            record = ReflectionRecord(
                question_summary=question_summary,
                quality_score=quality_score,
                error_types=error_types or [],
                suggestions=suggestions or [],
                retry_count=retry_count,
                final_answer_hash=final_answer_hash,
                timestamp=time.time(),
                user_id=user_id,
            )

            # 写入内存缓存
            cache_key = self._make_cache_key(question_summary, user_id)
            self._update_cache(cache_key, record)

            # 异步写入 Redis（如果可用）
            await self._save_to_redis(cache_key, record)

            app_logger.debug(
                f"[ReflectionMemory] 保存反思记录: score={quality_score:.2f}, "
                f"errors={error_types[:2]}, key={cache_key[:8]}"
            )
            return True

        except Exception as e:
            app_logger.warning(f"[ReflectionMemory] 保存反思记录失败: {e}")
            return False

    async def query_similar_reflections(
        self,
        question: str,
        top_k: int = 0,  # 0 表示从配置读取
        user_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """查询相似历史反思

        Args:
            question: 当前问题
            top_k: 返回最多 K 条（0 则从 REFLECTION_MEMORY_TOP_K 配置读取）
            user_id: 用户 ID

        Returns:
            List[Dict]: 相似反思记录列表
        """
        # top_k 为 0 时从配置读取
        if top_k == 0:
            top_k = getattr(settings, "REFLECTION_MEMORY_TOP_K", 3)

        try:
            question_lower = question.lower().strip()[:100]

            # 从内存缓存中查找相似项
            similar: List[tuple] = []  # (similarity_score, record)

            for key, record in self._cache.items():
                # 简单相似度：关键词重叠
                sim = self._calculate_similarity(question_lower, record.question_summary)
                if sim > 0.1:
                    similar.append((sim, record))

            # 尝试从 Redis 加载更多
            redis_records = await self._load_from_redis(question, user_id)
            for record in redis_records:
                sim = self._calculate_similarity(question_lower, record.question_summary)
                if sim > 0.1:
                    similar.append((sim, record))

            # 按相似度排序，取 top_k
            similar.sort(key=lambda x: x[0], reverse=True)
            results = [
                record.to_dict() for _, record in similar[:top_k]
            ]

            if results:
                app_logger.debug(
                    f"[ReflectionMemory] 查询到 {len(results)} 条相似反思"
                )

            return results

        except Exception as e:
            app_logger.warning(f"[ReflectionMemory] 查询相似反思失败: {e}")
            return []

    async def get_user_error_stats(
        self, user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """获取用户错误模式统计

        Returns:
            Dict: 错误类型统计、平均分数、常见建议
        """
        try:
            error_type_count: Dict[str, int] = {}
            total_score = 0.0
            count = 0
            all_suggestions: List[str] = []

            for record in self._cache.values():
                if user_id and record.user_id != user_id:
                    continue
                for et in record.error_types:
                    error_type_count[et] = error_type_count.get(et, 0) + 1
                total_score += record.quality_score
                count += 1
                all_suggestions.extend(record.suggestions[:1])

            avg_score = total_score / count if count > 0 else 0.0

            return {
                "total_reflections": count,
                "average_score": round(avg_score, 2),
                "error_type_distribution": error_type_count,
                "top_suggestions": list(set(all_suggestions))[:5],
            }

        except Exception as e:
            app_logger.warning(f"[ReflectionMemory] 获取错误统计失败: {e}")
            return {}

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算两个文本的简单相似度（Jaccard）"""
        if not text1 or not text2:
            return 0.0

        # 分词（简单按字符和空格）
        words1 = set(text1.split())
        words2 = set(text2.split())

        # 字符级 n-gram 相似度
        if not words1 or not words2:
            # 使用字符 bigram
            bigrams1 = set(text1[i:i+2] for i in range(len(text1)-1))
            bigrams2 = set(text2[i:i+2] for i in range(len(text2)-1))
            if not bigrams1 or not bigrams2:
                return 0.0
            intersection = bigrams1 & bigrams2
            union = bigrams1 | bigrams2
            return len(intersection) / len(union)

        # 词级 Jaccard
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union)

    def _make_cache_key(self, question_summary: str, user_id: Optional[int]) -> str:
        """生成缓存 key"""
        content = f"{user_id or 0}:{question_summary}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _update_cache(self, key: str, record: ReflectionRecord) -> None:
        """更新内存 LRU 缓存"""
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = record
        # 超出容量时淘汰最旧的
        while len(self._cache) > self._max_cache_size:
            self._cache.popitem(last=False)

    async def _save_to_redis(self, key: str, record: ReflectionRecord) -> None:
        """写入 Redis 热缓存"""
        try:
            from app.core.redis_client import get_redis_client
            redis = await get_redis_client()
            if redis is None:
                return
            redis_key = f"{self._redis_prefix}{key}"
            await redis.setex(
                redis_key,
                int(self._cache_ttl),
                json.dumps(record.to_dict(), ensure_ascii=False),
            )
        except Exception as e:
            app_logger.debug(f"[ReflectionMemory] Redis 写入失败（忽略）: {e}")

    async def _load_from_redis(
        self, question: str, user_id: Optional[int] = None
    ) -> List[ReflectionRecord]:
        """从 Redis 加载反思记录（扫描前缀）"""
        try:
            from app.core.redis_client import get_redis_client
            redis = await get_redis_client()
            if redis is None:
                return []

            records: List[ReflectionRecord] = []
            # 扫描所有反思 key（限制数量避免性能问题）
            async for redis_key in redis.scan_iter(f"{self._redis_prefix}*", count=100):
                raw = await redis.get(redis_key)
                if raw:
                    try:
                        data = json.loads(raw)
                        record = ReflectionRecord.from_dict(data)
                        # 过期检查
                        if time.time() - record.timestamp <= self._cache_ttl:
                            records.append(record)
                    except Exception:
                        pass
                if len(records) >= 200:  # 最多加载 200 条，避免内存爆炸
                    break
            return records
        except Exception as e:
            app_logger.debug(f"[ReflectionMemory] Redis 读取失败（忽略）: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        """获取服务统计信息"""
        return {
            "cache_size": len(self._cache),
            "max_cache_size": self._max_cache_size,
            "cache_ttl_seconds": self._cache_ttl,
            "top_k": getattr(settings, "REFLECTION_MEMORY_TOP_K", 3),
        }


_reflection_memory_instance: Optional[ReflectionMemoryService] = None


def get_reflection_memory_service() -> ReflectionMemoryService:
    global _reflection_memory_instance
    if _reflection_memory_instance is None:
        _reflection_memory_instance = ReflectionMemoryService()
    return _reflection_memory_instance
