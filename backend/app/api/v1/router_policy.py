"""API Router 暴露策略。

该模块只保存无框架依赖的路由元数据，便于在没有 FastAPI 和数据库的环境中
验证生产边界。Mock、骨架和待停用入口不出现在任何默认应用中。
"""

from typing import List, Tuple


RouterSpec = Tuple[str, str, str]


CORE_ROUTERS: Tuple[RouterSpec, ...] = (
    ("users", "/users", "用户"),
    ("meetings", "/meetings", "会议"),
    ("documents", "/documents", "文档"),
    ("todos", "/todos", "待办"),
    ("text_process", "/text-process", "文本处理"),
    ("rag", "/rag", "RAG 问答"),
    ("agents", "/agents", "Agent 智能助手"),
    ("feedback", "", "用户反馈"),
    ("tasks", "/tasks", "任务队列"),
)


INTERNAL_ROUTERS: Tuple[RouterSpec, ...] = (
    ("embedding", "/embedding", "向量化服务"),
    ("vector_search", "/vector-search", "向量检索"),
    ("evaluation", "/evaluation", "评估"),
    ("config", "/config", "配置管理"),
    ("templates", "/templates", "Prompt 模板"),
    ("frontend_events", "/frontend-events", "前端事件"),
    ("trace", "", "Agent Trace"),
    ("performance", "/performance", "性能指标"),
    ("memory", "", "长期记忆"),
    ("dynamic_tool", "", "动态工具"),
    ("reflection", "", "反思系统"),
    ("cost", "/cost", "成本管理"),
)


RETIRED_ROUTERS = frozenset({"tests", "workflow", "collaboration", "multi_agent"})


def enabled_router_specs(
    app_env: str,
    *,
    enable_knowledge_graph: bool = False,
    enable_mcp_server: bool = False,
) -> List[RouterSpec]:
    """返回当前环境允许注册的 Router；生产只返回正式业务入口。"""
    specs = list(CORE_ROUTERS)
    if app_env.strip().lower() in {"development", "test"}:
        specs.extend(INTERNAL_ROUTERS)
    if enable_knowledge_graph:
        specs.append(("graph", "/graph", "知识图谱"))
    if enable_mcp_server:
        specs.append(("mcp", "", "MCP"))
    return specs
