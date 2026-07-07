"""会议助手专用工具"""
import json
from typing import Optional, List, Dict, Any
from app.agents.tools.base import (
    BaseTool, ToolDefinition, ToolParameter, ToolCategory,
    ToolResult, ToolRegistry, ToolExecutor, ToolSelector
)
from app.services.vector_search_service import VectorSearchService
from app.services.llm_service import LLMService
from app.core.logger import app_logger


class MeetingSearchTool(BaseTool):
    """会议检索工具"""
    
    def __init__(self, vector_search_service: VectorSearchService):
        self.vector_search_service = vector_search_service
        super().__init__()
    
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_meeting",
            description="搜索会议相关内容，根据查询检索相关文档片段",
            category=ToolCategory.SEARCH,
            parameters=[
                ToolParameter(
                    name="query",
                    description="搜索查询",
                    type="string",
                    required=True
                ),
                ToolParameter(
                    name="meeting_id",
                    description="会议ID（可选）",
                    type="integer",
                    required=False
                ),
                ToolParameter(
                    name="top_k",
                    description="返回结果数量",
                    type="integer",
                    required=False,
                    default=5
                )
            ]
        )
    
    async def execute(self, query: str, meeting_id: Optional[int] = None, top_k: int = 5) -> ToolResult:
        try:
            results = await self.vector_search_service.search_by_text(
                query_text=query,
                top_k=top_k,
                meeting_id=meeting_id
            )
            
            # 格式化结果
            formatted = []
            for r in results:
                formatted.append({
                    "document_id": r.get("document_id"),
                    "content": r.get("content", r.get("chunk_text", "")),
                    "speaker": r.get("speaker_name", ""),
                    "similarity": r.get("similarity", 0)
                })
            
            return ToolResult(
                success=True,
                tool_name=self.definition.name,
                result=formatted,
                metadata={"count": len(formatted)}
            )
        except Exception as e:
            app_logger.error(f"[SearchTool] 检索失败: {e}")
            return ToolResult(
                success=False,
                tool_name=self.definition.name,
                result=None,
                error=str(e)
            )


class TodoExtractionTool(BaseTool):
    """待办抽取工具"""
    
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service
        super().__init__()
    
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="extract_todos",
            description="从会议内容中抽取待办事项，返回负责人和截止时间",
            category=ToolCategory.EXTRACT,
            parameters=[
                ToolParameter(
                    name="context",
                    description="会议上下文内容",
                    type="string",
                    required=True
                )
            ]
        )
    
    async def execute(self, context: str) -> ToolResult:
        prompt = f"""从以下会议内容中抽取待办事项：

{context}

请以JSON格式输出待办事项列表：
[
    {{
        "content": "待办内容",
        "assignee": "负责人（如果提到）",
        "deadline": "截止时间（如果提到）"
    }}
]

如果没有待办事项，返回空数组 []。"""

        try:
            messages = [
                {"role": "system", "content": "你是专业的待办抽取助手。"},
                {"role": "user", "content": prompt}
            ]
            
            response = await self.llm_service.chat(messages=messages, temperature=0.3)
            
            # 解析 JSON
            import re
            match = re.search(r'\[[\s\S]*\]', response)
            if match:
                todos = json.loads(match.group())
            else:
                todos = []
            
            return ToolResult(
                success=True,
                tool_name=self.definition.name,
                result=todos,
                metadata={"count": len(todos)}
            )
        except Exception as e:
            app_logger.error(f"[TodoTool] 抽取失败: {e}")
            return ToolResult(
                success=False,
                tool_name=self.definition.name,
                result=[],
                error=str(e)
            )


class MinutesGenerationTool(BaseTool):
    """会议纪要生成工具"""
    
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service
        super().__init__()
    
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="generate_minutes",
            description="生成结构化的会议纪要",
            category=ToolCategory.GENERATE,
            parameters=[
                ToolParameter(
                    name="context",
                    description="会议内容",
                    type="string",
                    required=True
                ),
                ToolParameter(
                    name="format",
                    description="输出格式（简略/详细）",
                    type="string",
                    required=False,
                    default="详细",
                    enum=["简略", "详细"]
                )
            ]
        )
    
    async def execute(self, context: str, format: str = "详细") -> ToolResult:
        prompt = f"""根据以下会议内容，生成{"简略" if format == "简略" else "详细"}的会议纪要：

{context}

请按以下结构输出：
1. 会议主题
2. 参会人员
3. 讨论要点
4. 决策事项
5. 后续行动"""

        try:
            messages = [
                {"role": "system", "content": "你是专业的会议纪要生成助手。"},
                {"role": "user", "content": prompt}
            ]
            
            response = await self.llm_service.chat(messages=messages, temperature=0.7)
            
            return ToolResult(
                success=True,
                tool_name=self.definition.name,
                result=response,
                metadata={"format": format}
            )
        except Exception as e:
            app_logger.error(f"[MinutesTool] 生成失败: {e}")
            return ToolResult(
                success=False,
                tool_name=self.definition.name,
                result=None,
                error=str(e)
            )


