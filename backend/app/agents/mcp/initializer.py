"""MCP 初始化器 - 自动注册配置的外部 MCP 服务器"""
from typing import Optional, Dict, Any
from fastapi import FastAPI
from app.core.config import settings
from app.core.logger import app_logger
from app.agents.mcp import (
    get_mcp_discovery,
    get_mcp_tool_manager,
    MCPConnectionConfig,
    MCPTransport,
)
from app.agents.mcp.external_services import (
    create_feishu_mcp_server,
    create_jira_mcp_server,
    create_notion_mcp_server,
    create_github_mcp_server,
)


_external_server_apps: Dict[str, FastAPI] = {}


async def initialize_mcp_servers(app: Optional[FastAPI] = None):
    """
    初始化配置的外部 MCP 服务器
    
    根据 .env 中的配置自动注册飞书、GitHub、Jira、Notion 等外部 MCP 服务器
    如果配置了应用密钥但没有配置 URL，则启动本地 MCP Server
    """
    discovery = get_mcp_discovery()
    tool_manager = get_mcp_tool_manager()
    registered_count = 0

    # 注册飞书 MCP
    if settings.FEISHU_MCP_ENABLED:
        if settings.FEISHU_MCP_URL:
            try:
                config = MCPConnectionConfig(
                    name="飞书MCP",
                    url=settings.FEISHU_MCP_URL,
                    transport=MCPTransport.HTTP,
                    api_key=settings.FEISHU_MCP_APP_SECRET,
                    headers={
                        "X-App-ID": settings.FEISHU_MCP_APP_ID,
                        "X-App-Secret": settings.FEISHU_MCP_APP_SECRET,
                    },
                    timeout=30,
                )
                discovery.register_server(config)
                await tool_manager.register_external_server(config)
                registered_count += 1
                app_logger.info(f"[MCP] 已注册外部飞书 MCP 服务器: {settings.FEISHU_MCP_URL}")
            except Exception as e:
                app_logger.error(f"[MCP] 注册飞书 MCP 失败: {e}")
        elif settings.FEISHU_MCP_APP_ID and settings.FEISHU_MCP_APP_SECRET:
            try:
                feishu_server = create_feishu_mcp_server(
                    app_id=settings.FEISHU_MCP_APP_ID,
                    app_secret=settings.FEISHU_MCP_APP_SECRET,
                )
                feishu_app = feishu_server.get_app()
                _external_server_apps["feishu"] = feishu_app
                if app:
                    app.mount("/mcp/feishu", feishu_app)
                
                config = MCPConnectionConfig(
                    name="飞书MCP",
                    url=f"http://localhost:8000/mcp/feishu/mcp",
                    transport=MCPTransport.HTTP,
                    api_key=settings.FEISHU_MCP_APP_SECRET,
                    headers={
                        "X-App-ID": settings.FEISHU_MCP_APP_ID,
                        "X-App-Secret": settings.FEISHU_MCP_APP_SECRET,
                    },
                    timeout=30,
                )
                discovery.register_server(config)
                await tool_manager.register_external_server(config)
                registered_count += 1
                app_logger.info(f"[MCP] 已启动本地飞书 MCP 服务器，挂载路径: /mcp/feishu")
            except Exception as e:
                app_logger.error(f"[MCP] 启动飞书 MCP 失败: {e}")

    # 注册 GitHub MCP
    if settings.GITHUB_MCP_ENABLED:
        if settings.GITHUB_MCP_URL:
            try:
                config = MCPConnectionConfig(
                    name="GitHubMCP",
                    url=settings.GITHUB_MCP_URL,
                    transport=MCPTransport.HTTP,
                    api_key=settings.GITHUB_MCP_TOKEN,
                    headers={
                        "Authorization": f"Bearer {settings.GITHUB_MCP_TOKEN}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                    timeout=30,
                )
                discovery.register_server(config)
                await tool_manager.register_external_server(config)
                registered_count += 1
                app_logger.info(f"[MCP] 已注册外部 GitHub MCP 服务器: {settings.GITHUB_MCP_URL}")
            except Exception as e:
                app_logger.error(f"[MCP] 注册 GitHub MCP 失败: {e}")
        elif settings.GITHUB_MCP_TOKEN:
            try:
                github_server = create_github_mcp_server(api_token=settings.GITHUB_MCP_TOKEN)
                github_app = github_server.get_app()
                _external_server_apps["github"] = github_app
                if app:
                    app.mount("/mcp/github", github_app)
                
                config = MCPConnectionConfig(
                    name="GitHubMCP",
                    url=f"http://localhost:8000/mcp/github/mcp",
                    transport=MCPTransport.HTTP,
                    api_key=settings.GITHUB_MCP_TOKEN,
                    headers={
                        "Authorization": f"Bearer {settings.GITHUB_MCP_TOKEN}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                    timeout=30,
                )
                discovery.register_server(config)
                await tool_manager.register_external_server(config)
                registered_count += 1
                app_logger.info(f"[MCP] 已启动本地 GitHub MCP 服务器，挂载路径: /mcp/github")
            except Exception as e:
                app_logger.error(f"[MCP] 启动 GitHub MCP 失败: {e}")

    # 注册 Jira MCP
    if settings.JIRA_MCP_ENABLED:
        if settings.JIRA_MCP_URL:
            try:
                import base64
                auth_token = base64.b64encode(
                    f"{settings.JIRA_MCP_USERNAME}:{settings.JIRA_MCP_API_TOKEN}".encode()
                ).decode()
                
                config = MCPConnectionConfig(
                    name="JiraMCP",
                    url=settings.JIRA_MCP_URL,
                    transport=MCPTransport.HTTP,
                    api_key=settings.JIRA_MCP_API_TOKEN,
                    headers={
                        "Authorization": f"Basic {auth_token}",
                        "Accept": "application/json",
                    },
                    timeout=30,
                )
                discovery.register_server(config)
                await tool_manager.register_external_server(config)
                registered_count += 1
                app_logger.info(f"[MCP] 已注册外部 Jira MCP 服务器: {settings.JIRA_MCP_URL}")
            except Exception as e:
                app_logger.error(f"[MCP] 注册 Jira MCP 失败: {e}")
        elif settings.JIRA_MCP_USERNAME and settings.JIRA_MCP_API_TOKEN and settings.JIRA_MCP_URL:
            try:
                jira_server = create_jira_mcp_server(
                    base_url=settings.JIRA_MCP_URL,
                    username=settings.JIRA_MCP_USERNAME,
                    api_token=settings.JIRA_MCP_API_TOKEN,
                )
                jira_app = jira_server.get_app()
                _external_server_apps["jira"] = jira_app
                if app:
                    app.mount("/mcp/jira", jira_app)
                
                import base64
                auth_token = base64.b64encode(
                    f"{settings.JIRA_MCP_USERNAME}:{settings.JIRA_MCP_API_TOKEN}".encode()
                ).decode()
                
                config = MCPConnectionConfig(
                    name="JiraMCP",
                    url=f"http://localhost:8000/mcp/jira/mcp",
                    transport=MCPTransport.HTTP,
                    api_key=settings.JIRA_MCP_API_TOKEN,
                    headers={
                        "Authorization": f"Basic {auth_token}",
                        "Accept": "application/json",
                    },
                    timeout=30,
                )
                discovery.register_server(config)
                await tool_manager.register_external_server(config)
                registered_count += 1
                app_logger.info(f"[MCP] 已启动本地 Jira MCP 服务器，挂载路径: /mcp/jira")
            except Exception as e:
                app_logger.error(f"[MCP] 启动 Jira MCP 失败: {e}")

    # 注册 Notion MCP
    if settings.NOTION_MCP_ENABLED:
        if settings.NOTION_MCP_URL:
            try:
                config = MCPConnectionConfig(
                    name="NotionMCP",
                    url=settings.NOTION_MCP_URL,
                    transport=MCPTransport.HTTP,
                    api_key=settings.NOTION_MCP_API_KEY,
                    headers={
                        "Authorization": f"Bearer {settings.NOTION_MCP_API_KEY}",
                        "Notion-Version": "2022-06-28",
                    },
                    timeout=30,
                )
                discovery.register_server(config)
                await tool_manager.register_external_server(config)
                registered_count += 1
                app_logger.info(f"[MCP] 已注册外部 Notion MCP 服务器: {settings.NOTION_MCP_URL}")
            except Exception as e:
                app_logger.error(f"[MCP] 注册 Notion MCP 失败: {e}")
        elif settings.NOTION_MCP_API_KEY:
            try:
                notion_server = create_notion_mcp_server(api_key=settings.NOTION_MCP_API_KEY)
                notion_app = notion_server.get_app()
                _external_server_apps["notion"] = notion_app
                if app:
                    app.mount("/mcp/notion", notion_app)
                
                config = MCPConnectionConfig(
                    name="NotionMCP",
                    url=f"http://localhost:8000/mcp/notion/mcp",
                    transport=MCPTransport.HTTP,
                    api_key=settings.NOTION_MCP_API_KEY,
                    headers={
                        "Authorization": f"Bearer {settings.NOTION_MCP_API_KEY}",
                        "Notion-Version": "2022-06-28",
                    },
                    timeout=30,
                )
                discovery.register_server(config)
                await tool_manager.register_external_server(config)
                registered_count += 1
                app_logger.info(f"[MCP] 已启动本地 Notion MCP 服务器，挂载路径: /mcp/notion")
            except Exception as e:
                app_logger.error(f"[MCP] 启动 Notion MCP 失败: {e}")

    if registered_count > 0:
        app_logger.info(f"[MCP] 共注册 {registered_count} 个外部 MCP 服务器")
    else:
        app_logger.info("[MCP] 未注册任何外部 MCP 服务器，请在 .env 中启用并配置")

    return registered_count


def get_external_server_apps() -> Dict[str, FastAPI]:
    """获取已启动的外部服务器应用"""
    return _external_server_apps


async def discover_external_tools():
    """
    发现所有已注册外部服务器的工具
    
    Returns:
        发现的工具总数
    """
    discovery = get_mcp_discovery()
    all_tools = await discovery.discover_all_tools()
    app_logger.info(f"[MCP] 从外部服务器发现 {len(all_tools)} 个工具")
    return len(all_tools)


async def get_mcp_status_summary() -> dict:
    """
    获取 MCP 系统状态摘要
    
    Returns:
        状态摘要字典
    """
    discovery = get_mcp_discovery()
    tool_manager = get_mcp_tool_manager()

    servers = discovery.list_servers()
    health = await discovery.health_check_all()
    status = await tool_manager.get_server_status()
    all_tools = await tool_manager.get_all_tools()

    return {
        "registered_servers": servers,
        "server_count": len(servers),
        "total_tools": len(all_tools),
        "server_health": health,
        "detailed_status": status,
    }