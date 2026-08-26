from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.agents.trace_integration import get_trace_store
from app.core.deps import get_admin_user
from app.models.user import User


router = APIRouter(prefix="/trace", tags=["Agent Trace"])


@router.get("/spans", response_model=List[Dict[str, Any]])
async def get_spans(
    limit: int = Query(100, ge=1, le=200),
    operation_name: Optional[str] = None,
    current_user: User = Depends(get_admin_user),
):
    return get_trace_store().list(limit=limit, operation_name=operation_name)


@router.get("/spans/{span_id}", response_model=Dict[str, Any])
async def get_span(span_id: str, current_user: User = Depends(get_admin_user)):
    span = get_trace_store().get(span_id)
    if span is None:
        raise HTTPException(status_code=404, detail="Trace span 不存在")
    return span


@router.get("/summary", response_model=Dict[str, Any])
async def get_trace_summary(current_user: User = Depends(get_admin_user)):
    return get_trace_store().summary()
