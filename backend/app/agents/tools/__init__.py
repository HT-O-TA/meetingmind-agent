"""Agent工具系统 - 动态工具注册与管理"""
from app.agents.tools.tool_metadata import (
    Tool,
    ToolMetadata,
    ToolParameter,
    ToolCategory,
    ToolStatus,
    ToolRiskLevel,
    ToolExecutionResult,
)
from app.agents.tools.registry import ToolRegistry, get_tool_registry
from app.agents.tools.executor import ToolExecutor, get_tool_executor
from app.agents.tools.selector import ToolSelector, get_tool_selector
from app.agents.tools.custom_manager import CustomToolManager, get_custom_tool_manager
from app.agents.tools.builtin import get_builtin_tools, execute_builtin_tool
from app.agents.tools.manager import ToolManager
from app.agents.tools.policy import ToolPolicy, ToolPolicyDecision

__all__ = [
    # 核心类
    "Tool",
    "ToolMetadata",
    "ToolParameter",
    "ToolCategory",
    "ToolStatus",
    "ToolRiskLevel",
    "ToolExecutionResult",
    # 管理器
    "ToolManager",
    "ToolPolicy",
    "ToolPolicyDecision",
    "ToolRegistry",
    "get_tool_registry",
    "ToolExecutor",
    "get_tool_executor",
    "ToolSelector",
    "get_tool_selector",
    "CustomToolManager",
    "get_custom_tool_manager",
    # 内置工具
    "get_builtin_tools",
    "execute_builtin_tool",
]
