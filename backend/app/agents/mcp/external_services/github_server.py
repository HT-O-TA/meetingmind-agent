"""GitHub MCP Server - 集成GitHub API

提供GitHub Issue、PR、仓库操作等工具的MCP服务
"""
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from fastapi import FastAPI, HTTPException
import httpx
import logging

logger = logging.getLogger(__name__)

try:
    from fastmcp.server import FastMCP
    HAS_FASTMCP = True
except ImportError:
    HAS_FASTMCP = False
    FastMCP = None


@dataclass
class GitHubConfig:
    api_token: str
    base_url: str = "https://api.github.com"


class GitHubMCPServer:
    """GitHub MCP Server 实现"""

    def __init__(self, config: GitHubConfig):
        self.config = config
        self.mcp = None
        self._http_client = httpx.AsyncClient(timeout=30)

    async def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """封装GitHub API请求"""
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"token {self.config.api_token}"
        headers["Accept"] = "application/vnd.github.v3+json"

        url = f"{self.config.base_url}{path}"
        response = await self._http_client.request(method, url, headers=headers, **kwargs)

        try:
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"[GitHub] API请求失败 {method} {url}: {e}")
            try:
                error_data = response.json()
                detail = error_data.get("message", str(e))
            except:
                detail = str(e)
            raise HTTPException(status_code=response.status_code, detail=detail)

    def get_create_issue_tool(self):
        async def create_issue(owner: str, repo: str, title: str = "", body: str = "", labels: Optional[List[str]] = None, assignees: Optional[List[str]] = None) -> Dict[str, Any]:
            """创建GitHub Issue
            
            Args:
                owner: 仓库所有者
                repo: 仓库名
                title: Issue标题
                body: Issue描述
                labels: 标签列表
                assignees: 负责人列表
                
            Returns:
                创建结果
            """
            labels = labels or []
            assignees = assignees or []
            if not owner or not repo or not title:
                return {"success": False, "error": "owner、repo 和 title 不能为空"}

            body_data = {
                "title": title,
                "body": body,
                "labels": labels,
                "assignees": assignees,
            }

            try:
                data = await self._request("POST", f"/repos/{owner}/{repo}/issues", json=body_data)
                return {"success": True, "issue_number": data.get("number"), "html_url": data.get("html_url"), "state": data.get("state")}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return create_issue

    def get_get_issue_tool(self):
        async def get_issue(owner: str, repo: str, issue_number: int) -> Dict[str, Any]:
            """获取GitHub Issue详情
            
            Args:
                owner: 仓库所有者
                repo: 仓库名
                issue_number: Issue编号
                
            Returns:
                Issue详情
            """
            if not owner or not repo or not issue_number:
                return {"success": False, "error": "owner、repo 和 issue_number 不能为空"}

            try:
                data = await self._request("GET", f"/repos/{owner}/{repo}/issues/{issue_number}")
                return {"success": True, "issue": data}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return get_issue

    def get_update_issue_tool(self):
        async def update_issue(owner: str, repo: str, issue_number: int, title: Optional[str] = None, body: Optional[str] = None, state: Optional[str] = None, labels: Optional[List[str]] = None, assignees: Optional[List[str]] = None) -> Dict[str, Any]:
            """更新GitHub Issue
            
            Args:
                owner: 仓库所有者
                repo: 仓库名
                issue_number: Issue编号
                title: 标题
                body: 描述
                state: 状态
                labels: 标签
                assignees: 负责人
                
            Returns:
                更新结果
            """
            if not owner or not repo or not issue_number:
                return {"success": False, "error": "owner、repo 和 issue_number 不能为空"}

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
                data = await self._request("PATCH", f"/repos/{owner}/{repo}/issues/{issue_number}", json=body_data)
                return {"success": True, "issue": data}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return update_issue

    def get_create_pull_request_tool(self):
        async def create_pull_request(owner: str, repo: str, head: str, base: str, title: str = "", body: str = "") -> Dict[str, Any]:
            """创建GitHub Pull Request
            
            Args:
                owner: 仓库所有者
                repo: 仓库名
                head: 源分支
                base: 目标分支
                title: PR标题
                body: PR描述
                
            Returns:
                创建结果
            """
            if not owner or not repo or not head or not base:
                return {"success": False, "error": "owner、repo、head 和 base 不能为空"}

            body_data = {
                "title": title,
                "body": body,
                "head": head,
                "base": base,
            }

            try:
                data = await self._request("POST", f"/repos/{owner}/{repo}/pulls", json=body_data)
                return {"success": True, "pr_number": data.get("number"), "html_url": data.get("html_url"), "state": data.get("state")}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return create_pull_request

    def get_get_pull_request_tool(self):
        async def get_pull_request(owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
            """获取GitHub Pull Request详情
            
            Args:
                owner: 仓库所有者
                repo: 仓库名
                pr_number: PR编号
                
            Returns:
                PR详情
            """
            if not owner or not repo or not pr_number:
                return {"success": False, "error": "owner、repo 和 pr_number 不能为空"}

            try:
                data = await self._request("GET", f"/repos/{owner}/{repo}/pulls/{pr_number}")
                return {"success": True, "pull_request": data}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return get_pull_request

    def get_create_release_tool(self):
        async def create_release(owner: str, repo: str, tag_name: str, name: Optional[str] = None, body: Optional[str] = None, draft: bool = False, prerelease: bool = False) -> Dict[str, Any]:
            """创建GitHub Release
            
            Args:
                owner: 仓库所有者
                repo: 仓库名
                tag_name: 标签名
                name: Release名称
                body: Release描述
                draft: 是否草稿
                prerelease: 是否预发布
                
            Returns:
                创建结果
            """
            if not owner or not repo or not tag_name:
                return {"success": False, "error": "owner、repo 和 tag_name 不能为空"}

            body_data = {
                "tag_name": tag_name,
                "name": name or tag_name,
                "body": body or "",
                "draft": draft,
                "prerelease": prerelease,
            }

            try:
                data = await self._request("POST", f"/repos/{owner}/{repo}/releases", json=body_data)
                return {"success": True, "id": data.get("id"), "html_url": data.get("html_url"), "upload_url": data.get("upload_url")}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return create_release

    def get_get_repo_tool(self):
        async def get_repo(owner: str, repo: str) -> Dict[str, Any]:
            """获取GitHub仓库信息
            
            Args:
                owner: 仓库所有者
                repo: 仓库名
                
            Returns:
                仓库信息
            """
            if not owner or not repo:
                return {"success": False, "error": "owner 和 repo 不能为空"}

            try:
                data = await self._request("GET", f"/repos/{owner}/{repo}")
                return {"success": True, "repo": data}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return get_repo

    def get_list_issues_tool(self):
        async def list_issues(owner: str, repo: str, state: str = "open", labels: Optional[str] = None, per_page: int = 30, page: int = 1) -> Dict[str, Any]:
            """列出GitHub Issues
            
            Args:
                owner: 仓库所有者
                repo: 仓库名
                state: 状态
                labels: 标签
                per_page: 每页数量
                page: 页码
                
            Returns:
                Issue列表
            """
            if not owner or not repo:
                return {"success": False, "error": "owner 和 repo 不能为空"}

            params = {
                "state": state,
                "per_page": per_page,
                "page": page,
            }
            if labels:
                params["labels"] = labels

            try:
                data = await self._request("GET", f"/repos/{owner}/{repo}/issues", params=params)
                return {"success": True, "issues": data}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return list_issues

    def get_app(self) -> FastAPI:
        """获取GitHub MCP Server 的 FastAPI 应用"""
        app = FastAPI(title="GitHub MCP Server", version="1.0.0")

        if HAS_FASTMCP and FastMCP:
            self.mcp = FastMCP(
                name="GitHubMCP",
                version="1.0.0",
                instructions="GitHub MCP 服务，提供Issue、PR、仓库操作等功能",
            )

            self.mcp.add_tool(self.get_create_issue_tool())
            self.mcp.add_tool(self.get_get_issue_tool())
            self.mcp.add_tool(self.get_update_issue_tool())
            self.mcp.add_tool(self.get_create_pull_request_tool())
            self.mcp.add_tool(self.get_get_pull_request_tool())
            self.mcp.add_tool(self.get_create_release_tool())
            self.mcp.add_tool(self.get_get_repo_tool())
            self.mcp.add_tool(self.get_list_issues_tool())

            mcp_app = self.mcp.http_app(path="/")
            app.mount("/mcp", mcp_app)

        @app.get("/health")
        async def health_check():
            return {"status": "ok", "service": "github-mcp"}

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


def create_github_mcp_server(api_token: str) -> GitHubMCPServer:
    """创建GitHub MCP Server 实例"""
    config = GitHubConfig(api_token=api_token)
    return GitHubMCPServer(config)