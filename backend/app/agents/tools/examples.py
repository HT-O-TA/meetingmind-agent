"""装饰器模式工具示例 - 展示如何使用新的装饰器注册工具"""
from typing import List, Optional
from app.agents.tools.decorator import (
    tool, meeting_tool, document_tool, todo_tool, multimodal_tool,
    get_tool_registry, ToolCategory
)


# ==================== 基础用法 ====================

@tool(name="search_meeting", description="根据关键词搜索会议内容", category=ToolCategory.MEETING, tags=["search", "meeting"])
async def search_meeting(query: str, top_k: int = 5, meeting_id: Optional[int] = None):
    """
    搜索会议内容
    
    Args:
        query: 搜索关键词
        top_k: 返回结果数量
        meeting_id: 可选的会议ID过滤
    """
    from app.services.vector_search_service import get_vector_search_service
    
    vector_service = get_vector_search_service()
    results = await vector_service.search_by_text(
        query_text=query,
        top_k=top_k,
        meeting_id=meeting_id
    )
    
    return {
        "query": query,
        "count": len(results),
        "results": results
    }


@tool(name="get_meeting_info", description="获取会议详细信息", category=ToolCategory.MEETING)
async def get_meeting_info(meeting_id: int):
    """获取会议信息"""
    from app.services.meeting_service import get_meeting_service
    
    service = get_meeting_service()
    meeting = await service.get_meeting(meeting_id)
    
    return meeting


@tool(name="extract_todos", description="从会议内容中提取待办事项", category=ToolCategory.TODO)
async def extract_todos(content: str, assignees: Optional[List[str]] = None):
    """
    提取待办事项
    
    Args:
        content: 会议内容
        assignees: 可选的负责人过滤
    """
    import re
    
    # 简单的待办提取模式
    todo_pattern = r'(?:待办|TODO|需要做|任务)(?::|：)?\s*(.+)'
    todos = re.findall(todo_pattern, content)
    
    results = []
    for i, todo_text in enumerate(todos):
        todo = {
            "id": f"todo_{i + 1}",
            "content": todo_text.strip(),
            "status": "pending"
        }
        
        # 尝试提取负责人
        assignee_pattern = r'[@（(](\w+)[)）]'
        assignees_found = re.findall(assignee_pattern, todo_text)
        if assignees_found:
            todo["assignee"] = assignees_found[0]
        
        # 尝试提取截止时间
        date_pattern = r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})'
        dates_found = re.findall(date_pattern, todo_text)
        if dates_found:
            todo["due_date"] = dates_found[0]
        
        # 过滤负责人
        if assignees and todo.get("assignee") not in assignees:
            continue
        
        results.append(todo)
    
    return results


@tool(name="generate_minutes", description="生成会议纪要", category=ToolCategory.MEETING)
async def generate_minutes(meeting_id: Optional[int] = None, content: Optional[str] = None):
    """
    生成会议纪要
    
    Args:
        meeting_id: 会议ID（如果提供，则从数据库获取内容）
        content: 会议内容文本（如果提供，则直接使用）
    """
    if meeting_id:
        from app.services.meeting_service import get_meeting_service
        service = get_meeting_service()
        meeting = await service.get_meeting(meeting_id)
        content = meeting.get("content", "") if meeting else ""
    
    if not content:
        return {"error": "No content provided"}
    
    from app.services.llm_service import LLMService
    llm = LLMService()
    
    prompt = f"""请根据以下会议内容，生成结构化的会议纪要：

{content}

请按以下格式输出：
1. 会议基本信息（时间、地点、参会人员）
2. 会议主题
3. 讨论内容摘要
4. 决议事项
5. 待办事项（包含负责人和截止时间）
6. 下次会议安排
"""
    
    try:
        minutes = await llm._call(prompt)
        return {"minutes": minutes, "meeting_id": meeting_id}
    except Exception as e:
        return {"error": str(e)}


# ==================== 文档工具 ====================

@document_tool(name="search_document", description="搜索文档内容")
async def search_document(query: str, document_ids: Optional[List[int]] = None):
    """搜索文档"""
    from app.services.document_service import get_document_service
    
    service = get_document_service()
    results = await service.search_documents(query, document_ids)
    
    return results


@document_tool(name="get_document_content", description="获取文档完整内容")
async def get_document_content(document_id: int, include_chunks: bool = False):
    """获取文档内容"""
    from app.services.document_service import get_document_service
    
    service = get_document_service()
    doc = await service.get_document(document_id)
    
    if include_chunks:
        chunks = await service.get_document_chunks(document_id)
        doc["chunks"] = chunks
    
    return doc


# ==================== 待办工具 ====================

@todo_tool(name="create_todo", description="创建待办事项")
async def create_todo(content: str, assignee: Optional[str] = None, due_date: Optional[str] = None, priority: str = "normal"):
    """创建待办"""
    from app.services.todo_service import get_todo_service
    
    service = get_todo_service()
    todo = await service.create_todo(
        content=content,
        assignee=assignee,
        due_date=due_date,
        priority=priority
    )
    
    return todo


@todo_tool(name="update_todo_status", description="更新待办状态")
async def update_todo_status(todo_id: int, status: str):
    """更新待办状态"""
    from app.services.todo_service import get_todo_service
    
    if status not in ["pending", "in_progress", "completed"]:
        return {"error": "Invalid status"}
    
    service = get_todo_service()
    result = await service.update_todo_status(todo_id, status)
    
    return result


# ==================== 多模态工具 ====================

@multimodal_tool(name="transcribe_audio", description="将音频转换为文字")
async def transcribe_audio(audio_url: str, language: Optional[str] = "zh"):
    """
    音频转文字（语音识别）
    
    Args:
        audio_url: 音频文件URL或路径
        language: 音频语言
    """
    # TODO: 集成Whisper或其他语音识别服务
    return {
        "text": "音频转文字功能待实现",
        "audio_url": audio_url,
        "language": language
    }


@multimodal_tool(name="describe_image", description="描述图片内容")
async def describe_image(image_url: str, detail_level: str = "medium"):
    """
    图片描述（多模态LLM）
    
    Args:
        image_url: 图片URL或路径
        detail_level: 描述详细程度 (low/medium/high)
    """
    # TODO: 集成多模态LLM服务
    return {
        "description": "图片描述功能待实现",
        "image_url": image_url,
        "detail_level": detail_level
    }


@multimodal_tool(name="extract_text_from_image", description="从图片中提取文字")
async def extract_text_from_image(image_url: str):
    """OCR文字识别"""
    # TODO: 集成OCR服务
    return {
        "text": "图片文字提取功能待实现",
        "image_url": image_url
    }


# ==================== 注册所有工具到注册表 ====================

def register_example_tools():
    """注册示例工具到全局注册表"""
    registry = get_tool_registry()
    
    tools = [
        search_meeting,
        get_meeting_info,
        extract_todos,
        generate_minutes,
        search_document,
        get_document_content,
        create_todo,
        update_todo_status,
        transcribe_audio,
        describe_image,
        extract_text_from_image,
    ]
    
    for tool_func in tools:
        # 工具已经在装饰器注册时被添加到注册表
        pass
    
    return len(tools)
