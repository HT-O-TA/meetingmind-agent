from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.response import Response
from app.db.database import get_db
from app.schemas.text_process import VectorSearchRequest
from app.services.vector_search_service import VectorSearchService
from app.core.config import settings

router = APIRouter(tags=["向量检索"])


async def get_vector_search_service(db: AsyncSession = Depends(get_db)) -> VectorSearchService:
    service = VectorSearchService(db)
    await service.check_pgvector_support()
    return service


@router.post("/search", summary="向量检索")
async def search_vectors(
    request: VectorSearchRequest,
    service: VectorSearchService = Depends(get_vector_search_service),
):
    """
    根据文本进行向量检索
    
    - **content**: 查询文本
    - **top_k**: 返回结果数量（默认使用配置文件中的值）
    - **meeting_id**: 指定会议ID（可选）
    - **department**: 指定部门（可选）
    - **similarity_threshold**: 相似度阈值（默认使用配置文件中的值）
    """
    # 只有参数为None时，才使用配置文件中的默认值
    top_k = request.top_k if request.top_k is not None else settings.TOP_K_DEFAULT
    similarity_threshold = (
        request.similarity_threshold 
        if request.similarity_threshold is not None 
        else settings.SIMILARITY_THRESHOLD
    )
    
    results = await service.search_by_text(
        query_text=request.content,
        top_k=top_k,
        meeting_id=request.meeting_id,
        department=request.department,
        similarity_threshold=similarity_threshold,
    )
    
    return Response(data={
        "query": request.content,
        "results": results,
        "count": len(results),
        "mode": "pgvector" if service.use_pgvector else "lightweight",
    })


@router.get("/chunks/{document_id}", summary="获取文档向量块")
async def get_document_chunks(
    document_id: int,
    service: VectorSearchService = Depends(get_vector_search_service),
):
    """获取指定文档的所有向量块"""
    chunks = await service.get_document_chunks(document_id)
    
    return Response(data={
        "document_id": document_id,
        "chunks": chunks,
        "count": len(chunks),
    })


@router.get("/status", summary="向量检索服务状态")
async def get_search_status(
    service: VectorSearchService = Depends(get_vector_search_service),
):
    """获取向量检索服务状态"""
    await service.check_pgvector_support()
    
    return Response(data={
        "status": "online",
        "mode": "pgvector" if service.use_pgvector else "lightweight",
        "pgvector_available": service.use_pgvector,
        "default_top_k": settings.TOP_K_DEFAULT,
        "similarity_threshold": settings.SIMILARITY_THRESHOLD,
    })
