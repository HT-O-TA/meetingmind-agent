from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserUpdate, UserUpdateByAdmin
from app.core.security import get_password_hash, verify_password
from app.core.exceptions import AppException
from app.core.cache import cache_get, cache_set, cache_delete
from app.utils.cache_utils import make_cache_key
import json


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: int) -> User:
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise AppException("用户不存在", 404)
        return user

    async def get_me_cached(self, user_id: int) -> dict:
        """返回字典（用于只读展示场景，命中缓存时不查库）"""
        cache_key = make_cache_key("users", "me", user_id)
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise AppException("用户不存在", 404)

        from app.schemas.user import UserOut
        data = UserOut.model_validate(user).model_dump(mode="json")
        await cache_set(cache_key, data, ttl=600)
        return data

    async def _invalidate_user(self, user_id: int):
        await cache_delete(make_cache_key("users", "me", user_id))

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
        
        # 验证角色是否有效
        valid_roles = [UserRole.admin, UserRole.user, UserRole.readonly]
        role = data.role if data.role in [r.value for r in valid_roles] else UserRole.user.value
        
        # passlib 限制密码长度最多72字节
        password = data.password[:72]
        
        user = User(
            username=data.username,
            email=data.email,
            hashed_password=get_password_hash(password),
            full_name=data.full_name,
            department=data.department,
            role=role,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def authenticate(self, username: str, password: str) -> User:
        user = await self.get_by_username(username)
        # passlib 限制密码长度最多72字节，验证时也需要截断
        password = password[:72]
        if not user or not verify_password(password, user.hashed_password):
            raise AppException("用户名或密码错误", 401)
        if not user.is_active:
            raise AppException("账号已被禁用", 403)
        return user

    async def update(self, user_id: int, data: UserUpdate) -> User:
        user = await self.get_by_id(user_id)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(user, field, value)
        await self.db.commit()
        await self.db.refresh(user)
        await self._invalidate_user(user_id)
        return user

    async def update_by_admin(self, user_id: int, data: UserUpdateByAdmin) -> User:
        """管理员更新用户信息（包括角色、状态、密码）"""
        user = await self.get_by_id(user_id)
        
        update_data = data.model_dump(exclude_none=True)
        
        # 验证角色是否有效
        if "role" in update_data:
            valid_roles = [UserRole.admin, UserRole.user, UserRole.readonly]
            if update_data["role"] not in [r.value for r in valid_roles]:
                raise AppException("无效的角色", 400)
        
        # 如果更新密码，需要哈希
        if "password" in update_data and update_data["password"]:
            update_data["hashed_password"] = get_password_hash(update_data["password"][:72])
            del update_data["password"]
        
        for field, value in update_data.items():
            setattr(user, field, value)
        
        await self.db.commit()
        await self.db.refresh(user)
        await self._invalidate_user(user_id)
        return user

    async def delete(self, user_id: int) -> None:
        """删除用户"""
        user = await self.get_by_id(user_id)
        await self.db.delete(user)
        await self.db.commit()
        await self._invalidate_user(user_id)

    async def list_users(self, page: int = 1, page_size: int = 20, keyword: Optional[str] = None):
        query = select(User)
        if keyword:
            query = query.where(
                or_(User.username.ilike(f"%{keyword}%"), User.full_name.ilike(f"%{keyword}%"))
            )
        count_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_q)).scalar()
        query = query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        users = (await self.db.execute(query)).scalars().all()
        return users, total

    async def set_active(self, user_id: int, is_active: bool) -> User:
        user = await self.get_by_id(user_id)
        user.is_active = is_active
        await self.db.commit()
        await self.db.refresh(user)
        await self._invalidate_user(user_id)
        return user

    async def update_permissions(self, user_id: int, permissions: List[str]) -> User:
        """更新用户自定义权限"""
        user = await self.get_by_id(user_id)
        user.permissions = json.dumps(permissions) if permissions else None
        await self.db.commit()
        await self.db.refresh(user)
        await self._invalidate_user(user_id)
        return user

    async def get_permissions(self, user_id: int) -> List[str]:
        """获取用户权限列表（角色默认权限 + 自定义权限）"""
        user = await self.get_by_id(user_id)
        
        # 角色默认权限
        role_permissions = {
            UserRole.admin: [
                "meeting_view", "meeting_create", "meeting_edit", "meeting_delete", "meeting_ai",
                "document_view", "document_upload", "document_edit", "document_delete",
                "graph_view", "graph_build", "graph_manage",
                "feedback_view", "feedback_analyze",
                "user_view", "user_create", "user_edit", "user_delete", "user_permission"
            ],
            UserRole.user: [
                "meeting_view", "meeting_create", "meeting_edit", "meeting_ai",
                "document_view", "document_upload", "document_edit",
                "graph_view",
                "feedback_view"
            ],
            UserRole.readonly: [
                "meeting_view",
                "document_view",
                "graph_view",
                "feedback_view"
            ]
        }
        
        base_permissions = role_permissions.get(user.role, [])
        
        # 如果有自定义权限，覆盖默认权限
        if user.permissions:
            try:
                custom_permissions = json.loads(user.permissions)
                return custom_permissions
            except json.JSONDecodeError:
                pass
        
        return base_permissions
