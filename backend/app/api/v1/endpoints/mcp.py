"""MCP API 端点 - 提供 MCP 工具发现和调用接口"""
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.core.logger import app_logger
from app.agents.mcp import (
    get_mcp_server,
    get_mcp_discovery,
    get_mcp_dynamic_discovery,
    init_mcp_dynamic_discovery,
    get_mcp_tool_manager,
    MCPConnectionConfig,
    MCPTransport,
)

router = APIRouter(prefix="/mcp", tags=["MCP"])


class ServerConfigRequest(BaseModel):
    """服务器配置请求"""
    name: str = Field(..., description="服务器名称")
    url: str = Field(..., description="服务器URL")
    api_key: Optional[str] = Field(None, description="API密钥")
    timeout: int = Field(30, description="超时时间")


class ToolCallRequest(BaseModel):
    """工具调用请求"""
    tool_id: str = Field(..., description="工具ID")
    parameters: Dict[str, Any] = Field(..., description="工具参数")


class ToolCallResponse(BaseModel):
    """工具调用响应"""
    success: bool = Field(..., description="是否成功")
    result: Optional[Any] = Field(None, description="调用结果")
    error: Optional[str] = Field(None, description="错误信息")
    source: Optional[str] = Field(None, description="工具来源")


@router.get("/tools", response_model=List[Dict[str, Any]])
async def get_all_tools(refresh: bool = False):
    """
    获取所有可用工具（内部+外部MCP）
    
    Args:
        refresh: 是否刷新缓存
        
    Returns:
        工具列表
    """
    try:
        mcp_tool_manager = get_mcp_tool_manager()
        tools = await mcp_tool_manager.get_all_tools(refresh=refresh)
        return [tool.__dict__ for tool in tools]
    except Exception as e:
        app_logger.error(f"获取工具列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools/{tool_id}", response_model=Optional[Dict[str, Any]])
async def get_tool_info(tool_id: str):
    """
    获取单个工具信息
    
    Args:
        tool_id: 工具ID
        
    Returns:
        工具信息
    """
    try:
        mcp_tool_manager = get_mcp_tool_manager()
        await mcp_tool_manager.get_all_tools()
        tool = mcp_tool_manager.get_tool_by_id(tool_id)
        if tool:
            return tool.__dict__
        else:
            raise HTTPException(status_code=404, detail=f"工具 {tool_id} 未找到")
    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"获取工具信息失败 {tool_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tools/{tool_id}/call", response_model=ToolCallResponse)
async def call_mcp_tool(tool_id: str, request: ToolCallRequest):
    """
    调用工具（自动判断内部或外部）
    
    Args:
        tool_id: 工具ID
        request: 调用请求
        
    Returns:
        调用结果
    """
    try:
        mcp_tool_manager = get_mcp_tool_manager()
        result = await mcp_tool_manager.call_tool(tool_id, request.parameters)
        return ToolCallResponse(**result)
    except Exception as e:
        app_logger.error(f"调用工具失败 {tool_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tools/search", response_model=List[Dict[str, Any]])
async def search_tools(query: str, limit: int = 10):
    """
    搜索工具
    
    Args:
        query: 搜索关键词
        limit: 返回数量限制
        
    Returns:
        匹配的工具列表
    """
    try:
        mcp_tool_manager = get_mcp_tool_manager()
        tools = await mcp_tool_manager.search_tools(query, limit)
        return [tool.__dict__ for tool in tools]
    except Exception as e:
        app_logger.error(f"搜索工具失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/servers", response_model=List[str])
async def list_servers():
    """
    列出所有已注册的外部MCP服务器
    
    Returns:
        服务器名称列表
    """
    try:
        discovery = get_mcp_discovery()
        return discovery.list_servers()
    except Exception as e:
        app_logger.error(f"获取服务器列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/servers")
async def register_server(config: ServerConfigRequest):
    """
    注册外部MCP服务器
    
    Args:
        config: 服务器配置
        
    Returns:
        注册结果
    """
    try:
        mcp_tool_manager = get_mcp_tool_manager()
        connection_config = MCPConnectionConfig(
            name=config.name,
            url=config.url,
            transport=MCPTransport.HTTP,
            api_key=config.api_key,
            timeout=config.timeout,
        )
        await mcp_tool_manager.register_external_server(connection_config)
        return {"success": True, "message": f"服务器 {config.name} 注册成功"}
    except Exception as e:
        app_logger.error(f"注册服务器失败 {config.name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/servers/{name}")
