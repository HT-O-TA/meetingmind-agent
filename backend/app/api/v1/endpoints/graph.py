"""知识图谱 API 端点"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, Optional
from app.db.database import get_db
from app.services.knowledge_graph import (
    get_graph_statistics,
    save_graph_to_neo4j,
    load_graph_from_neo4j,
    sync_graph_with_neo4j,
    clear_graph_in_neo4j,
    get_graph_neo4j_statistics,
    build_graph_from_chunks,
    get_entity_subgraph,
    enhance_search_results
)
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter(tags=["知识图谱"])


@router.get("/statistics", response_model=Dict[str, Any])
async def get_graph_stats(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    获取图谱统计信息
    """
    memory_stats = get_graph_statistics()
    neo4j_stats = await get_graph_neo4j_statistics()
    
    return {
        "memory": memory_stats,
        "neo4j": neo4j_stats
    }


@router.post("/save", response_model=Dict[str, Any])
async def save_graph(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    将知识图谱保存到 Neo4j
    """
    result = await save_graph_to_neo4j()
    
    if result["saved_entities"] == 0 and result["saved_relations"] == 0:
        raise HTTPException(
            status_code=500,
            detail="保存失败，请检查 Neo4j 连接配置"
        )
    
    return {
        "message": "图谱保存成功",
        **result
    }


@router.post("/load", response_model=Dict[str, Any])
async def load_graph(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    从 Neo4j 加载知识图谱到内存
    """
    result = await load_graph_from_neo4j()
    
    return {
        "message": "图谱加载成功",
        **result
    }


@router.post("/sync", response_model=Dict[str, Any])
async def sync_graph(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    同步内存图谱与 Neo4j（双向同步）
    """
    result = await sync_graph_with_neo4j()
    
    return {
        "message": "图谱同步成功",
        **result
    }


@router.delete("/clear", response_model=Dict[str, Any])
async def clear_graph(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    清空 Neo4j 中的图谱数据
    """
    result = await clear_graph_in_neo4j()
    
    if not result:
        raise HTTPException(
            status_code=500,
            detail="清空失败，请检查 Neo4j 连接配置"
        )
    
    return {
        "message": "图谱已清空"
    }


@router.get("/entity/{entity_name}", response_model=Dict[str, Any])
async def get_entity_graph(
    entity_name: str,
    depth: int = 2,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    获取实体的子图信息
    """
    result = await get_entity_subgraph(entity_name, depth)
    
    if "error" in result:
        raise HTTPException(
            status_code=404,
            detail=result["error"]
        )
    
    return result


@router.post("/build", response_model=Dict[str, Any])
async def build_graph(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    从文档块构建知识图谱（仅内存）
    """
    from app.services.document_service import get_all_document_chunks
    
    chunks = await get_all_document_chunks(db)
    result = await build_graph_from_chunks(chunks)
    
    return {
        "message": f"图谱构建成功，共处理 {len(chunks)} 个文档块",
        **result
    }


@router.post("/build-and-save", response_model=Dict[str, Any])
async def build_and_save_graph(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    从文档块构建知识图谱并保存到 Neo4j
    """
    from app.services.document_service import get_all_document_chunks
    
    chunks = await get_all_document_chunks(db)
    build_result = await build_graph_from_chunks(chunks)
    save_result = await save_graph_to_neo4j()
    
    return {
        "message": f"图谱构建并保存成功，共处理 {len(chunks)} 个文档块",
        "build": build_result,
        "save": save_result
    }
