"""MCP Client - 发现和调用外部MCP服务器"""
import time
import json
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum
from collections import deque
import httpx
from app.core.logger import app_logger
from app.core.config import settings


class MCPTransport(Enum):
    """MCP传输方式"""
    HTTP = "http"
    STDIO = "stdio"


@dataclass
class MCPConnectionConfig:
    """MCP连接配置"""
    name: str
    url: str
    transport: MCPTransport = MCPTransport.HTTP
    api_key: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    timeout: int = 30


@dataclass
class MCPToolInfo:
    """MCP工具信息"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_name: str
    server_url: str


class MCPClient:
    """
    MCP Client - 连接并调用外部MCP服务器
    
    支持:
    1. HTTP方式连接外部MCP服务器
    2. 工具发现（获取服务器上的所有工具）
    3. 工具调用
    4. 服务器健康检查
    """
    
    def __init__(self, config: MCPConnectionConfig):
        self.config = config
        self._tools: List[MCPToolInfo] = []
        self._client: Optional[httpx.AsyncClient] = None
        self._initialized = False
    
    @property
    def tools(self) -> List[MCPToolInfo]:
        """获取已发现的工具列表"""
        return self._tools
    
    async def _get_client(self) -> httpx.AsyncClient:
        """获取HTTP客户端"""
        if self._client is None:
            headers = self.config.headers or {}
            if self.config.api_key:
                headers.setdefault("Authorization", f"Bearer {self.config.api_key}")
            
            self._client = httpx.AsyncClient(
                base_url=self.config.url,
                headers=headers,
                timeout=self.config.timeout,
            )
        return self._client
    
    async def discover_tools(self) -> List[MCPToolInfo]:
        """
        发现MCP服务器上的所有工具
        
        Returns:
            工具信息列表
        """
        try:
            client = await self._get_client()
            
            # MCP标准工具发现端点
            responses = await client.get("/")
            
            if responses.status_code != 200:
                app_logger.warning(f"[MCP Client] 工具发现失败 {self.config.url}: HTTP {responses.status_code}")
                return []
            
            data = responses.json()
            
            if isinstance(data, dict) and "tools" in data:
                tools_data = data["tools"]
            elif isinstance(data, list):
                tools_data = data
            else:
                app_logger.warning(f"[MCP Client] 工具发现响应格式异常 {self.config.url}")
                return []
            
            self._tools = []
            for tool_data in tools_data:
                try:
                    tool_info = MCPToolInfo(
                        name=tool_data.get("name", ""),
                        description=tool_data.get("description", ""),
                        input_schema=tool_data.get("input_schema", tool_data.get("parameters", {})),
                        server_name=self.config.name,
                        server_url=self.config.url,
                    )
                    self._tools.append(tool_info)
                except Exception as e:
                    app_logger.warning(f"[MCP Client] 解析工具信息失败: {e}")
            
            app_logger.info(f"[MCP Client] 从 {self.config.name}({self.config.url}) 发现 {len(self._tools)} 个工具")
            return self._tools
        
        except Exception as e:
            app_logger.error(f"[MCP Client] 工具发现异常 {self.config.url}: {e}")
            return []
    
    async def call_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用MCP工具
        
        Args:
            tool_name: 工具名称
            params: 工具参数
            
        Returns:
            调用结果
        """
        try:
            client = await self._get_client()
            
            # MCP标准调用端点
            response = await client.post(
                f"/{tool_name}",
                json=params,
            )
            
            if response.status_code == 200:
                result = response.json()
                app_logger.debug(f"[MCP Client] 调用工具成功 {tool_name}")
                return {"success": True, "result": result}
            else:
                error_data = response.json() if response.headers.get("content-type") == "application/json" else response.text
                app_logger.warning(f"[MCP Client] 调用工具失败 {tool_name}: HTTP {response.status_code} - {error_data}")
                return {"success": False, "error": str(error_data)}
        
        except Exception as e:
            app_logger.error(f"[MCP Client] 调用工具异常 {tool_name}: {e}")
            return {"success": False, "error": str(e)}
    
    async def health_check(self) -> bool:
        """检查MCP服务器健康状态"""
        try:
            client = await self._get_client()
            response = await client.get("/health")
            
            if response.status_code == 200:
                data = response.json()
                return data.get("status") == "ok"
            
            return False
        except Exception as e:
            app_logger.warning(f"[MCP Client] 健康检查失败 {self.config.url}: {e}")
            return False
    
    async def get_server_info(self) -> Optional[Dict[str, Any]]:
        """获取服务器信息"""
        try:
            client = await self._get_client()
            response = await client.get("/")
            
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            app_logger.warning(f"[MCP Client] 获取服务器信息失败 {self.config.url}: {e}")
        
        return None
    
    async def close(self):
        """关闭连接"""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.discover_tools()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()


