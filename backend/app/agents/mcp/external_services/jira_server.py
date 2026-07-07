"""Jira MCP Server - 集成Jira API

提供Jira问题创建、查询、更新等工具的MCP服务
"""
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from fastapi import FastAPI, HTTPException
import httpx
import base64
import logging

logger = logging.getLogger(__name__)

try:
    from fastmcp.server import FastMCP
    HAS_FASTMCP = True
except ImportError:
    HAS_FASTMCP = False
    FastMCP = None


@dataclass
class JiraConfig:
    base_url: str
    username: str
    api_token: str


class JiraMCPServer:
    """Jira MCP Server 实现"""

    def __init__(self, config: JiraConfig):
        self.config = config
        self.mcp = None
        self._http_client = httpx.AsyncClient(timeout=30)

    def _get_auth_header(self) -> str:
        """获取Jira Basic认证头"""
        auth_str = f"{self.config.username}:{self.config.api_token}"
        return f"Basic {base64.b64encode(auth_str.encode()).decode()}"

    async def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """封装Jira API请求"""
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = self._get_auth_header()
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"

        url = f"{self.config.base_url}{path}"
        response = await self._http_client.request(method, url, headers=headers, **kwargs)

        try:
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"[Jira] API请求失败 {method} {url}: {e}")
            try:
                error_data = response.json()
                detail = error_data.get("errorMessages", [str(e)])[0] if error_data.get("errorMessages") else str(e)
            except:
                detail = str(e)
            raise HTTPException(status_code=response.status_code, detail=detail)

    def get_create_issue_tool(self):
        async def create_issue(project_key: str, issue_type: str = "Task", summary: str = "", description: str = "", assignee: Optional[str] = None, priority: str = "Medium", labels: Optional[List[str]] = None) -> Dict[str, Any]:
            """创建Jira问题
            
            Args:
                project_key: 项目Key
                issue_type: 问题类型
                summary: 问题摘要
                description: 问题描述
                assignee: 负责人
                priority: 优先级
                labels: 标签列表
                
            Returns:
                创建结果
            """
            labels = labels or []
            if not project_key or not summary:
                return {"success": False, "error": "project_key 和 summary 不能为空"}

            body = {
                "fields": {
                    "project": {"key": project_key},
                    "issuetype": {"name": issue_type},
                    "summary": summary,
                    "description": description,
                    "priority": {"name": priority},
                    "labels": labels,
                }
            }

            if assignee:
                body["fields"]["assignee"] = {"name": assignee}

            try:
                data = await self._request("POST", "/rest/api/3/issue", json=body)
                return {"success": True, "issue_id": data.get("id"), "issue_key": data.get("key"), "self": data.get("self")}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return create_issue

    def get_get_issue_tool(self):
        async def get_issue(issue_key: str) -> Dict[str, Any]:
            """获取Jira问题详情
            
            Args:
                issue_key: 问题Key
                
            Returns:
                问题详情
            """
            if not issue_key:
                return {"success": False, "error": "issue_key 不能为空"}

            try:
                data = await self._request("GET", f"/rest/api/3/issue/{issue_key}")
                return {"success": True, "issue": data}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return get_issue

    def get_update_issue_tool(self):
        async def update_issue(issue_key: str, title: Optional[str] = None, body: Optional[str] = None, state: Optional[str] = None, labels: Optional[List[str]] = None, assignees: Optional[List[str]] = None) -> Dict[str, Any]:
            """更新Jira问题
            
            Args:
                issue_key: 问题Key
                title: 标题
                body: 描述
                state: 状态
                labels: 标签
                assignees: 负责人
                
            Returns:
                更新结果
            """
            if not issue_key:
                return {"success": False, "error": "issue_key 不能为空"}

            body_data = {}
            if title is not None:
                body_data["title"] = title
            if body is not None:
                body_data["body"] = body
            if state is not None:
                body_data["state"] = state
            if labels is not None:
                body_data["labels"] = labels
            if assignees is not None:
                body_data["assignees"] = assignees

            try:
                data = await self._request("PUT", f"/rest/api/3/issue/{issue_key}", json={"fields": body_data})
                return {"success": True, "result": data}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return update_issue

    def get_search_issues_tool(self):
        async def search_issues(jql: str = "", max_results: int = 50, start_at: int = 0) -> Dict[str, Any]:
            """搜索Jira问题
            
            Args:
                jql: JQL查询语句
                max_results: 最大返回数量
                start_at: 起始位置
                
            Returns:
                问题列表
            """
            params = {
                "jql": jql,
                "maxResults": max_results,
                "startAt": start_at,
            }

            try:
                data = await self._request("GET", "/rest/api/3/search", params=params)
                return {"success": True, "issues": data.get("issues", []), "total": data.get("total", 0)}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return search_issues

    def get_add_comment_tool(self):
        async def add_comment(issue_key: str, body: str = "") -> Dict[str, Any]:
            """添加评论
            
            Args:
                issue_key: 问题Key
                body: 评论内容
                
            Returns:
                添加结果
            """
            if not issue_key or not body:
                return {"success": False, "error": "issue_key 和 body 不能为空"}

            try:
                data = await self._request("POST", f"/rest/api/3/issue/{issue_key}/comment", json={"body": body})
                return {"success": True, "comment_id": data.get("id"), "body": data.get("body")}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return add_comment

    def get_get_projects_tool(self):
        async def get_projects(max_results: int = 50) -> Dict[str, Any]:
            """获取项目列表
            
            Args:
                max_results: 最大返回数量
                
            Returns:
                项目列表
            """
            try:
                data = await self._request("GET", "/rest/api/3/project/search", params={"maxResults": max_results})
                return {"success": True, "projects": data.get("values", []), "total": data.get("total", 0)}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return get_projects

    def get_app(self) -> FastAPI:
        """获取Jira MCP Server 的 FastAPI 应用"""
        app = FastAPI(title="Jira MCP Server", version="1.0.0")

        if HAS_FASTMCP and FastMCP:
            self.mcp = FastMCP(
                name="JiraMCP",
                version="1.0.0",
                instructions="Jira MCP 服务，提供问题创建、查询、更新等功能",
            )

            self.mcp.add_tool(self.get_create_issue_tool())
            self.mcp.add_tool(self.get_get_issue_tool())
            self.mcp.add_tool(self.get_update_issue_tool())
            self.mcp.add_tool(self.get_search_issues_tool())
            self.mcp.add_tool(self.get_add_comment_tool())
            self.mcp.add_tool(self.get_get_projects_tool())

            mcp_app = self.mcp.http_app(path="/")
            app.mount("/mcp", mcp_app)

        @app.get("/health")
        async def health_check():
            return {"status": "ok", "service": "jira-mcp"}

        return app

    def get_tools(self) -> List[Dict[str, Any]]:
        """获取所有注册的工具信息"""
        tools = []
        if self.mcp and hasattr(self.mcp, '_tools'):
            for tool_name, tool in self.mcp._tools.items():
                tools.append({
                    "name": tool_name,
                    "description": tool.description or "",
                })
        return tools


def create_jira_mcp_server(base_url: str, username: str, api_token: str) -> JiraMCPServer:
    """创建Jira MCP Server 实例"""
    config = JiraConfig(base_url=base_url, username=username, api_token=api_token)
    return JiraMCPServer(config)