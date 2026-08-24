"""长期记忆服务 - 支持跨会议记忆关联和组织级知识存储

存储架构（P0 升级后）：
- PostgreSQL：主存储（持久化、结构化查询、不受 Redis OOM 影响）
- Redis：热缓存层（TTL=1小时，加速读取，减少 DB 压力）
- 内存：LRU 缓存（MAX_MEMORIES=2000，最快访问）

迁移状态（Phase 4）：
- 模块级便捷函数已移除，请使用 UnifiedMemoryService
- 本模块仅保留 LongTermMemory 类作为 UnifiedMemoryService 的存储后端
- MemoryType / MemoryScope 枚举供 UnifiedMemoryService 复用
"""
import json
import uuid
import asyncio
import warnings
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict, OrderedDict
from app.core.logger import app_logger
from app.core.config import settings

# Redis cache helpers
from app.core.cache import cache_get, cache_set, cache_delete, cache_delete_pattern

# Redis key prefixes
_REDIS_PREFIX = "ltm:"
_REDIS_MEMORY_KEY = _REDIS_PREFIX + "memory:{memory_id}"
_REDIS_INDEX_KEY = _REDIS_PREFIX + "index:all"           # set of all memory_ids
_REDIS_MEETING_KEY = _REDIS_PREFIX + "idx:meeting:{meeting_id}"
_REDIS_TYPE_KEY = _REDIS_PREFIX + "idx:type:{type_val}"
_REDIS_CONTEXT_KEY = _REDIS_PREFIX + "ctx:{meeting_id}"

# TTL constants
def _get_memory_ttls():
    """从 settings 读取 TTL（避免模块加载时循环导入）"""
    try:
        from app.core.config import settings
        return (
            settings.MEMORY_HOT_CACHE_TTL,
            settings.MEMORY_INDEX_TTL,
            settings.MEMORY_CONTEXT_TTL,
        )
    except Exception:
        return (3600, 86400, 604800)

_MEMORY_TTL, _INDEX_TTL, _CONTEXT_TTL = _get_memory_ttls()
_PG_MEMORY_EXPIRE_DAYS = 365 * 2   # PostgreSQL 记忆过期时间：2年

# Max in-memory entries before LRU eviction
MAX_MEMORIES = 2000


class MemoryType(str, Enum):
    """记忆类型"""
    MEETING_SUMMARY = "meeting_summary"
    DECISION = "decision"
    ACTION_ITEM = "action_item"
    CONTROVERSY = "controversy"
    TOPIC = "topic"
    KNOWLEDGE = "knowledge"
    RELATIONSHIP = "relationship"


class MemoryScope(str, Enum):
    """记忆范围"""
    TEAM = "team"
    DEPARTMENT = "department"
    ORGANIZATION = "organization"
    PROJECT = "project"


@dataclass
class MemoryEntry:
    """记忆条目"""
    memory_id: str
    type: MemoryType
    scope: MemoryScope
    content: str
    meeting_id: Optional[str] = None
    meeting_topic: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    entities: List[str] = field(default_factory=list)
    related_memories: List[str] = field(default_factory=list)
    confidence: float = 1.0
    expires_at: Optional[str] = None   # ISO datetime string; None = never expires
    metadata: Dict[str, Any] = field(default_factory=dict)
    # ── 事实准入与历史保留（对应 docs/总结.md 检索记忆层）──
    source_type: Optional[str] = None    # 来源类型：request / meeting / document / memory
    source_ref: Optional[str] = None     # 来源引用（meeting_id / document_id / 请求 ID）
    superseded_by: Optional[str] = None  # 被哪条新记忆替代（None=当前有效）

    def is_expired(self) -> bool:
        """判断记忆是否已过期"""
        if not self.expires_at:
            return False
        try:
            return datetime.now() > datetime.fromisoformat(self.expires_at)
        except Exception:
            return False

    def is_superseded(self) -> bool:
        """是否已被新记忆替代"""
        return self.superseded_by is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "type": self.type.value,
            "scope": self.scope.value,
            "content": self.content,
            "meeting_id": self.meeting_id,
            "meeting_topic": self.meeting_topic,
            "timestamp": self.timestamp,
            "entities": self.entities,
            "related_memories": self.related_memories,
            "confidence": self.confidence,
            "expires_at": self.expires_at,
            "metadata": self.metadata,
            "source_type": self.source_type,
            "source_ref": self.source_ref,
            "superseded_by": self.superseded_by,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
        return cls(
            memory_id=data["memory_id"],
            type=MemoryType(data["type"]),
            scope=MemoryScope(data["scope"]),
            content=data["content"],
            meeting_id=data.get("meeting_id"),
            meeting_topic=data.get("meeting_topic"),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            entities=data.get("entities", []),
            related_memories=data.get("related_memories", []),
            confidence=data.get("confidence", 1.0),
            expires_at=data.get("expires_at"),
            metadata=data.get("metadata", {}),
            source_type=data.get("source_type"),
            source_ref=data.get("source_ref"),
            superseded_by=data.get("superseded_by"),
        )


