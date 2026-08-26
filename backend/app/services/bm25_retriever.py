"""BM25 检索器 - 基于 PostgreSQL tsvector 全文索引"""
from typing import List, Dict, Optional, Any
from sqlalchemy import text
from app.db.database import async_session
from app.core.logger import app_logger
from app.core.security import AccessContext


class BM25Retriever:
    """
    BM25 检索器实现 - 使用 PostgreSQL tsvector 全文索引

    特点：
    1. 基于 PostgreSQL 原生全文检索，支持 GIN 索引加速
    2. 使用 ts_rank_cd 实现 BM25 风格的排名算法
    3. 支持按 meeting_id、document_id、department 过滤
    4. 支持 AccessContext 权限下推（先过滤权限再计算相关性）
    5. 持久化存储，重启不丢失索引
    """

    def __init__(self):
        pass

    async def search(
        self,
        query: str,
        top_k: int = 10,
        meeting_id: Optional[int] = None,
        document_ids: Optional[List[int]] = None,
        department: Optional[str] = None,
        access_context: Optional[AccessContext] = None,
    ) -> List[Dict[str, Any]]:
        """
        执行 BM25 风格的全文检索

        权限下推机制（对应 docs/总结.md 检索记忆层）：
        access_context 非空时，将用户/部门/会议/文档权限条件下推到 SQL WHERE 子句，
        先过滤权限再计算 ts_rank_cd 相关性，避免召回后过滤造成信息泄漏。

        Args:
            query: 查询文本
            top_k: 返回前k个结果
            meeting_id: 会议ID过滤
            document_ids: 文档ID列表过滤
            department: 部门过滤
            access_context: 访问上下文（JWT 权限下推，优先级高于单独参数）

        Returns:
            检索结果列表，包含 doc_id, score, content, document_id, chunk_id
        """
        if not query or not query.strip():
            return []
        
        async with async_session() as session:
            # 检测可用的分词配置
            ts_config = 'chinese'
            try:
                test_result = await session.execute(text("SELECT to_tsvector('chinese', '测试');"))
                if test_result.scalar() is None:
                    ts_config = 'simple'
            except:
                ts_config = 'simple'
            
            # 构建基本查询
            sql = """
                SELECT 
                    vc.id as chunk_id,
                    vc.document_id,
                    vc.chunk_text,
                    vc.meeting_id,
                    vc.department,
                    ts_rank_cd(vc.tsv_content, plainto_tsquery(CAST(:ts_config AS regconfig), :query)) as rank
                FROM vector_chunks vc
                JOIN documents d ON d.id = vc.document_id
                WHERE vc.tsv_content @@ plainto_tsquery(CAST(:ts_config AS regconfig), :query)
                  AND vc.deleted_at IS NULL
                  AND d.deleted_at IS NULL
            """
            
            params = {"query": query, "ts_config": ts_config}
            
            # 添加过滤条件
            filters = []
            if meeting_id:
                filters.append("vc.meeting_id = :meeting_id")
                params["meeting_id"] = meeting_id
            
            if document_ids:
                filters.append(f"vc.document_id IN ({','.join([':doc_id_' + str(i) for i in range(len(document_ids))])})")
                for i, doc_id in enumerate(document_ids):
                    params[f"doc_id_{i}"] = doc_id
            
            if department:
                filters.append("vc.department = :department")
                params["department"] = department

            # ── AccessContext 权限下推（先过滤权限再算相关性）──
            if access_context and not access_context.is_admin:
                ctx_filters = access_context.to_bm25_filters()
                acl_terms = []
                if ctx_filters.get("allow_public"):
                    acl_terms.append("d.is_public IS TRUE")
                if ctx_filters.get("user_id") is not None:
                    acl_terms.append("d.uploader_id = :ctx_user_id")
                    params["ctx_user_id"] = ctx_filters["user_id"]
                if ctx_filters.get("department"):
                    acl_terms.append("d.department = :ctx_department")
                    params["ctx_department"] = ctx_filters["department"]
                filters.append(f"({' OR '.join(acl_terms)})" if acl_terms else "FALSE")
                if ctx_filters.get("meeting_ids"):
                    placeholders = ", ".join(f":ctx_mid_{i}" for i in range(len(ctx_filters["meeting_ids"])))
                    filters.append(f"vc.meeting_id IN ({placeholders})")
                    for i, mid in enumerate(ctx_filters["meeting_ids"]):
                        params[f"ctx_mid_{i}"] = mid
                if ctx_filters.get("document_scope") is not None:
                    scope = ctx_filters["document_scope"]
                    if len(scope) == 0:
                        filters.append("vc.document_id IN (-1)")  # 空列表 = 无权限
                    else:
                        placeholders = ", ".join(f":ctx_did_{i}" for i in range(len(scope)))
                        filters.append(f"vc.document_id IN ({placeholders})")
                        for i, did in enumerate(scope):
                            params[f"ctx_did_{i}"] = did

            if filters:
                sql += " AND " + " AND ".join(filters)
            
            # 添加排序和限制
            sql += " ORDER BY rank DESC LIMIT :top_k"
            params["top_k"] = top_k
            
            result = await session.execute(text(sql), params)
            rows = result.fetchall()
            
            results = []
            for row in rows:
                results.append({
                    'chunk_id': row.chunk_id,
                    'document_id': row.document_id,
                    'doc_id': row.document_id,
                    'score': float(row.rank),
                    # 检索层返回完整正文；展示层如需摘要，应在 API/UI 层单独截断。
                    'content': row.chunk_text,
                    'chunk_text': row.chunk_text,
                    'meeting_id': row.meeting_id,
                    'department': row.department,
                })
            
            app_logger.debug(f"[BM25] 检索完成，返回 {len(results)} 条结果")
            return results
    
    async def search_with_document_filter(
        self,
        query: str,
        document_ids: List[int],
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        在指定文档范围内执行 BM25 检索
        
        Args:
            query: 查询文本
            document_ids: 文档ID列表
            top_k: 返回前k个结果
            
        Returns:
            检索结果列表
        """
        return await self.search(
            query=query,
            document_ids=document_ids,
            top_k=top_k,
        )
    
    async def get_document_count(self) -> int:
        """获取文档数量"""
        async with async_session() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM vector_chunks"))
            return result.scalar()
    
    async def clear(self):
        """清空（实际上不需要，数据在数据库中）"""
        pass


# 全局 BM25 检索器实例
_bm25_retriever = None

def get_bm25_retriever() -> BM25Retriever:
    """获取全局 BM25 检索器实例"""
    global _bm25_retriever
    if _bm25_retriever is None:
        _bm25_retriever = BM25Retriever()
    return _bm25_retriever

def init_bm25_retriever(documents: List[Dict[str, Any]] = None):
    """初始化 BM25 检索器（保留兼容接口，实际数据已在数据库中）"""
    retriever = get_bm25_retriever()
    app_logger.info("[BM25] 使用 PostgreSQL tsvector 索引，无需内存初始化")
    return retriever
