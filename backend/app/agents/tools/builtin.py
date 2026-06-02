"""内置工具定义"""
from typing import Dict, Any, List, Optional
from app.agents.tools.tool_metadata import (
    Tool, ToolMetadata, ToolCategory, ToolStatus, ToolParameter
)

def get_builtin_tools() -> List[Tool]:
    """获取所有内置工具"""
    return [
        # ============ 会议相关工具 ============
        Tool(
            metadata=ToolMetadata(
                tool_id="search_meeting",
                name="搜索会议",
                description="根据关键词搜索会议内容，返回相关片段",
                category=ToolCategory.MEETING,
                tags=["search", "meeting", "会议", "检索"],
                parameters=[
                    ToolParameter(
                        name="query",
                        type="string",
                        description="搜索关键词",
                        required=True
                    ),
                    ToolParameter(
                        name="top_k",
                        type="integer",
                        description="返回结果数量",
                        required=False,
                        default=5,
                        min_value=1,
                        max_value=20
                    ),
                ],
                return_type="array",
                supports_streaming=False,
                is_async=True,
            )
        ),
        
        Tool(
            metadata=ToolMetadata(
                tool_id="get_meeting_info",
                name="获取会议信息",
                description="获取会议的详细信息，包括参会人员、时间、主题等",
                category=ToolCategory.MEETING,
                tags=["meeting", "info", "会议", "信息"],
                parameters=[
                    ToolParameter(
                        name="meeting_id",
                        type="integer",
                        description="会议ID",
                        required=True
                    ),
                ],
                return_type="object",
                supports_streaming=False,
                is_async=True,
            )
        ),
        
        Tool(
            metadata=ToolMetadata(
                tool_id="extract_todos",
                name="提取待办事项",
                description="从会议内容中提取待办事项，包括负责人和截止时间",
                category=ToolCategory.TODO,
                tags=["todo", "task", "待办", "任务", "提取"],
                parameters=[
                    ToolParameter(
                        name="meeting_id",
                        type="integer",
                        description="会议ID",
                        required=False
                    ),
                    ToolParameter(
                        name="content",
                        type="string",
                        description="会议内容文本",
                        required=False
                    ),
                ],
                return_type="array",
                supports_streaming=False,
                is_async=True,
            )
        ),
        
        Tool(
            metadata=ToolMetadata(
                tool_id="extract_controversies",
                name="提取争议点",
                description="从会议内容中提取争议点和分歧意见",
                category=ToolCategory.MEETING,
                tags=["controversy", "dispute", "争议", "分歧"],
                parameters=[
                    ToolParameter(
                        name="meeting_id",
                        type="integer",
                        description="会议ID",
                        required=False
                    ),
                    ToolParameter(
                        name="content",
                        type="string",
                        description="会议内容文本",
                        required=False
                    ),
                ],
                return_type="array",
                supports_streaming=False,
                is_async=True,
            )
        ),
        
        Tool(
            metadata=ToolMetadata(
                tool_id="generate_minutes",
                name="生成会议纪要",
                description="根据会议内容生成结构化的会议纪要",
                category=ToolCategory.MINUTES,
                tags=["minutes", "summary", "纪要", "总结"],
                parameters=[
                    ToolParameter(
                        name="meeting_id",
                        type="integer",
                        description="会议ID",
                        required=False
                    ),
                    ToolParameter(
                        name="content",
                        type="string",
                        description="会议内容文本",
                        required=False
                    ),
                ],
                return_type="string",
                supports_streaming=False,
                is_async=True,
            )
        ),
        
        # ============ 文档相关工具 ============
        Tool(
            metadata=ToolMetadata(
                tool_id="search_document",
                name="搜索文档",
                description="根据关键词搜索文档内容",
                category=ToolCategory.DOCUMENT,
                tags=["search", "document", "文档", "检索"],
                parameters=[
                    ToolParameter(
                        name="query",
                        type="string",
                        description="搜索关键词",
                        required=True
                    ),
                    ToolParameter(
                        name="document_ids",
                        type="array",
                        description="文档ID列表",
                        required=False
                    ),
                ],
                return_type="array",
                supports_streaming=False,
                is_async=True,
            )
        ),
        
        Tool(
            metadata=ToolMetadata(
                tool_id="get_document_content",
                name="获取文档内容",
                description="根据文档ID获取文档的完整内容",
                category=ToolCategory.DOCUMENT,
                tags=["document", "content", "文档", "内容"],
                parameters=[
                    ToolParameter(
                        name="document_id",
                        type="integer",
                        description="文档ID",
                        required=True
                    ),
                ],
                return_type="object",
                supports_streaming=False,
                is_async=True,
            )
        ),
        
        # ============ 基础工具 ============
        Tool(
            metadata=ToolMetadata(
                tool_id="calculator",
                name="计算器",
                description="执行数学计算，支持加减乘除、幂运算等",
                category=ToolCategory.COMPUTATION,
                tags=["calculate", "math", "计算", "数学"],
                parameters=[
                    ToolParameter(
                        name="expression",
                        type="string",
                        description="数学表达式，如 '2 + 3 * 4'",
                        required=True
                    ),
                ],
                return_type="number",
                supports_streaming=False,
                is_async=False,
            )
        ),
        
        Tool(
            metadata=ToolMetadata(
                tool_id="date_calculator",
                name="日期计算器",
                description="计算日期差、添加天数等日期操作",
                category=ToolCategory.COMPUTATION,
                tags=["date", "time", "日期", "时间"],
                parameters=[
                    ToolParameter(
                        name="operation",
                        type="string",
                        description="操作类型",
                        required=True,
                        enum_values=["diff", "add_days", "add_months"]
                    ),
                    ToolParameter(
                        name="date1",
                        type="string",
                        description="第一个日期（YYYY-MM-DD格式）",
                        required=True
                    ),
                    ToolParameter(
                        name="date2",
                        type="string",
                        description="第二个日期（YYYY-MM-DD格式，用于diff操作）",
                        required=False
                    ),
                    ToolParameter(
                        name="days",
                        type="integer",
                        description="要添加的天数（用于add_days操作）",
                        required=False
                    ),
                ],
                return_type="string",
                supports_streaming=False,
                is_async=False,
            )
        ),
        
        Tool(
            metadata=ToolMetadata(
                tool_id="text_processor",
                name="文本处理器",
                description="对文本进行处理，如统计字数、提取关键词、格式化等",
                category=ToolCategory.INFO,
                tags=["text", "process", "文本", "处理"],
                parameters=[
                    ToolParameter(
                        name="operation",
                        type="string",
                        description="操作类型",
                        required=True,
                        enum_values=["count", "keyword", "format", "extract"]
                    ),
                    ToolParameter(
                        name="text",
                        type="string",
                        description="要处理的文本",
                        required=True
                    ),
                ],
                return_type="string",
                supports_streaming=False,
                is_async=False,
            )
        ),
        
        # ============ 信息查询工具 ============
        Tool(
            metadata=ToolMetadata(
                tool_id="wiki_search",
                name="维基搜索",
                description="搜索维基百科获取信息",
                category=ToolCategory.INFO,
                tags=["wiki", "search", "百科", "搜索"],
                parameters=[
                    ToolParameter(
                        name="query",
                        type="string",
                        description="搜索关键词",
                        required=True
                    ),
                    ToolParameter(
                        name="language",
                        type="string",
                        description="语言（zh/en）",
                        required=False,
                        default="zh",
                        enum_values=["zh", "en"]
                    ),
                ],
                return_type="string",
                supports_streaming=False,
                is_async=True,
            )
        ),
        
        # ============ 知识库工具 ============
        Tool(
            metadata=ToolMetadata(
                tool_id="knowledge_base_search",
                name="知识库搜索",
                description="在企业内部知识库中搜索相关内容",
                category=ToolCategory.KNOWLEDGE,
                tags=["knowledge", "search", "知识库", "检索"],
                parameters=[
                    ToolParameter(
                        name="query",
                        type="string",
                        description="搜索查询",
                        required=True
                    ),
                    ToolParameter(
                        name="category",
                        type="string",
                        description="知识分类",
                        required=False
                    ),
                    ToolParameter(
                        name="top_k",
                        type="integer",
                        description="返回结果数量",
                        required=False,
                        default=5,
                    ),
                ],
                return_type="array",
                supports_streaming=False,
                is_async=True,
            )
        ),
        
        # ============ 协作工具 ============
        Tool(
            metadata=ToolMetadata(
                tool_id="create_reminder",
                name="创建提醒",
                description="创建一个定时提醒",
                category=ToolCategory.NOTIFICATION,
                tags=["reminder", "notify", "提醒", "通知"],
                parameters=[
                    ToolParameter(
                        name="message",
                        type="string",
                        description="提醒内容",
                        required=True
                    ),
                    ToolParameter(
                        name="remind_at",
                        type="string",
                        description="提醒时间（ISO格式）",
                        required=True
                    ),
                ],
                return_type="object",
                supports_streaming=False,
                is_async=True,
            )
        ),
        
        Tool(
            metadata=ToolMetadata(
                tool_id="send_notification",
                name="发送通知",
                description="向用户或群组发送通知",
                category=ToolCategory.NOTIFICATION,
                tags=["notification", "send", "通知", "发送"],
                parameters=[
                    ToolParameter(
                        name="title",
                        type="string",
                        description="通知标题",
                        required=True
                    ),
                    ToolParameter(
                        name="content",
                        type="string",
                        description="通知内容",
                        required=True
                    ),
                    ToolParameter(
                        name="recipients",
                        type="array",
                        description="接收人ID列表",
                        required=True
                    ),
                ],
                return_type="object",
                supports_streaming=False,
                is_async=True,
            )
        ),
    ]


