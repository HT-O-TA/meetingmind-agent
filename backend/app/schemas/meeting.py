from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class MeetingCreate(BaseModel):
    title: str
    description: Optional[str] = None
    organizer_name: Optional[str] = None
    department: Optional[str] = None
    meeting_type: str = "general"
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    location: Optional[str] = None
    participants: Optional[str] = None
    raw_transcript: Optional[str] = None


class MeetingUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    location: Optional[str] = None
    participants: Optional[str] = None
    raw_transcript: Optional[str] = None
    summary: Optional[str] = None
    minutes: Optional[str] = None
    keywords: Optional[str] = None


class MeetingOut(BaseModel):
    id: int
    title: str
    description: Optional[str]
    organizer_id: Optional[int]
    organizer_name: Optional[str]
    department: Optional[str]
    meeting_type: Optional[str] = None
    status: Optional[str] = None
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    duration_minutes: Optional[int]
    location: Optional[str]
    participants: Optional[str]
    summary: Optional[str]
    minutes: Optional[str]
    keywords: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SpeechRecordCreate(BaseModel):
    speaker_name: str
    content: str
    start_time_offset: Optional[float] = None
    end_time_offset: Optional[float] = None
    sequence: Optional[int] = None


class SpeechRecordUpdate(BaseModel):
    speaker_name: Optional[str] = None
    content: Optional[str] = None
    start_time_offset: Optional[float] = None
    end_time_offset: Optional[float] = None
    sequence: Optional[int] = None
    sentiment: Optional[str] = None
    is_key_point: Optional[int] = None


class SpeechRecordOut(BaseModel):
    id: int
    meeting_id: int
    speaker_name: str
    content: str
    start_time_offset: Optional[float]
    end_time_offset: Optional[float]
    sequence: Optional[int]
    sentiment: Optional[str]
    is_key_point: Optional[int] = None
    source_type: Optional[str] = None
    source_task_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
