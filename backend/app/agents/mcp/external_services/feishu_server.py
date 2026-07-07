"""飞书 MCP Server - 集成飞书开放平台API

提供飞书消息、文档、日历、任务等工具的MCP服务
"""
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from fastapi import FastAPI, HTTPException
import httpx
import json
import logging

logger = logging.getLogger(__name__)

try:
    from fastmcp.server import FastMCP
    HAS_FASTMCP = True
except ImportError:
    HAS_FASTMCP = False
    FastMCP = None


@dataclass
class FeishuConfig:
    app_id: str
    app_secret: str
    base_url: str = "https://open.feishu.cn"


class FeishuMCPServer:
    """飞书 MCP Server 实现"""

    def __init__(self, config: FeishuConfig):
        self.config = config
        self.mcp = None
        self._http_client = httpx.AsyncClient(timeout=30)
        self._access_token = None
        self._token_expires_at = 0

    async def _get_access_token(self) -> str:
        """获取飞书 access_token"""
        import time
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        url = f"{self.config.base_url}/open-apis/auth/v3/tenant_access_token/internal"
        body = {
            "app_id": self.config.app_id,
            "app_secret": self.config.app_secret,
        }

        try:
            response = await self._http_client.post(url, json=body)
            response.raise_for_status()
            data = response.json()

            if data.get("code") == 0:
                self._access_token = data["tenant_access_token"]
                self._token_expires_at = time.time() + data.get("expire", 7200) - 60
                return self._access_token
            else:
                raise HTTPException(status_code=data.get("code", 500), detail=data.get("msg", "获取token失败"))
        except Exception as e:
            logger.error(f"[Feishu] 获取 access_token 失败: {e}")
            raise HTTPException(status_code=500, detail=f"获取飞书token失败: {str(e)}")

    async def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """封装飞书API请求"""
        token = await self._get_access_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        headers["Content-Type"] = "application/json; charset=utf-8"

        url = f"{self.config.base_url}{path}"
        response = await self._http_client.request(method, url, headers=headers, **kwargs)

        try:
            response.raise_for_status()
            data = response.json()
            if data.get("code") != 0:
                raise HTTPException(status_code=data.get("code", 500), detail=data.get("msg", "API调用失败"))
            return data.get("data", {})
        except httpx.HTTPStatusError as e:
            logger.error(f"[Feishu] API请求失败 {method} {url}: {e}")
            raise HTTPException(status_code=response.status_code, detail=str(e))

    def get_send_message_tool(self):
        async def send_message(user_id: Optional[str] = None, email: Optional[str] = None, content: str = "", msg_type: str = "text") -> Dict[str, Any]:
            """发送飞书消息
            
            Args:
                user_id: 用户ID
                email: 用户邮箱
                content: 消息内容
                msg_type: 消息类型
                
            Returns:
                发送结果
            """
            if not content:
                return {"success": False, "error": "内容不能为空"}

            body = {
                "msg_type": msg_type,
                "content": json.dumps({"text": content}) if msg_type == "text" else content,
            }

            if user_id:
                body["user_id"] = user_id
            elif email:
                body["email"] = email
            else:
                return {"success": False, "error": "user_id 或 email 不能为空"}

            try:
                data = await self._request("POST", "/open-apis/im/v1/messages", json=body)
                return {"success": True, "message_id": data.get("message_id")}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return send_message

    def get_create_document_tool(self):
        async def create_document(title: str = "新建文档", folder_token: Optional[str] = None) -> Dict[str, Any]:
            """创建飞书文档
            
            Args:
                title: 文档标题
                folder_token: 文件夹token
                
            Returns:
                创建结果
            """
            body = {"title": title}
            if folder_token:
                body["folder_token"] = folder_token

            try:
                data = await self._request("POST", "/open-apis/docx/v1/documents", json=body)
                return {"success": True, "document_id": data.get("document_id"), "url": data.get("url")}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return create_document

    def get_create_calendar_event_tool(self):
        async def create_calendar_event(summary: str, description: str = "", start_time: str = "", end_time: str = "", attendees: Optional[List[Dict]] = None) -> Dict[str, Any]:
            """创建日历事件
            
            Args:
                summary: 事件标题
                description: 事件描述
                start_time: 开始时间(ISO格式)
                end_time: 结束时间(ISO格式)
                attendees: 参会人员列表
                
            Returns:
                创建结果
            """
            attendees = attendees or []
            if not summary or not start_time or not end_time:
                return {"success": False, "error": "summary、start_time、end_time 不能为空"}

            body = {
                "summary": summary,
                "description": description,
                "start_time": start_time,
                "end_time": end_time,
                "attendees": attendees,
            }

            try:
                data = await self._request("POST", "/open-apis/calendar/v4/events", json=body)
                return {"success": True, "event_id": data.get("event_id"), "url": data.get("url")}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return create_calendar_event

    def get_create_task_tool(self):
        async def create_task(content: str, due_date: Optional[str] = None, priority: str = "medium", assignee_ids: Optional[List[str]] = None) -> Dict[str, Any]:
            """创建飞书任务
            
            Args:
                content: 任务内容
                due_date: 截止日期
                priority: 优先级
                assignee_ids: 负责人ID列表
                
            Returns:
                创建结果
            """
            assignee_ids = assignee_ids or []
            if not content:
                return {"success": False, "error": "content 不能为空"}

            body = {
                "content": content,
                "due_date": due_date,
                "priority": priority,
                "assignee_ids": assignee_ids,
            }

            try:
                data = await self._request("POST", "/open-apis/task/v2/tasks", json=body)
                return {"success": True, "task_id": data.get("task_id")}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return create_task

    def get_search_user_tool(self):
        async def search_user(keyword: str) -> Dict[str, Any]:
            """搜索飞书用户
            
            Args:
                keyword: 搜索关键词
                
            Returns:
                用户列表
            """
            if not keyword:
                return {"success": False, "error": "keyword 不能为空"}

            try:
                data = await self._request("GET", "/open-apis/contact/v3/users", params={"keyword": keyword})
                return {"success": True, "users": data.get("items", [])}
            except HTTPException as e:
                return {"success": False, "error": str(e.detail)}
        return search_user

    def get_app(self) -> FastAPI:
        """获取飞书 MCP Server 的 FastAPI 应用"""
        app = FastAPI(title="飞书 MCP Server", version="1.0.0")

        if HAS_FASTMCP and FastMCP:
            self.mcp = FastMCP(
                name="飞书MCP",
                version="1.0.0",
                instructions="飞书开放平台 MCP 服务，提供消息、文档、日历、任务等功能",
            )

            self.mcp.add_tool(self.get_send_message_tool())
            self.mcp.add_tool(self.get_create_document_tool())
            self.mcp.add_tool(self.get_create_calendar_event_tool())
            self.mcp.add_tool(self.get_create_task_tool())
            self.mcp.add_tool(self.get_search_user_tool())

            mcp_app = self.mcp.http_app(path="/")
            app.mount("/mcp", mcp_app)

        @app.get("/health")
        async def health_check():
            return {"status": "ok", "service": "feishu-mcp"}

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


def create_feishu_mcp_server(app_id: str, app_secret: str) -> FeishuMCPServer:
    """创建飞书 MCP Server 实例"""
    config = FeishuConfig(app_id=app_id, app_secret=app_secret)
    return FeishuMCPServer(config)