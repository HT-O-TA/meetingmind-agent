"""向量检索服务 - 支持 Milvus 混合检索和 PostgreSQL 回退

架构说明：
- 先用 Milvus 检索出 Top-K 的 ID（高性能向量检索）
- 再用这些 ID 去 PostgreSQL 做精确的权限过滤和完整内容读取
- 避免跨库关联查询，保持数据一致性
"""
import json
import time
import numpy as np
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, text, func, and_, or_, false
from app.models.vector import VectorChunk
from app.models.document import Document
from app.core.config import settings
from app.core.logger import app_logger
from app.core.security import AccessContext
from app.core.cache import cache_get, cache_set
from app.services.vector_cache_manager import get_cached_result as _get_cached_result, set_cached_result as _set_cached_result


class VectorCacheManager:
    """兼容层 - 映射到 vector_cache_manager 的便捷函数"""
    
    @staticmethod
    async def get_cached_result(query: str, **kwargs):
        # 将 meeting_id, document_ids, department 等转换为 filters
        filters = {}
        if 'meeting_id' in kwargs and kwargs['meeting_id']:
            filters['meeting_id'] = str(kwargs['meeting_id'])
        if 'document_ids' in kwargs and kwargs['document_ids']:
            filters['document_id'] = [str(d) for d in kwargs['document_ids']]
        if 'department' in kwargs and kwargs['department']:
            filters['department'] = kwargs['department']
        access_context = kwargs.get('access_context')
        if access_context:
            filters['acl'] = access_context.cache_scope()
        
        top_k = kwargs.get('top_k', 10)
        return await _get_cached_result(query, top_k=top_k, filters=filters or None)
    
    @staticmethod
    async def set_cached_result(query: str, results, **kwargs):
        # 将 meeting_id, document_ids, department 等转换为 filters
        filters = {}
        if 'meeting_id' in kwargs and kwargs['meeting_id']:
            filters['meeting_id'] = str(kwargs['meeting_id'])
        if 'document_ids' in kwargs and kwargs['document_ids']:
            filters['document_id'] = [str(d) for d in kwargs['document_ids']]
        if 'department' in kwargs and kwargs['department']:
            filters['department'] = kwargs['department']
        access_context = kwargs.get('access_context')
        if access_context:
            filters['acl'] = access_context.cache_scope()
        
        top_k = kwargs.get('top_k', 10)
        await _set_cached_result(query, results, top_k=top_k, filters=filters or None)

_global_vector_search_service = None


