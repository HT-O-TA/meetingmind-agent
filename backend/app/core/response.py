"""
统一响应格式模块

提供标准的 API 响应格式：
- Response: 通用响应（包含 code、message、data）
- PageResponse: 分页响应（包含分页元信息）

使用类方法创建响应：
- Response.ok(): 成功响应
- Response.created(): 创建成功响应
- Response.error(): 错误响应
"""
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

    def model_dump(self, **kwargs):
        result = super().model_dump(**kwargs)
        if result['data'] is not None and hasattr(result['data'], 'model_dump'):
            result['data'] = result['data'].model_dump(**kwargs)
        return result


class PageResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: Any = None
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 0

    def model_dump(self, **kwargs):
        result = super().model_dump(**kwargs)
        if result['data'] is not None and hasattr(result['data'], 'model_dump'):
            result['data'] = result['data'].model_dump(**kwargs)
        return result
