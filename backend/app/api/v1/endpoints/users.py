from fastapi import APIRouter, Depends, Request
from fastapi import Response as FastAPIResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.response import Response
from app.core.security import create_access_token
from app.db.database import get_db
from app.models.user import User
from app.schemas.user import TokenOut, UserCreate, UserLogin, UserOut
from app.services.user_service import UserService
from app.core.config import settings
from app.core.rate_limiter import enforce_anonymous_rate_limit


router = APIRouter()


@router.post("/register", response_model=Response)
async def register(
    data: UserCreate,
    request: Request,
    response: FastAPIResponse,
    db: AsyncSession = Depends(get_db),
):
    await enforce_anonymous_rate_limit(
        request=request,
        response=response,
        bucket="register",
        limit=settings.RATE_LIMIT_REGISTER_COUNT,
        window=settings.RATE_LIMIT_REGISTER_WINDOW_SECONDS,
    )
    user = await UserService(db).create(data)
    return Response.created(UserOut.model_validate(user), "注册成功")


@router.post("/login", response_model=Response)
async def login(
    data: UserLogin,
    request: Request,
    response: FastAPIResponse,
    db: AsyncSession = Depends(get_db),
):
    await enforce_anonymous_rate_limit(
        request=request,
        response=response,
        bucket="login",
        limit=settings.RATE_LIMIT_LOGIN_COUNT,
        window=settings.RATE_LIMIT_LOGIN_WINDOW_SECONDS,
        subject=data.username,
    )
    user = await UserService(db).authenticate(data.username, data.password)
    token = create_access_token({"sub": str(user.id), "username": user.username})
    return Response.ok(TokenOut(access_token=token, user=UserOut.model_validate(user)), "登录成功")


@router.get("/me", response_model=Response)
async def get_me(current_user: User = Depends(get_current_user)):
    return Response.ok(UserOut.model_validate(current_user))
