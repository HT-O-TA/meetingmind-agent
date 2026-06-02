"""RAG 问答 API"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.schemas.text_process import RAGAskRequest
from app.services.rag_service import RAGService
from app.services.vector_search_service import VectorSearchService
from app.services.llm_service import LLMService
from app.core.response import Response
from app.core.config import settings

router = APIRouter(tags=["RAG 问答"])


async def get_rag_service(db: AsyncSession = Depends(get_db)) -> RAGService:
    """获取 RAG 服务实例"""
    vector_service = VectorSearchService(db)
    await vector_service.check_pgvector_support()
    llm_service = LLMService()
    return RAGService(vector_service=vector_service, llm_service=llm_service)


@router.post("/ask", summary="RAG 智能问答")
async def rag_ask(
    request: RAGAskRequest,
    rag_service: RAGService = Depends(get_rag_service),
):
    """
    RAG 智能问答接口

    - **question**: 用户问题（必填）
    - **top_k**: 检索返回数量（默认 5）
    - **meeting_id**: 指定会议ID（可选）
    - **department**: 指定部门（可选）
    - **similarity_threshold**: 相似度阈值（默认 0.0）
    - **use_llm**: 是否使用 LLM 生成回答（默认 True）
    """
    result = await rag_service.ask(
        question=request.question,
        top_k=request.top_k or settings.TOP_K_DEFAULT,
        meeting_id=request.meeting_id,
        department=request.department,
        similarity_threshold=request.similarity_threshold or settings.SIMILARITY_THRESHOLD,
        use_llm=request.use_llm,
    )
    return Response.ok(result)
