"""无需外部凭据的文档工具元数据。"""

from typing import List

from app.agents.tools.tool_metadata import (
    Tool,
    ToolCategory,
    ToolMetadata,
    ToolParameter,
    ToolRiskLevel,
)


def _read_tool(
    tool_id: str,
    name: str,
    description: str,
    category: ToolCategory,
    tags: List[str],
    parameters: List[ToolParameter],
    return_type: str,
) -> Tool:
    return Tool(
        metadata=ToolMetadata(
            tool_id=tool_id,
            name=name,
            description=description,
            category=category,
            tags=tags,
            parameters=parameters,
            return_type=return_type,
            is_async=True,
            risk_level=ToolRiskLevel.LOW,
            requires_confirmation=False,
            idempotent=True,
        )
    )


def get_builtin_tools() -> List[Tool]:
    """只注册执行器有真实实现的文档读取工具。"""
    return [
        _read_tool(
            "get_document_content",
            "获取文档内容",
            "根据文档 ID 获取正文",
            ToolCategory.DOCUMENT,
            ["document", "content", "文档", "正文"],
            [ToolParameter("document_id", "integer", "文档 ID", required=True)],
            "object",
        ),
        _read_tool(
            "search_document",
            "搜索文档",
            "在允许访问的文档中检索相关片段",
            ToolCategory.SEARCH,
            ["document", "search", "文档", "检索"],
            [
                ToolParameter("query", "string", "检索问题", required=True),
                ToolParameter("document_ids", "array", "限定文档 ID", required=False),
                ToolParameter("top_k", "integer", "返回数量", required=False, default=5),
            ],
            "array",
        ),
    ]
