"""长期记忆服务API端点"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.services.long_term_memory import (
    get_long_term_memory,
    add_meeting_memory,
    search_related_memories,
    get_context_prompt,
    get_memory_statistics,
    add_memory,
    get_memory,
    get_memories_by_type,
    get_memories_by_scope,
    get_memories_by_meeting,
    delete_memory,
    search_memories,
)

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/statistics", response_model=Dict[str, Any])
async def memory_statistics():
    """获取记忆统计信息"""
    stats = get_memory_statistics()
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
):
    """添加会议记忆"""
    try:
        await add_meeting_memory(
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
async def get_meeting_memories(meeting_id: str):
    """获取会议相关记忆"""
    memories = get_memories_by_meeting(meeting_id)
    return {"success": True, "data": memories}


@router.get("/search", response_model=Dict[str, Any])
async def search_memories_endpoint(
    query: str,
    top_k: int = 10,
    memory_type: Optional[str] = None,
    scope: Optional[str] = None,
):
    """搜索相关记忆"""
    results = await search_related_memories(query, top_k=top_k)
    return {"success": True, "data": results}


@router.get("/context", response_model=Dict[str, Any])
async def get_context_endpoint(query: str):
    """生成上下文提示词"""
    prompt = await get_context_prompt(query)
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
):
    """添加记忆"""
    try:
        await add_memory(
            content=content,
            type=memory_type,
            scope=scope,
            meeting_id=meeting_id,
            meeting_topic=meeting_topic,
            entities=entities or [],
            metadata=metadata or {},
        )
        return {"success": True, "message": "记忆添加成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{memory_id}", response_model=Dict[str, Any])
async def get_memory_endpoint(memory_id: str):
    """获取单个记忆"""
    memory = get_memory(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {"success": True, "data": memory.to_dict()}


@router.delete("/{memory_id}", response_model=Dict[str, Any])
async def delete_memory_endpoint(memory_id: str):
    """删除记忆"""
    success = delete_memory(memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {"success": True, "message": "记忆删除成功"}


@router.get("/type/{memory_type}", response_model=Dict[str, Any])
async def get_memories_by_type_endpoint(memory_type: str):
    """按类型获取记忆"""
    memories = get_memories_by_type(memory_type)
    return {"success": True, "data": [m.to_dict() for m in memories]}


@router.get("/scope/{scope}", response_model=Dict[str, Any])
async def get_memories_by_scope_endpoint(scope: str):
    """按范围获取记忆"""
    memories = get_memories_by_scope(scope)
    return {"success": True, "data": [m.to_dict() for m in memories]}