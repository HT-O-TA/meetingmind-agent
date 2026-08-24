"""风险规则数据模型"""
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Boolean, Index
from sqlalchemy.sql import func
from app.db.database import Base


class RiskRule(Base):
    """可配置的风险规则

    支持按租户隔离，支持启用/禁用，支持热加载。
    keywords 存储为 JSON 数组，支持正则表达式（以 regex: 前缀标记）。
    """
    __tablename__ = "risk_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="规则名称，如'删除类'")
    description = Column(Text, nullable=True, comment="规则描述")
    keywords = Column(JSON, nullable=False, comment="关键词列表，如['删除','移除','delete']")
    level = Column(String(20), nullable=False, default="LOW",
                  comment="风险等级：LOW/MEDIUM/HIGH/CRITICAL")
    enabled = Column(Boolean, nullable=False, default=True, comment="是否启用")
    tenant_id = Column(String(50), nullable=True, comment="租户ID，空表示全局规则")
    priority = Column(Integer, nullable=False, default=0, comment="优先级，数值越大越先匹配")
    match_mode = Column(String(20), nullable=False, default="contains",
                        comment="匹配模式：contains(包含)/regex(正则)/exact(精确)")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_risk_rules_tenant", "tenant_id"),
        Index("ix_risk_rules_enabled", "enabled"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "keywords": self.keywords,
            "level": self.level,
            "enabled": self.enabled,
            "tenant_id": self.tenant_id,
            "priority": self.priority,
            "match_mode": self.match_mode,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
