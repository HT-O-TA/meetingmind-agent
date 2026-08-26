"""正式工具元数据注册表。"""

from __future__ import annotations

from typing import Dict, List, Optional

from app.agents.tools.tool_metadata import Tool, ToolCategory
from app.core.logger import app_logger


class ToolRegistry:
    """只提供规划与执行主链实际需要的注册和只读查询。"""

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}
        self._load_builtin_tools()
        self._load_enterprise_tools()

    def _load_builtin_tools(self) -> None:
        from app.agents.tools.builtin import get_builtin_tools

        for tool in get_builtin_tools():
            self.register(tool)

    def _load_enterprise_tools(self) -> None:
        from app.agents.tools.enterprise_tools import get_enterprise_tools

        for tool in get_enterprise_tools():
            self.register(tool)

    def register(self, tool: Tool) -> bool:
        tool_id = tool.metadata.tool_id
        if tool_id in self._tools:
            app_logger.debug("[Registry] 更新工具元数据: %s", tool_id)
        self._tools[tool_id] = tool
        return True

    def get(self, tool_id: str) -> Optional[Tool]:
        return self._tools.get(tool_id)

    def get_by_name(self, name: str) -> Optional[Tool]:
        return next((tool for tool in self._tools.values() if tool.metadata.name == name), None)

    def get_all(self) -> List[Tool]:
        return list(self._tools.values())

    def get_by_category(self, category: ToolCategory) -> List[Tool]:
        return [tool for tool in self._tools.values() if tool.metadata.category == category]

    def search(self, query: str, limit: int = 10) -> List[Tool]:
        normalized = query.strip().lower()
        ranked = []
        for tool in self._tools.values():
            metadata = tool.metadata
            haystacks = [metadata.tool_id, metadata.name, metadata.description, *metadata.tags]
            if any(normalized in str(value).lower() for value in haystacks):
                ranked.append(tool)
        return ranked[:limit]


_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