class ControversyDetectionTool(BaseTool):
    """争议点检测工具"""
    
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service
        super().__init__()
    
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="detect_controversies",
            description="从会议内容中识别争议点和分歧",
            category=ToolCategory.EXTRACT,
            parameters=[
                ToolParameter(
                    name="context",
                    description="会议内容",
                    type="string",
                    required=True
                )
            ]
        )
    
    async def execute(self, context: str) -> ToolResult:
        prompt = f"""从以下会议内容中识别争议点和分歧：

{context}

请以JSON格式输出争议点列表：
[
    {{
        "topic": "争议主题",
        "description": "争议描述",
        "parties": ["涉及方1", "涉及方2"]
    }}
]

如果没有争议点，返回空数组 []。"""

        try:
            messages = [
                {"role": "system", "content": "你是专业的争议点识别助手。"},
                {"role": "user", "content": prompt}
            ]
            
            response = await self.llm_service.chat(messages=messages, temperature=0.3)
            
            # 解析 JSON
            import re
            match = re.search(r'\[[\s\S]*\]', response)
            if match:
                controversies = json.loads(match.group())
            else:
                controversies = []
            
            return ToolResult(
                success=True,
                tool_name=self.definition.name,
                result=controversies,
                metadata={"count": len(controversies)}
            )
        except Exception as e:
            app_logger.error(f"[ControversyTool] 检测失败: {e}")
            return ToolResult(
                success=False,
                tool_name=self.definition.name,
                result=[],
                error=str(e)
            )


class QAAnswerTool(BaseTool):
    """问答回答工具"""
    
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service
        super().__init__()
    
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="answer_question",
            description="根据上下文回答用户问题",
            category=ToolCategory.GENERATE,
            parameters=[
                ToolParameter(
                    name="question",
                    description="用户问题",
                    type="string",
                    required=True
                ),
                ToolParameter(
                    name="context",
                    description="相关上下文",
                    type="string",
                    required=True
                )
            ]
        )
    
    async def execute(self, question: str, context: str) -> ToolResult:
        prompt = f"""根据以下上下文回答用户问题：

上下文：
{context}

问题：{question}

请给出准确、简洁的回答。"""

        try:
            messages = [
                {"role": "system", "content": "你是专业的问答助手。"},
                {"role": "user", "content": prompt}
            ]
            
            response = await self.llm_service.chat(messages=messages, temperature=0.7)
            
            return ToolResult(
                success=True,
                tool_name=self.definition.name,
                result=response,
                metadata={}
            )
        except Exception as e:
            app_logger.error(f"[QATool] 回答失败: {e}")
            return ToolResult(
                success=False,
                tool_name=self.definition.name,
                result=None,
                error=str(e)
            )


class MeetingToolManager:
    """会议工具管理器"""
    
    def __init__(
        self,
        llm_service: LLMService,
        vector_search_service: VectorSearchService
    ):
        self.llm_service = llm_service
        self.vector_search_service = vector_search_service
        
        # 创建注册表
        self.registry = ToolRegistry()
        self.executor = ToolExecutor(self.registry)
        self.selector = ToolSelector(self.registry)
        
        # 注册工具
        self._register_tools()
    
    def _register_tools(self):
        """注册所有工具"""
        # 会议检索工具
        search_tool = MeetingSearchTool(self.vector_search_service)
        self.registry.register(search_tool)
        
        # 待办抽取工具
        todo_tool = TodoExtractionTool(self.llm_service)
        self.registry.register(todo_tool)
        
        # 纪要生成工具
        minutes_tool = MinutesGenerationTool(self.llm_service)
        self.registry.register(minutes_tool)
        
        # 争议点检测工具
        controversy_tool = ControversyDetectionTool(self.llm_service)
        self.registry.register(controversy_tool)
        
        # 问答工具
        qa_tool = QAAnswerTool(self.llm_service)
        self.registry.register(qa_tool)
        
        app_logger.info(f"[MeetingToolManager] 已注册 {len(self.registry._tools)} 个工具")
    
    def get_tools_info(self) -> Dict[str, Any]:
        """获取工具信息"""
        return {
            "tools": [
                {
                    "name": t.definition.name,
                    "description": t.definition.description,
                    "category": t.definition.category.value
                }
                for t in self.registry._tools.values()
            ],
            "openai_format": self.registry.get_openai_tools()
        }


