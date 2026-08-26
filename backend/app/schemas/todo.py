from pydantic import BaseModel, ConfigDict, Field
from typing import Literal, Optional
from datetime import datetime


class TodoCreate(BaseModel):
    meeting_id: Optional[int] = None
    title: str = Field(min_length=1, max_length=256)
    description: Optional[str] = Field(None, max_length=10000)
    assignee_name: Optional[str] = Field(None, max_length=64)
    priority: Literal["high", "medium", "low"] = "medium"
    due_date: Optional[datetime] = None


class TodoUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=256)
    description: Optional[str] = Field(None, max_length=10000)
    assignee_name: Optional[str] = Field(None, max_length=64)
    priority: Optional[Literal["high", "medium", "low"]] = None
    status: Optional[Literal["pending", "in_progress", "done", "cancelled"]] = None
    due_date: Optional[datetime] = None


class TodoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    meeting_id: Optional[int]
    title: str
    description: Optional[str]
    assignee_name: Optional[str]
    priority: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
