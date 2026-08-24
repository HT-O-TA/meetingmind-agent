"""长期记忆服务API端点 - 基于 UnifiedMemoryService"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.services.unified_memory_service import UnifiedMemoryService, get_unified_memory_service

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/statistics", response_model=Dict[str, Any])
async def memory_statistics(db: AsyncSession = Depends(get_db)):
    """获取记忆统计信息"""
    memory_service = get_unified_memory_service(db)
    stats = await memory_service.get_statistics()
    return {"success": True, "data": stats}


@router.post("/meeting", response_model=Dict[str, Any])
async def add_meeting_endpoint(
    meeting_id: str,
    topic: str,
    date: str = Query(default_factory=lambda: datetime.now().isoformat()),
    participants: Optional[List[str]] = Query(None),
    summary: Optional[str] = None,
    decisions: Optional[List[str]] = Query(None),
    action_items: Optional[List[str]] = Query(None),
    controversies: Optional[List[str]] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """添加会议记忆"""
    try:
        memory_service = get_unified_memory_service(db)
        await memory_service.add_meeting_memory(
            meeting_id=meeting_id,
            topic=topic,
            date=date,
            participants=participants or [],
            summary=summary or "",
            decisions=decisions or [],
            action_items=action_items or [],
            controversies=controversies or [],
        )
        return {"success": True, "message": "会议记忆添加成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/meeting/{meeting_id}", response_model=Dict[str, Any])
async def get_meeting_memories(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取会议相关记忆"""
    memory_service = get_unified_memory_service(db)
    results = await memory_service.search_memories(
        query="",
        meeting_id=int(meeting_id) if meeting_id.isdigit() else None,
        include_semantic=True,
        include_structured=True,
    )
    return {"success": True, "data": results}


@router.get("/search", response_model=Dict[str, Any])
async def search_memories_endpoint(
    query: str,
    top_k: int = 10,
    memory_type: Optional[str] = None,
    scope: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """搜索相关记忆"""
    memory_service = get_unified_memory_service(db)
    results = await memory_service.search_memories(
        query=query,
        limit=top_k,
        memory_type=memory_type,
        include_semantic=True,
        include_structured=True,
    )
    return {"success": True, "data": results}


@router.get("/context", response_model=Dict[str, Any])
async def get_context_endpoint(
    query: str,
    meeting_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """生成上下文提示词"""
    memory_service = get_unified_memory_service(db)
    prompt = await memory_service.generate_context_prompt(query, meeting_id=meeting_id)
    return {"success": True, "data": {"prompt": prompt}}


@router.post("/", response_model=Dict[str, Any])
async def add_memory_endpoint(
    content: str,
    memory_type: str = "meeting_summary",
    scope: str = "team",
    meeting_id: Optional[str] = None,
    meeting_topic: Optional[str] = None,
    entities: Optional[List[str]] = Query(None),
    metadata: Optional[Dict[str, Any]] = None,
    db: AsyncSession = Depends(get_db),
):
    """添加记忆"""
    try:
        memory_service = get_unified_memory_service(db)
        meeting_id_int = int(meeting_id) if meeting_id and meeting_id.isdigit() else None
        await memory_service.add_memory(
            content=content,
            memory_type=memory_type,
            meeting_id=meeting_id_int,
            entities=entities or [],
            metadata=metadata or {"topic": meeting_topic} if meeting_topic else metadata,
            scope=scope,
        )
        return {"success": True, "message": "记忆添加成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{memory_id}", response_model=Dict[str, Any])
async def get_memory_endpoint(
    memory_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取单个记忆"""
    memory_service = get_unified_memory_service(db)
    memory = await memory_service.get_memory(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {"success": True, "data": memory}


@router.delete("/{memory_id}", response_model=Dict[str, Any])
async def delete_memory_endpoint(
    memory_id: str,
    db: AsyncSession = Depends(get_db),
):
    """删除记忆"""
    memory_service = get_unified_memory_service(db)
    result = await memory_service.delete_memory(memory_id)
    if result.get("status") == "failed":
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {"success": True, "message": "记忆删除成功"}


@router.get("/type/{memory_type}", response_model=Dict[str, Any])
async def get_memories_by_type_endpoint(
    memory_type: str,
    db: AsyncSession = Depends(get_db),
):
    """按类型获取记忆"""
    memory_service = get_unified_memory_service(db)
    results = await memory_service.search_memories(
        query="",
        memory_type=memory_type,
        include_semantic=False,
        include_structured=True,
    )
    return {"success": True, "data": results}


@router.get("/scope/{scope}", response_model=Dict[str, Any])
async def get_memories_by_scope_endpoint(
    scope: str,
    db: AsyncSession = Depends(get_db),
):
    """按范围获取记忆"""
    memory_service = get_unified_memory_service(db)
    results = await memory_service.search_memories(
        query="",
        include_semantic=True,
        include_structured=True,
    )
    return {"success": True, "data": results}