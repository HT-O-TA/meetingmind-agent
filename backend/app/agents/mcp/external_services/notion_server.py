"""Notion MCP Server - 集成Notion API

提供Notion页面、数据库、块操作等工具的MCP服务
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
class NotionConfig:
    api_key: str
    base_url: str = "https://api.notion.com"


class NotionMCPServer:
    """Notion MCP Server 实现"""

    def __init__(self, config: NotionConfig):
        self.config = config
        self.mcp = None
        self._http_client = httpx.AsyncClient(timeout=30)

    async def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """封装Notion API请求"""
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.config.api_key}"
        headers["Notion-Version"] = "2022-06-28"
        headers["Content-Type"] = "application/json"

        url = f"{self.config.base_url}{path}"
        response = await self._http_client.request(method, url, headers=headers, **kwargs)

        try:
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"[Notion] API请求失败 {method} {url}: {e}")
            try:
                error_data = response.json()
                detail = error_data.get("message", str(e))
            except:
                detail = str(e)
            raise HTTPException(status_code=response.status_code, detail=detail)

    def get_create_page_tool(self):
        async def create_page(parent_page_id: Optional[str] = None, parent_database_id: Optional[str] = None, title: str = "新建页面", content: Optional[List[Dict]] = None) -> Dict[str, Any]:
            """创建Notion页面
            
            Args:
                parent_page_id: 父页面ID
                parent_database_id: 父数据库ID
                title: 页面标题
                content: 页面内容块
                
            Returns:
                创建结果
            """
            content = content or []
            if not parent_page_id and not parent_database_id:
                return {"success": False, "error": "parent_page_id 或 parent_database_id 不能为空"}

            parent = {}
            if parent_page_id:
                parent = {"page_id": parent_page_id}
            elif parent_database_id:
                parent = {"database_id": parent_database_id}

            body = {
                "parent": parent,
                "properties": {
                    "title": [
                        {
                            "type": "text",
                            "text": {"content": title}
                        }
                    ]
                },
            }

            if content:
                body["children"] = content

            try:
                data = await self._request("POST", "/v1/pages", json=body)
                return {"success": True, "page_id": data.get("id"), "url": data.get("url")}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return create_page

    def get_get_page_tool(self):
        async def get_page(page_id: str) -> Dict[str, Any]:
            """获取Notion页面详情
            
            Args:
                page_id: 页面ID
                
            Returns:
                页面详情
            """
            if not page_id:
                return {"success": False, "error": "page_id 不能为空"}

            try:
                data = await self._request("GET", f"/v1/pages/{page_id}")
                return {"success": True, "page": data}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return get_page

    def get_update_page_tool(self):
        async def update_page(page_id: str, properties: Optional[Dict] = None, archived: Optional[bool] = None) -> Dict[str, Any]:
            """更新Notion页面
            
            Args:
                page_id: 页面ID
                properties: 页面属性
                archived: 是否归档
                
            Returns:
                更新结果
            """
            if not page_id:
                return {"success": False, "error": "page_id 不能为空"}

            body = {}
            if properties is not None:
                body["properties"] = properties
            if archived is not None:
                body["archived"] = archived

            try:
                data = await self._request("PATCH", f"/v1/pages/{page_id}", json=body)
                return {"success": True, "page": data}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return update_page

    def get_query_database_tool(self):
        async def query_database(database_id: str, filter: Optional[Dict] = None, sorts: Optional[List[Dict]] = None, page_size: int = 100, start_cursor: Optional[str] = None) -> Dict[str, Any]:
            """查询Notion数据库
            
            Args:
                database_id: 数据库ID
                filter: 过滤条件
                sorts: 排序条件
                page_size: 每页大小
                start_cursor: 起始游标
                
            Returns:
                查询结果
            """
            if not database_id:
                return {"success": False, "error": "database_id 不能为空"}

            body = {}
            if filter is not None:
                body["filter"] = filter
            if sorts is not None:
                body["sorts"] = sorts
            body["page_size"] = page_size
            if start_cursor:
                body["start_cursor"] = start_cursor

            try:
                data = await self._request("POST", f"/v1/databases/{database_id}/query", json=body)
                return {"success": True, "results": data.get("results", []), "has_more": data.get("has_more", False), "next_cursor": data.get("next_cursor")}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return query_database

    def get_append_block_tool(self):
        async def append_block(block_id: str, children: List[Dict]) -> Dict[str, Any]:
            """追加块内容
            
            Args:
                block_id: 块ID
                children: 子块内容
                
            Returns:
                添加结果
            """
            if not block_id or not children:
                return {"success": False, "error": "block_id 和 children 不能为空"}

            try:
                data = await self._request("PATCH", f"/v1/blocks/{block_id}/children", json={"children": children})
                return {"success": True, "results": data.get("results", [])}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return append_block

    def get_search_tool(self):
        async def search(query: str = "", filter: Optional[Dict] = None, sort: Optional[Dict] = None, page_size: int = 20) -> Dict[str, Any]:
            """搜索Notion内容
            
            Args:
                query: 搜索关键词
                filter: 过滤条件
                sort: 排序条件
                page_size: 返回数量
                
            Returns:
                搜索结果
            """
            body = {"query": query, "page_size": page_size}
            if filter is not None:
                body["filter"] = filter
            if sort is not None:
                body["sort"] = sort

            try:
                data = await self._request("POST", "/v1/search", json=body)
                return {"success": True, "results": data.get("results", []), "has_more": data.get("has_more", False)}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return search

    def get_app(self) -> FastAPI:
        """获取Notion MCP Server 的 FastAPI 应用"""
        app = FastAPI(title="Notion MCP Server", version="1.0.0")

        if HAS_FASTMCP and FastMCP:
            self.mcp = FastMCP(
                name="NotionMCP",
                version="1.0.0",
                instructions="Notion MCP 服务，提供页面、数据库、块操作等功能",
            )

            self.mcp.add_tool(self.get_create_page_tool())
            self.mcp.add_tool(self.get_get_page_tool())
            self.mcp.add_tool(self.get_update_page_tool())
            self.mcp.add_tool(self.get_query_database_tool())
            self.mcp.add_tool(self.get_append_block_tool())
            self.mcp.add_tool(self.get_search_tool())

            mcp_app = self.mcp.http_app(path="/")
            app.mount("/mcp", mcp_app)

        @app.get("/health")
        async def health_check():
            return {"status": "ok", "service": "notion-mcp"}

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


def create_notion_mcp_server(api_key: str) -> NotionMCPServer:
    """创建Notion MCP Server 实例"""
    config = NotionConfig(api_key=api_key)
    return NotionMCPServer(config)