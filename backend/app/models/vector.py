import json

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Float, cast, null, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.sql import func
from sqlalchemy.types import UserDefinedType
from app.db.database import Base


class _PgVector(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kwargs):
        return "vector"


async def embedding_column_type(db):
    return await db.scalar(text(
        "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
        "WHERE attrelid = 'vector_chunks'::regclass AND attname = 'embedding_array'"
    ))


def embedding_column_value(embedding, column_type):
    if column_type == "vector":
        return cast(cast(json.dumps(embedding), Text), _PgVector())
    if column_type and column_type.startswith("vector("):
        dimensions = int(column_type[len("vector("):-1])
        if len(embedding) != dimensions:
            return null()
        return cast(cast(json.dumps(embedding), Text), _PgVector())
    return embedding


class VectorChunk(Base):
    """向量知识库表（存储文本片段及其向量表示）"""
    __tablename__ = "vector_chunks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=True)  # 片段序号
    speaker_name = Column(String(64), nullable=True)
    time_offset = Column(Float, nullable=True)
    embedding = Column(Text, nullable=True)  # JSON存储向量（兼容模式）
    embedding_array = Column(ARRAY(Float), nullable=True)  # PostgreSQL ARRAY向量（pgvector模式）
    embedding_model = Column(String(64), nullable=True)
    department = Column(String(64), nullable=True)
    metadata_json = Column(Text, nullable=True)  # 额外元数据
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
