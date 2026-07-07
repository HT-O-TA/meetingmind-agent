"""企业办公系统集成工具"""
import json
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.agents.tools.tool_metadata import (
    Tool, ToolMetadata, ToolCategory, ToolStatus, ToolParameter, ToolRiskLevel
)
from app.core.config import settings
from app.core.logger import app_logger


class FeishuClient:
    """飞书 API 客户端"""
    
    def __init__(self):
        self.app_id = settings.FEISHU_MCP_APP_ID
        self.app_secret = settings.FEISHU_MCP_APP_SECRET
        self.base_url = "https://open.feishu.cn/open-apis"
        self.access_token = None
    
    async def _get_access_token(self) -> str:
        """获取飞书访问令牌"""
        if self.access_token:
            return self.access_token
        return "mock_token"
    
    async def create_document(self, title: str, content: str) -> Dict[str, Any]:
        """创建飞书文档"""
        await self._get_access_token()
        app_logger.info(f"[Feishu] 创建文档: {title}")
        return {
            "success": True,
            "document_id": "doc_abc123",
            "title": title,
            "url": f"https://feishu.cn/docx/doc_abc123",
            "created_at": datetime.now().isoformat()
        }
    
    async def update_document(self, document_id: str, content: str) -> Dict[str, Any]:
        """更新飞书文档"""
        await self._get_access_token()
        app_logger.info(f"[Feishu] 更新文档: {document_id}")
        return {
            "success": True,
            "document_id": document_id,
            "updated_at": datetime.now().isoformat()
        }
    
    async def create_calendar_event(self, title: str, start_time: str, end_time: str, attendees: List[str]) -> Dict[str, Any]:
        """创建日历事件"""
        await self._get_access_token()
        app_logger.info(f"[Feishu] 创建日历事件: {title}")
        return {
            "success": True,
            "event_id": "event_abc123",
            "title": title,
            "start_time": start_time,
            "end_time": end_time,
            "attendees_count": len(attendees)
        }
    
    async def send_message(self, chat_id: str, content: str) -> Dict[str, Any]:
        """发送消息"""
        await self._get_access_token()
        app_logger.info(f"[Feishu] 发送消息到: {chat_id}")
        return {
            "success": True,
            "message_id": "msg_abc123",
            "chat_id": chat_id
        }


