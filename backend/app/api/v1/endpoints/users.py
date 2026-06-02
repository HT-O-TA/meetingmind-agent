from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import cast
from app.db.database import get_db
from app.services.user_service import UserService
from app.schemas.user import UserCreate, UserLogin, UserOut, TokenOut, UserUpdate
from app.core.security import create_access_token
from app.core.response import Response, PageResponse
from app.core.exceptions import AppException
from app.core.deps import get_current_user
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


@router.get("", response_model=PageResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
):
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