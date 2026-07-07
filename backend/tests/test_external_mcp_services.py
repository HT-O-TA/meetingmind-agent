"""测试外部服务 MCP Server 集成"""
import asyncio
import pytest
from fastapi.testclient import TestClient


class TestFeishuMCPServer:
    """测试飞书 MCP Server"""

    def test_create_server(self):
        """测试创建飞书 MCP Server"""
        from app.agents.mcp.external_services import create_feishu_mcp_server
        
        server = create_feishu_mcp_server(app_id="test_app_id", app_secret="test_app_secret")
        assert server is not None
        assert server.config.app_id == "test_app_id"
        assert server.config.app_secret == "test_app_secret"

    def test_get_app(self):
        """测试获取飞书 MCP Server 应用"""
        from app.agents.mcp.external_services import create_feishu_mcp_server
        
        server = create_feishu_mcp_server(app_id="test_app_id", app_secret="test_app_secret")
        app = server.get_app()
        
        assert app is not None
        assert app.title == "飞书 MCP Server"
        
        tools = server.get_tools()
        assert len(tools) >= 5
        tool_names = [t["name"] for t in tools]
        assert "feishu_send_message" in tool_names
        assert "feishu_create_document" in tool_names
        assert "feishu_create_calendar_event" in tool_names
        assert "feishu_create_task" in tool_names
        assert "feishu_search_user" in tool_names

    def test_health_check(self):
        """测试飞书 MCP Server 健康检查"""
        from app.agents.mcp.external_services import create_feishu_mcp_server
        
        server = create_feishu_mcp_server(app_id="test_app_id", app_secret="test_app_secret")
        app = server.get_app()
        
        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "service": "feishu-mcp"}


class TestJiraMCPServer:
    """测试 Jira MCP Server"""

    def test_create_server(self):
        """测试创建 Jira MCP Server"""
        from app.agents.mcp.external_services import create_jira_mcp_server
        
        server = create_jira_mcp_server(
            base_url="https://jira.example.com",
            username="test_user",
            api_token="test_token"
        )
        assert server is not None
        assert server.config.base_url == "https://jira.example.com"
        assert server.config.username == "test_user"

    def test_get_app(self):
        """测试获取 Jira MCP Server 应用"""
        from app.agents.mcp.external_services import create_jira_mcp_server
        
        server = create_jira_mcp_server(
            base_url="https://jira.example.com",
            username="test_user",
            api_token="test_token"
        )
        app = server.get_app()
        
        assert app is not None
        assert app.title == "Jira MCP Server"
        
        tools = server.get_tools()
        assert len(tools) >= 6
        tool_names = [t["name"] for t in tools]
        assert "jira_create_issue" in tool_names
        assert "jira_get_issue" in tool_names
        assert "jira_update_issue" in tool_names
        assert "jira_search_issues" in tool_names
        assert "jira_add_comment" in tool_names
        assert "jira_get_projects" in tool_names

    def test_health_check(self):
        """测试 Jira MCP Server 健康检查"""
        from app.agents.mcp.external_services import create_jira_mcp_server
        
        server = create_jira_mcp_server(
            base_url="https://jira.example.com",
            username="test_user",
            api_token="test_token"
        )
        app = server.get_app()
        
        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "service": "jira-mcp"}


class TestNotionMCPServer:
    """测试 Notion MCP Server"""

    def test_create_server(self):
        """测试创建 Notion MCP Server"""
        from app.agents.mcp.external_services import create_notion_mcp_server
        
        server = create_notion_mcp_server(api_key="test_api_key")
        assert server is not None
        assert server.config.api_key == "test_api_key"

    def test_get_app(self):
        """测试获取 Notion MCP Server 应用"""
        from app.agents.mcp.external_services import create_notion_mcp_server
        
        server = create_notion_mcp_server(api_key="test_api_key")
        app = server.get_app()
        
        assert app is not None
        assert app.title == "Notion MCP Server"
        
        tools = server.get_tools()
        assert len(tools) >= 7
        tool_names = [t["name"] for t in tools]
        assert "notion_create_page" in tool_names
        assert "notion_get_page" in tool_names
        assert "notion_update_page" in tool_names
        assert "notion_append_block" in tool_names
        assert "notion_query_database" in tool_names
        assert "notion_create_database" in tool_names
        assert "notion_search" in tool_names

    def test_health_check(self):
        """测试 Notion MCP Server 健康检查"""
        from app.agents.mcp.external_services import create_notion_mcp_server
        
        server = create_notion_mcp_server(api_key="test_api_key")
        app = server.get_app()
        
        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "service": "notion-mcp"}


class TestGitHubMCPServer:
    """测试 GitHub MCP Server"""

    def test_create_server(self):
        """测试创建 GitHub MCP Server"""
        from app.agents.mcp.external_services import create_github_mcp_server
        
        server = create_github_mcp_server(api_token="test_token")
        assert server is not None
        assert server.config.api_token == "test_token"

    def test_get_app(self):
        """测试获取 GitHub MCP Server 应用"""
        from app.agents.mcp.external_services import create_github_mcp_server
        
        server = create_github_mcp_server(api_token="test_token")
        app = server.get_app()
        
        assert app is not None
        assert app.title == "GitHub MCP Server"
        
        tools = server.get_tools()
        assert len(tools) >= 8
        tool_names = [t["name"] for t in tools]
        assert "github_create_issue" in tool_names
        assert "github_get_issue" in tool_names
        assert "github_update_issue" in tool_names
        assert "github_create_pr" in tool_names
        assert "github_get_pr" in tool_names
        assert "github_list_issues" in tool_names
        assert "github_get_repo" in tool_names
        assert "github_create_release" in tool_names

    def test_health_check(self):
        """测试 GitHub MCP Server 健康检查"""
        from app.agents.mcp.external_services import create_github_mcp_server
        
        server = create_github_mcp_server(api_token="test_token")
        app = server.get_app()
        
        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "service": "github-mcp"}


class TestExternalServicesIntegration:
    """测试外部服务集成"""

    def test_all_services_importable(self):
        """测试所有外部服务模块可导入"""
        from app.agents.mcp.external_services import (
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
        
        assert FeishuMCPServer is not None
        assert JiraMCPServer is not None
        assert NotionMCPServer is not None
        assert GitHubMCPServer is not None

    def test_mcp_init_importable(self):
        """测试 MCP 初始化器导入"""
        from app.agents.mcp.initializer import (
            initialize_mcp_servers,
            get_external_server_apps,
        )
        
        assert initialize_mcp_servers is not None
        assert get_external_server_apps is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])