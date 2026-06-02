from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.sql import func
from app.db.database import Base


class TodoItem(Base):
    """会议待办表"""
    __tablename__ = "todo_items"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=True, index=True)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    assignee_name = Column(String(64), nullable=True)
    assignee_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    priority = Column(String(16), default="medium")  # high/medium/low
    status = Column(String(16), default="pending")  # pending/in_progress/done/cancelled
    due_date = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    source_speech_id = Column(Integer, ForeignKey("speech_records.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
