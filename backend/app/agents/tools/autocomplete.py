"""工具参数自动补全服务"""
import re
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum


class SuggestionType(str, Enum):
    """建议类型"""
    ENUM_VALUE = "enum"
    DEFAULT_VALUE = "default"
    HISTORICAL_VALUE = "historical"
    PATTERN_MATCH = "pattern"
    CONTEXTUAL = "contextual"


@dataclass
class ParameterSuggestion:
    """参数建议"""
    param_name: str
    suggestion_type: SuggestionType
    values: List[Any]
    score: float = 1.0
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CompletionContext:
    """补全上下文"""
    tool_name: str
    current_args: Dict[str, Any]
    partial_arg: Optional[str] = None
    user_history: List[Dict[str, Any]] = field(default_factory=list)
    session_context: Dict[str, Any] = field(default_factory=dict)


class ToolParameterAutocompleter:
    """工具参数自动补全器"""
    
    def __init__(self):
        self._history: Dict[str, List[Dict[str, Any]]] = {}
        self._contextual_hints: Dict[str, Callable] = {}
        self._pattern_hints: Dict[str, List[str]] = {
            "meeting_id": ["最近查看的会议ID"],
            "document_id": ["最近上传的文档ID"],
            "user_id": ["当前用户ID"],
            "date": ["YYYY-MM-DD", "YYYY-MM-DD HH:mm:ss"],
            "email": ["xxx@example.com"],
            "url": ["https://", "http://"]
        }
    
    def register_contextual_hint(self, param_pattern: str, hint_func: Callable):
        """注册上下文提示函数"""
        self._contextual_hints[param_pattern] = hint_func
    
    def record_usage(self, tool_name: str, args: Dict[str, Any]):
        """记录工具使用历史"""
        if tool_name not in self._history:
            self._history[tool_name] = []
        
        self._history[tool_name].append({
            "args": args,
            "timestamp": self._get_timestamp()
        })
        
        if len(self._history[tool_name]) > 100:
            self._history[tool_name] = self._history[tool_name][-100:]
    
    def _get_timestamp(self) -> str:
        """获取时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def get_suggestions(
        self,
        tool_info: Dict[str, Any],
        context: CompletionContext
    ) -> Dict[str, List[ParameterSuggestion]]:
        """
        获取参数补全建议
        
        Args:
            tool_info: 工具信息（包含参数定义）
            context: 补全上下文
            
        Returns:
            参数建议字典 {param_name: [suggestions]}
        """
        suggestions = {}
        parameters = tool_info.get("parameters", [])
        
        for param in parameters:
            param_name = param.get("name")
            param_type = param.get("type", "string")
            
            if param_name in context.current_args:
                continue
            
            param_suggestions = []
            
            if "enum" in param and param["enum"]:
                param_suggestions.append(ParameterSuggestion(
                    param_name=param_name,
                    suggestion_type=SuggestionType.ENUM_VALUE,
                    values=param["enum"],
                    reason="枚举值"
                ))
            
            if "default" in param and param["default"] is not None:
                param_suggestions.append(ParameterSuggestion(
                    param_name=param_name,
                    suggestion_type=SuggestionType.DEFAULT_VALUE,
                    values=[param["default"]],
                    reason="默认值"
                ))
            
            historical = self._get_historical_values(context.tool_name, param_name)
            if historical:
                param_suggestions.append(ParameterSuggestion(
                    param_name=param_name,
                    suggestion_type=SuggestionType.HISTORICAL_VALUE,
                    values=historical,
                    reason="历史使用值"
                ))
            
            pattern = self._get_pattern_suggestions(param_name, param_type, context)
            if pattern:
                param_suggestions.append(ParameterSuggestion(
                    param_name=param_name,
                    suggestion_type=SuggestionType.PATTERN_MATCH,
                    values=pattern,
                    reason="模式匹配"
                ))
            
            contextual = self._get_contextual_suggestions(param_name, context)
            if contextual:
                param_suggestions.append(ParameterSuggestion(
                    param_name=param_name,
                    suggestion_type=SuggestionType.CONTEXTUAL,
                    values=contextual,
                    reason="上下文相关"
                ))
            
            if param_suggestions:
                suggestions[param_name] = param_suggestions
        
        return suggestions
    
    def _get_historical_values(
        self,
        tool_name: str,
        param_name: str,
        limit: int = 5
    ) -> List[Any]:
        """获取历史使用的值"""
        if tool_name not in self._history:
            return []
        
        values = []
        seen = set()
        
        for record in reversed(self._history[tool_name]):
            args = record.get("args", {})
            if param_name in args:
                value = args[param_name]
                if value not in seen:
                    values.append(value)
                    seen.add(value)
                    if len(values) >= limit:
                        break
        
        return values
    
    def _get_pattern_suggestions(
        self,
        param_name: str,
        param_type: str,
        context: CompletionContext
    ) -> List[Any]:
        """获取模式匹配的建议"""
        suggestions = []
        
        if param_type == "integer" or param_type == "number":
            if "id" in param_name.lower():
                suggestions = [1, 2, 3, 5, 10]
            elif "limit" in param_name.lower() or "size" in param_name.lower():
                suggestions = [10, 20, 50, 100]
            elif "page" in param_name.lower():
                suggestions = [1, 2, 3]
        
        elif param_type == "string":
            if param_name in self._pattern_hints:
                suggestions = self._pattern_hints[param_name]
            elif "date" in param_name.lower():
                from datetime import datetime, timedelta
                today = datetime.now()
                suggestions = [
                    today.strftime("%Y-%m-%d"),
                    (today - timedelta(days=7)).strftime("%Y-%m-%d"),
                    (today + timedelta(days=7)).strftime("%Y-%m-%d")
                ]
        
        return suggestions
    
    def _get_contextual_suggestions(
        self,
        param_name: str,
        context: CompletionContext
    ) -> List[Any]:
        """获取上下文相关的建议"""
        suggestions = []
        
        for pattern, hint_func in self._contextual_hints.items():
            if pattern in param_name.lower():
                try:
                    hint_values = hint_func(context)
                    if hint_values:
                        suggestions.extend(hint_values)
                except Exception:
                    pass
        
        if "meeting" in param_name.lower():
            recent_meetings = context.session_context.get("recent_meetings", [])
            suggestions.extend(recent_meetings[:3])
        
        if "document" in param_name.lower():
            recent_docs = context.session_context.get("recent_documents", [])
            suggestions.extend(recent_docs[:3])
        
        return suggestions[:5]
    
    def filter_suggestions(
        self,
        suggestions: Dict[str, List[ParameterSuggestion]],
        filter_text: str
    ) -> Dict[str, List[ParameterSuggestion]]:
        """根据输入过滤建议"""
        if not filter_text:
            return suggestions
        
        filter_lower = filter_text.lower()
        filtered = {}
        
        for param_name, param_suggestions in suggestions.items():
            filtered_values = []
            
            for suggestion in param_suggestions:
                matched_values = [
                    v for v in suggestion.values
                    if filter_lower in str(v).lower()
                ]
                
                if matched_values:
                    filtered_values.append(ParameterSuggestion(
                        param_name=suggestion.param_name,
                        suggestion_type=suggestion.suggestion_type,
                        values=matched_values,
                        score=suggestion.score,
                        reason=suggestion.reason
                    ))
            
            if filtered_values:
                filtered[param_name] = filtered_values
        
        return filtered
    
    def get_completion_prompt(
        self,
        tool_info: Dict[str, Any],
        context: CompletionContext
    ) -> str:
        """
        生成补全提示文本
        
        Args:
            tool_info: 工具信息
            context: 补全上下文
            
        Returns:
            格式化的提示文本
        """
        suggestions = self.get_suggestions(tool_info, context)
        
        if not suggestions:
            return ""
        
        lines = ["可用的参数补全建议："]
        
        for param_name, param_suggestions in suggestions.items():
            lines.append(f"\n  {param_name}:")
            
            for suggestion in param_suggestions[:3]:
                if suggestion.values:
                    values_str = ", ".join(str(v) for v in suggestion.values[:3])
                    lines.append(f"    [{suggestion.suggestion_type.value}] {values_str}")
        
        return "\n".join(lines)


class SmartArgumentParser:
    """智能参数解析器 - 从自然语言中提取参数"""
    
    def __init__(self):
        self._patterns: Dict[str, List[tuple]] = {}
        self._init_patterns()
    
    def _init_patterns(self):
        """初始化解析模式"""
        self._patterns = {
            "meeting_id": [
                (r"会议[（(]?(\d+)[）)]?", 1),
                (r"meeting[_\s]*id[:\s]*(\d+)", 1),
                (r"第(\d+)次会议", 1),
            ],
            "document_id": [
                (r"文档[（(]?(\d+)[）)]?", 1),
                (r"document[_\s]*id[:\s]*(\d+)", 1),
            ],
            "date": [
                (r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})", 0),
                (r"(\d{4}年\d{1,2}月\d{1,2}日)", 0),
            ],
            "limit": [
                (r"前(\d+)个?", 1),
                (r"limit[:\s]*(\d+)", 1),
                (r"返回(\d+)条", 1),
            ],
            "query": [
                (r"搜索[：:]?\s*(.+)", 1),
                (r"查找[：:]?\s*(.+)", 1),
                (r"query[:\s]*(.+)", 1),
            ]
        }
    
    def extract_arguments(
        self,
        text: str,
        tool_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        从文本中提取参数
        
        Args:
            text: 自然语言文本
            tool_info: 工具信息
            
        Returns:
            提取的参数
        """
        args = {}
        text_lower = text.lower()
        
        for param in tool_info.get("parameters", []):
            param_name = param.get("name")
            param_type = param.get("type", "string")
            
            patterns = self._patterns.get(param_name, [])
            
            for pattern, group_idx in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    value = matches[0] if isinstance(matches[0], tuple) else matches[0]
                    
                    if param_type == "integer" or param_type == "number":
                        try:
                            value = int(value)
                        except ValueError:
                            continue
                    
                    args[param_name] = value
                    break
        
        return args
    
    def suggest_missing_params(
        self,
        text: str,
        tool_info: Dict[str, Any],
        current_args: Dict[str, Any]
    ) -> List[str]:
        """
        建议缺失的必需参数
        
        Args:
            text: 用户输入文本
            tool_info: 工具信息
            current_args: 当前已解析的参数
            
        Returns:
            缺失参数列表
        """
        missing = []
        
        for param in tool_info.get("parameters", []):
            param_name = param.get("name")
            required = param.get("required", True)
            
            if required and param_name not in current_args:
                patterns = self._patterns.get(param_name, [])
                found = False
                
                for pattern, _ in patterns:
                    if re.search(pattern, text, re.IGNORECASE):
                        found = True
                        break
                
                if not found:
                    missing.append(param_name)
        
        return missing


_autocompleter: Optional[ToolParameterAutocompleter] = None
_parser: Optional[SmartArgumentParser] = None


def get_autocompleter() -> ToolParameterAutocompleter:
    """获取自动补全器"""
    global _autocompleter
    if _autocompleter is None:
        _autocompleter = ToolParameterAutocompleter()
    return _autocompleter


def get_argument_parser() -> SmartArgumentParser:
    """获取参数解析器"""
    global _parser
    if _parser is None:
        _parser = SmartArgumentParser()
    return _parser


def get_autocomplete_service() -> ToolParameterAutocompleter:
    """获取自动补全服务（别名）"""
    return get_autocompleter()
