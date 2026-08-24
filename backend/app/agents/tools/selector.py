"""工具选择器 - 根据上下文智能选择合适的工具"""
from typing import Dict, List, Any, Optional, Tuple
from app.core.logger import app_logger
from app.agents.tools.registry import get_tool_registry
from app.agents.tools.tool_metadata import Tool, ToolCategory

class ToolSelector:
    """
    工具选择器
    
    根据问题上下文智能选择合适的工具，包括：
    1. 关键词匹配选择
    2. 语义相似度选择（可选，需要LLM）
    3. 多工具组合选择
    4. 依赖分析
    """
    
    def __init__(self, allowed_tool_ids: Optional[List[str]] = None):
        self.registry = get_tool_registry()
        self.allowed_tool_ids = set(allowed_tool_ids or [])
        # 关键词到工具ID的映射
        self._keyword_tool_mapping = self._build_keyword_mapping()

    def _iter_allowed_tools(self) -> List[Tool]:
        tools = self.registry.get_all()
        if not self.allowed_tool_ids:
            return tools
        return [tool for tool in tools if tool.metadata.tool_id in self.allowed_tool_ids]
    
    def _build_keyword_mapping(self) -> Dict[str, List[str]]:
        """构建关键词到工具的映射"""
        mapping = {}
        
        # 从所有工具构建映射
        for tool in self._iter_allowed_tools():
            # 从名称构建
            words = tool.metadata.name.split()
            for word in words:
                if word not in mapping:
                    mapping[word] = []
                if tool.metadata.tool_id not in mapping[word]:
                    mapping[word].append(tool.metadata.tool_id)
            
            # 从标签构建
            for tag in tool.metadata.tags:
                if tag not in mapping:
                    mapping[tag] = []
                if tool.metadata.tool_id not in mapping[tag]:
                    mapping[tag].append(tool.metadata.tool_id)
            
            # 从描述关键词构建
            keywords = self._extract_keywords(tool.metadata.description)
            for keyword in keywords:
                if keyword not in mapping:
                    mapping[keyword] = []
                if tool.metadata.tool_id not in mapping[keyword]:
                    mapping[keyword].append(tool.metadata.tool_id)
        
        return mapping
    
    def _extract_keywords(self, text: str) -> List[str]:
        """从文本中提取关键词"""
        # 简单的关键词提取
        stop_words = {"的", "了", "和", "是", "在", "有", "与", "对", "为", "等", "以及"}
        
        words = []
        current_word = ""
        for char in text:
            if char.isalnum():
                current_word += char
            else:
                if current_word and current_word not in stop_words and len(current_word) > 1:
                    words.append(current_word)
                current_word = ""
        
        if current_word and current_word not in stop_words and len(current_word) > 1:
            words.append(current_word)
        
        return words
    
    def select_tools(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        max_tools: int = 5,
        min_score: float = 0.3,
    ) -> List[Tuple[Tool, float]]:
        """
        根据查询选择工具
        
        Args:
            query: 用户查询
            context: 上下文信息
            max_tools: 最大选择工具数
            min_score: 最低选择分数
            
        Returns:
            工具列表（按分数排序），每个元素为 (tool, score) 元组
        """
        # 1. 关键词匹配
        keyword_matches = self._match_by_keywords(query)
        
        # 2. 分类匹配
        category_matches = self._match_by_category(query, context)
        
        # 3. 上下文匹配
        context_matches = self._match_by_context(context)
        
        # 合并分数
        all_scores = {}
        for tool_id, score in keyword_matches.items():
            all_scores[tool_id] = all_scores.get(tool_id, 0) + score * 0.5
        
        for tool_id, score in category_matches.items():
            all_scores[tool_id] = all_scores.get(tool_id, 0) + score * 0.3
        
        for tool_id, score in context_matches.items():
            all_scores[tool_id] = all_scores.get(tool_id, 0) + score * 0.2
        
        # 排序并返回
        sorted_tools = sorted(all_scores.items(), key=lambda x: x[1], reverse=True)
        
        results = []
        for tool_id, score in sorted_tools[:max_tools]:
            if score >= min_score:
                tool = self.registry.get(tool_id)
                if tool:
                    results.append((tool, score))
        
        return results
    
    def _match_by_keywords(self, query: str) -> Dict[str, float]:
        """根据关键词匹配"""
        scores = {}
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        for tool in self._iter_allowed_tools():
            score = 0.0
            tool_words = set()
            
            # 从名称匹配
            name_words = self._extract_keywords(tool.metadata.name)
            tool_words.update(name_words)
            
            # 从标签匹配
            tool_words.update([tag.lower() for tag in tool.metadata.tags])
            
            # 从描述匹配
            desc_words = self._extract_keywords(tool.metadata.description)
            tool_words.update(desc_words)
            
            # 计算匹配分数
            matches = len(query_words.intersection(tool_words))
            if matches > 0:
                score = matches / max(len(query_words), len(tool_words))
            
            if score > 0:
                scores[tool.metadata.tool_id] = score
        
        return scores
    
    def _match_by_category(self, query: str, context: Optional[Dict[str, Any]]) -> Dict[str, float]:
        """根据分类匹配"""
        scores = {}
        query_lower = query.lower()
        
        # 分类关键词映射
        category_keywords = {
            ToolCategory.MEETING: ["会议", "meeting", "会议纪要", "会议记录", "参会"],
            ToolCategory.MINUTES: ["纪要", "会议纪要", "总结", "记录"],
            ToolCategory.TODO: ["待办", "todo", "任务", "action", "要做", "需要做"],
            ToolCategory.DOCUMENT: ["文档", "文件", "doc", "pdf"],
            ToolCategory.SEARCH: ["搜索", "查找", "search", "找"],
            ToolCategory.INFO: ["查询", "了解", "知道", "信息"],
            ToolCategory.COMPUTATION: ["计算", "算", "数学", "统计"],
        }
        
        for tool in self._iter_allowed_tools():
            score = 0.0
            category_keywords_list = category_keywords.get(tool.metadata.category, [])
            
            for keyword in category_keywords_list:
                if keyword.lower() in query_lower:
                    score = 0.8
                    break
            
            if score > 0:
                scores[tool.metadata.tool_id] = score
        
        return scores
    
    def _match_by_context(self, context: Optional[Dict[str, Any]]) -> Dict[str, float]:
        """根据上下文匹配"""
        scores = {}
        
        if not context:
            return scores
        
        # 根据上下文中提到的实体类型选择工具
        if "meeting_id" in context:
            # 提到了会议ID，优先选择会议相关工具
            for tool in self._iter_allowed_tools():
                if tool.metadata.category == ToolCategory.MEETING:
                    scores[tool.metadata.tool_id] = 0.6
        
        if "document_id" in context:
            # 提到了文档ID，优先选择文档相关工具
            for tool in self._iter_allowed_tools():
                if tool.metadata.category == ToolCategory.DOCUMENT:
                    scores[tool.metadata.tool_id] = 0.6
        
        if "task_type" in context:
            task_type = context["task_type"]
            for tool in self._iter_allowed_tools():
                if task_type.lower() in tool.metadata.description.lower():
                    scores[tool.metadata.tool_id] = scores.get(tool.metadata.tool_id, 0) + 0.5
        
        return scores
    
    def select_for_task_type(
        self,
        task_type: str,
        max_tools: int = 3,
    ) -> List[Tool]:
        """
        根据任务类型选择工具
        
        Args:
            task_type: 任务类型（retrieve, qa, minutes, todo, controversy, combine）
            max_tools: 最大工具数
            
        Returns:
            工具列表
        """
        # 任务类型到工具的映射
        task_type_tools = {
            "retrieve": ["search_meeting", "search_document", "knowledge_base_search"],
            "qa": [],
            "minutes": ["generate_minutes"],
            "todo": ["extract_todos"],
            "controversy": ["extract_controversies"],
            "combine": [],
            "multi": ["search_meeting", "extract_todos", "extract_controversies", "generate_minutes"],
        }
        
        tool_ids = task_type_tools.get(task_type.lower(), [])
        tools = []
        
        for tool_id in tool_ids[:max_tools]:
            tool = self.registry.get(tool_id)
            if tool:
                tools.append(tool)
        
        return tools
    
    def get_tool_suggestions(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        获取工具建议
        
        Args:
            query: 用户查询
            limit: 返回数量
            
        Returns:
            工具建议列表
        """
        tools = self.select_tools(query, max_tools=limit)
        
        suggestions = []
        for tool, score in tools:
            suggestions.append({
                "tool_id": tool.metadata.tool_id,
                "name": tool.metadata.name,
                "description": tool.metadata.description,
                "score": score,
                "category": tool.metadata.category.value,
                "confidence": "high" if score > 0.7 else "medium" if score > 0.5 else "low",
            })
        
        return suggestions
    
    def analyze_dependencies(
        self,
        selected_tools: List[Tool],
    ) -> List[List[Tool]]:
        """
        分析工具依赖关系，返回可并行执行的工具组
        
        Args:
            selected_tools: 选中的工具列表
            
        Returns:
            可并行执行的工具分组列表
        """
        if not selected_tools:
            return []
        
        # 根据工具类型分组
        groups = []
        processed = set()
        
        # 第一组：检索类工具（可并行）
        retrieval_tools = [
            t for t in selected_tools
            if t.metadata.category in [ToolCategory.SEARCH, ToolCategory.RETRIEVAL]
            and t.metadata.tool_id not in processed
        ]
        if retrieval_tools:
            groups.append(retrieval_tools)
            processed.update([t.metadata.tool_id for t in retrieval_tools])
        
        # 第二组：提取类工具（可并行）
        extraction_tools = [
            t for t in selected_tools
            if t.metadata.category in [ToolCategory.TODO, ToolCategory.MEETING]
            and t.metadata.tool_id not in processed
        ]
        if extraction_tools:
            groups.append(extraction_tools)
            processed.update([t.metadata.tool_id for t in extraction_tools])
        
        # 第三组：生成类工具（串行）
        generation_tools = [
            t for t in selected_tools
            if t.metadata.category in [ToolCategory.MINUTES, ToolCategory.INFO]
            and t.metadata.tool_id not in processed
        ]
        if generation_tools:
            groups.append(generation_tools)
            processed.update([t.metadata.tool_id for t in generation_tools])
        
        # 第四组：其他工具
        other_tools = [
            t for t in selected_tools
            if t.metadata.tool_id not in processed
        ]
        if other_tools:
            groups.append(other_tools)
        
        return groups
    
    def format_tools_for_prompt(self) -> str:
        """格式化工具信息用于 prompt"""
        tools = self._iter_allowed_tools()
        lines = [
            "可用工具（tool_name 必须严格使用下列 tool_id，不要使用中文名称）：",
        ]
        
        for tool in tools:
            required_params = []
            optional_params = []
            for param in tool.metadata.parameters:
                target = required_params if getattr(param, "required", False) else optional_params
                param_type = getattr(param, "type", "string")
                default = getattr(param, "default", None)
                default_text = f", default={default}" if default is not None else ""
                target.append(f"{param.name}:{param_type}{default_text} - {param.description}")

            lines.append(f"- tool_id: {tool.metadata.tool_id}")
            lines.append(f"  name: {tool.metadata.name}")
            lines.append(f"  description: {tool.metadata.description}")
            lines.append(f"  required_args: {required_params or []}")
            lines.append(f"  optional_args: {optional_params or []}")
            lines.append(f"  example: {{\"tool_name\": \"{tool.metadata.tool_id}\", \"arguments\": {{...}}}}")
        
        return "\n".join(lines)


# 全局选择器实例
_selector: Optional[ToolSelector] = None

def get_tool_selector() -> ToolSelector:
    """获取全局工具选择器"""
    global _selector
    if _selector is None:
        _selector = ToolSelector()
    return _selector