async def unregister_server(name: str):
    """
    注销外部MCP服务器
    
    Args:
        name: 服务器名称
        
    Returns:
        注销结果
    """
    try:
        mcp_tool_manager = get_mcp_tool_manager()
        await mcp_tool_manager.unregister_external_server(name)
        return {"success": True, "message": f"服务器 {name} 注销成功"}
    except Exception as e:
        app_logger.error(f"注销服务器失败 {name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=Dict[str, Any])
async def get_status():
    """
    获取MCP系统状态
    
    Returns:
        系统状态
    """
    try:
        mcp_tool_manager = get_mcp_tool_manager()
        status = await mcp_tool_manager.get_server_status()
        return status
    except Exception as e:
        app_logger.error(f"获取系统状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/server-info")
async def get_server_info():
    """
    获取MCP Server信息
    
    Returns:
        服务器信息
    """
    try:
        mcp_server = get_mcp_server()
        info = {
            "name": mcp_server.config.name,
            "version": mcp_server.config.version,
            "description": mcp_server.config.description,
            "is_available": mcp_server.is_available(),
            "tools_count": len(mcp_server.get_tools()),
        }
        return info
    except Exception as e:
        app_logger.error(f"获取服务器信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/discover/auto", summary="自动发现MCP服务器")
async def auto_discover():
    """
    自动发现所有MCP服务器（从配置文件/环境变量/目录）
    
    Returns:
        发现结果
    """
    try:
        discovery = get_mcp_dynamic_discovery()
        await discovery.auto_discover()
        
        servers = discovery.list_servers()
        tools = await discovery.discover_all_tools()
        
        return {
            "success": True,
            "message": f"自动发现完成，共发现 {len(servers)} 个服务器，{len(tools)} 个工具",
            "servers": servers,
            "tool_count": len(tools)
        }
    except Exception as e:
        app_logger.error(f"自动发现失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/discover/reload", summary="热重载MCP服务器")
async def reload_server(name: Optional[str] = None):
    """
    热重载MCP服务器（无需重启即可发现新服务）
    
    Args:
        name: 服务器名称（可选，不传则重载所有服务器）
        
    Returns:
        重载结果
    """
    try:
        discovery = get_mcp_dynamic_discovery()
        
        if name:
            success = await discovery.reload_server(name)
            if success:
                return {"success": True, "message": f"服务器 {name} 热重载成功"}
            else:
                return {"success": False, "message": f"服务器 {name} 热重载失败"}
        else:
            await discovery.reload_all()
            servers = discovery.list_servers()
            return {"success": True, "message": f"所有服务器热重载完成，共 {len(servers)} 个服务器"}
    except Exception as e:
        app_logger.error(f"热重载失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/discover/heartbeat", summary="检查服务器心跳")
async def check_heartbeat():
    """
    检查所有服务器的心跳状态
    
    Returns:
        心跳状态列表
    """
    try:
        discovery = get_mcp_dynamic_discovery()
        heartbeat = await discovery.check_heartbeat()
        return heartbeat
    except Exception as e:
        app_logger.error(f"检查心跳失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/discover/registry", summary="获取工具注册表")
async def get_tool_registry():
    """
    获取所有已发现工具的注册表
    
    Returns:
        工具注册表
    """
    try:
        discovery = get_mcp_dynamic_discovery()
        registry = discovery.get_tool_registry()
        return {
            "total_tools": len(registry),
            "registry": registry
        }
    except Exception as e:
        app_logger.error(f"获取工具注册表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/discover/history", summary="获取发现历史")
async def get_discovery_history(limit: int = 20):
    """
    获取MCP服务器发现历史记录
    
    Args:
        limit: 返回数量限制
        
    Returns:
        发现历史列表
    """
    try:
        discovery = get_mcp_dynamic_discovery()
        history = discovery.get_discovery_history(limit)
        return {
            "total_records": len(history),
            "history": history
        }
    except Exception as e:
        app_logger.error(f"获取发现历史失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/discover/status", summary="获取动态发现状态")
async def get_dynamic_discovery_status():
    """
    获取动态发现服务的完整状态
    
    Returns:
        服务器状态列表
    """
    try:
        discovery = get_mcp_dynamic_discovery()
        status = discovery.get_server_status()
        heartbeat = await discovery.check_heartbeat()
        
        for server_name, server_status in status.items():
            if server_name in heartbeat:
                server_status["heartbeat"] = heartbeat[server_name]
        
        return status
    except Exception as e:
        app_logger.error(f"获取动态发现状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))