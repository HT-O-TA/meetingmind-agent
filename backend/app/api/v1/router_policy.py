"""面向 AI 应用主线的 API Router 暴露策略。"""

from typing import List, Tuple


RouterSpec = Tuple[str, str, str]


CORE_ROUTERS: Tuple[RouterSpec, ...] = (
    ("users", "/users", "用户"),
    ("meetings", "/meetings", "会议"),
    ("documents", "/documents", "文档"),
    ("todos", "/todos", "待办"),
    ("rag", "/rag", "RAG 问答"),
    ("agents", "/agents", "Agent 智能助手"),
    ("feedback", "", "用户反馈"),
    ("tasks", "/tasks", "任务队列"),
)


INTERNAL_ROUTERS: Tuple[RouterSpec, ...] = (
    ("trace", "", "Agent Trace"),
)


REMOVED_ROUTERS = frozenset(
    {
        "collaboration",
        "config",
        "cost",
        "dynamic_tool",
        "embedding",
        "evaluation",
        "frontend_events",
        "graph",
        "mcp",
        "memory",
        "multi_agent",
        "performance",
        "reflection",
        "templates",
        "tests",
        "text_process",
        "vector_search",
        "workflow",
    }
)


def enabled_router_specs(
    app_env: str,
) -> List[RouterSpec]:
    """返回当前环境允许注册的 Router；实验骨架不再提供运行开关。"""
    specs = list(CORE_ROUTERS)
    if app_env.strip().lower() in {"development", "test"}:
        specs.extend(INTERNAL_ROUTERS)
    return specs