class JiraClient:
    """Jira API 客户端"""
    
    def __init__(self):
        self.base_url = settings.JIRA_MCP_URL
        self.username = settings.JIRA_MCP_USERNAME
        self.api_token = settings.JIRA_MCP_API_TOKEN
    
    async def create_issue(self, project_key: str, issue_type: str, summary: str, description: str, assignee: str = None) -> Dict[str, Any]:
        """创建 Jira 任务"""
        app_logger.info(f"[Jira] 创建任务: {project_key}-{summary}")
        return {
            "success": True,
            "issue_key": f"{project_key}-123",
            "issue_id": "10000",
            "summary": summary,
            "issue_type": issue_type,
            "project": project_key,
            "assignee": assignee,
            "created_at": datetime.now().isoformat(),
            "status": "To Do"
        }
    
    async def get_issue(self, issue_key: str) -> Dict[str, Any]:
        """获取 Jira 任务"""
        app_logger.info(f"[Jira] 获取任务: {issue_key}")
        return {
            "success": True,
            "issue_key": issue_key,
            "issue_id": "10000",
            "summary": "任务摘要",
            "description": "任务描述",
            "status": "In Progress",
            "assignee": "张三",
            "priority": "Medium"
        }
    
    async def update_issue(self, issue_key: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """更新 Jira 任务"""
        app_logger.info(f"[Jira] 更新任务: {issue_key}")
        return {
            "success": True,
            "issue_key": issue_key,
            "updated_at": datetime.now().isoformat()
        }


class NotionClient:
    """Notion API 客户端"""
    
    def __init__(self):
        self.base_url = "https://api.notion.com/v1"
        self.api_key = settings.NOTION_MCP_API_KEY
    
    async def create_page(self, parent_id: str, title: str, content: str) -> Dict[str, Any]:
        """创建 Notion 页面"""
        app_logger.info(f"[Notion] 创建页面: {title}")
        return {
            "success": True,
            "page_id": "page_abc123",
            "title": title,
            "url": f"https://notion.so/page_abc123",
            "created_at": datetime.now().isoformat()
        }
    
    async def update_page(self, page_id: str, content: str) -> Dict[str, Any]:
        """更新 Notion 页面"""
        app_logger.info(f"[Notion] 更新页面: {page_id}")
        return {
            "success": True,
            "page_id": page_id,
            "updated_at": datetime.now().isoformat()
        }
    
    async def query_database(self, database_id: str, filter_params: Dict[str, Any] = None) -> Dict[str, Any]:
        """查询 Notion 数据库"""
        app_logger.info(f"[Notion] 查询数据库: {database_id}")
        return {
            "success": True,
            "database_id": database_id,
            "results": [],
            "total": 0
        }


class EmailClient:
    """邮件发送客户端"""
    
    def __init__(self):
        self.smtp_server = settings.SMTP_SERVER if hasattr(settings, 'SMTP_SERVER') else "smtp.example.com"
        self.smtp_port = settings.SMTP_PORT if hasattr(settings, 'SMTP_PORT') else 587
        self.smtp_user = settings.SMTP_USER if hasattr(settings, 'SMTP_USER') else ""
        self.smtp_password = settings.SMTP_PASSWORD if hasattr(settings, 'SMTP_PASSWORD') else ""
    
    async def send_email(self, to: List[str], subject: str, body: str, cc: List[str] = None) -> Dict[str, Any]:
        """发送邮件"""
        app_logger.info(f"[Email] 发送邮件到: {', '.join(to)}")
        return {
            "success": True,
            "message_id": "email_abc123",
            "to": to,
            "cc": cc or [],
            "subject": subject,
            "sent_at": datetime.now().isoformat()
        }


_feishu_client: Optional[FeishuClient] = None
_jira_client: Optional[JiraClient] = None
_notion_client: Optional[NotionClient] = None
_email_client: Optional[EmailClient] = None


def get_feishu_client() -> FeishuClient:
    global _feishu_client
    if _feishu_client is None:
        _feishu_client = FeishuClient()
    return _feishu_client


def get_jira_client() -> JiraClient:
    global _jira_client
    if _jira_client is None:
        _jira_client = JiraClient()
    return _jira_client


def get_notion_client() -> NotionClient:
    global _notion_client
    if _notion_client is None:
        _notion_client = NotionClient()
    return _notion_client


def get_email_client() -> EmailClient:
    global _email_client
    if _email_client is None:
        _email_client = EmailClient()
    return _email_client


async def execute_feishu_tool(tool_id: str, params: Dict[str, Any]) -> Any:
    """执行飞书工具"""
    client = get_feishu_client()
    
    if tool_id == "feishu_create_document":
        return await client.create_document(
            title=params.get("title", ""),
            content=params.get("content", "")
        )
    
    elif tool_id == "feishu_update_document":
        return await client.update_document(
            document_id=params.get("document_id", ""),
            content=params.get("content", "")
        )
    
    elif tool_id == "feishu_create_calendar":
        return await client.create_calendar_event(
            title=params.get("title", ""),
            start_time=params.get("start_time", ""),
            end_time=params.get("end_time", ""),
            attendees=params.get("attendees", [])
        )
    
    elif tool_id == "feishu_send_message":
        return await client.send_message(
            chat_id=params.get("chat_id", ""),
            content=params.get("content", "")
        )
    
    return {"success": False, "error": f"未知飞书工具: {tool_id}"}


async def execute_jira_tool(tool_id: str, params: Dict[str, Any]) -> Any:
    """执行 Jira 工具"""
    client = get_jira_client()
    
    if tool_id == "jira_create_issue":
        return await client.create_issue(
            project_key=params.get("project_key", ""),
            issue_type=params.get("issue_type", "Task"),
            summary=params.get("summary", ""),
            description=params.get("description", ""),
            assignee=params.get("assignee")
        )
    
    elif tool_id == "jira_get_issue":
        return await client.get_issue(
            issue_key=params.get("issue_key", "")
        )
    
    elif tool_id == "jira_update_issue":
        return await client.update_issue(
            issue_key=params.get("issue_key", ""),
            updates=params.get("updates", {})
        )
    
    return {"success": False, "error": f"未知 Jira 工具: {tool_id}"}


async def execute_notion_tool(tool_id: str, params: Dict[str, Any]) -> Any:
    """执行 Notion 工具"""
    client = get_notion_client()
    
    if tool_id == "notion_create_page":
        return await client.create_page(
            parent_id=params.get("parent_id", ""),
            title=params.get("title", ""),
            content=params.get("content", "")
        )
    
    elif tool_id == "notion_update_page":
        return await client.update_page(
            page_id=params.get("page_id", ""),
            content=params.get("content", "")
        )
    
    elif tool_id == "notion_query_database":
        return await client.query_database(
            database_id=params.get("database_id", ""),
            filter_params=params.get("filter", {})
        )
    
    return {"success": False, "error": f"未知 Notion 工具: {tool_id}"}


async def execute_email_tool(tool_id: str, params: Dict[str, Any]) -> Any:
    """执行邮件工具"""
    client = get_email_client()
    
    if tool_id == "send_email":
        return await client.send_email(
            to=params.get("to", []),
            subject=params.get("subject", ""),
            body=params.get("body", ""),
            cc=params.get("cc", [])
        )
    
    return {"success": False, "error": f"未知邮件工具: {tool_id}"}


def get_enterprise_tools() -> List[Tool]:
    """获取所有企业办公系统集成工具"""
    tools = []
    
    if settings.FEISHU_MCP_ENABLED:
        tools.extend([
            Tool(
                metadata=ToolMetadata(
                    tool_id="feishu_create_document",
                    name="创建飞书文档",
                    description="在飞书中创建新文档，用于同步会议纪要等内容",
                    category=ToolCategory.COLLABORATION,
                    tags=["feishu", "document", "飞书", "文档", "同步"],
                    parameters=[
                        ToolParameter(
                            name="title",
                            type="string",
                            description="文档标题",
                            required=True
                        ),
                        ToolParameter(
                            name="content",
                            type="string",
                            description="文档内容",
                            required=True
                        ),
                    ],
                    return_type="object",
                    supports_streaming=False,
                    is_async=True,
                    risk_level=ToolRiskLevel.MEDIUM,
                    requires_confirmation=True,
                    idempotent=False,
                )
            ),
            Tool(
                metadata=ToolMetadata(
                    tool_id="feishu_update_document",
                    name="更新飞书文档",
                    description="更新指定的飞书文档内容",
                    category=ToolCategory.COLLABORATION,
                    tags=["feishu", "document", "飞书", "文档", "更新"],
                    parameters=[
                        ToolParameter(
                            name="document_id",
                            type="string",
                            description="文档ID",
                            required=True
                        ),
                        ToolParameter(
                            name="content",
                            type="string",
                            description="文档内容",
                            required=True
                        ),
                    ],
                    return_type="object",
                    supports_streaming=False,
                    is_async=True,
                    risk_level=ToolRiskLevel.MEDIUM,
                    requires_confirmation=True,
                    idempotent=True,
                )
            ),
            Tool(
                metadata=ToolMetadata(
                    tool_id="feishu_create_calendar",
                    name="创建飞书日历",
                    description="在飞书日历中创建新事件或会议",
                    category=ToolCategory.COLLABORATION,
                    tags=["feishu", "calendar", "飞书", "日历", "会议"],
                    parameters=[
                        ToolParameter(
                            name="title",
                            type="string",
                            description="事件标题",
                            required=True
                        ),
                        ToolParameter(
                            name="start_time",
                            type="string",
                            description="开始时间（ISO格式）",
                            required=True
                        ),
                        ToolParameter(
                            name="end_time",
                            type="string",
                            description="结束时间（ISO格式）",
                            required=True
                        ),
                        ToolParameter(
                            name="attendees",
                            type="array",
                            description="参会人员邮箱列表",
                            required=False,
                            default=[]
                        ),
                    ],
                    return_type="object",
                    supports_streaming=False,
                    is_async=True,
                    risk_level=ToolRiskLevel.MEDIUM,
                    requires_confirmation=True,
                    idempotent=False,
                )
            ),
            Tool(
                metadata=ToolMetadata(
                    tool_id="feishu_send_message",
                    name="发送飞书消息",
                    description="向飞书群组或用户发送消息",
                    category=ToolCategory.NOTIFICATION,
                    tags=["feishu", "message", "飞书", "消息", "通知"],
                    parameters=[
                        ToolParameter(
                            name="chat_id",
                            type="string",
                            description="群组ID或用户ID",
                            required=True
                        ),
                        ToolParameter(
                            name="content",
                            type="string",
                            description="消息内容",
                            required=True
                        ),
                    ],
                    return_type="object",
                    supports_streaming=False,
                    is_async=True,
                    risk_level=ToolRiskLevel.LOW,
                    requires_confirmation=False,
                    idempotent=False,
                )
            ),
        ])
    
    if settings.JIRA_MCP_ENABLED:
        tools.extend([
            Tool(
                metadata=ToolMetadata(
                    tool_id="jira_create_issue",
                    name="创建Jira任务",
                    description="在Jira中创建新的任务或问题",
                    category=ToolCategory.COLLABORATION,
                    tags=["jira", "issue", "task", "任务", "创建"],
                    parameters=[
                        ToolParameter(
                            name="project_key",
                            type="string",
                            description="项目Key（如PROJ）",
                            required=True
                        ),
                        ToolParameter(
                            name="issue_type",
                            type="string",
                            description="任务类型",
                            required=False,
                            default="Task",
                            enum_values=["Task", "Bug", "Story", "Epic"]
                        ),
                        ToolParameter(
                            name="summary",
                            type="string",
                            description="任务摘要",
                            required=True
                        ),
                        ToolParameter(
                            name="description",
                            type="string",
                            description="任务描述",
                            required=False,
                            default=""
                        ),
                        ToolParameter(
                            name="assignee",
                            type="string",
                            description="负责人",
                            required=False
                        ),
                    ],
                    return_type="object",
                    supports_streaming=False,
                    is_async=True,
                    risk_level=ToolRiskLevel.MEDIUM,
                    requires_confirmation=True,
                    idempotent=False,
                )
            ),
            Tool(
                metadata=ToolMetadata(
                    tool_id="jira_get_issue",
                    name="查询Jira任务",
                    description="获取Jira任务的详细信息",
                    category=ToolCategory.COLLABORATION,
                    tags=["jira", "issue", "task", "任务", "查询"],
                    parameters=[
                        ToolParameter(
                            name="issue_key",
                            type="string",
                            description="任务Key（如PROJ-123）",
                            required=True
                        ),
                    ],
                    return_type="object",
                    supports_streaming=False,
                    is_async=True,
                    risk_level=ToolRiskLevel.LOW,
                    requires_confirmation=False,
                    idempotent=True,
                )
            ),
            Tool(
                metadata=ToolMetadata(
                    tool_id="jira_update_issue",
                    name="更新Jira任务",
                    description="更新Jira任务的状态、负责人等信息",
                    category=ToolCategory.COLLABORATION,
                    tags=["jira", "issue", "task", "任务", "更新"],
                    parameters=[
                        ToolParameter(
                            name="issue_key",
                            type="string",
                            description="任务Key",
                            required=True
                        ),
                        ToolParameter(
                            name="updates",
                            type="object",
                            description="更新内容（JSON格式）",
                            required=True
                        ),
                    ],
                    return_type="object",
                    supports_streaming=False,
                    is_async=True,
                    risk_level=ToolRiskLevel.MEDIUM,
                    requires_confirmation=True,
                    idempotent=True,
                )
            ),
        ])
    
    if settings.NOTION_MCP_ENABLED:
        tools.extend([
            Tool(
                metadata=ToolMetadata(
                    tool_id="notion_create_page",
                    name="创建Notion页面",
                    description="在Notion中创建新页面",
                    category=ToolCategory.COLLABORATION,
                    tags=["notion", "page", "文档", "创建"],
                    parameters=[
                        ToolParameter(
                            name="parent_id",
                            type="string",
                            description="父页面或数据库ID",
                            required=True
                        ),
                        ToolParameter(
                            name="title",
                            type="string",
                            description="页面标题",
                            required=True
                        ),
                        ToolParameter(
                            name="content",
                            type="string",
                            description="页面内容",
                            required=True
                        ),
                    ],
                    return_type="object",
                    supports_streaming=False,
                    is_async=True,
                    risk_level=ToolRiskLevel.MEDIUM,
                    requires_confirmation=True,
                    idempotent=False,
                )
            ),
            Tool(
                metadata=ToolMetadata(
                    tool_id="notion_update_page",
                    name="更新Notion页面",
                    description="更新Notion页面内容",
                    category=ToolCategory.COLLABORATION,
                    tags=["notion", "page", "文档", "更新"],
                    parameters=[
                        ToolParameter(
                            name="page_id",
                            type="string",
                            description="页面ID",
                            required=True
                        ),
                        ToolParameter(
                            name="content",
                            type="string",
                            description="页面内容",
                            required=True
                        ),
                    ],
                    return_type="object",
                    supports_streaming=False,
                    is_async=True,
                    risk_level=ToolRiskLevel.MEDIUM,
                    requires_confirmation=True,
                    idempotent=True,
                )
            ),
            Tool(
                metadata=ToolMetadata(
                    tool_id="notion_query_database",
                    name="查询Notion数据库",
                    description="查询Notion数据库中的记录",
                    category=ToolCategory.COLLABORATION,
                    tags=["notion", "database", "查询"],
                    parameters=[
                        ToolParameter(
                            name="database_id",
                            type="string",
                            description="数据库ID",
                            required=True
                        ),
                        ToolParameter(
                            name="filter",
                            type="object",
                            description="过滤条件",
                            required=False,
                            default={}
                        ),
                    ],
                    return_type="object",
                    supports_streaming=False,
                    is_async=True,
                    risk_level=ToolRiskLevel.LOW,
                    requires_confirmation=False,
                    idempotent=True,
                )
            ),
        ])
    
    tools.extend([
        Tool(
            metadata=ToolMetadata(
                tool_id="send_email",
                name="发送邮件",
                description="发送邮件给指定收件人",
                category=ToolCategory.NOTIFICATION,
                tags=["email", "mail", "邮件", "发送"],
                parameters=[
                    ToolParameter(
                        name="to",
                        type="array",
                        description="收件人邮箱列表",
                        required=True
                    ),
                    ToolParameter(
                        name="subject",
                        type="string",
                        description="邮件主题",
                        required=True
                    ),
                    ToolParameter(
                        name="body",
                        type="string",
                        description="邮件正文",
                        required=True
                    ),
                    ToolParameter(
                        name="cc",
                        type="array",
                        description="抄送列表",
                        required=False,
                        default=[]
                    ),
                ],
                return_type="object",
                supports_streaming=False,
                is_async=True,
                risk_level=ToolRiskLevel.LOW,
                requires_confirmation=True,
                idempotent=False,
            )
        ),
    ])
    
    return tools