"""统一响应格式和异常处理中间件"""
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from app.core.logger import app_logger


T = TypeVar("T")


class ResponseCode(str, Enum):
    """响应码枚举"""
    SUCCESS = "00000"
    BAD_REQUEST = "40000"
    UNAUTHORIZED = "40100"
    FORBIDDEN = "40300"
    NOT_FOUND = "40400"
    INTERNAL_ERROR = "50000"
    SERVICE_UNAVAILABLE = "50300"
    VALIDATION_ERROR = "42200"
    RATE_LIMIT = "42900"


class ResponseMessage(str, Enum):
    """响应消息枚举"""
    SUCCESS = "操作成功"
    BAD_REQUEST = "请求参数错误"
    UNAUTHORIZED = "未授权访问"
    FORBIDDEN = "权限不足"
    NOT_FOUND = "资源不存在"
    INTERNAL_ERROR = "服务器内部错误"
    SERVICE_UNAVAILABLE = "服务暂不可用"
    VALIDATION_ERROR = "数据验证失败"
    RATE_LIMIT = "请求过于频繁"


@dataclass
class ResponseMetadata:
    """响应元数据"""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    request_id: Optional[str] = None
    path: Optional[str] = None
    method: Optional[str] = None
    duration_ms: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class APIResponse(Generic[T]):
    """统一API响应格式"""
    code: str = ResponseCode.SUCCESS.value
    message: str = ResponseMessage.SUCCESS.value
    data: Optional[T] = None
    error: Optional[Dict[str, Any]] = None
    metadata: ResponseMetadata = field(default_factory=ResponseMetadata)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "code": self.code,
            "message": self.message,
        }
        
        if self.data is not None:
            result["data"] = self.data
        
        if self.error is not None:
            result["error"] = self.error
        
        result["metadata"] = {
            "timestamp": self.metadata.timestamp,
            "request_id": self.metadata.request_id,
            "path": self.metadata.path,
            "method": self.metadata.method,
            "duration_ms": self.metadata.duration_ms,
            **self.metadata.extra
        }
        
        return result
    
    @classmethod
    def success(
        cls,
        data: T = None,
        message: str = None,
        code: str = ResponseCode.SUCCESS.value,
        **metadata
    ) -> "APIResponse[T]":
        """创建成功响应"""
        return cls(
            code=code,
            message=message or ResponseMessage.SUCCESS.value,
            data=data,
            metadata=ResponseMetadata(**metadata)
        )
    
    @classmethod
    def error(
        cls,
        code: str,
        message: str,
        error_detail: Dict[str, Any] = None,
        **metadata
    ) -> "APIResponse[None]":
        """创建错误响应"""
        return cls(
            code=code,
            message=message,
            error=error_detail,
            metadata=ResponseMetadata(**metadata)
        )
    
    @classmethod
    def paginated(
        cls,
        items: List[Any],
        total: int,
        page: int = 1,
        page_size: int = 20,
        **metadata
    ) -> "APIResponse[Dict[str, Any]]":
        """创建分页响应"""
        return cls(
            code=ResponseCode.SUCCESS.value,
            message=ResponseMessage.SUCCESS.value,
            data={
                "items": items,
                "pagination": {
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": (total + page_size - 1) // page_size,
                    "has_next": page * page_size < total,
                    "has_prev": page > 1
                }
            },
            metadata=ResponseMetadata(**metadata)
        )
    
    def to_fastapi_response(self) -> JSONResponse:
        """转换为FastAPI响应"""
        status_code = 200
        if self.code.startswith("4"):
            status_code = int(self.code[:3])
        elif self.code.startswith("5"):
            status_code = int(self.code[:3])
        
        return JSONResponse(
            content=self.to_dict(),
            status_code=status_code
        )


