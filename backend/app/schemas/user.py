from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from typing import Optional
from datetime import datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: Optional[str] = Field(None, max_length=64)
    department: Optional[str] = Field(None, max_length=64)

    @field_validator("password")
    @classmethod
    def validate_bcrypt_password_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("密码的 UTF-8 编码不能超过 72 字节")
        return value


class UserLogin(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1)

    @field_validator("password")
    @classmethod
    def validate_bcrypt_password_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("密码的 UTF-8 编码不能超过 72 字节")
        return value


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    full_name: Optional[str]
    department: Optional[str]
    role: str
    is_active: bool
    permissions: Optional[str] = None
    created_at: datetime

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
