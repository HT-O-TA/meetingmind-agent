from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class DocumentUpdate(BaseModel):
    meeting_id: Optional[int] = None
    department: Optional[str] = None
    is_public: Optional[bool] = None


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    meeting_id: Optional[int]
    uploader_id: Optional[int]
    filename: str
    original_filename: str
    file_size: Optional[int]
    file_type: Optional[str]
    status: Optional[str] = None
    department: Optional[str]
    is_public: Optional[bool] = None
    created_at: datetime
