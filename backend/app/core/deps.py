"""
用户认证依赖注入模块

提供用户认证相关的依赖注入函数：
- get_current_user: 获取当前登录用户（必需）
- get_optional_user: 获取当前用户（可选，未登录返回 None）
- get_admin_user: 获取当前管理员用户（必需管理员权限）

通过 Authorization 请求头中的 Bearer Token 进行认证
"""
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from app.db.database import get_db
from app.core.security import decode_access_token
from app.core.exceptions import AppException
from app.models.user import User, UserRole


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise AppException("未提供认证令牌", 401)
    token = authorization.split(" ", 1)[1]
    payload = decode_access_token(token)
    if not payload:
        raise AppException("令牌无效或已过期", 401)
    user_id = int(payload.get("sub", 0))
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise AppException("用户不存在或已禁用", 401)
    return user


async def get_optional_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return await get_current_user(authorization, db)
    except AppException:
        return None


async def get_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """获取当前管理员用户，非管理员抛出403异常"""
    if current_user.role != UserRole.admin:
        raise AppException("需要管理员权限", 403)
    return current_user