class VectorSearchService:
    """向量检索服务（支持 Milvus 混合检索、pgvector 模式和轻量模式）"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.use_pgvector = False
        self.use_milvus = False
        self.last_retrieval_trace: Dict[str, Any] = {}
        
    async def check_pgvector_support(self) -> bool:
        """检查数据库是否支持pgvector"""
        try:
            # 检查是否安装了 pgvector 扩展
            result = await self.db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
            if result.scalar() is None:
                raise Exception("pgvector extension not installed")
            
            # 测试向量操作
            await self.db.execute(text("SELECT '[1,2,3]'::vector <-> '[4,5,6]'::vector"))
            
            # 检查 embedding_array 字段是否支持向量操作
            result = await self.db.execute(text("""
                SELECT data_type 
                FROM information_schema.columns 
                WHERE table_name = 'vector_chunks' AND column_name = 'embedding_array'
            """))
            col_type = result.scalar()
            if col_type and 'vector' not in col_type.lower():
                raise Exception(f"embedding_array column type is {col_type}, not vector type")
            
            self.use_pgvector = True
            app_logger.info("Using pgvector mode for vector search")
            return True
        except Exception as e:
            app_logger.warning(f"pgvector not available: {e}, using lightweight mode")
            self.use_pgvector = False
            return False
    
    async def check_milvus_support(self) -> bool:
        """检查 Milvus 是否可用"""
        try:
            from app.services.vector_store_milvus import get_milvus_vector_store
            
            milvus_store = get_milvus_vector_store()
            if milvus_store is None:
                raise Exception("Milvus store not initialized")
            
            count = await milvus_store.get_document_count()
            self.use_milvus = True
            app_logger.info(f"Using Milvus mode for vector search, document count: {count}")
            return True
        except Exception as e:
            app_logger.warning(f"Milvus not available: {e}, using pgvector/lightweight mode")
            self.use_milvus = False
            return False
    
    async def search_by_text(
        self,
        query_text: str,
        top_k: int = 5,
        document_ids: Optional[List[int]] = None,
        meeting_id: Optional[int] = None,
        department: Optional[str] = None,
        similarity_threshold: float = 0.0,
        access_context: Optional["AccessContext"] = None,
    ) -> List[dict]:
        """
        根据文本进行向量检索

        权限下推机制（对应 docs/总结.md 检索记忆层）：
        access_context 非空时，将权限条件转为 Milvus expr 过滤表达式，
        在向量召回阶段就过滤权限（先过滤后算相关性），避免召回后过滤泄漏。

        检索流程：
        1. 先从 Redis 精确缓存获取结果（仅简单查询）
        2. 使用 Milvus 检索出 Top-K 的 chunk_id（带权限 expr 过滤）
        3. 用这些 ID 去 PostgreSQL 做精确的权限过滤和完整内容读取

        Args:
            query_text: 查询文本
            top_k: 返回结果数量
            document_ids: 指定文档ID列表
            meeting_id: 指定会议ID
            department: 指定部门
            similarity_threshold: 相似度阈值
            access_context: 访问上下文（JWT 权限下推）

        Returns:
            检索结果列表（完整的 chunk 信息）
        """
        # 1. 尝试精确缓存（仅高频简单查询）
        cached_result = await VectorCacheManager.get_cached_result(
            query_text, top_k=top_k, meeting_id=meeting_id, 
            document_ids=document_ids, department=department,
            access_context=access_context,
        )
        if cached_result is not None:
            # 缓存只保存 ID/分数；每次命中仍回 PostgreSQL 做存活和 ACL 校验。
            cached_ids = [item.get("chunk_id") for item in cached_result if item.get("chunk_id")]
            live_chunks = await self._fetch_chunks_from_pg(
                cached_ids,
                document_ids=document_ids,
                meeting_id=meeting_id,
                department=department,
                access_context=access_context,
            )
            cached_scores = {item.get("chunk_id"): item.get("score", 0.0) for item in cached_result}
            app_logger.debug(f"[VectorSearch] 精确缓存命中并完成 PG 校验: {query_text[:50]}...")
            return [
                {
                    **chunk,
                    "chunk_id": chunk["id"],
                    "content": chunk["chunk_text"],
                    "full_text": chunk["chunk_text"],
                    "score": cached_scores.get(chunk["id"], 0.0),
                    "similarity": cached_scores.get(chunk["id"], 0.0),
                    "sources": ["dense_cache"],
                }
                for chunk in live_chunks
            ]
        
        # 2. 优先使用 Milvus 混合检索
        if self.use_milvus:
            try:
                # Step 1: Milvus 检索，获取 Top-K 的 ID 和分数
                milvus_results = await self._milvus_retrieve_ids(
                    query_text=query_text,
                    top_k=top_k * 4,  # 多取候选，PG 权威 ACL/存活过滤后可能不足
                    document_ids=document_ids,
                    meeting_id=meeting_id,
                    department=department,
                    access_context=access_context,
                )
                
                if not milvus_results:
                    app_logger.debug("[VectorSearch] Milvus 无结果，回退到 PG")
                    return await self._search_fallback(
                        query_text, top_k, document_ids, meeting_id, 
                        department, similarity_threshold, access_context
                    )
                
                # Step 2: 用 chunk_ids 去 PostgreSQL 做精确过滤和完整读取
                chunk_ids = [r["chunk_id"] for r in milvus_results]
                pg_results = await self._fetch_chunks_from_pg(
                    chunk_ids=chunk_ids,
                    document_ids=document_ids,
                    meeting_id=meeting_id,
                    department=department,
                    access_context=access_context,
                )
                
                # Step 3: 合并结果（保留 Milvus 分数 + PG 完整信息）
                result_map = {r["chunk_id"]: r for r in milvus_results}
                final_results = []
                for pg_chunk in pg_results:
                    chunk_id = pg_chunk["id"]
                    if chunk_id in result_map:
                        merged = {
                            **result_map[chunk_id],  # Milvus 分数和元数据
                            "chunk_id": chunk_id,
                            "content": pg_chunk["chunk_text"],  # PG 完整文本
                            "chunk_text": pg_chunk["chunk_text"],
                            "full_text": pg_chunk["chunk_text"],
                            "speaker_name": pg_chunk.get("speaker_name"),
                            "time_offset": pg_chunk.get("time_offset"),
                            "metadata": pg_chunk.get("metadata_json"),
                        }
                        final_results.append(merged)
                
                # Step 4: 应用相似度阈值和限制
                final_results = [r for r in final_results 
                               if r.get("score", 0) >= similarity_threshold]
                final_results = final_results[:top_k]
                
                # 缓存（仅适合缓存的简单查询）
                await VectorCacheManager.set_cached_result(
                    query_text, final_results,
                    top_k=top_k, meeting_id=meeting_id,
                    document_ids=document_ids, department=department,
                    access_context=access_context,
                )
                
                app_logger.info(
                    f"[VectorSearch] Milvus 检索完成: "
                    f"Milvus命中 {len(milvus_results)}, "
                    f"PG过滤后 {len(final_results)}"
                )
                return final_results
                
            except Exception as milvus_e:
                app_logger.warning(f"[VectorSearch] Milvus 检索失败，回退到 PG: {milvus_e}")
        
        # 3. 回退：PG 向量检索或轻量模式
        return await self._search_fallback(
            query_text, top_k, document_ids, meeting_id, 
            department, similarity_threshold, access_context
        )
    
    async def _milvus_retrieve_ids(
        self,
        query_text: str,
        top_k: int,
        document_ids: Optional[List[int]] = None,
        meeting_id: Optional[int] = None,
        department: Optional[str] = None,
        access_context: Optional["AccessContext"] = None,
    ) -> List[Dict[str, Any]]:
        """
        仅从 Milvus 检索 ID 和分数（不返回完整内容）

        权限下推：access_context 非空时，调用 to_milvus_expr() 生成过滤表达式，
        在向量召回阶段就过滤权限，避免召回后过滤造成信息泄漏。

        Returns:
            List of {chunk_id, document_id, score, ...}
        """
        from app.services.vector_store_milvus import get_milvus_vector_store

        milvus_store = get_milvus_vector_store()
        if milvus_store is None:
            return []

        # 构建过滤条件（仅元数据过滤）
        filters = {}
        if meeting_id:
            filters["meeting_id"] = str(meeting_id)
        if department:
            filters["department"] = department
        if document_ids:
            filters["document_id"] = [str(d) for d in document_ids]

        # ── AccessContext 权限下推：转为 Milvus expr 过滤表达式 ──
        if access_context and not access_context.is_admin:
            expr = access_context.to_milvus_expr()
            if expr:
                filters["expr"] = expr  # Milvus 原生过滤表达式

        # 检索：获取 ID 和分数
        raw_results = await milvus_store.search(
            query=query_text,
            top_k=top_k,
            filters=filters if filters else None,
            dense_weight=1.0,
            sparse_weight=0.0,
        )
        
        # 标准化结果（确保有 chunk_id）
        results = []
        for r in raw_results:
            chunk_id = r.get("chunk_id") or r.get("id")
            if chunk_id:
                results.append({
                    "chunk_id": int(chunk_id) if isinstance(chunk_id, str) and chunk_id.isdigit() else chunk_id,
                    "document_id": r.get("document_id"),
                    "score": r.get("score", 0),
                    "meeting_id": r.get("meeting_id"),
                    "department": r.get("department"),
                })
        
        return results
    
    async def _fetch_chunks_from_pg(
        self,
        chunk_ids: List[Any],
        document_ids: Optional[List[int]] = None,
        meeting_id: Optional[int] = None,
        department: Optional[str] = None,
        access_context: Optional["AccessContext"] = None,
    ) -> List[Dict[str, Any]]:
        """
        从 PostgreSQL 获取完整的 chunk 数据
        
        这是与 Milvus 协作的正确方式：
        1. 先用 Milvus 检索出 ID
        2. 再用 ID 去 PG 做精确过滤和完整读取
        """
        if not chunk_ids:
            return []
        
        # 构建查询：用 chunk_ids 做精确过滤
        query = select(VectorChunk).where(VectorChunk.id.in_(chunk_ids))
        query = self._apply_live_document_filters(query, access_context)
        
        # 添加额外过滤条件
        conditions = []
        if document_ids:
            conditions.append(VectorChunk.document_id.in_(document_ids))
        if meeting_id:
            conditions.append(VectorChunk.meeting_id == meeting_id)
        if department:
            conditions.append(VectorChunk.department == department)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        result = await self.db.execute(query)
        chunks = result.scalars().all()
        
        # 转换为字典
        chunk_list = []
        for chunk in chunks:
            chunk_list.append({
                "id": chunk.id,
                "document_id": chunk.document_id,
                "meeting_id": chunk.meeting_id,
                "chunk_text": chunk.chunk_text,
                "chunk_index": chunk.chunk_index,
                "speaker_name": chunk.speaker_name,
                "time_offset": chunk.time_offset,
                "department": chunk.department,
                "metadata_json": chunk.metadata_json,
            })
        
        # 保持与 chunk_ids 相同的顺序
        id_order = {cid: idx for idx, cid in enumerate(chunk_ids)}
        chunk_list.sort(key=lambda c: id_order.get(c["id"], len(chunk_ids)))
        
        return chunk_list

    def _apply_live_document_filters(self, query, access_context: Optional["AccessContext"] = None):
        """为 ORM 查询追加文档存活校验和权威 ACL。"""
        query = query.join(Document, Document.id == VectorChunk.document_id).where(
            VectorChunk.deleted_at.is_(None),
            Document.deleted_at.is_(None),
        )
        if not access_context or access_context.is_admin:
            return query

        acl_terms = []
        if access_context.allow_public:
            acl_terms.append(Document.is_public.is_(True))
        if access_context.user_id is not None:
            acl_terms.append(Document.uploader_id == access_context.user_id)
        if access_context.department:
            acl_terms.append(Document.department == access_context.department)
        query = query.where(or_(*acl_terms) if acl_terms else false())

        if access_context.document_scope is not None:
            if access_context.document_scope:
                query = query.where(VectorChunk.document_id.in_(access_context.document_scope))
            else:
                query = query.where(false())
        if access_context.meeting_ids:
            query = query.where(VectorChunk.meeting_id.in_(access_context.meeting_ids))
        return query

    @staticmethod
    def _build_acl_sql(access_context: Optional["AccessContext"] = None) -> Tuple[str, Dict[str, Any]]:
        """为 pgvector 原生 SQL 构建参数化 ACL；PostgreSQL 是权限权威来源。"""
        if not access_context or access_context.is_admin:
            return "", {}

        params: Dict[str, Any] = {}
        acl_terms: List[str] = []
        if access_context.allow_public:
            acl_terms.append("d.is_public IS TRUE")
        if access_context.user_id is not None:
            acl_terms.append("d.uploader_id = :acl_user_id")
            params["acl_user_id"] = access_context.user_id
        if access_context.department:
            acl_terms.append("d.department = :acl_department")
            params["acl_department"] = access_context.department

        clauses = [f" AND ({' OR '.join(acl_terms)})" if acl_terms else " AND FALSE"]
        if access_context.document_scope is not None:
            if not access_context.document_scope:
                clauses.append(" AND FALSE")
            else:
                placeholders = []
                for index, document_id in enumerate(access_context.document_scope):
                    key = f"acl_document_id_{index}"
                    placeholders.append(f":{key}")
                    params[key] = document_id
                clauses.append(f" AND vc.document_id IN ({', '.join(placeholders)})")
        if access_context.meeting_ids:
            placeholders = []
            for index, meeting_scope_id in enumerate(access_context.meeting_ids):
                key = f"acl_meeting_id_{index}"
                placeholders.append(f":{key}")
                params[key] = meeting_scope_id
            clauses.append(f" AND vc.meeting_id IN ({', '.join(placeholders)})")
        return "".join(clauses), params
    
    async def _search_fallback(
        self,
        query_text: str,
        top_k: int,
        document_ids: Optional[List[int]] = None,
        meeting_id: Optional[int] = None,
        department: Optional[str] = None,
        similarity_threshold: float = 0.0,
        access_context: Optional["AccessContext"] = None,
    ) -> List[dict]:
        """回退检索：PG 向量检索或轻量模式"""
        try:
            from app.services.embedding_service import EmbeddingService
            embedding_service = EmbeddingService()
            query_vector = embedding_service.encode_text(query_text)
            
            if not query_vector:
                app_logger.warning("[VectorSearch] 查询向量编码失败")
                return []
            
            # 根据模式选择检索方式
            if self.use_pgvector:
                return await self._search_pgvector(
                    query_vector, top_k, document_ids, meeting_id,
                    department, similarity_threshold, access_context
                )
            else:
                return await self._search_lightweight(
                    query_vector, top_k, document_ids, meeting_id,
                    department, similarity_threshold, access_context
                )
                
        except Exception as e:
            app_logger.error(f"[VectorSearch] 回退检索失败: {e}")
            return []
    
    async def search_by_vector(
        self,
        query_vector: List[float],
        top_k: int = 5,
        document_ids: Optional[List[int]] = None,
        meeting_id: Optional[int] = None,
        department: Optional[str] = None,
        similarity_threshold: float = 0.0,
        access_context: Optional["AccessContext"] = None,
    ) -> List[dict]:
        """
        根据向量进行检索
        
        Args:
            query_vector: 查询向量
            top_k: 返回结果数量
            document_ids: 指定文档ID列表
            meeting_id: 指定会议ID
            department: 指定部门
            similarity_threshold: 相似度阈值
            
        Returns:
            检索结果列表
        """
        if self.use_pgvector:
            return await self._search_pgvector(
                query_vector=query_vector,
                top_k=top_k,
                document_ids=document_ids,
                meeting_id=meeting_id,
                department=department,
                similarity_threshold=similarity_threshold,
                access_context=access_context,
            )
        else:
            return await self._search_lightweight(
                query_vector=query_vector,
                top_k=top_k,
                document_ids=document_ids,
                meeting_id=meeting_id,
                department=department,
                similarity_threshold=similarity_threshold,
                access_context=access_context,
            )
    
    async def _search_lightweight(
        self,
        query_vector: List[float],
        top_k: int = 5,
        document_ids: Optional[List[int]] = None,
        meeting_id: Optional[int] = None,
        department: Optional[str] = None,
        similarity_threshold: float = 0.0,
        access_context: Optional["AccessContext"] = None,
    ) -> List[dict]:
        """轻量模式：在Python中计算余弦相似度"""
        # 只选择需要的字段，避免选择 embedding_array（可能是pgvector类型导致解析错误）
        query = select(
            VectorChunk.id,
            VectorChunk.document_id,
            VectorChunk.meeting_id,
            VectorChunk.chunk_text,
            VectorChunk.chunk_index,
            VectorChunk.department,
            VectorChunk.speaker_name,
            VectorChunk.time_offset,
            VectorChunk.metadata_json,
            VectorChunk.embedding,  # 使用JSON格式的embedding
        )
        query = self._apply_live_document_filters(query, access_context)
        
        if document_ids:
            query = query.where(VectorChunk.document_id.in_(document_ids))
        if meeting_id:
            query = query.where(VectorChunk.meeting_id == meeting_id)
        if department:
            query = query.where(VectorChunk.department == department)
        
        result = await self.db.execute(query)
        rows = result.fetchall()
        
        # 计算相似度
        results = []
        for row in rows:
            chunk_id, document_id, meeting_id, chunk_text, chunk_index, department, speaker_name, time_offset, metadata_json, embedding_json = row
            
            if not embedding_json:
                continue
            
            try:
                embedding = json.loads(embedding_json)
                if not embedding:
                    continue
                
                similarity = self._cosine_similarity(query_vector, embedding)
                
                if similarity >= similarity_threshold:
                        results.append({
                            'chunk_id': chunk_id,
                            'document_id': document_id,
                            'meeting_id': meeting_id,
                            'chunk_text': chunk_text,
                            'chunk_index': chunk_index,
                            'similarity': round(similarity, 4),
                            'department': department,
                            'speaker_name': speaker_name,
                            'time_offset': time_offset,
                            'metadata_json': metadata_json,
                        })
            except (json.JSONDecodeError, TypeError) as e:
                app_logger.warning(f"Failed to parse embedding for chunk {chunk_id}: {e}")
                continue
        
        # 按相似度排序
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:top_k]
    
    async def _search_pgvector(
        self,
        query_vector: List[float],
        top_k: int = 5,
        document_ids: Optional[List[int]] = None,
        meeting_id: Optional[int] = None,
        department: Optional[str] = None,
        similarity_threshold: float = 0.0,
        access_context: Optional["AccessContext"] = None,
    ) -> List[dict]:
        """pgvector模式：使用数据库内置向量运算"""
        try:
            query_vector_str = "ARRAY[" + ",".join(map(str, query_vector)) + "]::vector"
            
            base_query = f"""
                SELECT
                    vc.id as chunk_id,
                    vc.document_id,
                    vc.meeting_id,
                    vc.chunk_text,
                    vc.chunk_index,
                    vc.department,
                    vc.speaker_name,
                    vc.time_offset,
                    vc.metadata_json,
                    1 - (vc.embedding_array::vector <=> {query_vector_str}) as similarity
                FROM vector_chunks vc
                JOIN documents d ON d.id = vc.document_id
                WHERE vc.embedding_array IS NOT NULL
                  AND vc.deleted_at IS NULL
                  AND d.deleted_at IS NULL
            """

            params = {}

            if document_ids:
                # Integer IDs are safe to inline; avoids SQLAlchemy expanding bindparam complexity
                id_list = ", ".join(str(int(i)) for i in document_ids)
                base_query += f" AND vc.document_id IN ({id_list})"

            if meeting_id:
                base_query += " AND vc.meeting_id = :meeting_id"
                params["meeting_id"] = meeting_id

            if department:
                base_query += " AND vc.department = :department"
                params["department"] = department

            acl_sql, acl_params = self._build_acl_sql(access_context)
            base_query += acl_sql
            params.update(acl_params)

            base_query += f"""
                AND 1 - (vc.embedding_array::vector <=> {query_vector_str}) >= :similarity_threshold
                ORDER BY vc.embedding_array::vector <=> {query_vector_str}
                LIMIT :top_k
            """
            params["similarity_threshold"] = similarity_threshold
            params["top_k"] = top_k

            result = await self.db.execute(text(base_query), params)
            rows = result.fetchall()
            
            return [
                {
                    'chunk_id': row[0],
                    'document_id': row[1],
                    'meeting_id': row[2],
                    'chunk_text': row[3],
                    'chunk_index': row[4],
                    'department': row[5],
                    'speaker_name': row[6],
                    'time_offset': row[7],
                    'metadata_json': row[8],
                    'similarity': round(float(row[9]), 4),
                }
                for row in rows
            ]
        except Exception as e:
            app_logger.error(f"Error in pgvector search: {e}")
            return []
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        if not vec1 or not vec2:
            return 0.0
        
        try:
            v1 = np.array(vec1)
            v2 = np.array(vec2)
            
            norm1 = np.linalg.norm(v1)
            norm2 = np.linalg.norm(v2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            return float(np.dot(v1, v2) / (norm1 * norm2))
        except Exception as e:
            app_logger.error(f"Error calculating cosine similarity: {e}")
            return 0.0
    
    async def get_document_chunks(
        self,
        document_id: int,
        access_context: Optional["AccessContext"] = None,
    ) -> List[dict]:
        """获取文档的所有向量块（按 chunk_index 顺序，不做相似度过滤）"""
        try:
            query = select(
                    VectorChunk.id,
                    VectorChunk.document_id,
                    VectorChunk.meeting_id,
                    VectorChunk.chunk_text,
                    VectorChunk.chunk_index,
                    VectorChunk.department,
                    VectorChunk.speaker_name,
                    VectorChunk.time_offset,
                    VectorChunk.metadata_json,
                ).where(VectorChunk.document_id == document_id)
            query = self._apply_live_document_filters(query, access_context)
            result = await self.db.execute(query.order_by(VectorChunk.chunk_index))
            chunks = result.all()

            return [
                {
                    'chunk_id': chunk.id,
                    'document_id': chunk.document_id,
                    'meeting_id': chunk.meeting_id,
                    'chunk_text': chunk.chunk_text,
                    'chunk_index': chunk.chunk_index,
                    'similarity': 1.0,
                    'department': chunk.department,
                    'speaker_name': chunk.speaker_name or '',
                    'time_offset': chunk.time_offset,
                    'metadata_json': chunk.metadata_json,
                }
                for chunk in chunks
            ]
        except Exception as e:
            app_logger.error(f"Error getting document chunks: {e}")
            return []
    
    async def search_with_multi_retrieval(
        self,
        query_text: str,
        top_k: int = 5,
        document_ids: Optional[List[int]] = None,
        meeting_id: Optional[int] = None,
        department: Optional[str] = None,
        similarity_threshold: float = 0.0,
        enable_bm25: bool = True,
        enable_vector: bool = True,
        enable_rerank: bool = True,
        strategy: Optional[str] = None,
        access_context: Optional["AccessContext"] = None,
    ) -> List[dict]:
        """
        多路召回检索 - BM25 + 向量检索 + 重排序
        
        支持两种策略：
        - 策略A（当前）：BM25 + dense向量 + 加权融合
        - 策略B（目标）：BM25 + dense向量 + sparse向量 + RRF融合
        
        Args:
            query_text: 查询文本
            top_k: 返回结果数量
            document_ids: 指定文档ID列表
            meeting_id: 指定会议ID
            department: 指定部门
            similarity_threshold: 相似度阈值
            enable_bm25: 是否启用BM25检索
            enable_vector: 是否启用向量检索
            enable_rerank: 是否启用重排序
            strategy: 检索策略，'A'或'B'，默认为配置文件中的设置
            
        Returns:
            检索结果列表
        """
        from app.services.enhanced_retrieval_fusion import get_enhanced_retrieval_fusion
        
        # 使用配置文件中的策略或传入的策略
        current_strategy = strategy or settings.RETRIEVAL_STRATEGY
        retrieval_started_at = time.perf_counter()
        degradation_reasons = []
        app_logger.debug(f"[MultiRetrieval] 使用策略: {current_strategy}")
        
        # 获取增强版融合器
        fusion = get_enhanced_retrieval_fusion(strategy=current_strategy)
        
        # 执行向量检索（dense）
        dense_results = []
        dense_started_at = time.perf_counter()
        if enable_vector:
            dense_results = await self.search_by_text(
                query_text=query_text,
                top_k=top_k * 2,  # 多取一些用于重排序
                document_ids=document_ids,
                meeting_id=meeting_id,
                department=department,
                similarity_threshold=similarity_threshold,
                access_context=access_context,
            )
            # 转换格式，添加 score 字段
            for r in dense_results:
                r['score'] = r.get('score', r.get('similarity', 0))
                r['doc_id'] = r.get('chunk_id', r.get('document_id', 0))
        dense_latency_ms = (time.perf_counter() - dense_started_at) * 1000
        
        # 执行BM25检索（如果启用）
        bm25_results = []
        bm25_started_at = time.perf_counter()
        if enable_bm25:
            try:
                from app.services.bm25_retriever import get_bm25_retriever
                
                bm25_retriever = get_bm25_retriever()
                
                bm25_results = await bm25_retriever.search(
                    query=query_text,
                    top_k=top_k * 2,
                    meeting_id=meeting_id,
                    document_ids=document_ids,
                    department=department,
                    access_context=access_context,
                )
            except Exception as e:
                app_logger.warning(f"BM25检索失败，跳过: {e}")
                degradation_reasons.append("bm25_failed")
        bm25_latency_ms = (time.perf_counter() - bm25_started_at) * 1000
        
        # 方案 A 不构建任何额外稀疏索引；Milvus Sparse 已从正式链路移除。
        sparse_index = None
        if current_strategy == 'B' and settings.ENABLE_SPARSE_RETRIEVAL:
            try:
                # 获取文档内容用于构建稀疏索引
                docs_for_sparse = []
                if document_ids:
                    for doc_id in document_ids:
                        chunks = await self.get_document_chunks(doc_id, access_context=access_context)
                        if chunks:
                            full_content = "\n".join(c.get('chunk_text', '') for c in chunks)
                            docs_for_sparse.append({'id': doc_id, 'content': full_content})
                else:
                    # 获取所有文档
                    from app.models.document import Document
                    document_query = select(Document.id, Document.content).where(
                        Document.deleted_at.is_(None)
                    )
                    if access_context and not access_context.is_admin:
                        acl_terms = []
                        if access_context.allow_public:
                            acl_terms.append(Document.is_public.is_(True))
                        if access_context.user_id is not None:
                            acl_terms.append(Document.uploader_id == access_context.user_id)
                        if access_context.department:
                            acl_terms.append(Document.department == access_context.department)
                        document_query = document_query.where(
                            or_(*acl_terms) if acl_terms else false()
                        )
                        if access_context.document_scope is not None:
                            document_query = document_query.where(
                                Document.id.in_(access_context.document_scope)
                                if access_context.document_scope
                                else false()
                            )
                        if access_context.meeting_ids:
                            document_query = document_query.where(
                                Document.meeting_id.in_(access_context.meeting_ids)
                            )
                    result = await self.db.execute(document_query)
                    for row in result.fetchall():
                        doc_id, content = row
                        if content:
                            docs_for_sparse.append({'id': doc_id, 'content': content})
                
                # 构建稀疏索引
                sparse_index = fusion._build_sparse_index(docs_for_sparse)
            except Exception as e:
                app_logger.warning(f"构建稀疏索引失败，将跳过稀疏检索: {e}")
        
        # 如果不启用重排序，直接融合返回
        if not enable_rerank:
            fusion_started_at = time.perf_counter()
            # 根据策略选择融合方式
            if current_strategy == 'B':
                # 使用RRF融合
                sparse_results = fusion._sparse_search(query_text, sparse_index, top_k=top_k * 2) if sparse_index else []
                fused_results = fusion._rrf_fusion(bm25_results, dense_results, sparse_results)
            else:
                # 使用加权融合
                fused_results = fusion._weighted_fusion(bm25_results, dense_results)
            final_results = fused_results[:top_k]
            self.last_retrieval_trace = {
                "schema_version": "retrieval_trace.v1",
                "strategy": current_strategy,
                "dense_count": len(dense_results),
                "bm25_count": len(bm25_results),
                "final_count": len(final_results),
                "dense_latency_ms": dense_latency_ms,
                "bm25_latency_ms": bm25_latency_ms,
                "fusion_latency_ms": (time.perf_counter() - fusion_started_at) * 1000,
                "total_latency_ms": (time.perf_counter() - retrieval_started_at) * 1000,
                "degradation_reasons": degradation_reasons,
            }
            return final_results
        
        # 使用增强版多路召回融合器进行融合和重排序
        fusion_started_at = time.perf_counter()
        results = await fusion.retrieve(
            query=query_text,
            bm25_results=bm25_results,
            dense_results=dense_results,
            sparse_index=sparse_index,
            top_k=top_k
        )
        
        self.last_retrieval_trace = {
            "schema_version": "retrieval_trace.v1",
            "strategy": current_strategy,
            "dense_count": len(dense_results),
            "bm25_count": len(bm25_results),
            "final_count": len(results),
            "dense_latency_ms": dense_latency_ms,
            "bm25_latency_ms": bm25_latency_ms,
            "fusion_rerank_latency_ms": (time.perf_counter() - fusion_started_at) * 1000,
            "total_latency_ms": (time.perf_counter() - retrieval_started_at) * 1000,
            "degradation_reasons": degradation_reasons,
        }
        return results
    
    async def update_bm25_index(self):
        """更新BM25索引"""
        from app.services.multi_retrieval_fusion import get_multi_retrieval_fusion
        
        # 获取所有文档内容
        result = await self.db.execute(
            select(Document.id, Document.content)
        )
        documents = []
        for row in result.fetchall():
            doc_id, content = row
            if content:
                documents.append({'id': doc_id, 'content': content})
        
        # 更新BM25索引
        fusion = get_multi_retrieval_fusion()
        fusion.update_bm25_index(documents)
        
        app_logger.info(f"BM25索引已更新，共 {len(documents)} 个文档")


async def get_vector_search_service() -> VectorSearchService:
    global _global_vector_search_service
    if _global_vector_search_service is None:
        engine = create_async_engine(settings.DATABASE_URL)
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            service = VectorSearchService(session)
            await service.check_pgvector_support()
            _global_vector_search_service = service
    return _global_vector_search_service
