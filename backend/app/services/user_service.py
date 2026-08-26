from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.security import get_password_hash, verify_password
from app.models.user import User, UserRole
from app.schemas.user import UserCreate


class UserService:
    """仅承担注册与登录所需的身份数据访问。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_username(self, username: str) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(self, data: UserCreate) -> User:
        if await self.get_by_username(data.username):
            raise AppException("用户名已存在", 400)
        if await self.get_by_email(data.email):
            raise AppException("邮箱已被注册", 400)

        user = User(
            username=data.username,
            email=data.email,
            hashed_password=get_password_hash(data.password),
            full_name=data.full_name,
            department=data.department,
            role=UserRole.user.value,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def authenticate(self, username: str, password: str) -> User:
        user = await self.get_by_username(username)
        if not user or not verify_password(password, user.hashed_password):
            raise AppException("用户名或密码错误", 401)
        if not user.is_active:
            raise AppException("账号已被禁用", 403)
        return user