def register_meeting_tools(
    llm_service: LLMService,
    vector_search_service: VectorSearchService = None
):
    """
    将会议工具注册到全局工具注册表
    
    Args:
        llm_service: LLM服务
        vector_search_service: 向量搜索服务
    """
    from app.agents.tools.registry import get_tool_registry
    from app.agents.tools.tool_metadata import Tool, ToolMetadata, ToolCategory, ToolParameter, ToolRiskLevel
    
    registry = get_tool_registry()
    
    # 注册搜索工具
    search_tool = Tool(
        metadata=ToolMetadata(
            tool_id="search_meeting",
            name="搜索会议",
            description="搜索会议相关内容，根据查询检索相关文档片段",
            category=ToolCategory.SEARCH,
            tags=["meeting", "search", "会议", "检索"],
            risk_level=ToolRiskLevel.LOW,
            requires_confirmation=False,
            idempotent=True,
            parameters=[
                ToolParameter(name="query", type="string", description="搜索查询", required=True),
                ToolParameter(name="meeting_id", type="integer", description="会议ID（可选）", required=False),
                ToolParameter(name="top_k", type="integer", description="返回结果数量", required=False, default=5),
            ],
            is_async=True,
        )
    )
    registry.register(search_tool)
    
    # 注册待办抽取工具
    todo_tool = Tool(
        metadata=ToolMetadata(
            tool_id="extract_todos",
            name="提取待办事项",
            description="从会议内容中抽取待办事项，返回负责人和截止时间",
            category=ToolCategory.EXTRACT,
            tags=["todo", "task", "待办", "任务"],
            risk_level=ToolRiskLevel.LOW,
            requires_confirmation=False,
            idempotent=True,
            parameters=[
                ToolParameter(name="context", type="string", description="会议上下文内容", required=True),
            ],
            is_async=True,
        )
    )
    registry.register(todo_tool)
    
    # 注册纪要生成工具
    minutes_tool = Tool(
        metadata=ToolMetadata(
            tool_id="generate_minutes",
            name="生成会议纪要",
            description="生成结构化的会议纪要",
            category=ToolCategory.GENERATE,
            tags=["minutes", "summary", "纪要", "总结"],
            risk_level=ToolRiskLevel.LOW,
            requires_confirmation=False,
            idempotent=True,
            parameters=[
                ToolParameter(name="context", type="string", description="会议内容", required=True),
                ToolParameter(name="format", type="string", description="输出格式（简略/详细）", required=False, default="详细"),
            ],
            is_async=True,
        )
    )
    registry.register(minutes_tool)
    
    # 注册争议点检测工具
    controversy_tool = Tool(
        metadata=ToolMetadata(
            tool_id="detect_controversies",
            name="检测争议点",
            description="从会议内容中识别争议点和分歧",
            category=ToolCategory.EXTRACT,
            tags=["controversy", "dispute", "争议", "分歧"],
            risk_level=ToolRiskLevel.LOW,
            requires_confirmation=False,
            idempotent=True,
            parameters=[
                ToolParameter(name="context", type="string", description="会议内容", required=True),
            ],
            is_async=True,
        )
    )
    registry.register(controversy_tool)
    
    # 注册问答工具
    qa_tool = Tool(
        metadata=ToolMetadata(
            tool_id="answer_question",
            name="回答问题",
            description="根据上下文回答用户问题",
            category=ToolCategory.GENERATE,
            tags=["qa", "question", "问答", "回答"],
            risk_level=ToolRiskLevel.LOW,
            requires_confirmation=False,
            idempotent=True,
            parameters=[
                ToolParameter(name="question", type="string", description="用户问题", required=True),
                ToolParameter(name="context", type="string", description="相关上下文", required=True),
            ],
            is_async=True,
        )
    )
    registry.register(qa_tool)
    
    app_logger.info(f"[register_meeting_tools] 已注册会议工具到全局注册表")


