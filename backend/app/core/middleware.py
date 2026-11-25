"""请求访问日志中间件"""
from contextlib import contextmanager
from contextvars import ContextVar
import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.responses import JSONResponse
from app.core.config import settings
from loguru import logger
import time


_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
_correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_EXTERNAL_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class AgentConcurrencyMiddleware:
    paths = {"/api/v1/agents/query", "/api/v1/agents/query-stream"}

    def __init__(self, app):
        self.app = app
        self.in_flight = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] not in self.paths:
            await self.app(scope, receive, send)
            return
        if self.in_flight >= settings.AGENT_HTTP_MAX_IN_FLIGHT:
            response = JSONResponse(
                {"code": 503, "message": "Agent is at capacity", "data": None},
                status_code=503,
                headers={"Retry-After": "1"},
            )
            await response(scope, receive, send)
            return
        self.in_flight += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self.in_flight -= 1


def route_template(request: Request) -> str:
    route = getattr(request.scope.get("route"), "path", None)
    if route:
        return route
    if request.url.path in AgentConcurrencyMiddleware.paths:
        return request.url.path
    return "unmatched"


def current_request_id() -> str | None:
    return _request_id_var.get()


@contextmanager
def bind_task_request_id(value):
    """Carry a server-generated HTTP ID while processing a queue delivery."""
    request_id = value if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) else None
    marker = _request_id_var.set(request_id)
    try:
        yield request_id
    finally:
        _request_id_var.reset(marker)


def current_correlation_id() -> str | None:
    return _correlation_id_var.get()


class AccessLogMiddleware(BaseHTTPMiddleware):
    """访问日志中间件"""

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.perf_counter()
        request_id = uuid.uuid4().hex
        external_id = request.headers.get("X-Request-ID", "")
        correlation_id = external_id if _EXTERNAL_ID_PATTERN.fullmatch(external_id) else None
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id
        request_token = _request_id_var.set(request_id)
        correlation_token = _correlation_id_var.set(correlation_id)
        log_context = f"request_id={request_id}"
        if correlation_id:
            log_context += f" correlation_id={correlation_id}"
        try:
            response = await call_next(request)
            process_time = (time.perf_counter() - start_time) * 1000
            response.headers["X-Request-ID"] = request_id
            logger.info(
                f"[RESPONSE] {request.method} {request.url.path} [{response.status_code}] "
                f"{process_time:.2f}ms {log_context} route={route_template(request)}"
            )
            return response
        except Exception as e:
            process_time = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"[ERROR] {request.method} {request.url.path} [500] "
                f"{process_time:.2f}ms {log_context} error_type={e.__class__.__name__} "
                f"route={route_template(request)}"
            )
            raise
        finally:
            _correlation_id_var.reset(correlation_token)
            _request_id_var.reset(request_token)


__all__ = [
    "AccessLogMiddleware",
    "current_correlation_id",
    "current_request_id",
]