class APIException(Exception):
    """API异常基类"""
    
    def __init__(
        self,
        code: str = ResponseCode.INTERNAL_ERROR.value,
        message: str = ResponseMessage.INTERNAL_ERROR.value,
        error_detail: Dict[str, Any] = None,
        status_code: int = 500
    ):
        self.code = code
        self.message = message
        self.error_detail = error_detail
        self.status_code = status_code
        super().__init__(message)
    
    def to_response(self, **metadata) -> APIResponse:
        """转换为API响应"""
        return APIResponse.error(
            code=self.code,
            message=self.message,
            error_detail=self.error_detail,
            **metadata
        )


class BadRequestException(APIException):
    """400 错误"""
    
    def __init__(self, message: str = None, error_detail: Dict[str, Any] = None):
        super().__init__(
            code=ResponseCode.BAD_REQUEST.value,
            message=message or ResponseMessage.BAD_REQUEST.value,
            error_detail=error_detail,
            status_code=400
        )


class UnauthorizedException(APIException):
    """401 错误"""
    
    def __init__(self, message: str = None):
        super().__init__(
            code=ResponseCode.UNAUTHORIZED.value,
            message=message or ResponseMessage.UNAUTHORIZED.value,
            status_code=401
        )


class ForbiddenException(APIException):
    """403 错误"""
    
    def __init__(self, message: str = None):
        super().__init__(
            code=ResponseCode.FORBIDDEN.value,
            message=message or ResponseMessage.FORBIDDEN.value,
            status_code=403
        )


class NotFoundException(APIException):
    """404 错误"""
    
    def __init__(self, resource: str = None):
        super().__init__(
            code=ResponseCode.NOT_FOUND.value,
            message=f"{resource}不存在" if resource else ResponseMessage.NOT_FOUND.value,
            status_code=404
        )


class ValidationException(APIException):
    """422 验证错误"""
    
    def __init__(self, errors: List[Dict[str, Any]] = None):
        super().__init__(
            code=ResponseCode.VALIDATION_ERROR.value,
            message=ResponseMessage.VALIDATION_ERROR.value,
            error_detail={"validation_errors": errors} if errors else None,
            status_code=422
        )


class ServiceUnavailableException(APIException):
    """503 服务不可用"""
    
    def __init__(self, message: str = None):
        super().__init__(
            code=ResponseCode.SERVICE_UNAVAILABLE.value,
            message=message or ResponseMessage.SERVICE_UNAVAILABLE.value,
            status_code=503
        )


class RateLimitException(APIException):
    """429 限流"""
    
    def __init__(self, retry_after: int = 60):
        super().__init__(
            code=ResponseCode.RATE_LIMIT.value,
            message=ResponseMessage.RATE_LIMIT.value,
            error_detail={"retry_after": retry_after},
            status_code=429
        )