class DocumentContentTool(BaseTool):
    """文档内容获取工具"""
    
    def __init__(self):
        super().__init__()
    
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="get_document_content",
            description="根据文档ID获取文档的完整内容",
            category=ToolCategory.SEARCH,
            parameters=[
                ToolParameter(
                    name="document_id",
                    description="文档ID",
                    type="integer",
                    required=True
                )
            ]
        )
    
    async def execute(self, document_id: int) -> ToolResult:
        try:
            from app.db.database import AsyncSessionLocal
            from app.models.document import Document
            from sqlalchemy import select
            
            # 将document_id转换为整数，确保类型正确
            document_id = int(document_id)
            
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(Document).where(Document.id == document_id))
                doc = result.scalar_one_or_none()
                
                if not doc:
                    return ToolResult(
                        success=False,
                        tool_name=self.definition.name,
                        result=None,
                        error=f"文档ID {document_id} 不存在"
                    )
                
                return ToolResult(
                    success=True,
                    tool_name=self.definition.name,
                    result={
                        "document_id": doc.id,
                        "filename": doc.filename,
                        "original_filename": doc.original_filename,
                        "content": doc.content,
                        "file_type": doc.file_type,
                        "status": doc.status,
                        "created_at": doc.created_at.isoformat() if doc.created_at else None
                    },
                    metadata={}
                )
        except Exception as e:
            app_logger.error(f"[DocumentContentTool] 获取文档内容失败: {e}")
            return ToolResult(
                success=False,
                tool_name=self.definition.name,
                result=None,
                error=str(e)
            )


class DocumentSearchTool(BaseTool):
    """文档搜索工具"""
    
    def __init__(self, vector_search_service: VectorSearchService):
        self.vector_search_service = vector_search_service
        super().__init__()
    
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_document",
            description="根据关键词搜索文档内容",
            category=ToolCategory.SEARCH,
            parameters=[
                ToolParameter(
                    name="query",
                    description="搜索关键词",
                    type="string",
                    required=True
                ),
                ToolParameter(
                    name="document_ids",
                    description="文档ID列表（可选，限制搜索范围）",
                    type="array",
                    required=False
                ),
                ToolParameter(
                    name="top_k",
                    description="返回结果数量",
                    type="integer",
                    required=False,
                    default=5
                )
            ]
        )
    
    async def execute(self, query: str, document_ids: Optional[List[int]] = None, top_k: int = 5) -> ToolResult:
        try:
            results = await self.vector_search_service.search_by_text(
                query_text=query,
                top_k=top_k,
                document_ids=document_ids
            )
            
            formatted = []
            for r in results:
                formatted.append({
                    "document_id": r.get("document_id"),
                    "content": r.get("content", r.get("chunk_text", "")),
                    "similarity": r.get("similarity", 0),
                    "chunk_id": r.get("id")
                })
            
            return ToolResult(
                success=True,
                tool_name=self.definition.name,
                result=formatted,
                metadata={"count": len(formatted)}
            )
        except Exception as e:
            app_logger.error(f"[DocumentSearchTool] 搜索失败: {e}")
            return ToolResult(
                success=False,
                tool_name=self.definition.name,
                result=[],
                error=str(e)
            )


class TextProcessorTool(BaseTool):
    """文本处理工具"""
    
    def __init__(self):
        super().__init__()
    
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="text_processor",
            description="对文本进行处理，如统计字数、提取关键词、格式化等",
            category=ToolCategory.INFO,
            parameters=[
                ToolParameter(
                    name="operation",
                    description="操作类型（count/keyword/format/extract）",
                    type="string",
                    required=True
                ),
                ToolParameter(
                    name="text",
                    description="要处理的文本",
                    type="string",
                    required=True
                )
            ]
        )
    
    async def execute(self, operation: str, text: str) -> ToolResult:
        """执行文本处理"""
        try:
            if not text:
                return ToolResult(
                    success=False,
                    tool_name=self.definition.name,
                    result=None,
                    error="文本不能为空"
                )
            
            if operation == "count":
                # 统计字数
                char_count = len(text)
                word_count = len(text.split())
                line_count = len(text.split('\n'))
                result = {
                    "char_count": char_count,
                    "word_count": word_count,
                    "line_count": line_count
                }
            elif operation == "keyword":
                # 简单的关键词提取（按词频）
                words = text.split()
                word_freq = {}
                for word in words:
                    if len(word) > 1:  # 忽略单字
                        word_freq[word] = word_freq.get(word, 0) + 1
                # 取前10个高频词
                keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
                result = {"keywords": [k[0] for k in keywords]}
            elif operation == "format":
                # 格式化文本（去除多余空格和换行）
                formatted = ' '.join(text.split())
                result = {"formatted_text": formatted}
            elif operation == "extract":
                # 提取摘要（取前200字）
                summary = text[:200] + "..." if len(text) > 200 else text
                result = {"summary": summary}
            else:
                return ToolResult(
                    success=False,
                    tool_name=self.definition.name,
                    result=None,
                    error=f"不支持的操作类型: {operation}"
                )
            
            return ToolResult(
                success=True,
                tool_name=self.definition.name,
                result=result
            )
        except Exception as e:
            app_logger.error(f"[TextProcessorTool] 处理失败: {e}")
            return ToolResult(
                success=False,
                tool_name=self.definition.name,
                result=None,
                error=str(e)
            )
