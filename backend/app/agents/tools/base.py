"""Agent Tool Calling - 工具调用系统"""
import json
import asyncio
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from abc import ABC, abstractmethod


class ToolCategory(Enum):
    """工具类别"""
    SEARCH = "search"           # 检索类
    RETRIEVE = "retrieve"       # 读取类
    GENERATE = "generate"       # 生成类
    EXTRACT = "extract"         # 抽取类
    FORMAT = "format"           # 格式化类
    UTILITY = "utility"         # 工具类


class ToolStatus(Enum):
    """工具执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class ToolParameter:
    """工具参数定义"""
    name: str
    description: str
    type: str  # "string", "number", "boolean", "array", "object"
    required: bool = True
    default: Any = None
    enum: List[Any] = field(default_factory=list)


@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    description: str
    category: ToolCategory
    parameters: List[ToolParameter] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    timeout: int = 30  # 超时时间（秒）
    
    def to_openai_format(self) -> Dict[str, Any]:
        """转换为 OpenAI 函数调用格式"""
        properties = {}
        required = []
        
        for param in self.parameters:
            param_dict = {"type": param.type, "description": param.description}
            if param.enum:
                param_dict["enum"] = param.enum
            if param.default is not None:
                param_dict["default"] = param.default
            properties[param.name] = param_dict
            if param.required:
                required.append(param.name)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }


@dataclass
class ToolCall:
    """工具调用记录"""
    tool_name: str
    arguments: Dict[str, Any]
    status: ToolStatus = ToolStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    execution_time: float = 0.0


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    tool_name: str
    result: Any
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseTool(ABC):
    """工具基类"""
    
    def __init__(self):
        self.definition = self.get_definition()
    
    @abstractmethod
    def get_definition(self) -> ToolDefinition:
        """获取工具定义"""
        pass
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """执行工具"""
        pass
    
    async def run(self, arguments: Dict[str, Any]) -> ToolResult:
        """运行工具（带计时）"""
        start = datetime.now()
        try:
            result = await self.execute(**arguments)
            end = datetime.now()
            result.execution_time = (end - start).total_seconds()
            result.tool_name = self.definition.name
            return result
        except Exception as e:
            end = datetime.now()
            return ToolResult(
                success=False,
                tool_name=self.definition.name,
                result=None,
                error=str(e),
                execution_time=(end - start).total_seconds()
            )


class ToolRegistry:
    """工具注册表"""
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._categories: Dict[ToolCategory, List[str]] = {
            cat: [] for cat in ToolCategory
        }
    
    def register(self, tool: BaseTool):
        """注册工具"""
        self._tools[tool.definition.name] = tool
        self._categories[tool.definition.category].append(tool.definition.name)
    
    def get(self, name: str) -> Optional[BaseTool]:
        """获取工具"""
        return self._tools.get(name)
    
    def get_by_category(self, category: ToolCategory) -> List[BaseTool]:
        """按类别获取工具"""
        tool_names = self._categories.get(category, [])
        return [self._tools[name] for name in tool_names if name in self._tools]
    
    def list_all(self) -> List[ToolDefinition]:
        """列出所有工具"""
        return [tool.definition for tool in self._tools.values()]
    
    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """获取 OpenAI 格式的工具列表"""
        return [tool.definition.to_openai_format() for tool in self._tools.values()]
    
    def get_summaries(self) -> Dict[str, str]:
        """获取工具摘要"""
        return {
            name: f"[{tool.definition.category.value}] {tool.definition.description}"
            for name, tool in self._tools.items()
        }


class ToolExecutor:
    """工具执行器"""
    
    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self.call_history: List[ToolCall] = []
    
    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """执行单个工具"""
        tool = self.registry.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                tool_name=tool_name,
                result=None,
                error=f"Tool '{tool_name}' not found"
            )
        
        # 记录调用
        call = ToolCall(tool_name=tool_name, arguments=arguments, start_time=datetime.now())
        self.call_history.append(call)
        
        try:
            result = await tool.run(arguments)
            call.status = ToolStatus.SUCCESS if result.success else ToolStatus.FAILED
            call.result = result.result
            call.error = result.error
            call.end_time = datetime.now()
            call.execution_time = result.execution_time
            return result
        except asyncio.TimeoutError:
            call.status = ToolStatus.TIMEOUT
            call.error = f"Tool execution timeout ({tool.definition.timeout}s)"
            call.end_time = datetime.now()
            return ToolResult(
                success=False,
                tool_name=tool_name,
                result=None,
                error=f"Tool execution timeout"
            )
        except Exception as e:
            call.status = ToolStatus.FAILED
            call.error = str(e)
            call.end_time = datetime.now()
            return ToolResult(
                success=False,
                tool_name=tool_name,
                result=None,
                error=str(e)
            )
    
    async def execute_multiple(self, tool_calls: List[Dict[str, Any]]) -> List[ToolResult]:
        """并行执行多个工具"""
        tasks = [
            self.execute(call["name"], call.get("arguments", {}))
            for call in tool_calls
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)
    
    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取调用历史"""
        history = self.call_history[-limit:]
        return [
            {
                "tool_name": call.tool_name,
                "arguments": call.arguments,
                "status": call.status.value,
                "result": str(call.result)[:100] if call.result else None,
                "error": call.error,
                "execution_time": call.execution_time
            }
            for call in reversed(history)
        ]
    
    def clear_history(self):
        """清空历史"""
        self.call_history = []


class ToolSelector:
    """工具选择器 - 根据上下文选择合适的工具"""
    
    def __init__(self, registry: ToolRegistry):
        self.registry = registry
    
    def select_by_intent(self, intent: str) -> List[str]:
        """根据意图选择工具"""
        intent_lower = intent.lower()
        selected = []
        
        # 关键词匹配
        keyword_map = {
            "search": ["搜索", "查找", "查询", "search", "find", "query"],
            "retrieve": ["获取", "读取", "查找", "retrieve", "get", "fetch"],
            "extract": ["抽取", "提取", "识别", "extract", "identify"],
            "generate": ["生成", "创建", "编写", "generate", "create", "write"],
            "format": ["格式化", "整理", "format", "organize"]
        }
        
        for category, keywords in keyword_map.items():
            if any(kw in intent_lower for kw in keywords):
                tools = self.registry.get_by_category(ToolCategory(category))
                selected.extend([t.definition.name for t in tools])
        
        # 如果没有匹配，返回所有工具
        if not selected:
            selected = list(self.registry._tools.keys())
        
        return list(set(selected))
    
    def format_tools_for_prompt(self) -> str:
        """格式化工具信息用于 prompt"""
        tools = self.registry.list_all()
        lines = ["可用工具："]
        
        for tool in tools:
            params = ", ".join([p.name for p in tool.parameters])
            lines.append(f"- {tool.name}({params}): {tool.description}")
        
        return "\n".join(lines)