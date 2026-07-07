"""外部服务 MCP Server 模块

提供飞书、Jira、Notion、GitHub 等外部服务的 MCP 集成
"""

from .feishu_server import (
    FeishuMCPServer,
    FeishuConfig,
    create_feishu_mcp_server,
)

from .jira_server import (
    JiraMCPServer,
    JiraConfig,
    create_jira_mcp_server,
)

from .notion_server import (
    NotionMCPServer,
    NotionConfig,
    create_notion_mcp_server,
)

from .github_server import (
    GitHubMCPServer,
    GitHubConfig,
    create_github_mcp_server,
)

__all__ = [
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