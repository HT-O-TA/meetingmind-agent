from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class TodoCreate(BaseModel):
    meeting_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    assignee_name: Optional[str] = None
    priority: str = "medium"
    due_date: Optional[datetime] = None


class TodoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assignee_name: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[datetime] = None


class TodoOut(BaseModel):
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

    class Config:
        from_attributes = True
