"""
依赖注入工厂 - 为 Agent 端点提供服务实例

本模块提供 FastAPI 依赖注入函数，用于在路由处理函数中注入服务实例：
- get_llm_service: 获取 LLM 服务实例
- get_vector_search_service: 获取向量检索服务实例

使用方式：在路由函数参数中使用 Depends(get_xxx_service)
"""
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