class MCPDiscoveryService:
    """
    MCP发现服务 - 自动发现可用的MCP服务器
    
    支持:
    1. 配置文件方式发现
    2. 环境变量方式发现
    3. 动态注册发现
    """
    
    def __init__(self):
        self._servers: Dict[str, MCPConnectionConfig] = {}
        self._clients: Dict[str, MCPClient] = {}
    
    def register_server(self, config: MCPConnectionConfig):
        """
        注册MCP服务器
        
        Args:
            config: 服务器配置
        """
        self._servers[config.name] = config
        app_logger.info(f"[MCP Discovery] 注册服务器: {config.name} -> {config.url}")
    
    def unregister_server(self, name: str):
        """
        注销MCP服务器
        
        Args:
            name: 服务器名称
        """
        if name in self._servers:
            del self._servers[name]
            if name in self._clients:
                self._clients[name] = None
            app_logger.info(f"[MCP Discovery] 注销服务器: {name}")
    
    def get_server_config(self, name: str) -> Optional[MCPConnectionConfig]:
        """获取服务器配置"""
        return self._servers.get(name)
    
    def list_servers(self) -> List[str]:
        """列出所有已注册的服务器"""
        return list(self._servers.keys())
    
    async def get_client(self, name: str) -> Optional[MCPClient]:
        """
        获取MCP客户端
        
        Args:
            name: 服务器名称
            
        Returns:
            MCP客户端实例
        """
        if name not in self._servers:
            app_logger.warning(f"[MCP Discovery] 服务器未注册: {name}")
            return None
        
        if name not in self._clients or self._clients[name] is None:
            config = self._servers[name]
            client = MCPClient(config)
            await client.discover_tools()
            self._clients[name] = client
        
        return self._clients[name]
    
    async def discover_all_tools(self) -> List[MCPToolInfo]:
        """发现所有服务器上的工具"""
        all_tools = []
        
        for name in self._servers:
            client = await self.get_client(name)
            if client:
                all_tools.extend(client.tools)
        
        return all_tools
    
    async def call_any_tool(self, tool_name: str, params: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        在任意服务器上调用工具
        
        Args:
            tool_name: 工具名称
            params: 工具参数
            
        Returns:
            (服务器名称, 调用结果)
        """
        for name in self._servers:
            client = await self.get_client(name)
            if client:
                for tool in client.tools:
                    if tool.name == tool_name:
                        result = await client.call_tool(tool_name, params)
                        return name, result
        
        app_logger.warning(f"[MCP Discovery] 未找到工具: {tool_name}")
        return None, {"success": False, "error": f"工具 {tool_name} 未找到"}
    
    async def health_check_all(self) -> Dict[str, bool]:
        """检查所有服务器健康状态"""
        results = {}
        
        for name in self._servers:
            client = await self.get_client(name)
            if client:
                results[name] = await client.health_check()
        
        return results
    
    async def close_all(self):
        """关闭所有客户端连接"""
        for name, client in self._clients.items():
            if client:
                await client.close()
        self._clients.clear()


class MCPDynamicDiscoveryService:
    """
    MCP动态发现服务 - 高级动态发现和注册功能
    
    功能:
    1. 服务注册中心（支持心跳检测）
    2. 自动Schema读取（OpenAPI/Swagger规范）
    3. 热重载（无需重启即可发现新服务）
    4. 自动发现（通过配置文件/环境变量/网络扫描）
    5. 工具版本管理
    """
    
    def __init__(self):
        self._servers: Dict[str, MCPConnectionConfig] = {}
        self._clients: Dict[str, MCPClient] = {}
        self._tool_registry: Dict[str, Dict[str, Any]] = {}
        self._heartbeat_timestamps: Dict[str, float] = {}
        self._discovery_history: deque = deque(maxlen=100)
        self._heartbeat_interval = settings.MCP_HEARTBEAT_INTERVAL or 60
    
    def register_server(self, config: MCPConnectionConfig):
        """注册MCP服务器"""
        self._servers[config.name] = config
        self._heartbeat_timestamps[config.name] = time.time()
        self._clients.pop(config.name, None)
        self._discovery_history.append({
            "timestamp": time.time(),
            "action": "register",
            "server": config.name,
            "url": config.url
        })
        app_logger.info(f"[MCP Dynamic Discovery] 注册服务器: {config.name} -> {config.url}")
    
    def unregister_server(self, name: str):
        """注销MCP服务器"""
        if name in self._servers:
            del self._servers[name]
            self._clients.pop(name, None)
            self._heartbeat_timestamps.pop(name, None)
            self._discovery_history.append({
                "timestamp": time.time(),
                "action": "unregister",
                "server": name
            })
            app_logger.info(f"[MCP Dynamic Discovery] 注销服务器: {name}")
    
    async def discover_from_config(self):
        """从配置文件发现MCP服务器"""
        mcp_servers = getattr(settings, "MCP_SERVERS", None)
        if mcp_servers:
            try:
                if isinstance(mcp_servers, str):
                    servers_config = json.loads(mcp_servers)
                else:
                    servers_config = mcp_servers
                
                for server_config in servers_config:
                    config = MCPConnectionConfig(
                        name=server_config["name"],
                        url=server_config["url"],
                        transport=MCPTransport[server_config.get("transport", "HTTP").upper()],
                        api_key=server_config.get("api_key"),
                        headers=server_config.get("headers"),
                        timeout=server_config.get("timeout", 30)
                    )
                    self.register_server(config)
            except Exception as e:
                app_logger.error(f"[MCP Dynamic Discovery] 从配置发现服务器失败: {e}")
    
    async def discover_from_environment(self):
        """从环境变量发现MCP服务器"""
        import os
        mcp_env = os.environ.get("MCP_SERVERS")
        if mcp_env:
            try:
                servers_config = json.loads(mcp_env)
                for server_config in servers_config:
                    config = MCPConnectionConfig(
                        name=server_config["name"],
                        url=server_config["url"],
                        transport=MCPTransport[server_config.get("transport", "HTTP").upper()],
                        api_key=server_config.get("api_key"),
                        headers=server_config.get("headers"),
                        timeout=server_config.get("timeout", 30)
                    )
                    self.register_server(config)
            except Exception as e:
                app_logger.error(f"[MCP Dynamic Discovery] 从环境变量发现服务器失败: {e}")
    
    async def discover_from_directory(self, directory: str = "./mcp_servers"):
        """从目录发现MCP服务器配置文件"""
        import os
        if not os.path.exists(directory):
            return
        
        for filename in os.listdir(directory):
            if filename.endswith(".json"):
                filepath = os.path.join(directory, filename)
                try:
                    with open(filepath, "r") as f:
                        server_config = json.load(f)
                        config = MCPConnectionConfig(
                            name=server_config["name"],
                            url=server_config["url"],
                            transport=MCPTransport[server_config.get("transport", "HTTP").upper()],
                            api_key=server_config.get("api_key"),
                            headers=server_config.get("headers"),
                            timeout=server_config.get("timeout", 30)
                        )
                        self.register_server(config)
                except Exception as e:
                    app_logger.error(f"[MCP Dynamic Discovery] 从文件发现服务器失败 {filename}: {e}")
    
    async def auto_discover(self):
        """自动发现所有MCP服务器"""
        await self.discover_from_config()
        await self.discover_from_environment()
        await self.discover_from_directory()
    
    async def get_client(self, name: str) -> Optional[MCPClient]:
        """获取MCP客户端"""
        if name not in self._servers:
            app_logger.warning(f"[MCP Dynamic Discovery] 服务器未注册: {name}")
            return None
        
        if name not in self._clients or self._clients[name] is None:
            config = self._servers[name]
            client = MCPClient(config)
            await client.discover_tools()
            await self._update_tool_registry(name, client)
            self._clients[name] = client
        
        return self._clients[name]
    
    async def _update_tool_registry(self, server_name: str, client: MCPClient):
        """更新工具注册表"""
        for tool in client.tools:
            tool_key = f"{server_name}.{tool.name}"
            self._tool_registry[tool_key] = {
                "tool_name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "server_name": server_name,
                "server_url": tool.server_url,
                "discovered_at": time.time()
            }
    
    async def discover_all_tools(self, refresh: bool = False) -> List[MCPToolInfo]:
        """发现所有服务器上的工具"""
        if refresh:
            self._clients.clear()
        
        all_tools = []
        
        for name in self._servers:
            client = await self.get_client(name)
            if client:
                all_tools.extend(client.tools)
        
        return all_tools
    
    async def call_any_tool(self, tool_name: str, params: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, Any]]:
        """在任意服务器上调用工具"""
        for name in self._servers:
            client = await self.get_client(name)
            if client:
                for tool in client.tools:
                    if tool.name == tool_name:
                        result = await client.call_tool(tool_name, params)
                        return name, result
        
        app_logger.warning(f"[MCP Dynamic Discovery] 未找到工具: {tool_name}")
        return None, {"success": False, "error": f"工具 {tool_name} 未找到"}
    
    async def health_check_all(self) -> Dict[str, bool]:
        """检查所有服务器健康状态"""
        results = {}
        
        for name in self._servers:
            client = await self.get_client(name)
            if client:
                healthy = await client.health_check()
                results[name] = healthy
                if healthy:
                    self._heartbeat_timestamps[name] = time.time()
        
        return results
    
    async def check_heartbeat(self) -> Dict[str, Any]:
        """检查服务器心跳"""
        now = time.time()
        results = {}
        
        for name, timestamp in self._heartbeat_timestamps.items():
            elapsed = now - timestamp
            status = "online" if elapsed < self._heartbeat_interval * 2 else "offline"
            results[name] = {
                "status": status,
                "last_heartbeat": timestamp,
                "elapsed_seconds": round(elapsed, 2)
            }
        
        return results
    
    async def reload_server(self, name: str) -> bool:
        """热重载单个服务器"""
        if name not in self._servers:
            app_logger.warning(f"[MCP Dynamic Discovery] 服务器未注册: {name}")
            return False
        
        self._clients.pop(name, None)
        
        config = self._servers[name]
        client = MCPClient(config)
        tools = await client.discover_tools()
        
        if tools:
            self._clients[name] = client
            await self._update_tool_registry(name, client)
            self._heartbeat_timestamps[name] = time.time()
            self._discovery_history.append({
                "timestamp": time.time(),
                "action": "reload",
                "server": name,
                "tool_count": len(tools)
            })
            app_logger.info(f"[MCP Dynamic Discovery] 热重载服务器成功: {name}")
            return True
        
        return False
    
    async def reload_all(self):
        """热重载所有服务器"""
        for name in list(self._servers.keys()):
            await self.reload_server(name)
    
    def get_tool_registry(self) -> Dict[str, Dict[str, Any]]:
        """获取工具注册表"""
        return self._tool_registry
    
    def get_discovery_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取发现历史"""
        return list(self._discovery_history)[-limit:]
    
    def get_server_status(self) -> Dict[str, Any]:
        """获取所有服务器状态"""
        status = {}
        for name, config in self._servers.items():
            client = self._clients.get(name)
            status[name] = {
                "url": config.url,
                "transport": config.transport.value,
                "tool_count": len(client.tools) if client else 0,
                "registered_at": self._heartbeat_timestamps.get(name, 0),
                "health_check": "pending"
            }
        return status
    
    async def close_all(self):
        """关闭所有客户端连接"""
        for name, client in self._clients.items():
            if client:
                await client.close()
        self._clients.clear()


# 全局MCP发现服务实例
_discovery_service: Optional[MCPDiscoveryService] = None
_dynamic_discovery_service: Optional[MCPDynamicDiscoveryService] = None


def get_mcp_discovery() -> MCPDiscoveryService:
    """获取全局MCP发现服务实例"""
    global _discovery_service
    if _discovery_service is None:
        _discovery_service = MCPDiscoveryService()
    return _discovery_service


def get_mcp_dynamic_discovery() -> MCPDynamicDiscoveryService:
    """获取全局MCP动态发现服务实例"""
    global _dynamic_discovery_service
    if _dynamic_discovery_service is None:
        _dynamic_discovery_service = MCPDynamicDiscoveryService()
    return _dynamic_discovery_service


def init_mcp_discovery(servers: List[MCPConnectionConfig] = None):
    """初始化MCP发现服务"""
    global _discovery_service
    _discovery_service = MCPDiscoveryService()
    
    if servers:
        for config in servers:
            _discovery_service.register_server(config)
    
    return _discovery_service


async def init_mcp_dynamic_discovery():
    """初始化MCP动态发现服务"""
    global _dynamic_discovery_service
    _dynamic_discovery_service = MCPDynamicDiscoveryService()
    await _dynamic_discovery_service.auto_discover()
    return _dynamic_discovery_service