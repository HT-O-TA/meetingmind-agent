from fastapi import FastAPI
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
from app.core.cache_init import init_all_caches, close_redis, redis_health
from app.core.middleware import AccessLogMiddleware
from app.api.v1.router import api_router

app = FastAPI(
    title=settings.APP_NAME,
    description="企业级会议智能助手 API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(AccessLogMiddleware)

app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)


@app.on_event("startup")
async def startup():
    app_logger.info(f"Starting {settings.APP_NAME} in {settings.APP_ENV} mode")
    await init_db()
    app_logger.info("Database initialized")
    
    # 初始化混合缓存系统（原生Redis + LLM缓存 + FastAPI-Cache）
    cache_results = await init_all_caches()
    app_logger.info(f"Cache systems initialized: {cache_results}")


@app.on_event("shutdown")
async def shutdown():
    await close_redis()


@app.get("/health")
async def health():
    redis_status = await redis_health()
    return {"status": "ok", "app": settings.APP_NAME, "redis": redis_status}


app.include_router(api_router, prefix="/api/v1")
