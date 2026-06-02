"""工具注册表 - 管理工具的注册、发现和管理"""
from typing import Dict, List, Optional, Any, Callable
from collections import defaultdict
from datetime import datetime
import json
import os
from app.core.logger import app_logger
from app.agents.tools.tool_metadata import (
    Tool, ToolMetadata, ToolCategory, ToolStatus, 
    ToolParameter, ToolExecutionResult
)

class ToolRegistry:
    """
    工具注册表
    
    提供工具的注册、发现、更新、删除等管理功能
    """
    
    def __init__(self):
        # 工具注册表: tool_id -> Tool
        self._tools: Dict[str, Tool] = {}
        
        # 按分类索引: category -> [tool_ids]
        self._category_index: Dict[str, List[str]] = defaultdict(list)
        
        # 按标签索引: tag -> [tool_ids]
        self._tag_index: Dict[str, List[str]] = defaultdict(list)
        
        # 工具执行函数: tool_id -> function
        self._executors: Dict[str, Callable] = {}
        
        # 缓存
        self._cache: Dict[str, Any] = {}
        
        # 加载内置工具
        self._load_builtin_tools()
    
    def _load_builtin_tools(self):
        """加载内置工具"""
        from app.agents.tools.builtin import get_builtin_tools
        
        builtin_tools = get_builtin_tools()
        for tool in builtin_tools:
            self.register(tool)
        
        app_logger.info(f"[Registry] 已加载 {len(builtin_tools)} 个内置工具")
    
    def register(self, tool: Tool, executor: Optional[Callable] = None) -> bool:
        """
        注册工具
        
        Args:
            tool: 工具实例
            executor: 执行函数（可选）
            
        Returns:
            是否注册成功
        """
        tool_id = tool.metadata.tool_id
        
        if tool_id in self._tools:
            app_logger.warning(f"[Registry] 工具 {tool_id} 已存在，将被覆盖")
        
        # 注册工具
        self._tools[tool_id] = tool
        
        # 注册执行函数
        if executor:
            self._executors[tool_id] = executor
            tool.set_function(executor)
        
        # 更新索引
        self._update_indexes(tool)
        
        app_logger.info(f"[Registry] 注册工具: {tool_id}")
        return True
    
    def unregister(self, tool_id: str) -> bool:
        """
        注销工具
        
        Args:
            tool_id: 工具ID
            
        Returns:
            是否成功注销
        """
        if tool_id not in self._tools:
            app_logger.warning(f"[Registry] 工具 {tool_id} 不存在")
            return False
        
        tool = self._tools[tool_id]
        
        # 从索引中移除
        self._remove_from_indexes(tool)
        
        # 删除工具和执行器
        del self._tools[tool_id]
        if tool_id in self._executors:
            del self._executors[tool_id]
        
        # 清除缓存
        if tool_id in self._cache:
            del self._cache[tool_id]
        
        app_logger.info(f"[Registry] 注销工具: {tool_id}")
        return True
    
    def get(self, tool_id: str) -> Optional[Tool]:
        """获取工具"""
        return self._tools.get(tool_id)
    
    def get_all(self) -> List[Tool]:
        """获取所有工具"""
        return list(self._tools.values())
    
    def get_by_category(self, category: ToolCategory) -> List[Tool]:
        """按分类获取工具"""
        tool_ids = self._category_index.get(category.value, [])
        return [self._tools[tid] for tid in tool_ids if tid in self._tools]
    
    def get_by_tag(self, tag: str) -> List[Tool]:
        """按标签获取工具"""
        tool_ids = self._tag_index.get(tag, [])
        return [self._tools[tid] for tid in tool_ids if tid in self._tools]
    
    def search(self, query: str, limit: int = 10) -> List[Tool]:
        """
        搜索工具
        
        Args:
            query: 搜索关键词
            limit: 返回数量限制
            
        Returns:
            匹配的工具列表
        """
        query_lower = query.lower()
        results = []
        
        for tool in self._tools.values():
            # 匹配名称
            if query_lower in tool.metadata.name.lower():
                results.append((tool, 1.0))
                continue
            
            # 匹配描述
            if query_lower in tool.metadata.description.lower():
                results.append((tool, 0.8))
                continue
            
            # 匹配标签
            if any(query_lower in tag.lower() for tag in tool.metadata.tags):
                results.append((tool, 0.6))
                continue
            
            # 匹配分类
            if query_lower in tool.metadata.category.value.lower():
                results.append((tool, 0.5))
        
        # 按分数排序
        results.sort(key=lambda x: x[1], reverse=True)
        return [tool for tool, score in results[:limit]]
    
    def get_schemas(self, tool_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        获取工具的schema列表
        
        Args:
            tool_ids: 工具ID列表（None表示获取所有）
            
        Returns:
            schema列表
        """
        if tool_ids is None:
            tools = self._tools.values()
        else:
            tools = [self._tools[tid] for tid in tool_ids if tid in self._tools]
        
        return [tool.get_schema() for tool in tools]
    
    def get_all_metadata(self) -> List[Dict[str, Any]]:
        """获取所有工具的元数据"""
        return [tool.metadata.to_dict() for tool in self._tools.values()]
    
    def update_metadata(self, tool_id: str, metadata: Dict[str, Any]) -> bool:
        """
        更新工具元数据
        
        Args:
            tool_id: 工具ID
            metadata: 新的元数据
            
        Returns:
            是否更新成功
        """
        tool = self._tools.get(tool_id)
        if not tool:
            return False
        
        # 更新字段
        for key, value in metadata.items():
            if hasattr(tool.metadata, key):
                setattr(tool.metadata, key, value)
        
        tool.metadata.updated_at = datetime.now()
        
        # 更新索引
        self._update_indexes(tool)
        
        app_logger.info(f"[Registry] 更新工具元数据: {tool_id}")
        return True
    
    def set_status(self, tool_id: str, status: ToolStatus) -> bool:
        """设置工具状态"""
        tool = self._tools.get(tool_id)
        if not tool:
            return False
        
        tool.metadata.status = status
        tool.metadata.updated_at = datetime.now()
        
        app_logger.info(f"[Registry] 设置工具状态: {tool_id} -> {status.value}")
        return True
    
    def _update_indexes(self, tool: Tool):
        """更新索引"""
        # 更新分类索引
        category = tool.metadata.category.value if isinstance(tool.metadata.category, ToolCategory) else tool.metadata.category
        if category not in self._category_index:
            self._category_index[category] = []
        if tool.metadata.tool_id not in self._category_index[category]:
            self._category_index[category].append(tool.metadata.tool_id)
        
        # 更新标签索引
        for tag in tool.metadata.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = []
            if tool.metadata.tool_id not in self._tag_index[tag]:
                self._tag_index[tag].append(tool.metadata.tool_id)
    
    def _remove_from_indexes(self, tool: Tool):
        """从索引中移除"""
        # 从分类索引移除
        category = tool.metadata.category.value if isinstance(tool.metadata.category, ToolCategory) else tool.metadata.category
        if category in self._category_index:
            if tool.metadata.tool_id in self._category_index[category]:
                self._category_index[category].remove(tool.metadata.tool_id)
        
        # 从标签索引移除
        for tag in tool.metadata.tags:
            if tag in self._tag_index:
                if tool.metadata.tool_id in self._tag_index[tag]:
                    self._tag_index[tag].remove(tool.metadata.tool_id)
    
    def export_tools(self, file_path: str) -> bool:
        """
        导出工具配置到文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            是否导出成功
        """
        try:
            data = {
                "export_time": datetime.now().isoformat(),
                "tools": self.get_all_metadata(),
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            app_logger.info(f"[Registry] 导出工具配置到: {file_path}")
            return True
        
        except Exception as e:
            app_logger.error(f"[Registry] 导出工具配置失败: {e}")
            return False
    
    def import_tools(self, file_path: str) -> int:
        """
        从文件导入工具配置
        
        Args:
            file_path: 文件路径
            
        Returns:
            导入的工具数量
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            count = 0
            for tool_data in data.get("tools", []):
                # 创建工具元数据
                metadata = ToolMetadata(
                    tool_id=tool_data["tool_id"],
                    name=tool_data["name"],
                    description=tool_data["description"],
                    category=ToolCategory(tool_data.get("category", "custom")),
                    tags=tool_data.get("tags", []),
                    version=tool_data.get("version", "1.0.0"),
                    author=tool_data.get("author", ""),
                )
                
                # 创建工具
                tool = Tool(metadata)
                self.register(tool)
                count += 1
            
            app_logger.info(f"[Registry] 从 {file_path} 导入 {count} 个工具")
            return count
        
        except Exception as e:
            app_logger.error(f"[Registry] 导入工具配置失败: {e}")
            return 0
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        total_tools = len(self._tools)
        active_tools = sum(1 for t in self._tools.values() if t.metadata.status == ToolStatus.ACTIVE)
        
        category_stats = {}
        for category, tool_ids in self._category_index.items():
            category_stats[category] = len(tool_ids)
        
        total_calls = sum(t.metadata.call_count for t in self._tools.values())
        total_success = sum(t.metadata.success_count for t in self._tools.values())
        
        return {
            "total_tools": total_tools,
            "active_tools": active_tools,
            "inactive_tools": total_tools - active_tools,
            "by_category": category_stats,
            "total_calls": total_calls,
            "total_success": total_success,
            "overall_success_rate": total_success / total_calls if total_calls > 0 else 0,
        }


# 全局工具注册表实例
_registry: Optional[ToolRegistry] = None

def get_tool_registry() -> ToolRegistry:
    """获取全局工具注册表"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
