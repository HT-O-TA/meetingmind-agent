from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from prometheus_fastapi_instrumentator import Instrumentator

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
from app.core.rabbitmq import close_rabbitmq
from app.core.middleware import AccessLogMiddleware
from app.api.v1.router import api_router

if settings.ENABLE_MCP_SERVER:
    try:
        from app.agents.mcp.server import get_mcp_server
        from app.agents.mcp.initializer import initialize_mcp_servers
        HAS_MCP = True
    except ImportError:
        HAS_MCP = False
        get_mcp_server = None
        initialize_mcp_servers = None
else:
    HAS_MCP = False
    get_mcp_server = None
    initialize_mcp_servers = None

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

# 初始化 Prometheus 指标暴露（必须在应用启动前调用）
Instrumentator().instrument(app).expose(app)


@app.on_event("startup")
async def startup():
    app_logger.info(f"Starting {settings.APP_NAME} in {settings.APP_ENV} mode")
    await init_db()
    app_logger.info("Database initialized")
    
    # 初始化混合缓存系统（原生Redis + LLM缓存 + FastAPI-Cache）
    cache_results = await init_all_caches()
    app_logger.info(f"Cache systems initialized: {cache_results}")
    
    # 初始化 MCP Server
    if settings.ENABLE_MCP_SERVER and HAS_MCP and get_mcp_server:
        try:
            mcp_server = get_mcp_server()
            mcp_app = mcp_server.get_app(path="/")
            if mcp_app:
                app.mount("/mcp", mcp_app)
                app_logger.info(f"MCP Server 挂载成功，端点: /mcp")
                
                # 初始化外部 MCP 服务器（飞书、GitHub、Jira、Notion）
                if initialize_mcp_servers:
                    try:
                        registered_count = await initialize_mcp_servers()
                        app_logger.info(f"外部 MCP 服务器初始化完成，已注册 {registered_count} 个服务器")
                    except Exception as e:
                        app_logger.error(f"外部 MCP 服务器初始化异常: {e}")
            else:
                app_logger.warning("MCP Server 初始化失败")
        except Exception as e:
            app_logger.error(f"MCP Server 初始化异常: {e}")
    
    # Agent 消费者依赖 RabbitMQ，默认不随 Web 进程隐式启动。
    if settings.ENABLE_AGENT_WORKER:
        try:
            from app.services.agent_worker import start_agent_worker
            await start_agent_worker()
            app_logger.info("Agent执行消费者启动成功")
        except Exception as e:
            app_logger.error(f"Agent执行消费者启动失败: {e}")


@app.on_event("shutdown")
async def shutdown():
    await close_rabbitmq()
    await close_redis()


@app.get("/health")
async def health():
    redis_status = await redis_health()
    return {"status": "ok", "app": settings.APP_NAME, "redis": redis_status}


app.include_router(api_router, prefix="/api/v1")
