"""API v1 路由注册：生产正式入口与内部诊断入口分离。"""

from importlib import import_module

from fastapi import APIRouter

from app.api.v1.router_policy import enabled_router_specs
from app.core.config import settings


api_router = APIRouter()

for module_name, prefix, tag in enabled_router_specs(
    settings.APP_ENV,
    enable_knowledge_graph=settings.ENABLE_KNOWLEDGE_GRAPH,
    enable_mcp_server=settings.ENABLE_MCP_SERVER,
):
    endpoint = import_module(f"app.api.v1.endpoints.{module_name}")
    api_router.include_router(endpoint.router, prefix=prefix, tags=[tag])
