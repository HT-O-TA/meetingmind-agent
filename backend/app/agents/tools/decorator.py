"""增强的工具调用系统 - 使用装饰器模式简化注册"""
import json
import asyncio
import inspect
from typing import Dict, List, Optional, Any, Callable, get_type_hints, get_origin, get_args
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import wraps
from app.core.logger import app_logger


class ToolCategory(str, Enum):
    """工具类别"""
    MEETING = "meeting"           # 会议相关
    DOCUMENT = "document"        # 文档相关
    TODO = "todo"               # 待办相关
    COMPUTATION = "computation"  # 计算相关
    INFO = "info"               # 信息查询
    KNOWLEDGE = "knowledge"      # 知识库
    NOTIFICATION = "notification" # 通知相关
    MULTIMODAL = "multimodal"   # 多模态
    UTILITY = "utility"          # 工具类


class ToolStatus(str, Enum):
    """工具状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"


@dataclass
class ParameterInfo:
    """参数信息"""
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    enum: List[Any] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    examples: List[Any] = None
    
    def __post_init__(self):
        if self.enum is None:
            self.enum = []
        if self.examples is None:
            self.examples = []
    
    def to_openai_format(self) -> Dict[str, Any]:
        """转换为OpenAI格式"""
        param = {
            "type": self.type,
            "description": self.description
        }
        if self.enum:
            param["enum"] = self.enum
        if self.default is not None:
            param["default"] = self.default
        if self.min_value is not None:
            param["minimum"] = self.min_value
        if self.max_value is not None:
            param["maximum"] = self.max_value
        if self.max_length is not None:
            param["maxLength"] = self.max_length
        if self.pattern is not None:
            param["pattern"] = self.pattern
        return param


@dataclass
class ToolInfo:
    """工具信息"""
    name: str
    description: str
    category: ToolCategory
    parameters: List[ParameterInfo] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    author: str = ""
    examples: List[Dict[str, Any]] = field(default_factory=list)
    timeout: int = 30
    is_async: bool = True
    status: ToolStatus = ToolStatus.ACTIVE
    
    def to_openai_format(self) -> Dict[str, Any]:
        """转换为OpenAI函数调用格式"""
        properties = {}
        required = []
        
        for param in self.parameters:
            properties[param.name] = param.to_openai_format()
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
    
    def get_parameter_schema(self) -> Dict[str, Any]:
        """获取参数JSON Schema"""
        properties = {}
        required = []
        
        for param in self.parameters:
            properties[param.name] = param.to_openai_format()
            if param.required:
                required.append(param.name)
        
        return {
            "type": "object",
            "properties": properties,
            "required": required
        }
    
    def validate_parameters(self, arguments: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """验证参数"""
        for param in self.parameters:
            if param.required and param.name not in arguments:
                return False, f"Missing required parameter: {param.name}"
            
            if param.name in arguments:
                value = arguments[param.name]
                
                # 类型检查
                if param.type == "string" and not isinstance(value, str):
                    return False, f"Parameter {param.name} must be a string"
                elif param.type == "integer" and not isinstance(value, int):
                    return False, f"Parameter {param.name} must be an integer"
                elif param.type == "number" and not isinstance(value, (int, float)):
                    return False, f"Parameter {param.name} must be a number"
                elif param.type == "boolean" and not isinstance(value, bool):
                    return False, f"Parameter {param.name} must be a boolean"
                elif param.type == "array" and not isinstance(value, list):
                    return False, f"Parameter {param.name} must be an array"
                
                # 枚举检查
                if param.enum and value not in param.enum:
                    return False, f"Parameter {param.name} must be one of {param.enum}"
                
                # 范围检查
                if param.min_value is not None and isinstance(value, (int, float)) and value < param.min_value:
                    return False, f"Parameter {param.name} must be >= {param.min_value}"
                if param.max_value is not None and isinstance(value, (int, float)) and value > param.max_value:
                    return False, f"Parameter {param.name} must be <= {param.max_value}"
                
                # 长度检查
                if param.max_length is not None and isinstance(value, str) and len(value) > param.max_length:
                    return False, f"Parameter {param.name} must not exceed {param.max_length} characters"
        
        return True, None
    
    def get_auto_complete_suggestions(self, partial_args: Dict[str, Any]) -> Dict[str, List[Any]]:
        """获取参数自动补全建议"""
        suggestions = {}
        
        for param in self.parameters:
            if param.name in partial_args:
                continue
            
            # 枚举值建议
            if param.enum:
                suggestions[param.name] = param.enum
            
            # 示例值建议
            elif param.examples:
                suggestions[param.name] = param.examples
            
            # 默认值建议
            elif param.default is not None:
                suggestions[param.name] = [param.default]
            
            # 常用值建议
            elif param.type == "integer":
                suggestions[param.name] = [1, 5, 10]
            elif param.type == "string":
                suggestions[param.name] = []
        
        return suggestions


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    tool_name: str
    result: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    """增强的工具注册表 - 使用装饰器模式"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._tools: Dict[str, ToolInfo] = {}
        self._executors: Dict[str, Callable] = {}
        self._async_executors: Dict[str, Callable] = {}
        self._category_index: Dict[str, List[str]] = {}
        self._tag_index: Dict[str, List[str]] = {}
        self._call_history: List[Dict[str, Any]] = []
        self._stats: Dict[str, Any] = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "by_tool": {}
        }
        self._initialized = True
        
        self._register_default_tools()
    
    def _register_default_tools(self):
        """注册默认工具（内省）"""
        pass
    
    def register(
        self,
        name: str = None,
        description: str = None,
        category: ToolCategory = ToolCategory.UTILITY,
        tags: List[str] = None,
        timeout: int = 30,
        **kwargs
    ):
        """
        工具注册装饰器
        
        用法:
            @tool_registry.register(
                name="my_tool",
                description="这是一个示例工具",
                category=ToolCategory.UTILITY
            )
            async def my_tool(query: str, limit: int = 10):
                return {"result": f"查询 {query} 的结果"}
        """
        def decorator(func: Callable):
            tool_name = name or func.__name__
            tool_desc = description or func.__doc__ or ""
            tool_tags = tags or []
            
            # 从函数签名推断参数
            parameters = self._infer_parameters(func)
            
            # 创建工具信息
            tool_info = ToolInfo(
                name=tool_name,
                description=tool_desc.strip(),
                category=category,
                parameters=parameters,
                tags=tool_tags,
                timeout=timeout,
                is_async=asyncio.iscoroutinefunction(func)
            )
            
            # 注册工具
            self._tools[tool_name] = tool_info
            
            if asyncio.iscoroutinefunction(func):
                self._async_executors[tool_name] = func
            else:
                self._executors[tool_name] = func
            
            # 更新索引
            self._update_indexes(tool_name, tool_info)
            
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                return await func(*args, **kwargs)
            
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper
        
        return decorator
    
    def _infer_parameters(self, func: Callable) -> List[ParameterInfo]:
        """从函数签名推断参数信息"""
        parameters = []
        sig = inspect.signature(func)
        hints = {}
        
        try:
            hints = get_type_hints(func)
        except Exception:
            pass
        
        for param_name, param in sig.parameters.items():
            if param_name in ('self', 'cls'):
                continue
            
            # 获取类型
            type_hint = hints.get(param_name, str)
            param_type = self._get_openai_type(type_hint)
            
            # 判断是否必需
            has_default = param.default is not inspect.Parameter.empty
            required = not has_default
            
            # 获取描述
            param_info = ParameterInfo(
                name=param_name,
                type=param_type,
                description=f"{param_name} parameter",
                required=required,
                default=param.default if has_default else None
            )
            
            parameters.append(param_info)
        
        return parameters
    
    def _get_openai_type(self, type_hint) -> str:
        """将Python类型映射到OpenAI类型"""
        origin = get_origin(type_hint)
        
        if origin is list or type_hint == list:
            return "array"
        elif origin is dict or type_hint == dict:
            return "object"
        elif type_hint == bool:
            return "boolean"
        elif type_hint in (int, float):
            return "number"
        elif type_hint == str:
            return "string"
        else:
            return "string"
    
    def _update_indexes(self, tool_name: str, tool_info: ToolInfo):
        """更新索引"""
        # 分类索引
        category = tool_info.category.value
        if category not in self._category_index:
            self._category_index[category] = []
        if tool_name not in self._category_index[category]:
            self._category_index[category].append(tool_name)
        
        # 标签索引
        for tag in tool_info.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = []
            if tool_name not in self._tag_index[tag]:
                self._tag_index[tag].append(tool_name)
    
    def get(self, name: str) -> Optional[ToolInfo]:
        """获取工具信息"""
        return self._tools.get(name)
    
    def get_executor(self, name: str) -> Optional[Callable]:
        """获取执行器"""
        if name in self._async_executors:
            return self._async_executors[name]
        return self._executors.get(name)
    
    def get_all(self) -> List[ToolInfo]:
        """获取所有工具"""
        return list(self._tools.values())
    
    def get_by_category(self, category: ToolCategory) -> List[ToolInfo]:
        """按分类获取工具"""
        tool_names = self._category_index.get(category.value, [])
        return [self._tools[name] for name in tool_names if name in self._tools]
    
    def get_by_tag(self, tag: str) -> List[ToolInfo]:
        """按标签获取工具"""
        tool_names = self._tag_index.get(tag, [])
        return [self._tools[name] for name in tool_names if name in self._tools]
    
    def search(self, query: str, limit: int = 10) -> List[ToolInfo]:
        """搜索工具"""
        query_lower = query.lower()
        results = []
        
        for tool in self._tools.values():
            score = 0
            
            # 匹配名称（最高权重）
            if query_lower in tool.name.lower():
                score = 1.0
            # 匹配描述
            elif query_lower in tool.description.lower():
                score = 0.8
            # 匹配标签
            elif any(query_lower in tag.lower() for tag in tool.tags):
                score = 0.6
            # 匹配分类
            elif query_lower in tool.category.value.lower():
                score = 0.4
            
            if score > 0:
                results.append((tool, score))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return [tool for tool, score in results[:limit]]
    
    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """获取OpenAI格式的工具列表"""
        return [tool.to_openai_format() for tool in self._tools.values()]
    
    def get_schemas(self) -> List[Dict[str, Any]]:
        """获取所有工具的schema"""
        return [tool.to_openai_format() for tool in self._tools.values()]
    
    async def execute(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        """执行工具"""
        start_time = datetime.now()
        
        tool_info = self._tools.get(name)
        if not tool_info:
            return ToolResult(
                success=False,
                tool_name=name,
                error=f"Tool '{name}' not found"
            )
        
        executor = self.get_executor(name)
        if not executor:
            return ToolResult(
                success=False,
                tool_name=name,
                error=f"Executor for '{name}' not found"
            )
        
        # 验证参数
        valid, error_msg = tool_info.validate_parameters(arguments)
        if not valid:
            return ToolResult(
                success=False,
                tool_name=name,
                error=error_msg,
                execution_time=(datetime.now() - start_time).total_seconds()
            )
        
        try:
            # 执行（带超时）
            result = await asyncio.wait_for(
                executor(**arguments),
                timeout=tool_info.timeout
            )
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # 记录调用
            self._record_call(name, True, execution_time)
            
            return ToolResult(
                success=True,
                tool_name=name,
                result=result,
                execution_time=execution_time
            )
        
        except asyncio.TimeoutError:
            execution_time = (datetime.now() - start_time).total_seconds()
            self._record_call(name, False, execution_time, f"Timeout after {tool_info.timeout}s")
            
            return ToolResult(
                success=False,
                tool_name=name,
                error=f"Tool execution timeout after {tool_info.timeout}s",
                execution_time=execution_time
            )
        
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            self._record_call(name, False, execution_time, str(e))
            
            return ToolResult(
                success=False,
                tool_name=name,
                error=str(e),
                execution_time=execution_time
            )
    
    def _record_call(self, tool_name: str, success: bool, execution_time: float, error: str = None):
        """记录调用"""
        self._stats["total_calls"] += 1
        if success:
            self._stats["successful_calls"] += 1
        else:
            self._stats["failed_calls"] += 1
        
        if tool_name not in self._stats["by_tool"]:
            self._stats["by_tool"][tool_name] = {
                "calls": 0,
                "successes": 0,
                "failures": 0,
                "total_time": 0
            }
        
        self._stats["by_tool"][tool_name]["calls"] += 1
        if success:
            self._stats["by_tool"][tool_name]["successes"] += 1
        else:
            self._stats["by_tool"][tool_name]["failures"] += 1
        
        self._stats["by_tool"][tool_name]["total_time"] += execution_time
        
        self._call_history.append({
            "tool_name": tool_name,
            "success": success,
            "execution_time": execution_time,
            "error": error,
            "timestamp": datetime.now().isoformat()
        })
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "success_rate": self._stats["successful_calls"] / max(1, self._stats["total_calls"]),
            "avg_execution_time": sum(h["execution_time"] for h in self._call_history) / max(1, len(self._call_history))
        }
    
    def get_call_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取调用历史"""
        return self._call_history[-limit:]
    
    def get_parameter_autocomplete(self, tool_name: str, partial_args: Dict[str, Any]) -> Dict[str, List[Any]]:
        """获取参数自动补全建议"""
        tool_info = self._tools.get(tool_name)
        if not tool_info:
            return {}
        return tool_info.get_auto_complete_suggestions(partial_args)


# 全局工具注册表实例
_tool_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    """获取全局工具注册表"""
    return _tool_registry


def tool(
    name: str = None,
    description: str = None,
    category: ToolCategory = ToolCategory.UTILITY,
    tags: List[str] = None,
    timeout: int = 30
):
    """
    工具装饰器 - 简化版
    
    用法:
        @tool(name="search", description="搜索工具")
        async def search(query: str, limit: int = 10):
            '''搜索相关文档'''
            return [...]
    """
    return _tool_registry.register(
        name=name,
        description=description,
        category=category,
        tags=tags,
        timeout=timeout
    )


# 预定义的工具装饰器
def meeting_tool(name: str = None, description: str = None, **kwargs):
    """会议相关工具装饰器"""
    return _tool_registry.register(
        name=name,
        description=description,
        category=ToolCategory.MEETING,
        **kwargs
    )


def document_tool(name: str = None, description: str = None, **kwargs):
    """文档相关工具装饰器"""
    return _tool_registry.register(
        name=name,
        description=description,
        category=ToolCategory.DOCUMENT,
        **kwargs
    )


def todo_tool(name: str = None, description: str = None, **kwargs):
    """待办相关工具装饰器"""
    return _tool_registry.register(
        name=name,
        description=description,
        category=ToolCategory.TODO,
        **kwargs
    )


def multimodal_tool(name: str = None, description: str = None, **kwargs):
    """多模态工具装饰器"""
    return _tool_registry.register(
        name=name,
        description=description,
        category=ToolCategory.MULTIMODAL,
        **kwargs
    )
