"""向量检索服务"""
import json
import numpy as np
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, text, func
from app.models.vector import VectorChunk
from app.models.document import Document
from app.core.config import settings
from app.core.logger import app_logger
from app.core.cache import cache_get, cache_set

_global_vector_search_service = None


class VectorSearchService:
    """向量检索服务（支持轻量模式和pgvector模式）"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.use_pgvector = False
        
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
    
    async def search_by_text(
        self,
        query_text: str,
        top_k: int = 5,
        document_ids: Optional[List[int]] = None,
        meeting_id: Optional[int] = None,
        department: Optional[str] = None,
        similarity_threshold: float = 0.0,
    ) -> List[dict]:
        """
        根据文本进行向量检索（带Redis缓存）
        
        Args:
            query_text: 查询文本
            top_k: 返回结果数量
            document_ids: 指定文档ID列表
            meeting_id: 指定会议ID
            department: 指定部门
            similarity_threshold: 相似度阈值
            
        Returns:
            检索结果列表
        """
        # 构建缓存key
        cache_key = f"vector_search:{query_text}:{top_k}:{meeting_id or 'all'}"
        if document_ids:
            cache_key += f":{','.join(map(str, sorted(document_ids)))}"
        
        # 尝试从缓存获取结果
        cached_result = await cache_get(cache_key)
        if cached_result is not None:
            app_logger.debug(f"Cache hit for query: {query_text[:50]}...")
            return cached_result
        
        try:
            from app.services.embedding_service import EmbeddingService
            embedding_service = EmbeddingService()
            query_vector = embedding_service.encode_text(query_text)
            
            if not query_vector:
                app_logger.warning("Failed to encode query text")
                return []
            
            result = await self.search_by_vector(
                query_vector=query_vector,
                top_k=top_k,
                document_ids=document_ids,
                meeting_id=meeting_id,
                department=department,
                similarity_threshold=similarity_threshold,
            )
            
            # 将结果存入缓存
            await cache_set(cache_key, result, ttl=settings.CACHE_TTL)
            return result
        except Exception as e:
            app_logger.error(f"Error in search_by_text: {e}")
            # 尝试使用轻量模式回退
            try:
                from app.services.embedding_service import EmbeddingService
                embedding_service = EmbeddingService()
                query_vector = embedding_service.encode_text(query_text)
                
                if query_vector:
                    app_logger.warning("Falling back to lightweight mode")
                    result = await self._search_lightweight(
                        query_vector=query_vector,
                        top_k=top_k,
                        document_ids=document_ids,
                        meeting_id=meeting_id,
                        department=department,
                        similarity_threshold=similarity_threshold,
                    )
                    # 将结果存入缓存
                    await cache_set(cache_key, result, ttl=settings.CACHE_TTL)
                    return result
            except Exception as fallback_e:
                app_logger.error(f"Failed to fallback to lightweight mode: {fallback_e}")
            return []
    
    async def search_by_vector(
        self,
        query_vector: List[float],
        top_k: int = 5,
        document_ids: Optional[List[int]] = None,
        meeting_id: Optional[int] = None,
        department: Optional[str] = None,
        similarity_threshold: float = 0.0,
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
            )
        else:
            return await self._search_lightweight(
                query_vector=query_vector,
                top_k=top_k,
                document_ids=document_ids,
                meeting_id=meeting_id,
                department=department,
                similarity_threshold=similarity_threshold,
            )
    
    async def _search_lightweight(
        self,
        query_vector: List[float],
        top_k: int = 5,
        document_ids: Optional[List[int]] = None,
        meeting_id: Optional[int] = None,
        department: Optional[str] = None,
        similarity_threshold: float = 0.0,
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
                WHERE vc.embedding_array IS NOT NULL
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
    
    async def get_document_chunks(self, document_id: int) -> List[dict]:
        """获取文档的所有向量块（按 chunk_index 顺序，不做相似度过滤）"""
        try:
            result = await self.db.execute(
                select(
                    VectorChunk.id,
                    VectorChunk.document_id,
                    VectorChunk.meeting_id,
                    VectorChunk.chunk_text,
                    VectorChunk.chunk_index,
                    VectorChunk.department,
                    VectorChunk.speaker_name,
                    VectorChunk.time_offset,
                    VectorChunk.metadata_json,
                )
                .where(VectorChunk.document_id == document_id)
                .order_by(VectorChunk.chunk_index)
            )
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
        app_logger.debug(f"[MultiRetrieval] 使用策略: {current_strategy}")
        
        # 获取增强版融合器
        fusion = get_enhanced_retrieval_fusion(strategy=current_strategy)
        
        # 执行向量检索（dense）
        dense_results = []
        if enable_vector:
            dense_results = await self.search_by_text(
                query_text=query_text,
                top_k=top_k * 2,  # 多取一些用于重排序
                document_ids=document_ids,
                meeting_id=meeting_id,
                department=department,
                similarity_threshold=similarity_threshold,
            )
            # 转换格式，添加 score 字段
            for r in dense_results:
                r['score'] = r.get('similarity', 0)
                r['doc_id'] = r.get('document_id', r.get('chunk_id', 0))
        
        # 执行BM25检索（如果启用）
        bm25_results = []
        if enable_bm25:
            try:
                from app.services.bm25_retriever import get_bm25_retriever
                
                bm25_retriever = get_bm25_retriever()
                
                # 如果指定了文档ID，需要过滤BM25结果
                if document_ids:
                    # 获取指定文档的内容用于BM25检索
                    docs_for_bm25 = []
                    for doc_id in document_ids:
                        chunks = await self.get_document_chunks(doc_id)
                        if chunks:
                            full_content = "\n".join(c.get('chunk_text', '') for c in chunks)
                            docs_for_bm25.append({'id': doc_id, 'content': full_content})
                    
                    # 创建临时BM25检索器
                    from app.services.bm25_retriever import BM25Retriever
                    temp_bm25 = BM25Retriever()
                    temp_bm25.add_documents(docs_for_bm25)
                    bm25_results = temp_bm25.search(query_text, top_k=top_k * 2)
                else:
                    bm25_results = bm25_retriever.search(query_text, top_k=top_k * 2)
            except Exception as e:
                app_logger.warning(f"BM25检索失败，跳过: {e}")
        
        # 策略B需要准备稀疏索引
        sparse_index = None
        if current_strategy == 'B' and settings.ENABLE_SPARSE_RETRIEVAL:
            try:
                # 获取文档内容用于构建稀疏索引
                docs_for_sparse = []
                if document_ids:
                    for doc_id in document_ids:
                        chunks = await self.get_document_chunks(doc_id)
                        if chunks:
                            full_content = "\n".join(c.get('chunk_text', '') for c in chunks)
                            docs_for_sparse.append({'id': doc_id, 'content': full_content})
                else:
                    # 获取所有文档
                    from app.models.document import Document
                    result = await self.db.execute(
                        select(Document.id, Document.content)
                    )
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
            # 根据策略选择融合方式
            if current_strategy == 'B':
                # 使用RRF融合
                sparse_results = fusion._sparse_search(query_text, sparse_index, top_k=top_k * 2) if sparse_index else []
                fused_results = fusion._rrf_fusion(bm25_results, dense_results, sparse_results)
            else:
                # 使用加权融合
                fused_results = fusion._weighted_fusion(bm25_results, dense_results)
            return fused_results[:top_k]
        
        # 使用增强版多路召回融合器进行融合和重排序
        results = await fusion.retrieve(
            query=query_text,
            bm25_results=bm25_results,
            dense_results=dense_results,
            sparse_index=sparse_index,
            top_k=top_k
        )
        
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
