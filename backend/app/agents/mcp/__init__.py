"""MCP (Model Context Protocol) 模块

提供 MeetingMind 的 MCP 集成能力：
1. MCP Server - 将内部工具暴露为 MCP 服务
2. MCP Client - 发现和调用外部 MCP 服务器
3. MCP Tool Manager - 统一管理内部和外部工具
4. MCP Initializer - 自动注册配置的外部服务器
5. 外部服务集成 - 飞书、Jira、Notion、GitHub MCP Server
"""

from .server import (
    MCPServer,
    MCPServerConfig,
    get_mcp_server,
    init_mcp_server,
)

from .client import (
    MCPClient,
    MCPDiscoveryService,
    MCPDynamicDiscoveryService,
    MCPConnectionConfig,
    MCPToolInfo,
    MCPTransport,
    get_mcp_discovery,
    get_mcp_dynamic_discovery,
    init_mcp_discovery,
    init_mcp_dynamic_discovery,
)

from .mcp_tool_manager import (
    MCPToolManager,
    UnifiedToolInfo,
    get_mcp_tool_manager,
    init_mcp_tool_manager,
)

from .initializer import (
    initialize_mcp_servers,
    discover_external_tools,
    get_mcp_status_summary,
    get_external_server_apps,
)

from .external_services import (
    FeishuMCPServer,
    FeishuConfig,
    create_feishu_mcp_server,
    JiraMCPServer,
    JiraConfig,
    create_jira_mcp_server,
    NotionMCPServer,
    NotionConfig,
    create_notion_mcp_server,
    GitHubMCPServer,
    GitHubConfig,
    create_github_mcp_server,
)

__all__ = [
    "MCPServer",
    "MCPServerConfig",
    "get_mcp_server",
    "init_mcp_server",
    "MCPClient",
    "MCPDiscoveryService",
    "MCPDynamicDiscoveryService",
    "MCPConnectionConfig",
    "MCPToolInfo",
    "MCPTransport",
    "get_mcp_discovery",
    "get_mcp_dynamic_discovery",
    "init_mcp_discovery",
    "init_mcp_dynamic_discovery",
    "MCPToolManager",
    "UnifiedToolInfo",
    "get_mcp_tool_manager",
    "init_mcp_tool_manager",
    "initialize_mcp_servers",
    "discover_external_tools",
    "get_mcp_status_summary",
    "get_external_server_apps",
    "FeishuMCPServer",
    "FeishuConfig",
    "create_feishu_mcp_server",
    "JiraMCPServer",
    "JiraConfig",
    "create_jira_mcp_server",
    "NotionMCPServer",
    "NotionConfig",
    "create_notion_mcp_server",
    "GitHubMCPServer",
    "GitHubConfig",
    "create_github_mcp_server",
]