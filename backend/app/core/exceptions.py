"""
全局异常处理模块

提供应用级异常定义和处理器：
- AppException: 自定义业务异常
- app_exception_handler: AppException 处理器
- http_exception_handler: HTTP 异常处理器
- validation_exception_handler: 请求验证异常处理器

所有异常统一返回 JSON 格式响应
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.logger import app_logger


class AppException(Exception):
    def __init__(self, message: str, code: int = 400):
        self.message = message
        self.code = code
        super().__init__(message)


async def app_exception_handler(request: Request, exc: AppException):
    app_logger.warning(f"AppException: {exc.message} | path={request.url.path}")
    return JSONResponse(
        status_code=exc.code,
        content={"code": exc.code, "message": exc.message, "data": None},
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    app_logger.warning(f"HTTPException {exc.status_code}: {exc.detail} | path={request.url.path}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "message": str(exc.detail), "data": None},
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    message = "; ".join([f"{e['loc'][-1]}: {e['msg']}" for e in errors])
    app_logger.warning(f"ValidationError: {message} | path={request.url.path}")
    return JSONResponse(
        status_code=422,
        content={"code": 422, "message": f"参数校验失败: {message}", "data": None},
    )


async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    error_details = traceback.format_exc()
    app_logger.error(f"UnhandledException: {str(exc)} | path={request.url.path}\n{error_details}")
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": f"服务器内部错误: {str(exc)[:200]}", "data": None},
    )
