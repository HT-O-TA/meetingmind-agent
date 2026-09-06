"""真实企业工具适配器。

阶段 2 只保留一个正式外部写目标：Jira Cloud REST API v3。未完成真实接入的飞书、Notion 和邮件工具不再注册，避免把 mock ID 当成外部执行成功。
"""
from __future__ import annotations

import asyncio
import time
import re
from email.utils import parsedate_to_datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from app.agents.tools.tool_metadata import (
    Tool,
    ToolCategory,
    ToolMetadata,
    ToolParameter,
    ToolRiskLevel,
)
from app.core.config import settings
from app.core.logger import app_logger
from app.core.secret_provider import get_secret_provider


class JiraConfigurationError(RuntimeError):
    """Jira 配置缺失或不安全。"""


class JiraAPIError(RuntimeError):
    """带稳定分类的 Jira 上游错误，供审计与重试策略使用。"""

    def __init__(
        self,
        message: str,
        *,
        category: str,
        status_code: Optional[int] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.status_code = status_code
        self.retryable = retryable


class JiraClient:
    """最小 Jira Cloud REST v3 客户端。

    创建 Issue 是非幂等外部写，发生超时或 5xx 时不会自动重试；GET/PUT 可在
    429/5xx 上做有界重试。测试可注入 MockTransport 对应的 AsyncClient。
    """

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        api_token: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        max_retries: Optional[int] = None,
        max_retry_delay: Optional[float] = None,
    ) -> None:
        self.base_url = (base_url if base_url is not None else settings.JIRA_URL).rstrip("/")
        self.username = username if username is not None else settings.JIRA_USERNAME
        self.api_token = (
            api_token
            if api_token is not None
            else get_secret_provider().get("JIRA_API_TOKEN")
            or settings.JIRA_API_TOKEN
        )
        self.max_retries = max_retries if max_retries is not None else settings.JIRA_MAX_RETRIES
        self.max_retry_delay = (
            max_retry_delay
            if max_retry_delay is not None
            else settings.JIRA_MAX_RETRY_DELAY_SECONDS
        )
        self._sleep = sleep
        self._client = http_client
        self._transport = transport

    def _validate_configuration(self) -> None:
        missing = [
            name
            for name, value in (
                ("JIRA_URL", self.base_url),
                ("JIRA_USERNAME", self.username),
                ("JIRA_API_TOKEN", self.api_token),
            )
            if not value
        ]
        if missing:
            raise JiraConfigurationError(f"Jira 配置缺失: {', '.join(missing)}")

        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise JiraConfigurationError("JIRA_URL 必须是合法的 HTTPS Jira 站点地址")
        if parsed.username or parsed.password:
            raise JiraConfigurationError("JIRA_URL 不得包含用户名或密码")

    def _get_client(self) -> httpx.AsyncClient:
        self._validate_configuration()
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                auth=(self.username, self.api_token),
                timeout=settings.JIRA_HTTP_TIMEOUT_SECONDS,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                transport=self._transport,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                delay = float(retry_after)
            except ValueError:
                try:
                    parsed = parsedate_to_datetime(retry_after)
                    delay = max(0.0, parsed.timestamp() - time.time())
                except (TypeError, ValueError, OverflowError):
                    delay = 2**attempt
        else:
            delay = 2**attempt
        return min(max(0.0, delay), float(self.max_retry_delay))

    @staticmethod
    def _error_from_response(response: httpx.Response) -> JiraAPIError:
        categories = {
            400: "invalid_request",
            401: "authentication",
            403: "permission",
            404: "not_found",
            409: "conflict",
            429: "rate_limited",
        }
        category = categories.get(response.status_code, "upstream")
        try:
            body = response.json()
            detail = body.get("errorMessages") or body.get("errors") or body
        except (ValueError, AttributeError):
            detail = response.text[:500]
        return JiraAPIError(
            f"Jira API 返回 {response.status_code}: {detail}",
            category=category,
            status_code=response.status_code,
            retryable=response.status_code == 429 or response.status_code >= 500,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
        idempotent: bool,
    ) -> httpx.Response:
        client = self._get_client()
        attempts = 1 + (self.max_retries if idempotent else 0)

        for attempt in range(attempts):
            try:
                response = await client.request(method, path, json=json_body)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if idempotent and attempt + 1 < attempts:
                    await self._sleep(min(2**attempt, self.max_retry_delay))
                    continue
                raise JiraAPIError(
                    f"Jira 网络请求失败: {exc.__class__.__name__}",
                    category="timeout" if isinstance(exc, httpx.TimeoutException) else "network",
                    retryable=idempotent,
                ) from exc

            if response.status_code < 400:
                return response

            error = self._error_from_response(response)
            if idempotent and error.retryable and attempt + 1 < attempts:
                await self._sleep(self._retry_delay(response, attempt))
                continue
            raise error

        raise JiraAPIError("Jira 请求未完成", category="upstream", retryable=idempotent)

    async def create_issue(
        self,
        project_key: str,
        issue_type: str,
        summary: str,
        description: str = "",
        assignee: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", project_key or ""):
            raise JiraAPIError("Jira project_key 格式非法", category="invalid_request")
        if not summary or len(summary) > 255:
            raise JiraAPIError("Jira summary 必须为 1-255 个字符", category="invalid_request")
        fields: Dict[str, Any] = {
            "project": {"key": project_key},
            "issuetype": {"name": issue_type},
            "summary": summary,
        }
        if description:
            fields["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}],
                    }
                ],
            }
        if assignee:
            fields["assignee"] = {"accountId": assignee}

        response = await self._request(
            "POST",
            "/rest/api/3/issue",
            json_body={"fields": fields},
            idempotent=False,
        )
        payload = response.json()
        app_logger.info("[Jira] Issue 创建成功: %s", payload.get("key"))
        return {
            "success": True,
            "issue_id": payload.get("id"),
            "issue_key": payload.get("key"),
            "self": payload.get("self"),
            "external_id": payload.get("key") or payload.get("id"),
        }

    async def get_issue(self, issue_key: str) -> Dict[str, Any]:
        self._validate_issue_key(issue_key)
        response = await self._request(
            "GET",
            f"/rest/api/3/issue/{issue_key}",
            idempotent=True,
        )
        payload = response.json()
        return {
            "success": True,
            "issue_id": payload.get("id"),
            "issue_key": payload.get("key"),
            "fields": payload.get("fields", {}),
            "external_id": payload.get("key") or payload.get("id"),
        }

    async def update_issue(self, issue_key: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        self._validate_issue_key(issue_key)
        if not updates:
            raise JiraAPIError("Jira updates 不能为空", category="invalid_request")
        await self._request(
            "PUT",
            f"/rest/api/3/issue/{issue_key}",
            json_body={"fields": updates},
            idempotent=True,
        )
        return {"success": True, "issue_key": issue_key, "external_id": issue_key}

    @staticmethod
    def _validate_issue_key(issue_key: str) -> None:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*-[1-9][0-9]*", issue_key or ""):
            raise JiraAPIError("Jira issue_key 格式非法", category="invalid_request")


_jira_client: Optional[JiraClient] = None


def get_jira_client() -> JiraClient:
    global _jira_client
    if _jira_client is None:
        _jira_client = JiraClient()
    return _jira_client


def reset_jira_client() -> None:
    """清除进程缓存；主要供配置热更新和隔离测试使用。"""
    global _jira_client
    _jira_client = None


async def execute_jira_tool(tool_id: str, params: Dict[str, Any]) -> Any:
    client = get_jira_client()
    if tool_id == "jira_create_issue":
        return await client.create_issue(
            project_key=params["project_key"],
            issue_type=params.get("issue_type", "Task"),
            summary=params["summary"],
            description=params.get("description", ""),
            assignee=params.get("assignee"),
        )
    if tool_id == "jira_get_issue":
        return await client.get_issue(issue_key=params["issue_key"])
    if tool_id == "jira_update_issue":
        return await client.update_issue(
            issue_key=params["issue_key"],
            updates=params["updates"],
        )
    raise ValueError(f"未知 Jira 工具: {tool_id}")


def _jira_metadata(
    *,
    tool_id: str,
    name: str,
    description: str,
    tags: List[str],
    parameters: List[ToolParameter],
    risk_level: ToolRiskLevel,
    operation_type: str,
    requires_confirmation: bool,
    idempotent: bool,
) -> ToolMetadata:
    external_effect = operation_type != "read"
    return ToolMetadata(
        tool_id=tool_id,
        name=name,
        description=description,
        category=ToolCategory.COLLABORATION,
        tags=tags,
        parameters=parameters,
        return_type="object",
        is_async=True,
        requires_auth=True,
        cacheable=False,
        risk_level=risk_level,
        risk_reason=(
            "会修改外部 Jira 数据，必须由当前用户明确确认"
            if external_effect
            else "只读查询，不修改 Jira 数据"
        ),
        operation_type=operation_type,
        reversible=False if external_effect else True,
        external_effect=external_effect,
        requires_confirmation=requires_confirmation,
        idempotent=idempotent,
    )


def get_enterprise_tools() -> List[Tool]:
    """只注册已经实现真实适配器且由配置显式开启的企业工具。"""
    if not settings.JIRA_ENABLED:
        return []

    return [
        Tool(
            metadata=_jira_metadata(
                tool_id="jira_create_issue",
                name="创建 Jira Issue",
                description="通过 Jira Cloud REST API v3 创建 Issue",
                tags=["jira", "issue", "task", "任务", "创建"],
                parameters=[
                    ToolParameter("project_key", "string", "Jira 项目 Key", required=True),
                    ToolParameter(
                        "issue_type",
                        "string",
                        "Issue 类型",
                        required=False,
                        default="Task",
                        enum_values=["Task", "Bug", "Story", "Epic"],
                    ),
                    ToolParameter("summary", "string", "Issue 摘要", required=True),
                    ToolParameter("description", "string", "Issue 描述", required=False, default=""),
                    ToolParameter(
                        "assignee",
                        "string",
                        "Jira Cloud 负责人 accountId",
                        required=False,
                    ),
                ],
                risk_level=ToolRiskLevel.MEDIUM,
                operation_type="external",
                requires_confirmation=True,
                idempotent=False,
            )
        ),
        Tool(
            metadata=_jira_metadata(
                tool_id="jira_get_issue",
                name="查询 Jira Issue",
                description="通过 Jira Cloud REST API v3 查询 Issue",
                tags=["jira", "issue", "task", "任务", "查询"],
                parameters=[ToolParameter("issue_key", "string", "Issue Key", required=True)],
                risk_level=ToolRiskLevel.LOW,
                operation_type="read",
                requires_confirmation=False,
                idempotent=True,
            )
        ),
        Tool(
            metadata=_jira_metadata(
                tool_id="jira_update_issue",
                name="更新 Jira Issue",
                description="通过 Jira Cloud REST API v3 更新 Issue 字段",
                tags=["jira", "issue", "task", "任务", "更新"],
                parameters=[
                    ToolParameter("issue_key", "string", "Issue Key", required=True),
                    ToolParameter("updates", "object", "Jira fields 更新对象", required=True),
                ],
                risk_level=ToolRiskLevel.MEDIUM,
                operation_type="external",
                requires_confirmation=True,
                idempotent=True,
            )
        ),
    ]
