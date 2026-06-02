"""请求访问日志中间件"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from loguru import logger
import time


class AccessLogMiddleware(BaseHTTPMiddleware):
    """访问日志中间件"""

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()
        try:
            response = await call_next(request)
            process_time = (time.time() - start_time) * 1000
            logger.info(
                f"[RESPONSE] {request.method} {request.url.path} [{response.status_code}] {process_time:.2f}ms"
            )
            return response
        except Exception as e:
            process_time = (time.time() - start_time) * 1000
            logger.error(
                f"[ERROR] {request.method} {request.url.path} [500] {process_time:.2f}ms - {e}"
            )
            raise
