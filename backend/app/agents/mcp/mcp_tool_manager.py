"""MCP工具管理器 - 整合内部工具和外部MCP工具"""
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from app.core.logger import app_logger
from app.agents.tools.registry import get_tool_registry
from app.agents.tools.executor import get_tool_executor
from app.agents.tools.tool_metadata import Tool, ToolMetadata, ToolParameter, ToolExecutionResult
from app.agents.mcp.client import MCPDiscoveryService, MCPToolInfo, get_mcp_discovery, MCPConnectionConfig
from app.services.llm_service import LLMService
from app.services.vector_search_service import VectorSearchService
from app.db.database import get_db


@dataclass
class UnifiedToolInfo:
    """统一工具信息"""
    tool_id: str
    name: str
    description: str
    source: str
    source_url: Optional[str] = None
    parameters: List[Dict[str, Any]] = None
    input_schema: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.parameters is None:
            self.parameters = []


class MCPToolManager:
    """
    MCP工具管理器 - 统一管理内部工具和外部MCP工具
    
    功能:
    1. 获取所有可用工具（内部+外部）
    2. 动态发现外部MCP服务器工具
    3. 统一调用接口（透明调用内部或外部工具）
    4. 工具搜索和匹配
    """
    
    def __init__(self):
        self._internal_registry = get_tool_registry()
        self._internal_executor = get_tool_executor()
        self._mcp_discovery = get_mcp_discovery()
        self._llm_service = None
        self._vector_search_service = None
        self._cached_tools: Optional[List[UnifiedToolInfo]] = None
    
    async def _get_services(self):
        """延迟初始化服务"""
        if self._llm_service is None:
            self._llm_service = LLMService()
        if self._vector_search_service is None:
            db = await get_db().__anext__()
            self._vector_search_service = VectorSearchService(db)
            await self._vector_search_service.check_pgvector_support()
    
    async def get_all_tools(self, refresh: bool = False) -> List[UnifiedToolInfo]:
        """
        获取所有可用工具（内部+外部MCP）
        
        Args:
            refresh: 是否刷新缓存
            
        Returns:
            统一工具信息列表
        """
        if self._cached_tools and not refresh:
            return self._cached_tools
        
        tools = []
        
        # 获取内部工具
        internal_tools = self._internal_registry.get_all()
        for tool in internal_tools:
            tools.append(self._convert_internal_tool(tool))
        
        # 获取外部MCP工具
        external_tools = await self._mcp_discovery.discover_all_tools()
        for tool_info in external_tools:
            tools.append(self._convert_external_tool(tool_info))
        
        self._cached_tools = tools
        app_logger.info(f"[MCP Tool Manager] 共发现 {len(tools)} 个工具（内部: {len(internal_tools)}, 外部: {len(external_tools)}）")
        
        return tools
    
    def _convert_internal_tool(self, tool: Tool) -> UnifiedToolInfo:
        """将内部工具转换为统一格式"""
        parameters = []
        for param in tool.metadata.parameters:
            if isinstance(param, ToolParameter):
                param_dict = param.to_dict()
                parameters.append(param_dict)
        
        return UnifiedToolInfo(
            tool_id=tool.metadata.tool_id,
            name=tool.metadata.name,
            description=tool.metadata.description,
            source="internal",
            parameters=parameters,
            input_schema=tool.get_schema(),
        )
    
    def _convert_external_tool(self, tool_info: MCPToolInfo) -> UnifiedToolInfo:
        """将外部MCP工具转换为统一格式"""
        parameters = []
        schema = tool_info.input_schema
        
        if schema and isinstance(schema, dict):
            properties = schema.get("properties", {})
            for name, prop in properties.items():
                param_dict = {
                    "name": name,
                    "type": prop.get("type", "string"),
                    "description": prop.get("description", ""),
                    "required": name in schema.get("required", []),
                    "default": prop.get("default"),
                    "enum_values": prop.get("enum"),
                }
                parameters.append(param_dict)
        
        return UnifiedToolInfo(
            tool_id=tool_info.name,
            name=tool_info.name,
            description=tool_info.description,
            source=tool_info.server_name,
            source_url=tool_info.server_url,
            parameters=parameters,
            input_schema=schema,
        )
    
    async def call_tool(self, tool_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用工具（自动判断内部或外部）
        
        Args:
            tool_id: 工具ID
            params: 工具参数
            
        Returns:
            调用结果
        """
        # 先尝试调用内部工具
        internal_result = await self._try_call_internal(tool_id, params)
        if internal_result["success"]:
            return internal_result
        
        # 尝试调用外部MCP工具
        external_result = await self._try_call_external(tool_id, params)
        return external_result
    
    async def _try_call_internal(self, tool_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """尝试调用内部工具"""
        await self._get_services()
        
        try:
            result = await self._internal_executor.execute(
                tool_id,
                params,
                llm_service=self._llm_service,
                vector_search_service=self._vector_search_service,
            )
            
            if result.success:
                app_logger.debug(f"[MCP Tool Manager] 内部工具调用成功: {tool_id}")
                return {"success": True, "result": result.result, "source": "internal"}
            else:
                app_logger.debug(f"[MCP Tool Manager] 内部工具调用失败: {tool_id}")
                return {"success": False, "error": result.error}
        
        except Exception as e:
            app_logger.debug(f"[MCP Tool Manager] 内部工具调用异常: {tool_id} - {e}")
            return {"success": False, "error": str(e)}
    
    async def _try_call_external(self, tool_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """尝试调用外部MCP工具"""
        server_name, result = await self._mcp_discovery.call_any_tool(tool_id, params)
        
        if server_name:
            app_logger.debug(f"[MCP Tool Manager] 外部工具调用成功: {tool_id} from {server_name}")
            result["source"] = server_name
            return result
        else:
            app_logger.warning(f"[MCP Tool Manager] 外部工具调用失败: {tool_id}")
            return {"success": False, "error": f"工具 {tool_id} 未找到"}
    
    async def search_tools(self, query: str, limit: int = 10) -> List[UnifiedToolInfo]:
        """
        搜索工具
        
        Args:
            query: 搜索关键词
            limit: 返回数量限制
            
        Returns:
            匹配的工具列表
        """
        tools = await self.get_all_tools()
        query_lower = query.lower()
        
        results = []
        for tool in tools:
            score = 0.0
            
            if query_lower in tool.name.lower():
                score += 0.5
            if query_lower in tool.description.lower():
                score += 0.3
            if any(query_lower in param.get("name", "").lower() for param in tool.parameters):
                score += 0.2
            
            if score > 0:
                results.append((tool, score))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return [tool for tool, score in results[:limit]]
    
    async def register_external_server(self, config: MCPConnectionConfig):
        """
        注册外部MCP服务器
        
        Args:
            config: 服务器配置
        """
        self._mcp_discovery.register_server(config)
        self._cached_tools = None
        app_logger.info(f"[MCP Tool Manager] 注册外部MCP服务器: {config.name}")
    
    async def unregister_external_server(self, name: str):
        """
        注销外部MCP服务器
        
        Args:
            name: 服务器名称
        """
        self._mcp_discovery.unregister_server(name)
        self._cached_tools = None
        app_logger.info(f"[MCP Tool Manager] 注销外部MCP服务器: {name}")
    
    def get_tool_by_id(self, tool_id: str) -> Optional[UnifiedToolInfo]:
        """
        根据ID获取工具信息
        
        Args:
            tool_id: 工具ID
            
        Returns:
            工具信息（如果存在）
        """
        tools = self._cached_tools or []
        for tool in tools:
            if tool.tool_id == tool_id:
                return tool
        return None
    
    async def get_server_status(self) -> Dict[str, Any]:
        """获取所有服务器状态"""
        internal_status = {
            "internal": {
                "status": "online",
                "tool_count": len(self._internal_registry.get_all()),
            }
        }
        
        external_status = await self._mcp_discovery.health_check_all()
        
        return {
            "internal": internal_status["internal"],
            "external": {
                server: {"status": "online" if healthy else "offline"}
                for server, healthy in external_status.items()
            },
        }
    
    async def get_tools_for_prompt(self) -> str:
        """
        获取格式化的工具列表用于Prompt
        
        Returns:
            格式化的工具描述字符串
        """
        tools = await self.get_all_tools()
        
        lines = ["可用工具（tool_name 必须严格使用下列 tool_id，不要使用中文名称）："]
        
        for tool in tools:
            required_params = []
            optional_params = []
            
            for param in tool.parameters:
                param_type = param.get("type", "string")
                default = param.get("default")
                default_text = f", default={default}" if default is not None else ""
                
                if param.get("required", False):
                    required_params.append(f"{param['name']}:{param_type}{default_text}")
                else:
                    optional_params.append(f"{param['name']}:{param_type}{default_text}")
            
            source_text = f" (来源: {tool.source})" if tool.source != "internal" else ""
            
            lines.append(f"- tool_id: {tool.tool_id}{source_text}")
            lines.append(f"  name: {tool.name}")
            lines.append(f"  description: {tool.description}")
            lines.append(f"  required_args: {required_params or []}")
            lines.append(f"  optional_args: {optional_params or []}")
        
        return "\n".join(lines)


# 全局MCP工具管理器实例
_mcp_tool_manager: Optional[MCPToolManager] = None


def get_mcp_tool_manager() -> MCPToolManager:
    """获取全局MCP工具管理器实例"""
    global _mcp_tool_manager
    if _mcp_tool_manager is None:
        _mcp_tool_manager = MCPToolManager()
    return _mcp_tool_manager


def init_mcp_tool_manager() -> MCPToolManager:
    """初始化MCP工具管理器"""
    global _mcp_tool_manager
    _mcp_tool_manager = MCPToolManager()
    return _mcp_tool_manager