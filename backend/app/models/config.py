"""配置模型 - 用于持久化配置到数据库"""
from sqlalchemy import Column, String, Text, DateTime, Boolean, Float, Integer, JSON
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class ConfigModel(Base):
    """配置模型"""
    __tablename__ = "configs"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(255), unique=True, index=True, nullable=False)
    value = Column(Text)
    description = Column(String(500))
    category = Column(String(50))
    data_type = Column(String(20))
    source = Column(String(20))
    required = Column(Boolean, default=False)
    min_value = Column(Float)
    max_value = Column(Float)
    enum_values = Column(JSON)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    def to_dict(self):
        return {
            "id": self.id,
            "key": self.key,
            "value": self.value,
            "description": self.description,
            "category": self.category,
            "data_type": self.data_type,
            "source": self.source,
            "required": self.required,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "enum_values": self.enum_values,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
