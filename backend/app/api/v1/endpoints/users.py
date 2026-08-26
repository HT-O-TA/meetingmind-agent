from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.response import Response
from app.core.security import create_access_token
from app.db.database import get_db
from app.models.user import User
from app.schemas.user import TokenOut, UserCreate, UserLogin, UserOut
from app.services.user_service import UserService


router = APIRouter()


@router.post("/register", response_model=Response)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    user = await UserService(db).create(data)
    return Response.created(UserOut.model_validate(user), "注册成功")


@router.post("/login", response_model=Response)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    user = await UserService(db).authenticate(data.username, data.password)
    token = create_access_token({"sub": str(user.id), "username": user.username})
    return Response.ok(TokenOut(access_token=token, user=UserOut.model_validate(user)), "登录成功")


@router.get("/me", response_model=Response)
async def get_me(current_user: User = Depends(get_current_user)):
    return Response.ok(UserOut.model_validate(current_user))