def execute_builtin_tool(tool_id: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Any:
    """
    执行内置工具
    
    Args:
        tool_id: 工具ID
        params: 参数
        context: 上下文
        
    Returns:
        执行结果
    """
    import re
    from datetime import datetime, timedelta
    
    # 会议搜索
    if tool_id == "search_meeting":
        query = params.get("query", "")
        top_k = params.get("top_k", 5)
        # 这里应该调用实际的向量检索服务
        return f"搜索 '{query}' 找到 {top_k} 个相关会议片段"
    
    # 获取会议信息
    elif tool_id == "get_meeting_info":
        meeting_id = params.get("meeting_id")
        return {"meeting_id": meeting_id, "title": "会议标题", "status": "进行中"}
    
    # 提取待办
    elif tool_id == "extract_todos":
        content = params.get("content", "")
        # 简单的正则提取
        todos = re.findall(r'(?:待办|todo|TODO|需要做)([^。]+)', content)
        return [{"content": t.strip(), "status": "pending"} for t in todos] if todos else []
    
    # 提取争议
    elif tool_id == "extract_controversies":
        content = params.get("content", "")
        controversies = re.findall(r'(?:争议|分歧|不同意见)([^。]+)', content)
        return [{"topic": c.strip(), "status": "open"} for c in controversies] if controversies else []
    
    # 生成纪要
    elif tool_id == "generate_minutes":
        content = params.get("content", "")
        return f"会议纪要：\n1. 讨论主题\n2. 主要结论\n3. 待办事项"
    
    # 文档搜索
    elif tool_id == "search_document":
        query = params.get("query", "")
        return f"文档搜索 '{query}' 的结果"
    
    # 获取文档内容
    elif tool_id == "get_document_content":
        document_id = params.get("document_id")
        return {"document_id": document_id, "content": "文档内容..."}
    
    # 计算器
    elif tool_id == "calculator":
        expression = params.get("expression", "")
        try:
            # 安全评估数学表达式
            result = eval(expression, {"__builtins__": {}}, {})
            return result
        except:
            return "计算错误"
    
    # 日期计算器
    elif tool_id == "date_calculator":
        operation = params.get("operation", "diff")
        date1_str = params.get("date1", "")
        
        try:
            date1 = datetime.strptime(date1_str, "%Y-%m-%d")
            
            if operation == "diff":
                date2_str = params.get("date2", "")
                date2 = datetime.strptime(date2_str, "%Y-%m-%d")
                diff = (date2 - date1).days
                return f"相差 {abs(diff)} 天"
            elif operation == "add_days":
                days = params.get("days", 0)
                result_date = date1 + timedelta(days=days)
                return result_date.strftime("%Y-%m-%d")
        except:
            return "日期计算错误"
        
        return "未知操作"
    
    # 文本处理
    elif tool_id == "text_processor":
        operation = params.get("operation", "count")
        text = params.get("text", "")
        
        if operation == "count":
            return {"字数": len(text), "字符数": len(text.replace(' ', '')), "行数": len(text.split('\n'))}
        elif operation == "keyword":
            words = text.split()
            word_freq = {}
            for word in words:
                word_freq[word] = word_freq.get(word, 0) + 1
            return sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
        
        return text
    
    # 维基搜索
    elif tool_id == "wiki_search":
        query = params.get("query", "")
        return f"关于 '{query}' 的维基百科信息..."
    
    # 知识库搜索
    elif tool_id == "knowledge_base_search":
        query = params.get("query", "")
        return f"知识库中 '{query}' 的相关条目"
    
    # 创建提醒
    elif tool_id == "create_reminder":
        message = params.get("message", "")
        remind_at = params.get("remind_at", "")
        return {"success": True, "reminder_id": "123", "message": message, "remind_at": remind_at}
    
    # 发送通知
    elif tool_id == "send_notification":
        title = params.get("title", "")
        content = params.get("content", "")
        recipients = params.get("recipients", [])
        return {"success": True, "notification_id": "456", "title": title, "recipients_count": len(recipients)}
    
    return f"未知的工具: {tool_id}"
