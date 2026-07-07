"""前端交互事件日志端点。"""
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.logger import app_logger


router = APIRouter(tags=["前端事件"])


class FrontendEventLog(BaseModel):
    event_type: str = Field(..., max_length=32)
    path: str = Field(..., max_length=512)
    target: Optional[str] = Field(default=None, max_length=128)
    label: Optional[str] = Field(default=None, max_length=256)
    action: Optional[str] = Field(default=None, max_length=128)


@router.post("/log")
async def log_frontend_event(event: FrontendEventLog):
    app_logger.info(
        "[FRONTEND] "
        f"{event.event_type} path={event.path} "
        f"target={event.target or '-'} "
        f"label={event.label or '-'} "
        f"action={event.action or '-'}"
    )
    return {"ok": True}
