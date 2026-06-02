"""自定义工具管理器 - 支持用户添加自定义工具"""
from typing import Dict, Any, Callable, Optional
import json
import os
from datetime import datetime
from app.core.logger import app_logger
from app.agents.tools.registry import get_tool_registry
from app.agents.tools.tool_metadata import (
    Tool, ToolMetadata, ToolParameter, ToolCategory, ToolStatus
)

class CustomToolManager:
    """
    自定义工具管理器
    
    支持用户：
    1. 注册自定义工具
    2. 从JSON文件导入工具
    3. 导出工具到JSON文件
    4. 管理工具的启用/禁用
    """
    
    def __init__(self):
        self.registry = get_tool_registry()
        self.custom_tools_dir = "./custom_tools"
        self._ensure_directory()
    
    def _ensure_directory(self):
        """确保自定义工具目录存在"""
        if not os.path.exists(self.custom_tools_dir):
            os.makedirs(self.custom_tools_dir)
            app_logger.info(f"[CustomTools] 创建自定义工具目录: {self.custom_tools_dir}")
    
    def register_custom_tool(
        self,
        tool_id: str,
        name: str,
        description: str,
        category: str = "custom",
        parameters: list = None,
        executor: Callable = None,
        tags: list = None,
        version: str = "1.0.0",
        author: str = "user",
    ) -> bool:
        """
        注册自定义工具
        
        Args:
            tool_id: 工具ID（唯一标识）
            name: 工具名称
            description: 工具描述
            category: 分类
            parameters: 参数定义列表
            executor: 执行函数
            tags: 标签
            version: 版本
            author: 作者
            
        Returns:
            是否注册成功
        """
        # 检查工具是否已存在
        if self.registry.get(tool_id):
            app_logger.warning(f"[CustomTools] 工具 {tool_id} 已存在，将被覆盖")
        
        # 创建工具元数据
        metadata = ToolMetadata(
            tool_id=tool_id,
            name=name,
            description=description,
            category=ToolCategory(category) if isinstance(category, str) else category,
            tags=tags or [],
            version=version,
            author=author,
            status=ToolStatus.ACTIVE,
        )
        
        # 添加参数
        if parameters:
            for param in parameters:
                if isinstance(param, dict):
                    metadata.parameters.append(ToolParameter(**param))
                elif isinstance(param, ToolParameter):
                    metadata.parameters.append(param)
        
        # 创建工具
        tool = Tool(metadata)
        
        # 注册工具
        if executor:
            self.registry.register(tool, executor)
        else:
            self.registry.register(tool)
        
        app_logger.info(f"[CustomTools] 注册自定义工具: {tool_id}")
        return True
    
    def register_from_json(self, json_path: str) -> bool:
        """
        从JSON文件注册自定义工具
        
        Args:
            json_path: JSON文件路径
            
        Returns:
            是否注册成功
        """
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 解析工具定义
            tool_def = data.get("tool", data)
            
            # 提取执行函数（如果有）
            executor = None
            if "function_name" in tool_def:
                # 尝试从模块导入函数
                try:
                    module_path = tool_def.get("module", "app.agents.tools.builtin")
                    import importlib
                    module = importlib.import_module(module_path)
                    executor = getattr(module, tool_def["function_name"], None)
                except Exception as e:
                    app_logger.warning(f"[CustomTools] 无法加载函数 {tool_def['function_name']}: {e}")
            
            # 注册工具
            return self.register_custom_tool(
                tool_id=tool_def["tool_id"],
                name=tool_def["name"],
                description=tool_def["description"],
                category=tool_def.get("category", "custom"),
                parameters=tool_def.get("parameters", []),
                executor=executor,
                tags=tool_def.get("tags", []),
                version=tool_def.get("version", "1.0.0"),
                author=tool_def.get("author", "user"),
            )
        
        except Exception as e:
            app_logger.error(f"[CustomTools] 从JSON注册工具失败: {e}")
            return False
    
    def export_to_json(self, tool_id: str, output_path: str = None) -> bool:
        """
        导出工具到JSON文件
        
        Args:
            tool_id: 工具ID
            output_path: 输出路径（可选）
            
        Returns:
            是否导出成功
        """
        tool = self.registry.get(tool_id)
        if not tool:
            app_logger.error(f"[CustomTools] 工具 {tool_id} 不存在")
            return False
        
        if output_path is None:
            output_path = os.path.join(self.custom_tools_dir, f"{tool_id}.json")
        
        try:
            data = {
                "export_time": datetime.now().isoformat(),
                "tool": tool.metadata.to_dict(),
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            app_logger.info(f"[CustomTools] 导出工具到: {output_path}")
            return True
        
        except Exception as e:
            app_logger.error(f"[CustomTools] 导出工具失败: {e}")
            return False
    
    def load_all_from_directory(self) -> int:
        """
        从自定义工具目录加载所有工具
        
        Returns:
            加载的工具数量
        """
        count = 0
        for filename in os.listdir(self.custom_tools_dir):
            if filename.endswith('.json'):
                file_path = os.path.join(self.custom_tools_dir, filename)
                if self.register_from_json(file_path):
                    count += 1
        
        app_logger.info(f"[CustomTools] 从目录加载了 {count} 个自定义工具")
        return count
    
    def save_all_custom_tools(self) -> bool:
        """
        保存所有自定义工具到目录
        
        Returns:
            是否保存成功
        """
        try:
            # 获取所有自定义工具（通过检查是否有自定义标记）
            for tool in self.registry.get_all():
                if tool.metadata.author == "user" or "custom" in tool.metadata.tags:
                    self.export_to_json(tool.metadata.tool_id)
            
            app_logger.info("[CustomTools] 保存所有自定义工具完成")
            return True
        
        except Exception as e:
            app_logger.error(f"[CustomTools] 保存自定义工具失败: {e}")
            return False
    
    def create_sample_tools(self):
        """创建示例自定义工具"""
        samples = [
            {
                "tool_id": "weather_query",
                "name": "天气查询",
                "description": "查询指定城市的天气信息",
                "category": "info",
                "tags": ["weather", "天气", "查询"],
                "parameters": [
                    {"name": "city", "type": "string", "description": "城市名称", "required": True},
                    {"name": "date", "type": "string", "description": "查询日期（可选，默认今天）", "required": False},
                ],
            },
            {
                "tool_id": "unit_converter",
                "name": "单位转换",
                "description": "进行常用单位之间的转换",
                "category": "computation",
                "tags": ["convert", "转换", "单位"],
                "parameters": [
                    {"name": "value", "type": "float", "description": "要转换的数值", "required": True},
                    {"name": "from_unit", "type": "string", "description": "源单位", "required": True, "enum_values": ["km", "miles", "kg", "lbs"]},
                    {"name": "to_unit", "type": "string", "description": "目标单位", "required": True, "enum_values": ["km", "miles", "kg", "lbs"]},
                ],
            },
            {
                "tool_id": "code_executor",
                "name": "代码执行器",
                "description": "安全地执行Python代码片段",
                "category": "computation",
                "tags": ["code", "代码", "执行", "python"],
                "parameters": [
                    {"name": "code", "type": "string", "description": "要执行的Python代码", "required": True},
                    {"name": "timeout", "type": "integer", "description": "超时时间（秒）", "required": False, "default": 10},
                ],
            },
        ]
        
        for sample in samples:
            self.register_custom_tool(**sample)
        
        app_logger.info(f"[CustomTools] 创建了 {len(samples)} 个示例自定义工具")


# 全局管理器实例
_custom_tool_manager: Optional[CustomToolManager] = None

def get_custom_tool_manager() -> CustomToolManager:
    """获取全局自定义工具管理器"""
    global _custom_tool_manager
    if _custom_tool_manager is None:
        _custom_tool_manager = CustomToolManager()
    return _custom_tool_manager