class APIExceptionHandler(BaseHTTPMiddleware):
    """API异常处理中间件"""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self._exception_handlers: Dict[Type[Exception], callable] = {
            APIException: self._handle_api_exception,
            ValueError: self._handle_value_error,
            TypeError: self._handle_type_error,
            KeyError: self._handle_key_error,
        }
    
    def add_exception_handler(self, exc_type: Type[Exception], handler: callable):
        """添加异常处理器"""
        self._exception_handlers[exc_type] = handler
    
    async def dispatch(self, request: Request, call_next):
        """处理请求"""
        start_time = datetime.now()
        request_id = request.headers.get("X-Request-ID", self._generate_request_id())
        
        try:
            response = await call_next(request)
            
            # 如果响应已经是JSONResponse，直接返回
            if isinstance(response, JSONResponse):
                return response
            
            # 如果是普通响应，包装为统一格式
            return response
        
        except APIException as e:
            return await self._handle_api_exception(request, e, request_id, start_time)
        
        except Exception as e:
            # 未知异常
            app_logger.error(f"Unhandled exception: {e}", exc_info=True)
            return await self._handle_unknown_exception(request, e, request_id, start_time)
    
    async def _handle_api_exception(
        self,
        request: Request,
        exc: APIException,
        request_id: str = None,
        start_time: datetime = None
    ) -> JSONResponse:
        """处理API异常"""
        duration_ms = None
        if start_time:
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        response = exc.to_response(
            request_id=request_id or self._generate_request_id(),
            path=str(request.url.path),
            method=request.method,
            duration_ms=duration_ms
        )
        
        return JSONResponse(
            content=response.to_dict(),
            status_code=exc.status_code,
            headers={"X-Request-ID": request_id or self._generate_request_id()}
        )
    
    async def _handle_value_error(
        self,
        request: Request,
        exc: ValueError,
        request_id: str = None,
        start_time: datetime = None
    ) -> JSONResponse:
        """处理值错误"""
        duration_ms = None
        if start_time:
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        response = APIResponse.error(
            code=ResponseCode.BAD_REQUEST.value,
            message=str(exc),
            request_id=request_id or self._generate_request_id(),
            path=str(request.url.path),
            method=request.method,
            duration_ms=duration_ms
        )
        
        return JSONResponse(content=response.to_dict(), status_code=400)
    
    async def _handle_type_error(
        self,
        request: Request,
        exc: TypeError,
        request_id: str = None,
        start_time: datetime = None
    ) -> JSONResponse:
        """处理类型错误"""
        duration_ms = None
        if start_time:
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        response = APIResponse.error(
            code=ResponseCode.BAD_REQUEST.value,
            message=f"Type error: {str(exc)}",
            request_id=request_id or self._generate_request_id(),
            path=str(request.url.path),
            method=request.method,
            duration_ms=duration_ms
        )
        
        return JSONResponse(content=response.to_dict(), status_code=400)
    
    async def _handle_key_error(
        self,
        request: Request,
        exc: KeyError,
        request_id: str = None,
        start_time: datetime = None
    ) -> JSONResponse:
        """处理键错误"""
        duration_ms = None
        if start_time:
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        response = APIResponse.error(
            code=ResponseCode.NOT_FOUND.value,
            message=f"Missing key: {str(exc)}",
            request_id=request_id or self._generate_request_id(),
            path=str(request.url.path),
            method=request.method,
            duration_ms=duration_ms
        )
        
        return JSONResponse(content=response.to_dict(), status_code=404)
    
    async def _handle_unknown_exception(
        self,
        request: Request,
        exc: Exception,
        request_id: str = None,
        start_time: datetime = None
    ) -> JSONResponse:
        """处理未知异常"""
        duration_ms = None
        if start_time:
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        app_logger.error(
            f"Unhandled exception on {request.method} {request.url.path}: {exc}",
            exc_info=True
        )
        
        response = APIResponse.error(
            code=ResponseCode.INTERNAL_ERROR.value,
            message="An internal error occurred",
            error_detail={"type": type(exc).__name__} if app_logger.level <= 10 else None,
            request_id=request_id or self._generate_request_id(),
            path=str(request.url.path),
            method=request.method,
            duration_ms=duration_ms
        )
        
        return JSONResponse(content=response.to_dict(), status_code=500)
    
    def _generate_request_id(self) -> str:
        """生成请求ID"""
        import uuid
        return str(uuid.uuid4())


def create_success_response(data: Any = None, message: str = None, **kwargs) -> APIResponse:
    """创建成功响应（便捷函数）"""
    return APIResponse.success(data=data, message=message, **kwargs)


def create_error_response(
    code: str,
    message: str,
    error_detail: Dict[str, Any] = None,
    **kwargs
) -> APIResponse:
    """创建错误响应（便捷函数）"""
    return APIResponse.error(code=code, message=message, error_detail=error_detail, **kwargs)


def create_paginated_response(
    items: List[Any],
    total: int,
    page: int = 1,
    page_size: int = 20,
    **kwargs
) -> APIResponse:
    """创建分页响应（便捷函数）"""
    return APIResponse.paginated(items=items, total=total, page=page, page_size=page_size, **kwargs)
