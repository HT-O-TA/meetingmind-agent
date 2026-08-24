"""记忆存储服务 - PostgreSQL 主存储 + Redis 缓存层"""
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, text
from app.models.memory import Memory, MemoryEntity, MemoryEntityRelation
from app.core.logger import app_logger
from app.core.cache import cache_get, cache_set, cache_delete
import json
import hashlib


class MemoryStore:
    """记忆存储服务 - PostgreSQL 持久化 + Redis 缓存

    会话管理：
    - 可传入持久化 db 会话（如 FastAPI 请求生命周期）
    - 也可不传，内部自动为每个操作创建/关闭会话（适用于后台任务）
    """

    # 缓存配置
    CACHE_TTL = 3600  # 1小时缓存
    CACHE_PREFIX = "memory:pg:"  # 缓存键前缀
    HOT_DATA_THRESHOLD = 5  # 访问次数超过此值视为热点数据

    def __init__(self, db: Optional[AsyncSession] = None):
        """初始化记忆存储服务

        Args:
            db: 可选的持久化数据库会话。如果不提供，将在每次操作时自动创建会话。
        """
        self._db = db
        self._db_factory = None  # 懒加载

    @property
    def db(self) -> AsyncSession:
        """获取数据库会话（懒加载，自动创建）"""
        if self._db is None:
            self._db = self._create_session()
        return self._db

    def _create_session(self) -> AsyncSession:
        """创建新的数据库会话"""
        from app.db.database import AsyncSessionLocal
        return AsyncSessionLocal()

    # ==================== Memory CRUD ====================

    async def create_memory(
        self,
        content: str,
        memory_type: str = "long_term",
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        importance_score: float = 0.5,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        source_meeting_id: Optional[int] = None,
        expires_at: Optional[datetime] = None,
    ) -> Memory:
        """创建记忆"""
        import uuid
        memory_id = f"mem_{uuid.uuid4().hex[:16]}"

        memory = Memory(
            memory_id=memory_id,
            user_id=user_id,
            session_id=session_id,
            memory_type=memory_type,
            content=content,
            content_summary=self._generate_summary(content),
            importance_score=importance_score,
            metadata=metadata or {},
            source_type=source_type,
            source_id=source_id,
            source_meeting_id=source_meeting_id,
            expires_at=expires_at,
        )

        self.db.add(memory)
        await self.db.flush()
        await self.db.commit()

        app_logger.info(f"[MemoryStore] 创建记忆: {memory_id}, 类型: {memory_type}")
        return memory

    async def get_memory_by_id(self, memory_id: str) -> Optional[Memory]:
        """根据ID获取记忆（带缓存）"""
        cache_key = f"{self.CACHE_PREFIX}id:{memory_id}"

        # 1. 先查缓存
        cached = await cache_get(cache_key)
        if cached:
            app_logger.debug(f"[MemoryStore] 缓存命中: {memory_id}")
            return self._deserialize_memory(cached)

        # 2. 查数据库
        result = await self.db.execute(
            select(Memory).where(Memory.memory_id == memory_id)
        )
        memory = result.scalar_one_or_none()

        if memory:
            # 3. 写入缓存
            await cache_set(cache_key, self._serialize_memory(memory), ttl=self.CACHE_TTL)
            # 更新访问统计
            await self._update_access_stats(memory)
            app_logger.debug(f"[MemoryStore] 数据库命中: {memory_id}")

        return memory

    async def search_memories(
        self,
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
        memory_type: Optional[str] = None,
        memory_status: str = "active",
        keyword: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        min_importance: float = 0.0,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Memory]:
        """搜索记忆（结构化查询）"""
        query = select(Memory).where(Memory.memory_status == memory_status)

        # 条件过滤
        if user_id:
            query = query.where(Memory.user_id == user_id)
        if session_id:
            query = query.where(Memory.session_id == session_id)
        if memory_type:
            query = query.where(Memory.memory_type == memory_type)
        if keyword:
            # 使用 PostgreSQL 全文搜索（如果有tsvector）或 ILIKE
            query = query.where(Memory.content.ilike(f"%{keyword}%"))
        if start_time:
            query = query.where(Memory.created_at >= start_time)
        if end_time:
            query = query.where(Memory.created_at <= end_time)
        if min_importance > 0:
            query = query.where(Memory.importance_score >= min_importance)

        # 排序：按重要性和时间
        query = query.order_by(
            Memory.importance_score.desc(),
            Memory.created_at.desc()
        )

        # 分页
        query = query.offset(offset).limit(limit)

        result = await self.db.execute(query)
        memories = result.scalars().all()

        app_logger.info(f"[MemoryStore] 搜索记忆: 找到 {len(memories)} 条")
        return memories

    async def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        importance_score: Optional[float] = None,
        memory_status: Optional[str] = None,
    ) -> Optional[Memory]:
        """更新记忆"""
        memory = await self.get_memory_by_id(memory_id)
        if not memory:
            return None

        if content is not None:
            memory.content = content
            memory.content_summary = self._generate_summary(content)
        if metadata is not None:
            memory.metadata = metadata
        if importance_score is not None:
            memory.importance_score = importance_score
        if memory_status is not None:
            memory.memory_status = memory_status

        memory.updated_at = datetime.now()
        await self.db.commit()

        # 清除缓存
        cache_key = f"{self.CACHE_PREFIX}id:{memory_id}"
        await cache_delete(cache_key)

        app_logger.info(f"[MemoryStore] 更新记忆: {memory_id}")
        return memory

    async def delete_memory(self, memory_id: str) -> bool:
        """删除记忆（软删除 -> 归档）"""
        memory = await self.get_memory_by_id(memory_id)
        if not memory:
            return False

        memory.memory_status = "archived"
        memory.updated_at = datetime.now()
        await self.db.commit()

        # 清除缓存
        cache_key = f"{self.CACHE_PREFIX}id:{memory_id}"
        await cache_delete(cache_key)

        app_logger.info(f"[MemoryStore] 归档记忆: {memory_id}")
        return True

    async def hard_delete_memory(self, memory_id: str) -> bool:
        """硬删除记忆"""
        result = await self.db.execute(
            select(Memory).where(Memory.memory_id == memory_id)
        )
        memory = result.scalar_one_or_none()

        if not memory:
            return False

        await self.db.delete(memory)
        await self.db.commit()

        # 清除缓存
        cache_key = f"{self.CACHE_PREFIX}id:{memory_id}"
        await cache_delete(cache_key)

        app_logger.info(f"[MemoryStore] 硬删除记忆: {memory_id}")
        return True

    async def get_memory_count(
        self,
        user_id: Optional[int] = None,
        memory_type: Optional[str] = None,
        memory_status: str = "active",
    ) -> int:
        """获取记忆数量"""
        query = select(func.count(Memory.id)).where(Memory.memory_status == memory_status)

        if user_id:
            query = query.where(Memory.user_id == user_id)
        if memory_type:
            query = query.where(Memory.memory_type == memory_type)

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def increment_access_count(self, memory_id: str) -> None:
        """增加访问计数"""
        memory = await self.get_memory_by_id(memory_id)
        if memory:
            memory.access_count += 1
            memory.last_accessed_at = datetime.now()
            await self.db.commit()

            # 如果是热点数据，延长缓存时间
            if memory.access_count >= self.HOT_DATA_THRESHOLD:
                cache_key = f"{self.CACHE_PREFIX}id:{memory_id}"
                await cache_set(cache_key, self._serialize_memory(memory), ttl=self.CACHE_TTL * 2)

    # ==================== Entity CRUD ====================

    async def create_entity(
        self,
        name: str,
        entity_type: str,
        user_id: Optional[int] = None,
        properties: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
    ) -> MemoryEntity:
        """创建实体"""
        import uuid
        entity_id = f"ent_{uuid.uuid4().hex[:16]}"

        entity = MemoryEntity(
            entity_id=entity_id,
            name=name,
            entity_type=entity_type,
            user_id=user_id,
            properties=properties or {},
            description=description,
        )

        self.db.add(entity)
        await self.db.flush()
        await self.db.commit()

        app_logger.info(f"[MemoryStore] 创建实体: {entity_id}, 类型: {entity_type}")
        return entity

    async def get_entity_by_id(self, entity_id: str) -> Optional[MemoryEntity]:
        """根据ID获取实体"""
        result = await self.db.execute(
            select(MemoryEntity).where(MemoryEntity.entity_id == entity_id)
        )
        return result.scalar_one_or_none()

    async def get_entity_by_name(
        self,
        name: str,
        user_id: Optional[int] = None,
    ) -> Optional[MemoryEntity]:
        """根据名称获取实体"""
        query = select(MemoryEntity).where(MemoryEntity.name == name)
        if user_id:
            query = query.where(MemoryEntity.user_id == user_id)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def search_entities(
        self,
        user_id: Optional[int] = None,
        entity_type: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 20,
    ) -> List[MemoryEntity]:
        """搜索实体"""
        query = select(MemoryEntity)

        if user_id:
            query = query.where(MemoryEntity.user_id == user_id)
        if entity_type:
            query = query.where(MemoryEntity.entity_type == entity_type)
        if keyword:
            query = query.where(
                or_(
                    MemoryEntity.name.ilike(f"%{keyword}%"),
                    MemoryEntity.description.ilike(f"%{keyword}%") if MemoryEntity.description.isnot(None) else text('false')
                )
            )

        query = query.order_by(MemoryEntity.importance_score.desc(), MemoryEntity.name)
        query = query.limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    # ==================== Entity Relation CRUD ====================

    async def create_relation(
        self,
        source_entity_id: str,
        target_entity_id: str,
        relation_type: str,
        description: Optional[str] = None,
        confidence_score: float = 1.0,
        source_memory_id: Optional[str] = None,
    ) -> MemoryEntityRelation:
        """创建实体关系"""
        relation = MemoryEntityRelation(
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            relation_type=relation_type,
            description=description,
            confidence_score=confidence_score,
            source_memory_id=source_memory_id,
        )

        self.db.add(relation)
        await self.db.flush()
        await self.db.commit()

        app_logger.info(f"[MemoryStore] 创建关系: {source_entity_id} -[{relation_type}]-> {target_entity_id}")
        return relation

    async def get_relations(
        self,
        entity_id: str,
        relation_type: Optional[str] = None,
        direction: str = "outgoing",  # outgoing, incoming, both
    ) -> List[MemoryEntityRelation]:
        """获取实体关系"""
        query = select(MemoryEntityRelation)

        if direction in ("outgoing", "both"):
            outgoing = select(MemoryEntityRelation).where(
                MemoryEntityRelation.source_entity_id == entity_id
            )
            if relation_type:
                outgoing = outgoing.where(MemoryEntityRelation.relation_type == relation_type)

        if direction in ("incoming", "both"):
            incoming = select(MemoryEntityRelation).where(
                MemoryEntityRelation.target_entity_id == entity_id
            )
            if relation_type:
                incoming = incoming.where(MemoryEntityRelation.relation_type == relation_type)

        # 简单实现：先查 outgoing
        query = select(MemoryEntityRelation).where(MemoryEntityRelation.source_entity_id == entity_id)
        if relation_type:
            query = query.where(MemoryEntityRelation.relation_type == relation_type)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_related_entities(
        self,
        entity_id: str,
        relation_type: Optional[str] = None,
    ) -> List[MemoryEntity]:
        """获取相关实体"""
        relations = await self.get_relations(entity_id, relation_type)

        related_ids = [r.target_entity_id for r in relations]
        if not related_ids:
            return []

        result = await self.db.execute(
            select(MemoryEntity).where(MemoryEntity.entity_id.in_(related_ids))
        )
        return result.scalars().all()

    # ==================== 辅助方法 ====================

    def _generate_summary(self, content: str, max_length: int = 100) -> str:
        """生成内容摘要"""
        if not content:
            return ""

        # 简单截取前N个字符作为摘要
        if len(content) <= max_length:
            return content
        return content[:max_length] + "..."

    def _serialize_memory(self, memory: Memory) -> Dict[str, Any]:
        """序列化记忆为字典（用于缓存）"""
        return {
            "memory_id": memory.memory_id,
            "user_id": memory.user_id,
            "session_id": memory.session_id,
            "memory_type": memory.memory_type,
            "memory_status": memory.memory_status,
            "content": memory.content,
            "content_summary": memory.content_summary,
            "importance_score": memory.importance_score,
            "relevance_score": memory.relevance_score,
            "confidence_score": memory.confidence_score,
            "metadata": memory.metadata,
            "created_at": memory.created_at.isoformat() if memory.created_at else None,
            "updated_at": memory.updated_at.isoformat() if memory.updated_at else None,
        }

    def _deserialize_memory(self, data: Dict[str, Any]) -> Memory:
        """反序列化字典为内存中的Memory对象"""
        from datetime import datetime as dt
        memory = Memory(
            memory_id=data["memory_id"],
            user_id=data.get("user_id"),
            session_id=data.get("session_id"),
            memory_type=data["memory_type"],
            memory_status=data.get("memory_status", "active"),
            content=data["content"],
            content_summary=data.get("content_summary"),
            importance_score=data.get("importance_score", 0.5),
            relevance_score=data.get("relevance_score", 1.0),
            confidence_score=data.get("confidence_score", 1.0),
            metadata=data.get("metadata"),
        )
        if data.get("created_at"):
            memory.created_at = dt.fromisoformat(data["created_at"])
        if data.get("updated_at"):
            memory.updated_at = dt.fromisoformat(data["updated_at"])
        return memory

    async def _update_access_stats(self, memory: Memory) -> None:
        """更新访问统计"""
        memory.access_count += 1
        memory.last_accessed_at = datetime.now()
        await self.db.commit()

    async def expire_memories(self) -> int:
        """过期清理：删除已过期的记忆"""
        now = datetime.now()

        result = await self.db.execute(
            select(Memory).where(
                Memory.expires_at.isnot(None),
                Memory.expires_at < now,
                Memory.memory_status == "active"
            )
        )
        expired_memories = result.scalars().all()

        if expired_memories:
            for memory in expired_memories:
                memory.memory_status = "archived"

            await self.db.commit()
            app_logger.info(f"[MemoryStore] 归档 {len(expired_memories)} 条过期记忆")

        return len(expired_memories)

    async def get_memory_stats(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """获取记忆统计"""
        query = select(
            func.count(Memory.id).label("total"),
            func.sum(Memory.importance_score).label("avg_importance"),
        ).where(Memory.memory_status == "active")

        if user_id:
            query = query.where(Memory.user_id == user_id)

        # 按类型分组统计
        type_stats = {}
        for memory_type in ["short_term", "long_term", "episodic", "semantic", "working"]:
            type_query = select(func.count(Memory.id)).where(
                Memory.memory_type == memory_type,
                Memory.memory_status == "active"
            )
            if user_id:
                type_query = type_query.where(Memory.user_id == user_id)

            type_result = await self.db.execute(type_query)
            type_stats[memory_type] = type_result.scalar() or 0

        return {
            "total_count": sum(type_stats.values()),
            "by_type": type_stats,
        }


def get_memory_store(db: Optional[AsyncSession] = None) -> MemoryStore:
    """获取记忆存储服务实例

    Args:
        db: 可选的数据库会话（FastAPI 依赖注入时传入，其他场景不传则自动管理）
    """
    return MemoryStore(db=db)
