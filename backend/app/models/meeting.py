from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Float
from sqlalchemy.sql import func
from app.db.database import Base


class Meeting(Base):
    """会议主表"""
    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(256), nullable=False, index=True)
    description = Column(Text, nullable=True)
    organizer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    organizer_name = Column(String(64), nullable=True)
    department = Column(String(64), nullable=True)
    meeting_type = Column(String(32), default="general")  # general/project/weekly/etc
    status = Column(String(16), default="draft")  # draft/processing/completed/archived
    start_time = Column(DateTime(timezone=True), nullable=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    location = Column(String(128), nullable=True)
    participants = Column(Text, nullable=True)  # JSON array of participant names
    raw_transcript = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    minutes = Column(Text, nullable=True)  # 会议纪要
    keywords = Column(Text, nullable=True)  # JSON array
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SpeechRecord(Base):
    """发言记录表"""
    __tablename__ = "speech_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True, index=True)
    speaker_name = Column(String(64), nullable=False)
    speaker_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    content = Column(Text, nullable=False)
    start_time_offset = Column(Float, nullable=True)  # 相对开始时间(秒)
    end_time_offset = Column(Float, nullable=True)
    sequence = Column(Integer, nullable=True)  # 发言顺序
    sentiment = Column(String(16), nullable=True)  # positive/negative/neutral
    is_key_point = Column(Integer, default=0)  # 0/1 是否关键发言
    created_at = Column(DateTime(timezone=True), server_default=func.now())
