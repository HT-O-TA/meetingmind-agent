from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class DocumentUpdate(BaseModel):
    meeting_id: Optional[int] = None
    department: Optional[str] = None
    is_public: Optional[bool] = None


class DocumentOut(BaseModel):
    id: int
    meeting_id: Optional[int]
    uploader_id: Optional[int]
    filename: str
    original_filename: str
    file_size: Optional[int]
    file_type: Optional[str]
    status: str
    department: Optional[str]
    is_public: bool
    created_at: datetime

    class Config:
        from_attributes = True