@dataclass
class MeetingContext:
    """会议上下文"""
    meeting_id: str
    topic: str
    date: str
    participants: List[str]
    summary: str
    decisions: List[str]
    action_items: List[str]
    controversies: List[str]
    related_topics: List[str] = field(default_factory=list)
    referenced_memories: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "meeting_id": self.meeting_id,
            "topic": self.topic,
            "date": self.date,
            "participants": self.participants,
            "summary": self.summary,
            "decisions": self.decisions,
            "action_items": self.action_items,
            "controversies": self.controversies,
            "related_topics": self.related_topics,
            "referenced_memories": self.referenced_memories,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MeetingContext":
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


class LongTermMemory:
    """长期记忆系统

    存储策略：
    - 每条 MemoryEntry 序列化为 JSON 存入 Redis（key: ltm:memory:{id}）
    - 全量 ID 集合维护在 Redis set（key: ltm:index:all）
    - 进程内维护 LRU 缓存（OrderedDict），上限 MAX_MEMORIES 条
    - 启动时异步懒加载，首次 search 触发全量 warm-up
    """

    def __init__(self):
        # LRU 内存缓存：memory_id -> MemoryEntry（OrderedDict 保持访问顺序）
        self._memories: OrderedDict[str, MemoryEntry] = OrderedDict()
        self._meeting_contexts: Dict[str, MeetingContext] = {}

        # 内存索引（从 Redis 恢复后重建）
        self._entity_index: Dict[str, List[str]] = defaultdict(list)
        self._type_index: Dict[MemoryType, List[str]] = defaultdict(list)
        self._scope_index: Dict[MemoryScope, List[str]] = defaultdict(list)
        self._meeting_index: Dict[str, List[str]] = defaultdict(list)
        self._topic_index: Dict[str, List[str]] = defaultdict(list)

        self._loaded = False   # 是否已从 Redis 完成初始加载
        self._lock = asyncio.Lock()

        # 向量嵌入模型（懒加载）
        self._embedder = None
        self._embedder_loaded = False

    # ------------------------------------------------------------------
    # 持久化层（PostgreSQL 主存储 + Redis 热缓存）
    # ------------------------------------------------------------------

    async def _ensure_loaded(self):
        """确保已从存储层加载数据（懒加载，只执行一次）"""
        if self._loaded:
            return
        async with self._lock:
            if self._loaded:
                return
            await self._load_from_storage()
            self._loaded = True

    async def _load_from_storage(self):
        """冷启动加载：优先从 PostgreSQL 加载，回退到 Redis 缓存"""
        pg_loaded = await self._load_from_pg()
        if not pg_loaded:
            await self._load_from_redis()

    async def _load_from_pg(self) -> bool:
        """从 PostgreSQL 加载最近的记忆（冷启动热身）"""
        try:
            from app.db.database import AsyncSessionLocal
            from app.services.memory_store import MemoryStore
            async with AsyncSessionLocal() as db:
                store = MemoryStore(db)
                pg_memories = await store.search_memories(
                    memory_type=None,
                    memory_status="active",
                    limit=MAX_MEMORIES,
                )
                loaded = 0
                for mem in pg_memories:
                    try:
                        meta = mem.metadata or {}
                        memory_id = meta.get("memory_id") or str(mem.id)
                        entry = MemoryEntry(
                            memory_id=memory_id,
                            type=MemoryType(mem.memory_type) if mem.memory_type in [t.value for t in MemoryType] else MemoryType.MEETING_SUMMARY,
                            scope=MemoryScope(meta.get("scope", "team")) if meta.get("scope") in [s.value for s in MemoryScope] else MemoryScope.TEAM,
                            content=mem.content,
                            meeting_id=meta.get("meeting_id") or (str(mem.source_meeting_id) if mem.source_meeting_id else None),
                            meeting_topic=meta.get("meeting_topic"),
                            entities=meta.get("entities", []),
                            related_memories=meta.get("related_memories", []),
                            confidence=float(meta.get("confidence", mem.confidence_score or 1.0)),
                            expires_at=mem.expires_at.isoformat() if mem.expires_at else None,
                        )
                        if not entry.is_expired():
                            self._add_to_index(entry)
                            loaded += 1
                    except Exception as e:
                        app_logger.warning(f"[Memory] 跳过 PG 记忆: {e}")
            app_logger.info(f"[Memory] 从 PostgreSQL 恢复 {loaded} 条记忆")
            return loaded > 0
        except Exception as e:
            app_logger.warning(f"[Memory] PostgreSQL 加载失败，回退到 Redis: {e}")
            return False

    async def _load_from_redis(self):
        """从 Redis 热缓存恢复所有记忆到内存索引（回退方案）"""
        try:
            all_ids_data = await cache_get(_REDIS_INDEX_KEY)
            all_ids: List[str] = all_ids_data if isinstance(all_ids_data, list) else []

            loaded = 0
            expired = 0
            for memory_id in all_ids:
                raw = await cache_get(_REDIS_MEMORY_KEY.format(memory_id=memory_id))
                if not raw:
                    continue
                try:
                    data = raw if isinstance(raw, dict) else json.loads(raw)
                    entry = MemoryEntry.from_dict(data)
                    if entry.is_expired():
                        expired += 1
                        continue
                    self._add_to_index(entry)
                    loaded += 1
                except Exception as e:
                    app_logger.warning(f"[Memory] 跳过损坏记忆 {memory_id}: {e}")

            # 加载会议上下文
            ctx_ids_data = await cache_get(_REDIS_PREFIX + "ctx_index:all")
            ctx_ids: List[str] = ctx_ids_data if isinstance(ctx_ids_data, list) else []
            for mid in ctx_ids:
                raw = await cache_get(_REDIS_CONTEXT_KEY.format(meeting_id=mid))
                if raw:
                    try:
                        data = raw if isinstance(raw, dict) else json.loads(raw)
                        self._meeting_contexts[mid] = MeetingContext.from_dict(data)
                    except Exception:
                        pass

            app_logger.info(f"[Memory] 从 Redis 恢复 {loaded} 条记忆，跳过 {expired} 条过期记忆")
        except Exception as e:
            app_logger.error(f"[Memory] Redis 加载失败（降级为纯内存模式）: {e}")

    async def _persist_memory(self, entry: MemoryEntry):
        """将单条记忆持久化：主存储 PostgreSQL + 热缓存 Redis"""
        # ── 1. 写入 PostgreSQL（主存储）──────────────────────────────
        try:
            from app.db.database import AsyncSessionLocal
            from app.services.memory_store import MemoryStore
            async with AsyncSessionLocal() as db:
                store = MemoryStore(db)
                # 检查是否已存在（避免重复写入）
                existing = await store.get_memory_by_id(entry.memory_id)
                if existing is None:
                    expires_at_dt = None
                    if entry.expires_at:
                        try:
                            expires_at_dt = datetime.fromisoformat(entry.expires_at)
                        except Exception:
                            pass
                    await store.create_memory(
                        content=entry.content,
                        memory_type=entry.type.value,
                        metadata={
                            "scope": entry.scope.value,
                            "meeting_id": entry.meeting_id,
                            "meeting_topic": entry.meeting_topic,
                            "entities": entry.entities,
                            "related_memories": entry.related_memories,
                            "confidence": entry.confidence,
                            "memory_id": entry.memory_id,
                        },
                        importance_score=entry.confidence,
                        source_type="meeting",
                        source_id=entry.meeting_id,
                        expires_at=expires_at_dt,
                    )
                    app_logger.debug(f"[Memory] 已写入 PostgreSQL: {entry.memory_id}")
        except Exception as e:
            app_logger.warning(f"[Memory] PostgreSQL 写入失败（降级到 Redis 缓存）: {e}")

        # ── 2. 写入 Redis 热缓存（TTL=1小时）───────────────────────
        try:
            data = entry.to_dict()
            key = _REDIS_MEMORY_KEY.format(memory_id=entry.memory_id)
            await cache_set(key, data, ttl=_MEMORY_TTL)

            # 更新全量 ID 列表（仅用于冷启动加载）
            all_ids_data = await cache_get(_REDIS_INDEX_KEY)
            all_ids: List[str] = all_ids_data if isinstance(all_ids_data, list) else []
            if entry.memory_id not in all_ids:
                all_ids.append(entry.memory_id)
                await cache_set(_REDIS_INDEX_KEY, all_ids, ttl=_INDEX_TTL)
        except Exception as e:
            app_logger.warning(f"[Memory] Redis 热缓存写入失败: {e}")

    async def _remove_from_redis(self, memory_id: str):
        """从 Redis 删除单条记忆"""
        try:
            await cache_delete(_REDIS_MEMORY_KEY.format(memory_id=memory_id))
            all_ids_data = await cache_get(_REDIS_INDEX_KEY)
            all_ids: List[str] = all_ids_data if isinstance(all_ids_data, list) else []
            if memory_id in all_ids:
                all_ids.remove(memory_id)
                await cache_set(_REDIS_INDEX_KEY, all_ids, ttl=_INDEX_TTL)
        except Exception as e:
            app_logger.warning(f"[Memory] Redis 删除失败: {e}")

    async def _persist_context(self, context: MeetingContext):
        """持久化会议上下文"""
        try:
            await cache_set(
                _REDIS_CONTEXT_KEY.format(meeting_id=context.meeting_id),
                context.to_dict(),
                ttl=_CONTEXT_TTL,
            )
            ctx_ids_data = await cache_get(_REDIS_PREFIX + "ctx_index:all")
            ctx_ids: List[str] = ctx_ids_data if isinstance(ctx_ids_data, list) else []
            if context.meeting_id not in ctx_ids:
                ctx_ids.append(context.meeting_id)
                await cache_set(_REDIS_PREFIX + "ctx_index:all", ctx_ids, ttl=_INDEX_TTL)
        except Exception as e:
            app_logger.warning(f"[Memory] 会议上下文持久化失败: {e}")

    # ------------------------------------------------------------------
    # 内存索引管理
    # ------------------------------------------------------------------

    def _add_to_index(self, entry: MemoryEntry):
        """将 entry 加入内存 LRU 和所有索引"""
        self._memories[entry.memory_id] = entry
        self._memories.move_to_end(entry.memory_id)

        self._type_index[entry.type].append(entry.memory_id)
        self._scope_index[entry.scope].append(entry.memory_id)
        if entry.meeting_id:
            self._meeting_index[entry.meeting_id].append(entry.memory_id)
        if entry.meeting_topic:
            self._topic_index[entry.meeting_topic.lower()].append(entry.memory_id)
        for entity in entry.entities:
            self._entity_index[entity.lower()].append(entry.memory_id)

        # LRU 淘汰
        while len(self._memories) > MAX_MEMORIES:
            oldest_id, _ = self._memories.popitem(last=False)
            app_logger.debug(f"[Memory] LRU 淘汰内存缓存: {oldest_id}（Redis 中仍保留）")

    def _remove_from_index(self, entry: MemoryEntry):
        """从内存索引中删除 entry"""
        self._memories.pop(entry.memory_id, None)

        def _remove(lst, val):
            try:
                lst.remove(val)
            except ValueError:
                pass

        _remove(self._type_index[entry.type], entry.memory_id)
        _remove(self._scope_index[entry.scope], entry.memory_id)
        if entry.meeting_id:
            _remove(self._meeting_index[entry.meeting_id], entry.memory_id)
        if entry.meeting_topic:
            _remove(self._topic_index[entry.meeting_topic.lower()], entry.memory_id)
        for entity in entry.entities:
            _remove(self._entity_index[entity.lower()], entry.memory_id)
        for related_id in entry.related_memories:
            related = self._memories.get(related_id)
            if related:
                _remove(related.related_memories, entry.memory_id)

    # ------------------------------------------------------------------
    # 向量嵌入（懒加载，失败时回退关键词匹配）
    # ------------------------------------------------------------------

    def _get_embedder(self):
        """懒加载本地向量模型"""
        if self._embedder_loaded:
            return self._embedder
        self._embedder_loaded = True
        try:
            from sentence_transformers import SentenceTransformer
            import os
            # 优先使用多语言模型（对中文更友好）
            model_candidates = [
                "backend/model/paraphrase-multilingual-MiniLM-L12-v2",
                "backend/model/all-MiniLM-L6-v2",
                "paraphrase-multilingual-MiniLM-L12-v2",
            ]
            for candidate in model_candidates:
                if os.path.exists(candidate):
                    self._embedder = SentenceTransformer(candidate)
                    app_logger.info(f"[Memory] 向量模型已加载: {candidate}")
                    return self._embedder
            # 回退到在线模型名称
            self._embedder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
            app_logger.info("[Memory] 向量模型已加载（在线）")
            return self._embedder
        except Exception as e:
            app_logger.warning(f"[Memory] 向量模型加载失败，将使用关键词匹配: {e}")
            self._embedder = None
            return None

    def _compute_similarity(self, query: str, texts: List[str]) -> List[float]:
        """计算 query 与 texts 的余弦相似度，失败时返回空列表"""
        embedder = self._get_embedder()
        if not embedder or not texts:
            return []
        try:
            import numpy as np
            vecs = embedder.encode([query] + texts, normalize_embeddings=True)
            query_vec = vecs[0]
            doc_vecs = vecs[1:]
            scores = (doc_vecs @ query_vec).tolist()
            return scores
        except Exception as e:
            app_logger.warning(f"[Memory] 向量相似度计算失败: {e}")
            return []

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_memory_id() -> str:
        """生成全局唯一 memory_id（uuid4，并发安全）"""
        return f"mem_{uuid.uuid4().hex}"

    # ── 长期记忆写入两道门（对应 docs/总结.md 检索记忆层）──────────

    # 第一道门：事实准入
    # - 用户明确提交的内容必须带请求来源
    # - 系统自动提取的事实必须带会议/文档/记忆引用，并达到置信度阈值
    # - 普通 Agent 回答不直接沉淀，只有纪要/决策/待办/争议等结构化产物才写入
    ADMISSION_THRESHOLD = 0.6  # 置信度准入阈值

    # 允许写入的结构化产物类型
    ADMISSIBLE_TYPES = {
        MemoryType.MEETING_SUMMARY,
        MemoryType.DECISION,
        MemoryType.ACTION_ITEM,
        MemoryType.CONTROVERSY,
    }

    # 第二道门：写入决策
    # - ADD：新事实，直接写入
    # - UPDATE：已有相似记忆但内容更新，在同一事务中写入新记录并将旧记录标记 superseded
    # - DELETE：与已有记忆冲突且新事实置信度更高，标记旧记录 superseded（不物理删除）
    # - NOOP：重复内容，跳过
    UPDATE_SIMILARITY_THRESHOLD = 0.92  # 超过此值视为重复（NOOP）
    CONFLICT_SIMILARITY_THRESHOLD = 0.75  # 超过此值但低于重复阈值，视为更新（UPDATE）

    def _check_admission(
        self,
        type: MemoryType,
        confidence: float,
        source_type: Optional[str],
        source_ref: Optional[str],
    ) -> tuple[bool, str]:
        """第一道门：事实准入检查

        Returns:
            (是否准入, 原因)
        """
        # 普通回答不沉淀
        if type not in self.ADMISSIBLE_TYPES:
            return False, f"类型 {type.value} 非结构化产物，不写入长期记忆"
        # 必须带来源
        if not source_type or not source_ref:
            return False, "缺少来源引用，不写入"
        # 置信度阈值
        if confidence < self.ADMISSION_THRESHOLD:
            return False, f"置信度 {confidence:.2f} 低于阈值 {self.ADMISSION_THRESHOLD}"
        return True, "准入通过"

    def _decide_write(self, new_content: str, new_type: MemoryType) -> tuple[str, Optional[MemoryEntry]]:
        """第二道门：写入决策

        通过简单文本相似度比较新事实与同类型已有记忆：
        - similarity >= UPDATE_SIMILARITY_THRESHOLD → NOOP（重复跳过）
        - CONFLICT_SIMILARITY_THRESHOLD <= similarity < UPDATE_SIMILARITY_THRESHOLD → UPDATE
        - similarity < CONFLICT_SIMILARITY_THRESHOLD → ADD（新事实）

        Returns:
            (决策: ADD/UPDATE/NOOP, 旧记忆条目或None)
        """
        best_match: Optional[MemoryEntry] = None
        best_sim = 0.0
        for mid in self._type_index.get(new_type, []):
            entry = self._memories.get(mid)
            if not entry or entry.is_superseded() or entry.is_expired():
                continue
            sim = self._text_similarity(new_content, entry.content)
            if sim > best_sim:
                best_sim = sim
                best_match = entry

        if best_sim >= self.UPDATE_SIMILARITY_THRESHOLD:
            return "NOOP", best_match
        if best_sim >= self.CONFLICT_SIMILARITY_THRESHOLD:
            return "UPDATE", best_match
        return "ADD", None

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """轻量文本相似度（Jaccard，基于字符集合）

        生产环境可替换为向量相似度，这里用轻量算法避免依赖嵌入模型。
        """
        if not a or not b:
            return 0.0
        set_a = set(a)
        set_b = set(b)
        intersection = set_a & set_b
        union = set_a | set_b
        return len(intersection) / len(union) if union else 0.0

    async def add_memory(
        self,
        type: MemoryType,
        scope: MemoryScope,
        content: str,
        meeting_id: Optional[str] = None,
        meeting_topic: Optional[str] = None,
        entities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        expires_at: Optional[str] = None,
        confidence: float = 1.0,
        source_type: Optional[str] = None,
        source_ref: Optional[str] = None,
    ) -> Optional[MemoryEntry]:
        """添加记忆（持久化到 PostgreSQL 主存储 + Redis 热缓存）

        写入流程（两道门）：
        1. 事实准入：检查类型/来源/置信度
        2. 写入决策：与已有记忆比较，决定 ADD/UPDATE/NOOP
        3. ADD：直接写入；UPDATE：写入新记录 + 旧记录标记 superseded；NOOP：跳过
        """
        await self._ensure_loaded()

        # 第一道门：事实准入
        admitted, reason = self._check_admission(type, confidence, source_type, source_ref)
        if not admitted:
            app_logger.debug(f"[Memory] 准入拒绝: {reason}")
            return None

        # 第二道门：写入决策
        decision, old_entry = self._decide_write(content, type)

        if decision == "NOOP":
            app_logger.debug(f"[Memory] 写入跳过（NOOP），与已有记忆重复")
            return None

        memory_id = self._generate_memory_id()
        entry = MemoryEntry(
            memory_id=memory_id,
            type=type,
            scope=scope,
            content=content,
            meeting_id=meeting_id,
            meeting_topic=meeting_topic,
            entities=entities or [],
            metadata=metadata or {},
            expires_at=expires_at,
            confidence=confidence,
            source_type=source_type,
            source_ref=source_ref,
        )

        # UPDATE：在同一事务中写入新记录并将旧记录标记 superseded
        if decision == "UPDATE" and old_entry:
            old_entry.superseded_by = memory_id
            await self._persist_memory(old_entry)  # 更新旧记录的 superseded_by
            app_logger.info(f"[Memory] 更新记忆: {old_entry.memory_id} → {memory_id}（旧记录标记 superseded）")

        self._add_to_index(entry)
        await self._link_related_memories(entry)
        await self._persist_memory(entry)

        app_logger.info(f"[Memory] 写入记忆: {memory_id} - {type.value}（决策: {decision}）")
        return entry

    async def _link_related_memories(self, entry: MemoryEntry):
        """关联相关记忆（实体 + 主题共现）"""
        related_ids: set = set()

        for entity in entry.entities:
            for mid in self._entity_index.get(entity.lower(), []):
                if mid != entry.memory_id:
                    related_ids.add(mid)

        if entry.meeting_topic:
            for mid in self._topic_index.get(entry.meeting_topic.lower(), []):
                if mid != entry.memory_id:
                    related_ids.add(mid)

        entry.related_memories = list(related_ids)

        for mid in related_ids:
            related = self._memories.get(mid)
            if related and entry.memory_id not in related.related_memories:
                related.related_memories.append(entry.memory_id)

    async def _compress_summary(self, summary: str, topic: str, max_chars: int = 300) -> str:
        """使用 LLM 将会议摘要压缩到 max_chars 字以内（Level-1 摘要压缩）"""
        if len(summary) <= max_chars:
            return summary
        try:
            from app.services.llm_service import LLMService
            from app.core.config import settings
            llm = LLMService()
            prompt = (
                f"请将以下会议摘要压缩到{max_chars}字以内，保留核心决策和行动项，删除冗余细节。\n"
                f"会议主题：{topic}\n"
                f"原始摘要：\n{summary}\n"
                f"压缩摘要（不超过{max_chars}字，直接输出，不要任何前缀）："
            )
            compressed = await llm.generate_text(prompt)
            if compressed and len(compressed.strip()) > 10:
                result = compressed.strip()[:max_chars]
                app_logger.debug(f"[Memory] 摘要压缩: {len(summary)}→{len(result)} 字")
                return result
        except Exception as e:
            app_logger.warning(f"[Memory] LLM 摘要压缩失败，使用原始截断: {e}")
        # 回退：直接截断
        return summary[:max_chars]

    async def add_meeting_context(self, context: MeetingContext):
        """添加会议上下文，自动拆解为多条结构化记忆（写入前做 LLM 摘要压缩）

        所有记忆带来源 source_type=meeting, source_ref=meeting_id，通过事实准入检查。
        """
        self._meeting_contexts[context.meeting_id] = context
        await self._persist_context(context)

        # P1 #3: Level-1 压缩——写入前用 LLM 将摘要压缩到 300 字以内
        compressed_summary = await self._compress_summary(
            context.summary, context.topic, max_chars=300
        )

        # 结构化产物带会议来源，通过两道门写入
        await self.add_memory(
            type=MemoryType.MEETING_SUMMARY,
            scope=MemoryScope.TEAM,
            content=compressed_summary,
            meeting_id=context.meeting_id,
            meeting_topic=context.topic,
            entities=context.participants,
            source_type="meeting",
            source_ref=context.meeting_id,
        )
        for decision in context.decisions:
            await self.add_memory(
                type=MemoryType.DECISION,
                scope=MemoryScope.TEAM,
                content=decision,
                meeting_id=context.meeting_id,
                meeting_topic=context.topic,
                source_type="meeting",
                source_ref=context.meeting_id,
            )
        for action_item in context.action_items:
            await self.add_memory(
                type=MemoryType.ACTION_ITEM,
                scope=MemoryScope.TEAM,
                content=action_item,
                meeting_id=context.meeting_id,
                meeting_topic=context.topic,
                source_type="meeting",
                source_ref=context.meeting_id,
            )
        for controversy in context.controversies:
            await self.add_memory(
                type=MemoryType.CONTROVERSY,
                scope=MemoryScope.TEAM,
                content=controversy,
                meeting_id=context.meeting_id,
                meeting_topic=context.topic,
                source_type="meeting",
                source_ref=context.meeting_id,
            )
        app_logger.info(f"[Memory] 添加会议上下文: {context.meeting_id}")

    def get_memory(self, memory_id: str) -> Optional[MemoryEntry]:
        """获取单条记忆（过期则返回 None）"""
        entry = self._memories.get(memory_id)
        if entry and entry.is_expired():
            return None
        return entry

    def get_memories_by_type(self, type: MemoryType) -> List[MemoryEntry]:
        return [
            self._memories[m] for m in self._type_index.get(type, [])
            if m in self._memories and not self._memories[m].is_expired()
        ]

    def get_memories_by_scope(self, scope: MemoryScope) -> List[MemoryEntry]:
        return [
            self._memories[m] for m in self._scope_index.get(scope, [])
            if m in self._memories and not self._memories[m].is_expired()
        ]

    def get_memories_by_meeting(self, meeting_id: str) -> List[MemoryEntry]:
        return [
            self._memories[m] for m in self._meeting_index.get(meeting_id, [])
            if m in self._memories and not self._memories[m].is_expired()
        ]

    async def delete_memory(self, memory_id: str) -> bool:
        """删除记忆（内存 + Redis + PostgreSQL）"""
        await self._ensure_loaded()
        entry = self._memories.get(memory_id)
        if not entry:
            return False
        self._remove_from_index(entry)
        await self._remove_from_redis(memory_id)
        # ── 同步删除 PostgreSQL 主存储 ───────────────────────────────
        try:
            from app.db.database import AsyncSessionLocal
            from app.services.memory_store import MemoryStore
            async with AsyncSessionLocal() as db:
                store = MemoryStore(db)
                await store.hard_delete_memory(memory_id)
                app_logger.debug(f"[Memory] 已从 PostgreSQL 删除: {memory_id}")
        except Exception as e:
            app_logger.warning(f"[Memory] PostgreSQL 删除失败（内存/Redis 已删除）: {e}")
        app_logger.info(f"[Memory] 删除记忆: {memory_id}")
        return True

    async def purge_expired(self) -> int:
        """清理所有已过期记忆（内存 + Redis + PostgreSQL），返回清理数量"""
        await self._ensure_loaded()
        expired_ids = [
            mid for mid, entry in self._memories.items() if entry.is_expired()
        ]
        for mid in expired_ids:
            entry = self._memories[mid]
            self._remove_from_index(entry)
            await self._remove_from_redis(mid)
        # ── 批量删除 PostgreSQL 主存储中的过期记录 ──────────────────────
        if expired_ids:
            try:
                from app.db.database import AsyncSessionLocal
                from app.services.memory_store import MemoryStore
                async with AsyncSessionLocal() as db:
                    store = MemoryStore(db)
                    for mid in expired_ids:
                        try:
                            await store.hard_delete_memory(mid)
                        except Exception:
                            pass
                    app_logger.debug(f"[Memory] 已从 PostgreSQL 批量删除 {len(expired_ids)} 条过期记忆")
            except Exception as e:
                app_logger.warning(f"[Memory] PostgreSQL 批量删除失败（内存/Redis 已清理）: {e}")
            app_logger.info(f"[Memory] 已清理 {len(expired_ids)} 条过期记忆")
        return len(expired_ids)

    async def search_memories(
        self, query: str, limit: int = 10
    ) -> List[Tuple[MemoryEntry, float]]:
        """搜索相关记忆

        策略：
        1. 优先向量语义检索（余弦相似度）
        2. 向量模型不可用时回退到关键词匹配
        3. 两种方式均叠加时间衰减系数
        4. 自动过滤已过期记忆
        """
        await self._ensure_loaded()

        # 先过滤有效记忆
        valid_entries: List[MemoryEntry] = [
            e for e in self._memories.values() if not e.is_expired()
        ]
        if not valid_entries:
            return []

        def _recency(entry: MemoryEntry) -> float:
            try:
                age_days = (datetime.now() - datetime.fromisoformat(entry.timestamp)).days
                return max(0.1, 1.0 - age_days / 30)
            except Exception:
                return 0.5

        # ------ 尝试向量语义检索 ------
        contents = [e.content for e in valid_entries]
        sim_scores = self._compute_similarity(query, contents)

        if sim_scores and len(sim_scores) == len(valid_entries):
            results = [
                (entry, float(sim_scores[i]) * _recency(entry) * entry.confidence)
                for i, entry in enumerate(valid_entries)
                if sim_scores[i] > 0.1   # 过滤低相关
            ]
            results.sort(key=lambda x: x[1], reverse=True)
            app_logger.debug(f"[Memory] 向量检索命中 {len(results)} 条记忆")
            return results[:limit]

        # ------ 回退：关键词匹配 ------
        query_lower = query.lower()
        results = []
        for entry in valid_entries:
            score = 0.0
            if query_lower in entry.content.lower():
                score += 0.5
            if query_lower in (entry.meeting_topic or "").lower():
                score += 0.3
            for entity in entry.entities:
                if query_lower in entity.lower():
                    score += 0.2
            if score > 0:
                score *= _recency(entry) * entry.confidence
                results.append((entry, score))

        results.sort(key=lambda x: x[1], reverse=True)
        app_logger.debug(f"[Memory] 关键词检索命中 {len(results)} 条记忆")
        return results[:limit]

    async def find_relevant_memories(
        self, query: str, context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """查找相关记忆并返回引用格式"""
        results = await self.search_memories(query, limit=5)
        referenced = []
        for entry, score in results:
            referenced.append({
                "memory_id": entry.memory_id,
                "type": entry.type.value,
                "content": entry.content[:200] + "..." if len(entry.content) > 200 else entry.content,
                "meeting_topic": entry.meeting_topic,
                "meeting_id": entry.meeting_id,
                "timestamp": entry.timestamp,
                "relevance_score": round(score, 3),
                "entities": entry.entities,
                "related_memories": entry.related_memories[:3],
            })
        return referenced

    async def generate_context_prompt(
        self, query: str, context: Optional[Dict[str, Any]] = None
    ) -> str:
        """生成包含历史记忆的上下文提示词"""
        memories = await self.find_relevant_memories(query, context)
        if not memories:
            return ""

        prompt_parts = ["【历史会议参考】"]
        for i, memory in enumerate(memories, 1):
            try:
                ts = datetime.fromisoformat(memory["timestamp"])
                days_ago = (datetime.now() - ts).days
                if days_ago == 0:
                    time_ago = "今天"
                elif days_ago == 1:
                    time_ago = "昨天"
                elif days_ago < 7:
                    time_ago = f"{days_ago}天前"
                else:
                    time_ago = ts.strftime("%m-%d")
            except Exception:
                time_ago = "之前"

            prompt_parts.append(
                f"{i}. [{memory['type']}] {memory['content']}\n"
                f"   (来源: {memory['meeting_topic'] or '历史会议'}, {time_ago})\n"
            )
        return "\n".join(prompt_parts)

    async def get_cross_meeting_context(self, current_meeting_id: str) -> List[Dict[str, Any]]:
        """获取跨会议上下文"""
        await self._ensure_loaded()
        current_ctx = self._meeting_contexts.get(current_meeting_id)
        if not current_ctx:
            return []

        all_related = []
        for topic in current_ctx.related_topics:
            for mid in self._topic_index.get(topic.lower(), []):
                entry = self._memories.get(mid)
                if entry and not entry.is_expired() and entry.meeting_id != current_meeting_id:
                    all_related.append(entry.to_dict())

        # 去重（按 meeting_id 保留首条）
        seen: Dict[str, Dict] = {}
        for mem in all_related:
            m_id = mem.get("meeting_id")
            if m_id and m_id not in seen:
                seen[m_id] = mem
        return list(seen.values())

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        valid = [e for e in self._memories.values() if not e.is_expired()]
        type_counts = {t.value: 0 for t in MemoryType}
        for e in valid:
            type_counts[e.type.value] = type_counts.get(e.type.value, 0) + 1

        return {
            "total_memories": len(valid),
            "total_in_lru": len(self._memories),
            "total_meetings": len(self._meeting_contexts),
            "by_type": type_counts,
            "loaded_from_redis": self._loaded,
            "vector_search_available": self._get_embedder() is not None,
        }

    async def clear(self):
        """清空所有记忆（内存 + Redis）"""
        self._memories.clear()
        self._meeting_contexts.clear()
        self._entity_index.clear()
        self._type_index.clear()
        self._scope_index.clear()
        self._meeting_index.clear()
        self._topic_index.clear()
        try:
            await cache_delete(_REDIS_INDEX_KEY)
            await cache_delete(_REDIS_PREFIX + "ctx_index:all")
            await cache_delete_pattern(_REDIS_PREFIX + "*")
        except Exception as e:
            app_logger.warning(f"[Memory] Redis 清空失败: {e}")
        app_logger.info("[Memory] 已清空所有记忆")
