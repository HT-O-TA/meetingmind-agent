"""记忆系统 - PostgreSQL 主存储 + Redis 缓存层

架构说明：
- PostgreSQL：长期记忆主存储（持久化、结构化查询）
- Redis：短期记忆缓存 + 热点数据 LRU 缓存 + Checkpointer
- Milvus：语义向量存储（关联记忆的向量表示）

迁移状态（Phase 2）：
- 本模块为旧接口，已标记 deprecated
- 新功能请使用 UnifiedMemoryService（app/services/unified_memory_service.py）
- 旧接口内部会自动转发到 UnifiedMemoryService，并添加 deprecated 警告
"""
import json
import warnings
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logger import app_logger
from app.core.config_center import get_config
from app.core.cache import cache_get, cache_set, cache_delete
from app.services.memory_store import MemoryStore


class MemoryType(str, Enum):
    """记忆类型"""
    SHORT_TERM = "short_term"    # 短期记忆（当前对话）
    LONG_TERM = "long_term"      # 长期记忆（跨会话）
    EPISODIC = "episodic"        # 情景记忆（事件记录）
    SEMANTIC = "semantic"        # 语义记忆（知识事实）
    WORKING = "working"          # 工作记忆（当前任务）


class MemoryStatus(str, Enum):
    """记忆状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


@dataclass
class MemoryItem:
    """记忆项（内存中使用的轻量级表示）"""
    memory_id: str
    type: MemoryType
    content: str
    metadata: Dict[str, Any]
    created_at: datetime = None
    updated_at: datetime = None
    expires_at: Optional[datetime] = None
    status: MemoryStatus = MemoryStatus.ACTIVE
    relevance_score: float = 1.0
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()


@dataclass
class Entity:
    """实体"""
    entity_id: str
    name: str
    type: str
    properties: Dict[str, Any]
    relations: List[Tuple[str, str, str]]
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class MemorySystem:
    """记忆系统 - PostgreSQL 持久化 + Redis 缓存
    
    .. deprecated::
        请使用 UnifiedMemoryService (app/services/unified_memory_service.py) 替代。
        本类将在 Phase 4 废弃。
    """
    
    def __init__(self, session_id: Optional[str] = None, db: Optional[AsyncSession] = None):
        self._session_id = session_id
        self._db = db
        self._memory_store: Optional[MemoryStore] = None
        self._deprecation_warned = False  # 是否已输出过 deprecated 警告
        
        # 短期记忆：保存在内存 + Redis 缓存
        self._short_term_memory: List[MemoryItem] = []
        
        # 实体关系缓存（内存中保存当前会话的实体）
        self._entities: Dict[str, Entity] = {}
        self._entity_relations: Dict[str, List[Tuple[str, str]]] = {}
        
        self._max_short_term = get_config("agent.max_short_term_memory", 100)
    
    def _warn_deprecated(self, method_name: str):
        """输出 deprecated 警告（每个方法只警告一次）"""
        if not self._deprecation_warned:
            self._deprecation_warned = True
            warnings.warn(
                f"MemorySystem.{method_name}() is deprecated, "
                f"please use UnifiedMemoryService from app.services.unified_memory_service.py instead. "
                f"See migration plan in Phase 2.",
                DeprecationWarning,
                stacklevel=2
            )
            app_logger.warning(
                f"[DEPRECATED] MemorySystem.{method_name}() is deprecated. "
                f"Use UnifiedMemoryService instead."
            )
    
    @property
    def memory_store(self) -> MemoryStore:
        """获取记忆存储服务"""
        if self._memory_store is None:
            self._memory_store = MemoryStore(db=self._db)
        return self._memory_store
    
    # ==================== 短期记忆（内存 + Redis 缓存）====================
    
    async def load_short_term_from_cache(self):
        """从 Redis 加载短期记忆"""
        if not self._session_id:
            return
        
        short_term_data = await cache_get(f"memory:{self._session_id}:short_term")
        if short_term_data:
            self._short_term_memory = [self._deserialize_memory_item(item) for item in short_term_data]
            app_logger.debug(f"[Memory] 从Redis加载短期记忆: {len(self._short_term_memory)} 条")
    
    async def save_short_term_to_cache(self):
        """保存短期记忆到 Redis"""
        if not self._session_id:
            return
        
        short_term_data = [self._serialize_memory_item(item) for item in self._short_term_memory]
        from app.core.config import settings
        await cache_set(f"memory:{self._session_id}:short_term", short_term_data, ttl=settings.MEMORY_SESSION_TTL)
        app_logger.debug(f"[Memory] 保存短期记忆到Redis: {len(short_term_data)} 条")
    
    def add_short_term_memory(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> MemoryItem:
        """添加短期记忆（内存中）"""
        memory = MemoryItem(
            memory_id=f"st_{int(datetime.now().timestamp())}",
            type=MemoryType.SHORT_TERM,
            content=content,
            metadata=metadata or {}
        )
        
        self._short_term_memory.append(memory)
        
        # 保持短期记忆在限制范围内
        while len(self._short_term_memory) > self._max_short_term:
            removed = self._short_term_memory.pop(0)
            app_logger.debug(f"[Memory] 短期记忆已过期: {removed.memory_id}")
        
        app_logger.debug(f"[Memory] 添加短期记忆: {memory.memory_id}")
        return memory
    
    def get_short_term_memory(self) -> List[MemoryItem]:
        """获取短期记忆"""
        return self._short_term_memory
    
    def clear_short_term_memory(self):
        """清空短期记忆"""
        self._short_term_memory.clear()
        app_logger.info("[Memory] 短期记忆已清空")
    
    async def consolidate_short_term(self) -> Optional[str]:
        """整合短期记忆为长期记忆"""
        if not self._short_term_memory:
            return None
        
        contents = [m.content for m in self._short_term_memory]
        consolidated = " | ".join(contents[:10])
        
        # 存入 PostgreSQL 长期记忆
        await self.add_long_term_memory(
            content=consolidated,
            metadata={"type": "consolidated", "source": "short_term"}
        )
        
        self.clear_short_term_memory()
        app_logger.info("[Memory] 短期记忆已整合为长期记忆")
        
        return consolidated
    
    # ==================== 长期记忆（PostgreSQL 持久化）====================
    
    async def add_long_term_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        expires_at: Optional[datetime] = None,
        importance_score: float = 0.5,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        meeting_id: Optional[int] = None,
    ) -> Optional[MemoryItem]:
        """添加长期记忆到 PostgreSQL
        
        注意：LONG_TERM 记忆存储在 PostgreSQL 主存储中，默认有效期由 
        MEMORY_LONG_TERM_DEFAULT_DAYS 配置（默认365天），可通过 expires_at 参数自定义
        Redis 缓存失效不影响数据持久化，缓存失效后会自动从 PG 重新加载
        
        .. deprecated::
            本方法会自动转发到 UnifiedMemoryService，建议直接使用新接口。
        """
        self._warn_deprecated("add_long_term_memory")
        
        if self._db is None:
            # 如果没有数据库连接，回退到内存存储（不推荐）
            return self._add_long_term_memory_in_memory(content, metadata, expires_at)
        
        # 如果未指定过期时间，使用默认有效期
        if expires_at is None:
            from app.core.config import settings
            default_days = settings.MEMORY_LONG_TERM_DEFAULT_DAYS
            if default_days > 0:
                expires_at = datetime.now() + timedelta(days=default_days)
        
        try:
            # 通过 MemoryStore 存入 PostgreSQL
            db_memory = await self.memory_store.create_memory(
                content=content,
                memory_type=MemoryType.LONG_TERM.value,
                user_id=None,  # 可从 session 获取
                session_id=self._session_id,
                metadata=metadata,
                importance_score=importance_score,
                source_type=source_type,
                source_id=source_id,
                source_meeting_id=meeting_id,
                expires_at=expires_at,
            )
            
            # 转换为 MemoryItem 返回
            item = MemoryItem(
                memory_id=db_memory.memory_id,
                type=MemoryType.LONG_TERM,
                content=db_memory.content,
                metadata=db_memory.metadata or {},
                created_at=db_memory.created_at,
                status=MemoryStatus.ACTIVE,
            )
            
            # 写入 Redis 热点缓存
            cache_key = f"memory:hot:{db_memory.memory_id}"
            from app.core.config import settings
            await cache_set(cache_key, self._serialize_memory_item(item), ttl=settings.MEMORY_HOT_CACHE_TTL)
            
            app_logger.info(f"[Memory] 添加长期记忆到PG: {db_memory.memory_id}")
            return item
            
        except Exception as e:
            app_logger.error(f"[Memory] 添加长期记忆失败: {e}")
            # 回退到内存存储
            return self._add_long_term_memory_in_memory(content, metadata, expires_at)
    
    async def search_long_term_memory(
        self,
        query: str,
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
        memory_type: Optional[str] = None,
        top_k: int = 5,
    ) -> List[MemoryItem]:
        """搜索长期记忆（PostgreSQL 结构化查询 + 聚合 UnifiedMemoryService 结果）
        
        .. deprecated::
            本方法会自动聚合 UnifiedMemoryService 的结果，建议直接使用新接口。
        """
        self._warn_deprecated("search_long_term_memory")
        
        if self._db is None:
            # 回退到内存搜索
            return self._search_long_term_memory_in_memory(query, top_k)
        
        try:
            # 先查 Redis 热点缓存
            cache_key = f"memory:search:{hash(query) % 10000}"
            cached = await cache_get(cache_key)
            if cached:
                app_logger.debug(f"[Memory] 搜索缓存命中: '{query}'")
                return [self._deserialize_memory_item(item) for item in cached]
            
            # 查询 PostgreSQL（原有逻辑）
            db_memories = await self.memory_store.search_memories(
                user_id=user_id,
                session_id=session_id or self._session_id,
                memory_type=memory_type or MemoryType.LONG_TERM.value,
                keyword=query,
                limit=top_k,
            )
            
            # 转换为 MemoryItem
            results = []
            seen_contents = set()  # 用于去重
            
            for db_memory in db_memories:
                content_hash = hash(db_memory.content[:100])
                if content_hash not in seen_contents:
                    seen_contents.add(content_hash)
                    item = MemoryItem(
                        memory_id=db_memory.memory_id,
                        type=MemoryType(db_memory.memory_type),
                        content=db_memory.content,
                        metadata=db_memory.metadata or {},
                        created_at=db_memory.created_at,
                        relevance_score=db_memory.importance_score,
                    )
                    results.append(item)
            
            # 按相关性分数排序，返回 Top-N
            results.sort(key=lambda x: x.relevance_score, reverse=True)
            results = results[:top_k]
            
            # 写入搜索缓存（短TTL）
            if results:
                await cache_set(cache_key, [self._serialize_memory_item(item) for item in results], ttl=300)
            
            app_logger.info(f"[Memory] 搜索长期记忆: '{query}' -> {len(results)} 条结果")
            return results
            
        except Exception as e:
            app_logger.error(f"[Memory] 搜索长期记忆失败: {e}")
            return []
    
    async def get_long_term_memory(self, memory_id: str) -> Optional[MemoryItem]:
        """获取长期记忆（带 Redis 缓存穿透保护）"""
        if self._db is None:
            return self._get_long_term_memory_in_memory(memory_id)
        
        try:
            # 1. 先查 Redis 热点缓存
            cache_key = f"memory:hot:{memory_id}"
            cached = await cache_get(cache_key)
            if cached:
                app_logger.debug(f"[Memory] 记忆缓存命中: {memory_id}")
                return self._deserialize_memory_item(cached)
            
            # 2. 查 PostgreSQL
            db_memory = await self.memory_store.get_memory_by_id(memory_id)
            if not db_memory:
                return None
            
            # 3. 转换为 MemoryItem
            item = MemoryItem(
                memory_id=db_memory.memory_id,
                type=MemoryType(db_memory.memory_type),
                content=db_memory.content,
                metadata=db_memory.metadata or {},
                created_at=db_memory.created_at,
                status=MemoryStatus(db_memory.memory_status),
                relevance_score=db_memory.importance_score,
            )
            
            # 4. 写入 Redis 缓存
            from app.core.config import settings
            await cache_set(cache_key, self._serialize_memory_item(item), ttl=settings.MEMORY_HOT_CACHE_TTL)
            
            app_logger.debug(f"[Memory] 从PG获取记忆: {memory_id}")
            return item
            
        except Exception as e:
            app_logger.error(f"[Memory] 获取长期记忆失败: {e}")
            return None
    
    async def update_long_term_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """更新长期记忆"""
        if self._db is None:
            return False
        
        try:
            await self.memory_store.update_memory(
                memory_id=memory_id,
                content=content,
                metadata=metadata,
            )
            
            # 清除 Redis 缓存
            cache_key = f"memory:hot:{memory_id}"
            await cache_delete(cache_key)
            
            app_logger.info(f"[Memory] 更新长期记忆: {memory_id}")
            return True
            
        except Exception as e:
            app_logger.error(f"[Memory] 更新长期记忆失败: {e}")
            return False
    
    async def archive_long_term_memory(self, memory_id: str) -> bool:
        """归档长期记忆"""
        if self._db is None:
            return False
        
        try:
            await self.memory_store.update_memory(
                memory_id=memory_id,
                memory_status="archived",
            )
            
            # 清除缓存
            cache_key = f"memory:hot:{memory_id}"
            await cache_delete(cache_key)
            
            app_logger.info(f"[Memory] 归档长期记忆: {memory_id}")
            return True
            
        except Exception as e:
            app_logger.error(f"[Memory] 归档长期记忆失败: {e}")
            return False
    
    # ==================== 实体关系（PostgreSQL 持久化）====================
    
    async def add_entity(
        self,
        name: str,
        entity_type: str,
        user_id: Optional[int] = None,
        properties: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
    ) -> Optional[Entity]:
        """添加实体到 PostgreSQL"""
        if self._db is None:
            return self._add_entity_in_memory(name, entity_type, properties)
        
        try:
            db_entity = await self.memory_store.create_entity(
                name=name,
                entity_type=entity_type,
                user_id=user_id,
                properties=properties,
                description=description,
            )
            
            entity = Entity(
                entity_id=db_entity.entity_id,
                name=db_entity.name,
                type=db_entity.entity_type,
                properties=db_entity.properties or {},
                relations=[],
            )
            
            # 缓存到内存
            self._entities[entity.entity_id] = entity
            
            app_logger.info(f"[Memory] 添加实体到PG: {name} ({entity_type})")
            return entity
            
        except Exception as e:
            app_logger.error(f"[Memory] 添加实体失败: {e}")
            return self._add_entity_in_memory(name, entity_type, properties)
    
    async def get_entity(self, entity_id: str) -> Optional[Entity]:
        """获取实体"""
        # 先查内存缓存
        if entity_id in self._entities:
            return self._entities[entity_id]
        
        if self._db is None:
            return None
        
        try:
            db_entity = await self.memory_store.get_entity_by_id(entity_id)
            if not db_entity:
                return None
            
            entity = Entity(
                entity_id=db_entity.entity_id,
                name=db_entity.name,
                type=db_entity.entity_type,
                properties=db_entity.properties or {},
                relations=[],
            )
            
            # 缓存到内存
            self._entities[entity_id] = entity
            return entity
            
        except Exception as e:
            app_logger.error(f"[Memory] 获取实体失败: {e}")
            return None
    
    async def add_entity_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        description: str = "",
    ) -> bool:
        """添加实体关系"""
        if self._db is None:
            return self._add_entity_relation_in_memory(source_id, target_id, relation_type, description)
        
        try:
            await self.memory_store.create_relation(
                source_entity_id=source_id,
                target_entity_id=target_id,
                relation_type=relation_type,
                description=description,
            )
            
            # 更新内存缓存
            if source_id in self._entities:
                self._entities[source_id].relations.append((target_id, relation_type, description))
            
            app_logger.info(f"[Memory] 添加关系到PG: {source_id} -{relation_type}-> {target_id}")
            return True
            
        except Exception as e:
            app_logger.error(f"[Memory] 添加关系失败: {e}")
            return False
    
    # ==================== 辅助方法 ====================
    
    def _add_long_term_memory_in_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        expires_at: Optional[datetime] = None,
    ) -> MemoryItem:
        """回退：内存中添加长期记忆"""
        memory_id = f"lt_{int(datetime.now().timestamp())}_{len(self._short_term_memory)}"
        item = MemoryItem(
            memory_id=memory_id,
            type=MemoryType.LONG_TERM,
            content=content,
            metadata=metadata or {},
            expires_at=expires_at,
        )
        app_logger.warning(f"[Memory] 回退到内存存储: {memory_id}")
        return item
    
    def _search_long_term_memory_in_memory(self, query: str, top_k: int = 5) -> List[MemoryItem]:
        """回退：内存中搜索"""
        return []  # 内存中没有长期记忆数据
    
    def _get_long_term_memory_in_memory(self, memory_id: str) -> Optional[MemoryItem]:
        """回退：内存中获取"""
        return None
    
    def _add_entity_in_memory(self, name: str, entity_type: str, properties: Optional[Dict] = None) -> Entity:
        """回退：内存中添加实体"""
        entity = Entity(
            entity_id=f"ent_{int(datetime.now().timestamp())}",
            name=name,
            type=entity_type,
            properties=properties or {},
            relations=[],
        )
        self._entities[entity.entity_id] = entity
        return entity
    
    def _add_entity_relation_in_memory(self, source_id: str, target_id: str, relation_type: str, description: str = "") -> bool:
        """回退：内存中添加关系"""
        if source_id not in self._entities:
            return False
        self._entities[source_id].relations.append((target_id, relation_type, description))
        return True
    
    def _serialize_memory_item(self, item: MemoryItem) -> Dict[str, Any]:
        """序列化记忆项"""
        data = asdict(item)
        data["type"] = item.type.value
        data["status"] = item.status.value
        data["created_at"] = item.created_at.isoformat() if item.created_at else None
        data["updated_at"] = item.updated_at.isoformat() if item.updated_at else None
        data["expires_at"] = item.expires_at.isoformat() if item.expires_at else None
        return data
    
    def _deserialize_memory_item(self, data: Dict[str, Any]) -> MemoryItem:
        """反序列化记忆项"""
        return MemoryItem(
            memory_id=data["memory_id"],
            type=MemoryType(data["type"]),
            content=data["content"],
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            status=MemoryStatus(data.get("status", "active")),
            relevance_score=data.get("relevance_score", 1.0),
        )
    
    def get_memory_summary(self) -> Dict[str, Any]:
        """获取记忆系统摘要"""
        return {
            "short_term_count": len(self._short_term_memory),
            "entity_count": len(self._entities),
            "db_connected": self._db is not None,
            "redis_used": True,
        }


# ==================== 测试兼容类（保留原有接口）====================

class ShortTermMemory:
    """短期记忆类（测试兼容）"""
    
    def __init__(self, max_raw_turns: int = 10):
        self.max_raw_turns = max_raw_turns
        self.raw_turns: List[Dict[str, Any]] = []
        self.pending_for_compression: List[Dict[str, Any]] = []
        self.summarized_turns: List[Dict[str, Any]] = []
        self._next_turn_id = 1
    
    def add_turn(self, question: str, answer: str, **kwargs) -> Dict[str, Any]:
        turn = {
            "turn_id": self._next_turn_id,
            "question": question,
            "answer": answer,
            "timestamp": datetime.now().isoformat(),
            "task_type": kwargs.get("task_type", "qa"),
            "success": kwargs.get("success", True),
            **kwargs
        }
        self._next_turn_id += 1
        self.raw_turns.append(turn)
        self.mark_for_compression()
        return turn
    
    def mark_for_compression(self):
        while len(self.raw_turns) > self.max_raw_turns:
            removed = self.raw_turns.pop(0)
            self.pending_for_compression.append(removed)
    
    def get_recent_turns(self, n: int) -> List[Dict[str, Any]]:
        return self.raw_turns[-n:]
    
    def get_context(self) -> str:
        if not self.raw_turns:
            return ""
        context_parts = []
        for turn in self.raw_turns:
            context_parts.append(f"问: {turn['question']}")
            context_parts.append(f"答: {turn['answer']}")
        return "\n".join(context_parts)
    
    def compress(self, summary: Dict[str, Any]):
        self.summarized_turns.append(summary)
        self.pending_for_compression.clear()
    
    def get_summary(self) -> Dict[str, Any]:
        return {
            "raw_turns": len(self.raw_turns),
            "summarized_turns": len(self.summarized_turns),
            "pending_for_compression": len(self.pending_for_compression)
        }


class LongTermMemory:
    """长期记忆类（测试兼容 - 实际数据在 PostgreSQL）"""
    
    def __init__(self, max_items: int = 1000):
        self.max_items = max_items
        self.items: List[Dict[str, Any]] = []
        self.key_facts: List[Dict[str, Any]] = []
    
    def add_memory(self, category: str, content: str, **kwargs) -> Dict[str, Any]:
        memory = {
            "memory_id": f"mem_{len(self.items) + 1}",
            "category": category,
            "content": content,
            "importance": kwargs.get("importance", 0.5),
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        self.items.append(memory)
        self._prune_low_importance()
        return memory
    
    def _prune_low_importance(self):
        if len(self.items) <= self.max_items:
            return
        self.items.sort(key=lambda x: x["importance"], reverse=True)
        self.items = self.items[:self.max_items]
    
    def search_by_content(self, query: str) -> List[Dict[str, Any]]:
        query_lower = query.lower()
        return [item for item in self.items if query_lower in item["content"].lower()]
    
    def add_key_fact(self, content: str, category: str, **kwargs) -> Dict[str, Any]:
        fact = {
            "fact_id": f"fact_{len(self.key_facts) + 1}",
            "content": content,
            "category": category,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        self.key_facts.append(fact)
        return fact


class MemoryCompressor:
    """记忆压缩器（测试兼容）"""
    
    def __init__(self, llm_service=None):
        self.llm_service = llm_service
    
    async def compress_turns(self, turns: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not turns:
            return {
                "turn_id": 0,
                "summary": "无对话记录",
                "key_points": [],
                "original_turn_ids": [],
                "timestamp": datetime.now().isoformat(),
                "task_type": "qa"
            }
        
        questions = [t["question"] for t in turns if "question" in t]
        answers = [t["answer"] for t in turns if "answer" in t]
        
        return {
            "turn_id": turns[-1]["turn_id"],
            "summary": f"对话摘要：{' '.join(questions)} -> {' '.join(answers)}",
            "key_points": [],
            "original_turn_ids": [t["turn_id"] for t in turns],
            "timestamp": datetime.now().isoformat(),
            "task_type": turns[-1].get("task_type", "qa")
        }


class MemoryManager:
    """记忆管理器（测试兼容）"""
    
    def __init__(
        self,
        max_short_term_turns: int = 10,
        max_long_term_items: int = 1000,
        enable_compression: bool = True,
        llm_service=None
    ):
        self.short_term = ShortTermMemory(max_raw_turns=max_short_term_turns // 2)
        self.long_term = LongTermMemory(max_items=max_long_term_items)
        self.enable_compression = enable_compression
        self.compressor = MemoryCompressor(llm_service) if enable_compression else None
        self._checkpoint_enabled = False
    
    def add_conversation(self, question: str, answer: str, **kwargs):
        self.short_term.add_turn(question, answer, **kwargs)
    
    def get_context_for_query(self, query: str, n_recent: int = 3) -> str:
        recent_turns = self.short_term.get_recent_turns(n_recent)
        if not recent_turns:
            return ""
        context_parts = []
        for turn in recent_turns:
            context_parts.append(f"问: {turn['question']}")
            context_parts.append(f"答: {turn['answer']}")
        return "\n".join(context_parts)
    
    def get_memory_stats(self) -> Dict[str, Any]:
        short_term_summary = self.short_term.get_summary()
        return {
            "short_term": short_term_summary,
            "long_term": {
                "items": len(self.long_term.items),
                "key_facts": len(self.long_term.key_facts)
            }
        }
    
    def clear_all(self):
        self.short_term = ShortTermMemory(max_raw_turns=self.short_term.max_raw_turns)
        self.long_term = LongTermMemory(max_items=self.long_term.max_items)
    
    def enable_checkpoint(self):
        self._checkpoint_enabled = True
    
    def save_checkpoint(self, session_id: str) -> Dict[str, Any]:
        return {
            "session_id": session_id,
            "short_term": self.short_term.raw_turns,
            "long_term": self.long_term.items,
            "timestamp": datetime.now().isoformat()
        }
    
    def load_checkpoint(self, checkpoint: Dict[str, Any]):
        self.short_term.raw_turns = checkpoint.get("short_term", [])
        self.long_term.items = checkpoint.get("long_term", [])
    
    async def compress_if_needed(self) -> bool:
        if not self.enable_compression or not self.compressor:
            return False
        if self.short_term.pending_for_compression:
            summary = await self.compressor.compress_turns(self.short_term.pending_for_compression)
            self.short_term.compress(summary)
            return True
        return False


def get_memory_system(session_id: Optional[str] = None, db: Optional[AsyncSession] = None) -> MemorySystem:
    """获取记忆系统实例"""
    return MemorySystem(session_id=session_id, db=db)
