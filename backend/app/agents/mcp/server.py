"""MCP Server - 将MeetingMind工具暴露为MCP服务"""
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass
from fastapi import FastAPI
from app.core.logger import app_logger
from app.agents.tools.registry import get_tool_registry
from app.agents.tools.tool_metadata import Tool, ToolParameter, ToolCategory
from app.agents.tools.executor import get_tool_executor
from app.services.llm_service import LLMService
from app.services.vector_search_service import VectorSearchService
from app.db.database import get_db

try:
    from fastmcp.server import MCP, Route
    from fastmcp.server.auth import AuthCheck
    HAS_FASTMCP = True
except ImportError:
    HAS_FASTMCP = False
    MCP = None
    Route = None
    AuthCheck = None


@dataclass
class MCPServerConfig:
    """MCP Server配置"""
    name: str = "MeetingMind MCP Server"
    version: str = "1.0.0"
    description: str = "企业级会议智能助手 MCP 服务"
    host: str = "127.0.0.1"
    port: int = 8000
    enable_auth: bool = False
    api_key: Optional[str] = None


class MCPServer:
    """
    MCP Server - 将MeetingMind工具暴露为MCP服务
    
    支持:
    1. 将现有MeetingMind工具自动转换为MCP工具
    2. HTTP端点暴露
    3. 工具发现
    4. 工具调用
    """
    
    def __init__(self, config: MCPServerConfig = None):
        self.config = config or MCPServerConfig()
        self.mcp = None
        self._tool_executor = get_tool_executor()
        self._tool_registry = get_tool_registry()
        self._llm_service = None
        self._vector_search_service = None
        
        if HAS_FASTMCP:
            self._init_mcp()
    
    def _init_mcp(self):
        """初始化MCP服务器"""
        try:
            self.mcp = MCP(
                name=self.config.name,
                version=self.config.version,
                description=self.config.description,
            )
            
            # 注册所有可用工具
            self._register_tools()
            
            app_logger.info(f"[MCP Server] 初始化成功，注册了 {len(self._tool_registry.get_all())} 个工具")
        except Exception as e:
            app_logger.error(f"[MCP Server] 初始化失败: {e}")
            self.mcp = None
    
    def _register_tools(self):
        """注册所有MeetingMind工具为MCP工具"""
        if not HAS_FASTMCP or not self.mcp:
            return
        
        tools = self._tool_registry.get_all()
        
        for tool in tools:
            try:
                self._register_tool(tool)
                app_logger.debug(f"[MCP Server] 注册工具: {tool.metadata.tool_id}")
            except Exception as e:
                app_logger.warning(f"[MCP Server] 注册工具失败 {tool.metadata.tool_id}: {e}")
    
    def _register_tool(self, tool: Tool):
        """将单个工具注册为MCP工具"""
        if not HAS_FASTMCP or not self.mcp:
            return
        
        # 构建参数schema
        params = {}
        required = []
        
        for param in tool.metadata.parameters:
            if isinstance(param, ToolParameter):
                param_type = self._convert_type(param.type)
                param_dict = {"description": param.description}
                
                if param_type:
                    param_dict["type"] = param_type
                if param.enum_values:
                    param_dict["enum"] = param.enum_values
                if param.default is not None:
                    param_dict["default"] = param.default
                
                params[param.name] = param_dict
                
                if param.required:
                    required.append(param.name)
        
        # 创建MCP路由
        async def tool_handler(**kwargs):
            return await self._execute_tool(tool.metadata.tool_id, kwargs)
        
        # 添加路由
        self.mcp.add_route(
            Route(
                name=tool.metadata.tool_id,
                description=tool.metadata.description,
                input_schema={
                    "type": "object",
                    "properties": params,
                    "required": required,
                },
                handler=tool_handler,
            )
        )
    
    def _convert_type(self, type_str: str) -> Optional[str]:
        """转换类型字符串为JSON Schema类型"""
        type_mapping = {
            "string": "string",
            "integer": "integer",
            "float": "number",
            "boolean": "boolean",
            "array": "array",
            "object": "object",
        }
        return type_mapping.get(type_str)
    
    async def _execute_tool(self, tool_id: str, params: Dict[str, Any]) -> Any:
        """执行工具并返回结果"""
        # 延迟初始化服务
        if self._llm_service is None:
            self._llm_service = LLMService()
        if self._vector_search_service is None:
            db = await get_db().__anext__()
            self._vector_search_service = VectorSearchService(db)
            await self._vector_search_service.check_pgvector_support()
        
        result = await self._tool_executor.execute(
            tool_id,
            params,
            llm_service=self._llm_service,
            vector_search_service=self._vector_search_service,
        )
        
        if result.success:
            return {"success": True, "result": result.result}
        else:
            return {"success": False, "error": result.error}
    
    def get_app(self, path: str = "/") -> Optional[FastAPI]:
        """获取MCP HTTP应用"""
        if not HAS_FASTMCP or not self.mcp:
            return None
        
        try:
            return self.mcp.http_app(path=path)
        except Exception as e:
            app_logger.error(f"[MCP Server] 获取HTTP应用失败: {e}")
            return None
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """获取所有注册的工具信息"""
        return self._tool_registry.get_all_metadata()
    
    def get_tool_schema(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """获取单个工具的schema"""
        tool = self._tool_registry.get(tool_id)
        if tool:
            return tool.get_schema()
        return None
    
    def is_available(self) -> bool:
        """检查MCP是否可用"""
        return HAS_FASTMCP and self.mcp is not None


# 全局MCP Server实例
_mcp_server: Optional[MCPServer] = None


def get_mcp_server() -> MCPServer:
    """获取全局MCP Server实例"""
    global _mcp_server
    if _mcp_server is None:
        _mcp_server = MCPServer()
    return _mcp_server


def init_mcp_server(config: MCPServerConfig = None) -> MCPServer:
    """初始化MCP Server"""
    global _mcp_server
    _mcp_server = MCPServer(config)
    return _mcp_server
