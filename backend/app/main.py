from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.logger import app_logger
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    global_exception_handler,
)
from app.db.database import init_db
from app.core.cache_init import init_all_caches, close_redis
from app.agents.checkpoint import initialize_checkpoint_store, close_checkpoint_store
from app.core.rabbitmq import close_rabbitmq
from app.core.middleware import AccessLogMiddleware, AgentConcurrencyMiddleware
from app.core.health import build_readiness_report
from app.api.v1.router import api_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    app_logger.info(f"Starting {settings.APP_NAME} in {settings.APP_ENV} mode")
    await init_db()
    app_logger.info("Database initialized")
    cache_results = await init_all_caches()
    app_logger.info(f"Cache systems initialized: {cache_results}")
    await initialize_checkpoint_store()
    app_logger.info("Agent checkpoint store initialized")
    try:
        yield
    finally:
        await close_checkpoint_store()
        await close_rabbitmq()
        await close_redis()

class MeetingMindAPI(FastAPI):
    def build_middleware_stack(self):
        return CORSMiddleware(
            super().build_middleware_stack(),
            allow_origins=settings.cors_origins_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID"],
        )


app = MeetingMindAPI(
    title=settings.APP_NAME,
    description="会议文档 RAG 与安全工具 Agent API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(AgentConcurrencyMiddleware)
app.add_middleware(AccessLogMiddleware)

if settings.METRICS_ENABLED:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    from starlette.responses import Response

    from app.core.metrics import HttpMetricsMiddleware, registry

    app.add_middleware(HttpMetricsMiddleware)

    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        return Response(generate_latest(registry), headers={"Content-Type": CONTENT_TYPE_LATEST})

app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)


@app.get("/live")
async def live():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def _readiness_response(*, compatibility: bool = False) -> JSONResponse:
    ready, report = await build_readiness_report()
    payload = {"app": settings.APP_NAME, **report}
    if compatibility:
        payload["compatibility_alias"] = "/ready"
    return JSONResponse(status_code=200 if ready else 503, content=payload)


@app.get("/ready")
async def ready():
    return await _readiness_response()


@app.get("/health")
async def health():
    return await _readiness_response(compatibility=True)


app.include_router(api_router, prefix="/api/v1")
