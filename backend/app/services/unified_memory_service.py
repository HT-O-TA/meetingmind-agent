"""统一记忆服务门面 - 消除 memory.py 与 long_term_memory.py 的数据孤岛

架构说明：
- UnifiedMemoryService 作为门面，协调两套记忆系统
- MemoryStore (memory.py): 负责 PostgreSQL 持久化存储、结构化查询
- LongTermMemory (long_term_memory.py): 负责组织级记忆管理、向量语义检索
- 新功能全部走此门面，旧接口标记为 deprecated

迁移计划：
- Phase 1: 门面创建完成，新功能使用 UnifiedMemoryService
- Phase 2: 旧接口内部转发到门面
- Phase 3: 数据迁移到统一表结构
- Phase 4: 废弃旧系统
"""

from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logger import app_logger
from app.core.config import settings


class UnifiedMemoryService:
    """统一记忆服务门面

    协调两套记忆系统：
    1. MemoryStore: PostgreSQL 持久化、结构化查询、会话级记忆
    2. LongTermMemory: 组织级记忆、向量语义检索、跨会议关联

    会话管理：
    - 可传入持久化 db 会话（如 FastAPI 请求生命周期）
    - 也可不传，内部自动为每个操作创建/关闭会话（适用于后台任务）
    """

    def __init__(self, db: Optional[AsyncSession] = None):
        """初始化统一记忆服务

        Args:
            db: 可选的持久化数据库会话。如果不提供，将在每次操作时自动创建会话。
        """
        self._db = db
        self._memory_store = None  # MemoryStore 实例（懒加载）
        self._ltm = None  # LongTermMemory 实例（懒加载）
        self._milvus_store = None  # Milvus 派生向量索引（懒加载）
        self._embedder = None  # 向量编码器（懒加载）

        app_logger.info("[UnifiedMemoryService] 初始化完成")

    @property
    def memory_store(self):
        """懒加载 MemoryStore"""
        if self._memory_store is None:
            from app.services.memory_store import MemoryStore
            self._memory_store = MemoryStore(db=self._db)
        return self._memory_store

    @property
    def ltm(self):
        """懒加载 LongTermMemory"""
        if self._ltm is None:
            from app.services.long_term_memory import LongTermMemory
            self._ltm = LongTermMemory()
        return self._ltm

    @property
    def milvus_store(self):
        """懒加载 Milvus 向量存储

        Milvus 作为派生向量索引，与文档共用 collection，
        通过 resource_type=memory|document 区分资源类型。
        """
        if self._milvus_store is None:
            try:
                from app.services.vector_store_milvus import get_milvus_vector_store
                self._milvus_store = get_milvus_vector_store()
            except Exception as e:
                app_logger.warning(f"[UnifiedMemory] Milvus 不可用，将回退到 PG: {e}")
                self._milvus_store = None
        return self._milvus_store

    @property
    def embedder(self):
        """懒加载向量编码器

        写入时预计算记忆向量，查询时只编码用户问题（不重新编码全部记忆）。
        """
        if self._embedder is None:
            try:
                from app.services.embedding_service import get_embedding_service
                self._embedder = get_embedding_service()
            except Exception as e:
                app_logger.warning(f"[UnifiedMemory] Embedding 服务不可用: {e}")
                self._embedder = None
        return self._embedder

    # ==================== 记忆写入（双写） ====================

    async def add_memory(
        self,
        content: str,
        memory_type: str = "long_term",
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
        meeting_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        importance_score: float = 0.5,
        entities: Optional[List[str]] = None,
        scope: str = "team",
        expires_at: Optional[datetime] = None,
        dual_write: bool = True,
    ) -> Dict[str, Any]:
        """添加记忆（双写两套系统）

        Args:
            content: 记忆内容
            memory_type: 记忆类型 (decision, action_item, knowledge, ...)
            user_id: 用户 ID
            session_id: 会话 ID
            meeting_id: 会议 ID
            metadata: 元数据
            importance_score: 重要性评分
            entities: 关联实体列表
            scope: 记忆范围 (team, department, organization, project)
            expires_at: 过期时间
            dual_write: 是否双写两套系统

        Returns:
            写入结果，包含两套系统的 memory_id
        """
        result = {
            "pg_memory_id": None,
            "ltm_memory_id": None,
            "status": "success",
            "errors": []
        }

        # 自动设置默认过期时间
        if expires_at is None:
            default_days = settings.MEMORY_LONG_TERM_DEFAULT_DAYS
            if default_days > 0:
                expires_at = datetime.now() + timedelta(days=default_days)

        # 1. 写入 MemoryStore (PostgreSQL)
        try:
            pg_memory = await self.memory_store.create_memory(
                content=content,
                memory_type=memory_type,
                user_id=user_id,
                session_id=session_id,
                metadata=metadata,
                importance_score=importance_score,
                source_type="unified_memory",
                source_meeting_id=meeting_id,
                expires_at=expires_at,
            )
            result["pg_memory_id"] = pg_memory.memory_id
            app_logger.info(f"[UnifiedMemory] 写入 MemoryStore: {pg_memory.memory_id}")
        except Exception as e:
            result["errors"].append(f"MemoryStore 写入失败: {e}")
            app_logger.error(f"[UnifiedMemory] MemoryStore 写入失败: {e}")

        # 2. 写入 LongTermMemory (组织级索引 + 语义检索)
        if dual_write:
            try:
                from app.services.long_term_memory import MemoryType as LTMemoryType, MemoryScope

                ltm_type = self._map_memory_type(memory_type)
                ltm_scope = self._map_scope(scope)

                meeting_id_str = str(meeting_id) if meeting_id else None

                ltm_entry = await self.ltm.add_memory(
                    type=ltm_type,
                    scope=ltm_scope,
                    content=content,
                    meeting_id=meeting_id_str,
                    entities=entities or metadata.get("entities", []) if metadata else entities,
                    metadata=metadata,
                    expires_at=expires_at.isoformat() if expires_at else None,
                )
                result["ltm_memory_id"] = ltm_entry.memory_id
                app_logger.info(f"[UnifiedMemory] 写入 LongTermMemory: {ltm_entry.memory_id}")
            except Exception as e:
                result["errors"].append(f"LongTermMemory 写入失败: {e}")
                app_logger.error(f"[UnifiedMemory] LongTermMemory 写入失败: {e}")

        # 如果两套系统都失败
        if not result["pg_memory_id"] and not result["ltm_memory_id"]:
            result["status"] = "failed"
        elif result["errors"]:
            result["status"] = "partial_success"

        return result

    async def add_decision(
        self,
        content: str,
        meeting_id: Optional[int] = None,
        entities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """快捷方法：添加决策类记忆"""
        return await self.add_memory(
            content=content,
            memory_type="decision",
            user_id=user_id,
            session_id=session_id,
            meeting_id=meeting_id,
            entities=entities,
            scope="team",
            metadata=metadata or {"type": "decision"},
            importance_score=0.8,  # 决策通常较重要
        )

    async def add_action_item(
        self,
        content: str,
        meeting_id: Optional[int] = None,
        entities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """快捷方法：添加行动项"""
        return await self.add_memory(
            content=content,
            memory_type="action_item",
            user_id=user_id,
            session_id=session_id,
            meeting_id=meeting_id,
            entities=entities,
            scope="team",
            metadata=metadata or {"type": "action_item"},
            importance_score=0.7,
        )

    async def add_knowledge(
        self,
        content: str,
        entities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        scope: str = "organization",
    ) -> Dict[str, Any]:
        """快捷方法：添加知识库条目"""
        return await self.add_memory(
            content=content,
            memory_type="knowledge",
            user_id=user_id,
            entities=entities,
            scope=scope,
            metadata=metadata or {"type": "knowledge"},
            importance_score=0.9,  # 知识库条目最重要
        )

    # ==================== 记忆检索（聚合查询） ====================

    async def search_memories(
        self,
        query: str,
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
        memory_type: Optional[str] = None,
        meeting_id: Optional[int] = None,
        limit: int = 10,
        include_semantic: bool = True,
        include_structured: bool = True,
    ) -> List[Dict[str, Any]]:
        """统一检索 - 从两套系统中聚合结果

        Args:
            query: 查询文本
            user_id: 用户过滤
            session_id: 会话过滤
            memory_type: 记忆类型过滤
            meeting_id: 会议 ID 过滤
            limit: 返回数量
            include_semantic: 是否包含语义检索（LongTermMemory）
            include_structured: 是否包含结构化检索（MemoryStore）

        Returns:
            聚合后的记忆列表，带统一格式和来源标记
        """
        results = []

        # 1. 从 LongTermMemory 语义检索
        if include_semantic:
            try:
                ltm_results = await self.ltm.search_memories(query, limit=limit)
                for entry, score in ltm_results:
                    results.append({
                        "memory_id": entry.memory_id,
                        "content": entry.content,
                        "type": entry.type.value,
                        "scope": entry.scope.value,
                        "source": "long_term_memory",
                        "score": score,
                        "meeting_id": entry.meeting_id,
                        "entities": entry.entities,
                        "created_at": entry.timestamp,
                    })
                app_logger.debug(f"[UnifiedMemory] LongTermMemory 检索: {len(ltm_results)} 条")
            except Exception as e:
                app_logger.warning(f"[UnifiedMemory] LongTermMemory 检索失败: {e}")

        # 2. 从 MemoryStore 结构化检索
        if include_structured:
            try:
                pg_results = await self.memory_store.search_memories(
                    user_id=user_id,
                    session_id=session_id,
                    memory_type=memory_type,
                    keyword=query,
                    limit=limit,
                )
                for memory in pg_results:
                    # 避免重复（用内容哈希做简单去重）
                    content_hash = hash(memory.content[:100])
                    is_duplicate = any(
                        hash(r["content"][:100]) == content_hash for r in results
                    )
                    if not is_duplicate:
                        results.append({
                            "memory_id": memory.memory_id,
                            "content": memory.content,
                            "type": memory.memory_type,
                            "scope": None,
                            "source": "memory_store",
                            "score": memory.importance_score,
                            "meeting_id": memory.source_meeting_id,
                            "entities": memory.memory_metadata.get("entities", []) if memory.memory_metadata else [],
                            "created_at": memory.created_at.isoformat() if memory.created_at else None,
                        })
                app_logger.debug(f"[UnifiedMemory] MemoryStore 检索: {len(pg_results)} 条")
            except Exception as e:
                app_logger.warning(f"[UnifiedMemory] MemoryStore 检索失败: {e}")

        # 3. 按分数排序，返回 Top-N
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    # ==================== 向量预计算与 Milvus 回退 ====================
    # 对应 docs/总结.md 检索记忆层：
    # - Milvus 作为派生向量索引，与文档共用 collection，resource_type 区分
    # - 记忆向量在写入时预计算，查询时只编码用户问题
    # - Milvus 不可用时回退到 PostgreSQL 预计算向量做内存检索

    async def precompute_and_store_vector(
        self,
        memory_id: str,
        content: str,
        memory_type: str,
        meeting_id: Optional[str] = None,
    ) -> bool:
        """写入时预计算记忆向量并存入 Milvus

        Milvus 与文档共用 collection，通过 resource_type=memory 标记。
        向量同时持久化到 PostgreSQL（用于 Milvus 不可用时的回退）。

        Returns:
            是否成功
        """
        embedder = self.embedder
        if embedder is None:
            app_logger.warning("[UnifiedMemory] Embedder 不可用，跳过向量预计算")
            return False

        try:
            # 1. 预计算向量
            vector = await embedder.embed_text(content)
            if vector is None:
                return False

            # 2. 持久化到 PostgreSQL（用于回退）
            await self.memory_store.store_embedding(memory_id, vector)

            # 3. 写入 Milvus（与文档共用 collection，resource_type=memory 区分）
            store = self.milvus_store
            if store is not None:
                await store.insert(
                    id=hash(memory_id) & 0x7FFFFFFF,  # 转为正整数 ID
                    vector=vector,
                    content=content,
                    resource_type="memory",
                    resource_id=memory_id,
                    meeting_id=meeting_id,
                    memory_type=memory_type,
                )
                app_logger.debug(f"[UnifiedMemory] 向量写入 Milvus: {memory_id}")
            else:
                app_logger.debug(f"[UnifiedMemory] Milvus 不可用，向量仅存 PG: {memory_id}")
            return True
        except Exception as e:
            app_logger.warning(f"[UnifiedMemory] 向量预计算失败: {e}")
            return False

    async def search_memories_with_vector(
        self,
        query: str,
        top_k: int = 10,
        meeting_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """向量检索记忆（带 Milvus 回退）

        查询时只编码用户问题一次（不重新编码全部记忆）：
        1. 优先从 Milvus 检索（resource_type=memory 过滤）
        2. Milvus 不可用时回退到 PostgreSQL 预计算向量做内存检索
        """
        embedder = self.embedder
        if embedder is None:
            # Embedder 也不可用，回退到文本检索
            return await self.search_memories(query, limit=top_k)

        try:
            # 只编码用户问题一次
            query_vector = await embedder.embed_text(query)
            if query_vector is None:
                return await self.search_memories(query, limit=top_k)
        except Exception as e:
            app_logger.warning(f"[UnifiedMemory] 查询向量编码失败，回退文本检索: {e}")
            return await self.search_memories(query, limit=top_k)

        store = self.milvus_store
        if store is not None:
            # 1. 优先从 Milvus 检索
            try:
                results = await self._search_via_milvus(
                    query_vector, top_k, meeting_id
                )
                if results:
                    return results
            except Exception as e:
                app_logger.warning(f"[UnifiedMemory] Milvus 检索失败，回退 PG: {e}")

        # 2. Milvus 不可用 → 回退到 PostgreSQL 预计算向量做内存检索
        return await self._search_via_pg_vectors(query_vector, top_k, meeting_id)

    async def _search_via_milvus(
        self,
        query_vector: List[float],
        top_k: int,
        meeting_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """从 Milvus 检索记忆向量（resource_type=memory 过滤）"""
        store = self.milvus_store
        if store is None:
            return []

        # 构建过滤表达式：只检索记忆资源
        expr = 'resource_type == "memory"'
        if meeting_id:
            expr += f' and meeting_id == "{meeting_id}"'

        raw_results = await store.search_by_vector(
            vector=query_vector,
            top_k=top_k,
            expr=expr,
        )

        results = []
        for r in raw_results:
            results.append({
                "memory_id": r.get("resource_id"),
                "content": r.get("content", ""),
                "score": r.get("score", 0.0),
                "source": "milvus_memory",
            })
        return results

    async def _search_via_pg_vectors(
        self,
        query_vector: List[float],
        top_k: int,
        meeting_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Milvus 不可用时回退：从 PostgreSQL 读预计算向量做内存检索

        不重新编码全部记忆，而是利用写入时已持久化的预计算向量，
        在进程内计算余弦相似度。
        """
        try:
            # 从 PG 批量读取记忆的预计算向量
            memories = await self.memory_store.load_embeddings(
                meeting_id=meeting_id,
                limit=500,  # 限制加载量避免内存溢出
            )
            if not memories:
                return await self.search_memories("", limit=top_k)

            # 内存中计算余弦相似度
            import numpy as np
            query_arr = np.array(query_vector)
            scored = []
            for mem in memories:
                vec = mem.get("embedding")
                if vec is None:
                    continue
                mem_arr = np.array(vec)
                # 余弦相似度
                sim = float(
                    np.dot(query_arr, mem_arr)
                    / (np.linalg.norm(query_arr) * np.linalg.norm(mem_arr) + 1e-8)
                )
                scored.append((mem, sim))

            scored.sort(key=lambda x: x[1], reverse=True)
            return [
                {
                    "memory_id": mem.get("memory_id"),
                    "content": mem.get("content", ""),
                    "score": sim,
                    "source": "pg_vector_fallback",
                }
                for mem, sim in scored[:top_k]
            ]
        except Exception as e:
            app_logger.warning(f"[UnifiedMemory] PG 向量回退失败: {e}")
            return []

    async def get_memory(
        self,
        memory_id: str,
        source: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """根据 ID 获取记忆

        Args:
            memory_id: 记忆 ID
            source: 来源过滤（memory_store / long_term_memory / None=自动查找）
        """
        # 从 MemoryStore 查找
        if source is None or source == "memory_store":
            try:
                memory = await self.memory_store.get_memory_by_id(memory_id)
                if memory:
                    return {
                        "memory_id": memory.memory_id,
                        "content": memory.content,
                        "type": memory.memory_type,
                        "source": "memory_store",
                        "created_at": memory.created_at.isoformat() if memory.created_at else None,
                    }
            except Exception:
                pass

        # 从 LongTermMemory 查找
        if source is None or source == "long_term_memory":
            try:
                entry = self.ltm.get_memory(memory_id)
                if entry:
                    return {
                        "memory_id": entry.memory_id,
                        "content": entry.content,
                        "type": entry.type.value,
                        "source": "long_term_memory",
                        "created_at": entry.timestamp,
                    }
            except Exception:
                pass

        return None

    # ==================== 记忆更新与删除 ====================

    async def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        importance_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        """更新记忆（需要知道 memory_id 属于哪个系统）

        注意：由于两套系统 ID 格式不同，目前只能更新 MemoryStore 中的记录。
        LongTermMemory 的更新需要另行处理。
        """
        result = {"status": "success", "errors": []}

        # 尝试从 MemoryStore 更新
        try:
            updated = await self.memory_store.update_memory(
                memory_id=memory_id,
                content=content,
                metadata=metadata,
                importance_score=importance_score,
            )
            if updated:
                result["memory_store"] = "updated"
            else:
                result["errors"].append(f"MemoryStore 中未找到 memory_id: {memory_id}")
        except Exception as e:
            result["errors"].append(f"更新失败: {e}")
            result["status"] = "failed"

        return result

    async def delete_memory(self, memory_id: str) -> Dict[str, Any]:
        """删除/归档记忆"""
        result = {"status": "success", "errors": []}

        # 从 MemoryStore 归档
        try:
            success = await self.memory_store.delete_memory(memory_id)
            if success:
                result["memory_store"] = "archived"
            else:
                result["errors"].append(f"MemoryStore 中未找到 memory_id: {memory_id}")
        except Exception as e:
            result["errors"].append(f"MemoryStore 删除失败: {e}")

        # 从 LongTermMemory 删除
        try:
            ltm_success = await self.ltm.delete_memory(memory_id)
            if ltm_success:
                result["long_term_memory"] = "deleted"
        except Exception as e:
            # LongTermMemory 中可能不存在该 ID，忽略错误
            pass

        if result["errors"] and not result.get("memory_store") and not result.get("long_term_memory"):
            result["status"] = "failed"

        return result

    # ==================== 辅助方法 ====================

    def _map_memory_type(self, type_str: str):
        """将 memory_type 字符串映射到 MemoryType 枚举"""
        from app.services.long_term_memory import MemoryType

        mapping = {
            "decision": MemoryType.DECISION,
            "action_item": MemoryType.ACTION_ITEM,
            "controversy": MemoryType.CONTROVERSY,
            "meeting_summary": MemoryType.MEETING_SUMMARY,
            "topic": MemoryType.TOPIC,
            "knowledge": MemoryType.KNOWLEDGE,
            "relationship": MemoryType.RELATIONSHIP,
        }
        return mapping.get(type_str, MemoryType.KNOWLEDGE)

    def _map_scope(self, scope_str: str):
        """将 scope 字符串映射到 MemoryScope 枚举"""
        from app.services.long_term_memory import MemoryScope

        mapping = {
            "team": MemoryScope.TEAM,
            "department": MemoryScope.DEPARTMENT,
            "organization": MemoryScope.ORGANIZATION,
            "project": MemoryScope.PROJECT,
        }
        return mapping.get(scope_str, MemoryScope.TEAM)

    async def get_statistics(self) -> Dict[str, Any]:
        """获取记忆系统统计信息"""
        stats = {
            "memory_store": {},
            "long_term_memory": {},
            "total": 0,
        }

        # MemoryStore 统计
        try:
            pg_stats = await self.memory_store.get_memory_stats()
            stats["memory_store"] = {
                "total_memories": pg_stats.get("total", 0),
                "avg_importance": pg_stats.get("avg_importance", 0),
            }
        except Exception:
            pass

        # LongTermMemory 统计
        try:
            ltm_stats = self.ltm.get_statistics()
            stats["long_term_memory"] = ltm_stats
        except Exception:
            pass

        return stats

    async def purge_expired(self) -> Dict[str, Any]:
        """清理过期记忆"""
        result = {
            "memory_store_archived": 0,
            "ltm_cleaned": 0,
        }

        # MemoryStore 归档过期记忆
        try:
            archived = await self.memory_store.expire_memories()
            result["memory_store_archived"] = archived
            app_logger.info(f"[UnifiedMemory] MemoryStore 归档 {archived} 条过期记忆")
        except Exception as e:
            app_logger.error(f"[UnifiedMemory] MemoryStore 清理失败: {e}")

        # LongTermMemory 清理过期记忆
        try:
            cleaned = await self.ltm.purge_expired()
            result["ltm_cleaned"] = cleaned
            app_logger.info(f"[UnifiedMemory] LongTermMemory 清理 {cleaned} 条过期记忆")
        except Exception as e:
            app_logger.error(f"[UnifiedMemory] LongTermMemory 清理失败: {e}")

        return result

    # ==================== 兼容旧接口的便捷方法 ====================

    async def generate_context_prompt(
        self,
        query: str,
        meeting_id: Optional[int] = None,
    ) -> str:
        """生成上下文提示词（兼容旧接口 get_context_prompt）

        Args:
            query: 查询文本
            meeting_id: 可选的会议 ID 过滤
        """
        try:
            results = await self.search_memories(
                query=query,
                meeting_id=meeting_id,
                limit=5,
                include_semantic=True,
                include_structured=True,
            )

            if not results:
                return ""

            context_parts = ["【历史会议记忆】"]
            for i, item in enumerate(results, 1):
                content = item.get("content", "")
                if len(content) > 200:
                    content = content[:200] + "..."
                context_parts.append(f"{i}. [{item.get('type', 'unknown')}]: {content}")

            return "\n".join(context_parts)
        except Exception as e:
            app_logger.warning(f"[UnifiedMemory] generate_context_prompt 失败: {e}")
            return ""

    async def find_relevant_memories(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """查找相关记忆（兼容旧接口 LongTermMemory.find_relevant_memories）"""
        return await self.search_memories(
            query=query,
            limit=limit,
            include_semantic=True,
            include_structured=True,
        )

    async def add_meeting_memory(
        self,
        meeting_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """添加会议记忆（兼容旧接口 add_meeting_memory）

        支持灵活的参数格式：
        - 简化版: meeting_id, title, content, session_id
        - 完整版: meeting_id, topic, date, participants, summary, decisions, action_items, controversies
        """
        meeting_id_int = int(meeting_id) if meeting_id and str(meeting_id).isdigit() else None

        # 简化版参数
        if title or content:
            metadata = kwargs.get("metadata", {})
            if title:
                metadata["topic"] = title
            if session_id:
                metadata["session_id"] = session_id

            # 添加摘要
            if content:
                await self.add_memory(
                    content=content,
                    memory_type="meeting_summary",
                    meeting_id=meeting_id_int,
                    metadata=metadata,
                    importance_score=0.7,
                )

            # 处理关键要点/待办
            key_points = kwargs.get("key_points", [])
            if key_points:
                for kp in key_points:
                    await self.add_action_item(
                        content=kp if isinstance(kp, str) else str(kp),
                        meeting_id=meeting_id_int,
                    )

            # 处理决策/争议
            decisions = kwargs.get("decisions", [])
            if decisions:
                for d in decisions:
                    await self.add_decision(
                        content=d if isinstance(d, str) else str(d),
                        meeting_id=meeting_id_int,
                    )

            return {"success": True, "meeting_id": meeting_id}

        # 完整版参数（来自 API 端点）
        topic = kwargs.get("topic", "")
        date = kwargs.get("date")
        participants = kwargs.get("participants", [])
        summary = kwargs.get("summary", "")
        decisions = kwargs.get("decisions", [])
        action_items = kwargs.get("action_items", [])
        controversies = kwargs.get("controversies", [])

        if summary:
            await self.add_memory(
                content=summary,
                memory_type="meeting_summary",
                meeting_id=meeting_id_int,
                entities=participants,
                metadata={"topic": topic, "date": date, "type": "meeting_summary"},
                importance_score=0.7,
            )

        for decision in (decisions or []):
            await self.add_decision(
                content=decision,
                meeting_id=meeting_id_int,
                entities=participants,
            )

        for action_item in (action_items or []):
            await self.add_action_item(
                content=action_item,
                meeting_id=meeting_id_int,
                entities=participants,
            )

        for controversy in (controversies or []):
            await self.add_memory(
                content=controversy,
                memory_type="controversy",
                meeting_id=meeting_id_int,
                entities=participants,
                metadata={"type": "controversy"},
                importance_score=0.6,
            )

        return {"success": True, "meeting_id": meeting_id}


# 全局单例（通过 FastAPI dependency 注入）
_unified_memory_service: Optional[UnifiedMemoryService] = None


def get_unified_memory_service(db: Optional[AsyncSession] = None) -> UnifiedMemoryService:
    """获取统一记忆服务实例（工厂函数）

    用法：
        # 在 FastAPI 路由中（有 db session）
        from app.services.unified_memory_service import get_unified_memory_service

        @app.get("/memories")
        async def get_memories(db: AsyncSession = Depends(get_db)):
            memory_service = get_unified_memory_service(db)
            memories = await memory_service.search_memories("查询内容")
            return memories

        # 在后台任务中（无需 db session）
        memory_service = get_unified_memory_service()
        await memory_service.add_memory(content="...", memory_type="decision")

    注意：传入 db 参数时，会话生命周期由调用方管理。
    不传 db 时，服务会在每次操作时自动创建/关闭会话。
    """
    return UnifiedMemoryService(db=db)


def get_unified_memory(db: Optional[AsyncSession] = None) -> UnifiedMemoryService:
    """便捷函数：获取统一记忆服务实例（推荐使用此函数名）"""
    return UnifiedMemoryService(db=db)
