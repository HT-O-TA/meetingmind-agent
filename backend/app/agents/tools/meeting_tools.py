"""会议助手专用工具"""
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


class ToolManager:
    """工具管理器"""
    
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
        
        app_logger.info(f"[ToolManager] 已注册 {len(self.registry._tools)} 个工具")
    
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