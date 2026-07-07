from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import cast, List
from app.db.database import get_db
from app.services.user_service import UserService
from app.schemas.user import UserCreate, UserLogin, UserOut, TokenOut, UserUpdate, UserUpdateByAdmin, UserPermissionsUpdate
from app.core.security import create_access_token
from app.core.response import Response, PageResponse
from app.core.exceptions import AppException
from app.core.deps import get_current_user, get_admin_user
from app.models.user import User

router = APIRouter()


@router.post("/register", response_model=Response)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    svc = UserService(db)
    user = await svc.create(data)
    return Response.created(UserOut.model_validate(user), "注册成功")


@router.post("/login", response_model=Response)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    svc = UserService(db)
    user = await svc.authenticate(data.username, data.password)
    token = create_access_token({"sub": str(user.id), "username": user.username})
    return Response.ok(TokenOut(access_token=token, user=UserOut.model_validate(user)), "登录成功")


@router.get("/me", response_model=Response)
async def get_me(current_user: User = Depends(get_current_user)):
    return Response.ok(UserOut.model_validate(current_user))


@router.put("/me", response_model=Response)
async def update_me(
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = UserService(db)
    user = await svc.update(cast(int, current_user.id), data)
    return Response.ok(UserOut.model_validate(user))


@router.get("/me/permissions", response_model=Response)
async def get_my_permissions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户权限列表"""
    svc = UserService(db)
    permissions = await svc.get_permissions(cast(int, current_user.id))
    return Response.ok({"permissions": permissions})


@router.get("", response_model=PageResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """管理员：获取用户列表"""
    svc = UserService(db)
    users, total = await svc.list_users(page, page_size, keyword)
    import math
    return PageResponse(
        data=[UserOut.model_validate(u) for u in users],
        total=cast(int, total),
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total else 0,
    )


@router.post("", response_model=Response)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """管理员：创建用户"""
    svc = UserService(db)
    user = await svc.create(data)
    return Response.created(UserOut.model_validate(user), "创建成功")


@router.put("/{user_id}", response_model=Response)
async def update_user_by_admin(
    user_id: int,
    data: UserUpdateByAdmin,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """管理员：更新用户信息（包括角色、状态）"""
    svc = UserService(db)
    user = await svc.update_by_admin(user_id, data)
    return Response.ok(UserOut.model_validate(user), "更新成功")


@router.delete("/{user_id}", response_model=Response)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """管理员：删除用户"""
    svc = UserService(db)
    await svc.delete(user_id)
    return Response.ok(None, "删除成功")


@router.get("/{user_id}/permissions", response_model=Response)
async def get_user_permissions(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """管理员：获取用户权限列表"""
    svc = UserService(db)
    permissions = await svc.get_permissions(user_id)
    return Response.ok({"permissions": permissions})


@router.put("/{user_id}/permissions", response_model=Response)
async def update_user_permissions(
    user_id: int,
    data: UserPermissionsUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """管理员：更新用户权限"""
    svc = UserService(db)
    user = await svc.update_permissions(user_id, data.permissions)
    return Response.ok(UserOut.model_validate(user), "权限更新成功")