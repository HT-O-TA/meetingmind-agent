"""记忆数据模型 - 长期记忆存储在 PostgreSQL"""
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Float, JSON, Index
from sqlalchemy.sql import func
from datetime import datetime
from app.db.database import Base


class Memory(Base):
    """长期记忆表（PostgreSQL 主存储）"""
    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    memory_id = Column(String(64), unique=True, index=True, nullable=False)

    # 关联用户
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    session_id = Column(String(64), nullable=True, index=True, comment="会话ID")

    # 记忆类型
    memory_type = Column(String(32), nullable=False, index=True,
                        comment="记忆类型: short_term, long_term, episodic, semantic, working")
    memory_status = Column(String(16), default="active", index=True,
                           comment="状态: active, inactive, archived")

    # 记忆内容
    content = Column(Text, nullable=False, comment="记忆内容")
    content_summary = Column(Text, nullable=True, comment="内容摘要（用于快速检索）")

    # 重要性评分（0-1）
    importance_score = Column(Float, default=0.5, comment="重要性评分")
    relevance_score = Column(Float, default=1.0, comment="相关性评分")
    confidence_score = Column(Float, default=1.0, comment="置信度评分")

    # 元数据（JSON格式存储额外信息）
    memory_metadata = Column('memory_metadata', JSON, nullable=True, comment="元数据: 包含记忆来源、关联实体等")

    # 向量关联（Milvus中的向量ID）
    vector_ref_id = Column(String(64), nullable=True, index=True,
                           comment="Milvus向量引用ID，用于关联语义检索")

    # 时间信息
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # 使用统计
    access_count = Column(Integer, default=0, comment="访问次数")
    last_accessed_at = Column(DateTime(timezone=True), nullable=True, comment="最后访问时间")

    # 来源信息
    source_type = Column(String(32), nullable=True, comment="来源类型: conversation, document, summary")
    source_id = Column(String(64), nullable=True, comment="来源ID")
    source_meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True, index=True)

    # 创建复合索引用于常用查询
    __table_args__ = (
        Index('ix_memories_user_type', 'user_id', 'memory_type'),
        Index('ix_memories_type_status', 'memory_type', 'memory_status'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "memory_id": self.memory_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "memory_type": self.memory_type,
            "memory_status": self.memory_status,
            "content": self.content,
            "content_summary": self.content_summary,
            "importance_score": self.importance_score,
            "relevance_score": self.relevance_score,
            "confidence_score": self.confidence_score,
            "metadata": self.memory_metadata,
            "vector_ref_id": self.vector_ref_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "access_count": self.access_count,
            "last_accessed_at": self.last_accessed_at.isoformat() if self.last_accessed_at else None,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "source_meeting_id": self.source_meeting_id,
        }


class MemoryEntity(Base):
    """记忆实体表（实体关系存储）"""
    __tablename__ = "memory_entities"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    entity_id = Column(String(64), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)

    name = Column(String(256), nullable=False, index=True, comment="实体名称")
    entity_type = Column(String(64), nullable=False, index=True, comment="实体类型: person, organization, project, event")

    properties = Column(JSON, nullable=True, comment="实体属性")
    description = Column(Text, nullable=True, comment="实体描述")

    importance_score = Column(Float, default=0.5)
    access_count = Column(Integer, default=0)
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('ix_entities_user_type', 'user_id', 'entity_type'),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "entity_id": self.entity_id,
            "user_id": self.user_id,
            "name": self.name,
            "entity_type": self.entity_type,
            "properties": self.properties,
            "description": self.description,
            "importance_score": self.importance_score,
            "access_count": self.access_count,
            "last_accessed_at": self.last_accessed_at.isoformat() if self.last_accessed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class MemoryEntityRelation(Base):
    """实体关系表"""
    __tablename__ = "memory_entity_relations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    source_entity_id = Column(String(64), ForeignKey("memory_entities.entity_id", ondelete="CASCADE"), nullable=False, index=True)
    target_entity_id = Column(String(64), ForeignKey("memory_entities.entity_id", ondelete="CASCADE"), nullable=False, index=True)

    relation_type = Column(String(64), nullable=False, index=True,
                           comment="关系类型: works_on, manages, participates_in, related_to")
    description = Column(Text, nullable=True)

    confidence_score = Column(Float, default=1.0)
    source_memory_id = Column(String(64), nullable=True, comment="来源记忆ID")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('ix_relations_source', 'source_entity_id'),
        Index('ix_relations_target', 'target_entity_id'),
        Index('ix_relations_type', 'relation_type'),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "source_entity_id": self.source_entity_id,
            "target_entity_id": self.target_entity_id,
            "relation_type": self.relation_type,
            "description": self.description,
            "confidence_score": self.confidence_score,
            "source_memory_id": self.source_memory_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
