from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.sql import func
from app.db.database import Base


class Document(Base):
    """文档库表"""
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True, index=True)
    uploader_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    filename = Column(String(256), nullable=False)
    original_filename = Column(String(256), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_size = Column(Integer, nullable=True)  # bytes
    file_type = Column(String(32), nullable=True)  # txt/pdf/docx/mp3/mp4
    content = Column(Text, nullable=True)  # 解析后文本内容
    status = Column(String(16), default="uploaded")  # uploaded/parsing/parsed/failed
    department = Column(String(64), nullable=True)
    is_public = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
