from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Enum
from sqlalchemy.sql import func
from app.db.database import Base
import enum


class UserRole(str, enum.Enum):
    admin = "admin"      # 管理员：全部权限
    user = "user"        # 普通用户：基本操作权限
    readonly = "readonly"  # 只读用户：仅查看权限


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(128), unique=True, nullable=False, index=True)
    hashed_password = Column(String(256), nullable=False)
    full_name = Column(String(64), nullable=True)
    department = Column(String(64), nullable=True)
    role = Column(String(16), default=UserRole.user, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    avatar = Column(String(256), nullable=True)
    permissions = Column(Text, nullable=True)  # JSON格式的自定义权限列表
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
