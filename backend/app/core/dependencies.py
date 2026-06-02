"""依赖注入工厂 - 为 Agent 端点提供服务实例"""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.services.llm_service import LLMService
from app.services.vector_search_service import VectorSearchService


async def get_llm_service() -> LLMService:
    return LLMService()


async def get_vector_search_service(
    db: AsyncSession = Depends(get_db),
) -> VectorSearchService:
    service = VectorSearchService(db)
    await service.check_pgvector_support()
    return service
