from typing import Any, Optional
from pydantic import BaseModel


class Response(BaseModel):
    code: int = 200
    message: str = "success"
    data: Any = None

    @classmethod
    def ok(cls, data: Any = None, message: str = "success") -> "Response":
        return cls(code=200, message=message, data=data)

    @classmethod
    def created(cls, data: Any = None, message: str = "创建成功") -> "Response":
        return cls(code=201, message=message, data=data)

    @classmethod
    def error(cls, message: str = "操作失败", code: int = 400) -> "Response":
        return cls(code=code, message=message, data=None)


class PageResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: Any = None
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 0
