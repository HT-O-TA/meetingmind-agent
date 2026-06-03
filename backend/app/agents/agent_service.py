"""Agent 服务封装 - 支持 Tool Calling
"""
import re
from typing import Optional, List, Dict, Any, TypedDict
from app.agents.state import AgentState, AgentResult, ChunkMetadata, TaskType, Plan, ReflectionResult
from app.agents.graph import create_agent_graph, print_agent_architecture
from app.agents.graph_toolcalling import create_tool_calling_graph, print_tool_calling_architecture
from app.agents.memory import MemoryManager
from app.agents.tools import ToolManager
from app.agents.prompts import PromptManager
from app.agents.errors import ErrorRecoveryManager
from app.agents.monitor import AgentMonitor
from app.services.llm_service import LLMService
from app.services.vector_search_service import VectorSearchService
from app.core.logger import app_logger


class SearchResult(TypedDict):
    """向量检索结果（统一的接口契约）"""
    chunk_id: int
    document_id: int
    meeting_id: Optional[int]
    content: str
    chunk_index: int
    similarity: float
    department: Optional[str]
    speaker_name: str
    time_offset: Optional[float]
    metadata_json: Optional[str]


class AgentService:
    """Agent 服务类 - 支持 Tool Calling 和人机协作"""

    def __init__(
        self,
        llm_service: LLMService,
        vector_search_service: VectorSearchService,
        enable_checkpointer: bool = False,
        enable_memory: bool = True,
        enable_tool_calling: bool = True,
        enable_human_in_the_loop: bool = False,
        max_short_term_turns: int = 10,
        max_long_term_items: int = 1000,
        enable_compression: bool = True,
        enable_monitoring: bool = True,
    ):
        self.llm_service = llm_service
        self.vector_search_service = vector_search_service
        self.enable_checkpointer = enable_checkpointer
        self.enable_memory = enable_memory
        self.enable_compression = enable_compression
        self.enable_tool_calling = enable_tool_calling
        self.enable_monitoring = enable_monitoring
        self.enable_human_in_the_loop = enable_human_in_the_loop

        # 初始化核心模块
        self.prompt_manager = PromptManager()
        self.error_manager = ErrorRecoveryManager()
        self.monitor = AgentMonitor() if enable_monitoring else None

        # 人机协作服务
        from app.agents.human_in_the_loop import get_hitl_service
        self.hitl_service = get_hitl_service()

        # 工具管理器（如果启用 Tool Calling）
        self.tool_manager: Optional[ToolManager] = None
        if self.enable_tool_calling:
            self.tool_manager = ToolManager(llm_service, vector_search_service)
            self.graph = create_tool_calling_graph(llm_service, self.tool_manager)
            print_tool_calling_architecture()
        else:
            self.graph = create_agent_graph(llm_service, vector_search_service)
            print_agent_architecture()

        self.app = self._compile_graph()

        # 记忆管理
        self.memory_manager = MemoryManager(
            max_short_term_turns=max_short_term_turns,
            max_long_term_items=max_long_term_items,
            enable_compression=enable_compression,
            llm_service=llm_service if enable_compression else None
        )

        # 每个会话的记忆管理器
        self.session_memories: Dict[str, MemoryManager] = {}

        if enable_checkpointer:
            self.memory_manager.enable_checkpoint()

    def _compile_graph(self):
        """编译图，支持可选的 checkpointer"""
        from langgraph.checkpoint.memory import MemorySaver

        if self.enable_checkpointer:
            checkpointer = MemorySaver()
            return self.graph.compile(checkpointer=checkpointer)
        return self.graph.compile()

    def _get_session_memory(self, session_id: str) -> MemoryManager:
        """获取或创建会话记忆管理器"""
        if session_id not in self.session_memories:
            self.session_memories[session_id] = MemoryManager(
                max_short_term_turns=self.memory_manager.short_term.max_raw_turns,
                max_long_term_items=self.memory_manager.long_term.max_items,
                enable_compression=self.enable_compression,
                llm_service=self.llm_service if self.enable_compression else None,
            )
            if self.enable_checkpointer:
                self.session_memories[session_id].enable_checkpoint()
        return self.session_memories[session_id]

    async def process_query(
        self,
        question: str,
        meeting_id: Optional[int] = None,
        document_ids: Optional[List[int]] = None,
        config: Optional[Dict[str, Any]] = None,
        event_callback: Optional[callable] = None,
    ) -> AgentResult:
        """处理用户查询
        """
        span_id = None
        if self.monitor:
            self.monitor.info(f"开始处理查询: {question}")
            self.monitor.info(f"Tool Calling: {self.enable_tool_calling}")
            span_id = self.monitor.start_span("agent_process_query", attributes={"question": question[:50]})

        session_id = config.get("thread_id") if config else None
        memory = self._get_session_memory(session_id or "default")

        async def emit_event(event_type, data):
            if event_callback:
                await event_callback(event_type, data)

        try:
            await emit_event("start", {"question": question, "phase": "初始化"})

            # 获取记忆上下文
            memory_context = ""
            if self.enable_memory:
                memory_context = memory.get_context_for_query(question, n_recent=3)

            # 检索上下文
            await emit_event("phase", {"phase": "context", "message": "正在检索相关文档..."})
            context_chunks = await self._retrieve_context(
                question=question,
                meeting_id=meeting_id,
                document_ids=document_ids
            )
            await emit_event("context", {"chunks_count": len(context_chunks)})

            # 合并上下文
            raw_context = self._format_chunks_to_text(context_chunks)
            if memory_context and self.enable_memory:
                raw_context.insert(0, f"【相关记忆】\n{memory_context}")

            # 初始化状态
            initial_state: AgentState = {
                "question": question,
                "meeting_id": meeting_id,
                "document_ids": document_ids,
                "context": context_chunks,
                "raw_context": raw_context,
                "current_phase": "plan",
                "task_type": TaskType.QA,
                "plan": None,
                "minutes": None,
                "todos": None,
                "controversies": None,
                "answer": None,
                "reflection": None,
                "error": None,
                "cot_thoughts": [],
                "agents_involved": [],
                "event_callback": event_callback,
                "human_confirmations": [],
                "enable_human_in_the_loop": self.enable_human_in_the_loop,
            }

            # 执行
            await emit_event("phase", {"phase": "execute", "message": "开始执行Agent..."})
            invoke_config = {"configurable": config} if config else None
            final_state = await self.app.ainvoke(initial_state, config=invoke_config)

            # 构建结果
            task_type = final_state.get("task_type") or TaskType.QA
            reflection = final_state.get("reflection")

            plan = final_state.get("plan")
            formatted_plan = None
            if plan:
                formatted_plan = {
                    "analysis": plan.get("analysis", ""),
                    "tasks": plan.get("tasks", []),
                    "execution_order": plan.get("execution_order", []),
                    "parallel_groups": plan.get("parallel_groups", []),
                    "tool_calls": plan.get("tool_calls", []) if self.enable_tool_calling else None
                }

            result = AgentResult(
                success=True,
                task_type=task_type,
                answer=final_state.get("answer"),
                minutes=final_state.get("minutes"),
                todos=final_state.get("todos"),
                controversies=final_state.get("controversies"),
                thoughts=final_state.get("cot_thoughts"),
                reflection=reflection,
                plan=formatted_plan,
            )

            # 保存记忆
            if self.enable_memory:
                memory.add_conversation(
                    question=question,
                    answer=result.answer or "",
                    plan=formatted_plan,
                    reflection=reflection,
                    task_type=task_type.value if task_type else "qa",
                    success=result.success
                )
                if self.enable_compression:
                    compressed = await memory.compress_if_needed()
                    if compressed:
                        self.monitor.info("[Agent] 记忆已自动压缩") if self.monitor else app_logger.info("[Agent] 记忆已自动压缩")

                stats = memory.short_term.get_summary()
                self.monitor.info(f"[Agent] 记忆: {stats['raw_turns']} 原始 + {stats['summarized_turns']} 摘要") if self.monitor else app_logger.info(f"[Agent] 记忆: {stats['raw_turns']} 原始 + {stats['summarized_turns']} 摘要")

            # 统计
            thoughts = final_state.get("cot_thoughts", [])
            phases = {}
            for t in thoughts:
                phase = t.get("phase", "unknown")
                phases[phase] = phases.get(phase, 0) + 1

            self.monitor.info(f"[Agent] 处理完成 - 任务: {result.task_type.value}, 思维链: {len(thoughts)} 步") if self.monitor else app_logger.info(f"[Agent] 处理完成 - 任务: {result.task_type.value}, 思维链: {len(thoughts)} 步")
            if result.reflection:
                self.monitor.info(f"[Agent] 质量评分: {result.reflection.get('quality_score', 0):.2f}") if self.monitor else app_logger.info(f"[Agent] 质量评分: {result.reflection.get('quality_score', 0):.2f}")

            if span_id:
                self.monitor.finish_span(span_id, {"success": True, "task_type": result.task_type.value})
                
            return result

        except Exception as e:
            self.monitor.error(f"[Agent] 处理失败: {e}") if self.monitor else app_logger.error(f"[Agent] 处理失败: {e}")
            
            # 记录错误
            error_info = self.error_manager.handle_error(e, {"question": question})
            
            if span_id:
                self.monitor.finish_span(span_id, {"success": False, "error": str(e)})
            
            return AgentResult(
                success=False,
                task_type=TaskType.QA,
                error=str(e),
            )

    def _format_chunks_to_text(self, chunks: List[SearchResult]) -> List[str]:
        texts = []
        for chunk in chunks:
            content = chunk.get("content", "")
            speaker = chunk.get("speaker_name", "")
            if speaker:
                texts.append(f"[{speaker}]: {content}")
            else:
                texts.append(content)
        return texts

    def _extract_document_ids_from_question(self, question: str) -> List[int]:
        """从问题中提取明确提及的 document_id，如「id为4」「文档4」「第4个文档」"""
        patterns = [
            r'(?:id|ID|编号|文档id|文档ID)\s*(?:为|是|=|：|:)?\s*(\d+)',
            r'(?:文档|文件|第)\s*(\d+)\s*(?:号|个|篇)?(?:文档|文件)?',
            r'#(\d+)',
        ]
        ids = []
        for pattern in patterns:
            for m in re.finditer(pattern, question):
                ids.append(int(m.group(1)))
        return list(dict.fromkeys(ids))  # 去重保序

    def _is_document_summary_intent(self, question: str) -> bool:
        """判断问题是否为「某文档内容是什么/主要讲了什么」类意图"""
        keywords = ['主要讲', '讲了什么', '内容是什么', '内容有哪些', '说了什么',
                    '介绍了什么', '包含什么', '包含哪些', '总结', '摘要', '概述']
        return any(kw in question for kw in keywords)

    def _raw_results_to_search_results(self, raw_list: List[dict]) -> List[SearchResult]:
        return [
            SearchResult(
                chunk_id=r.get("chunk_id", 0),
                document_id=r.get("document_id", 0),
                meeting_id=r.get("meeting_id"),
                content=r.get("content", r.get("chunk_text", "")),
                chunk_index=r.get("chunk_index", 0),
                similarity=r.get("similarity", 0.0),
                department=r.get("department"),
                speaker_name=r.get("speaker_name", ""),
                time_offset=r.get("time_offset"),
                metadata_json=r.get("metadata_json"),
            )
            for r in raw_list
        ]

    async def _retrieve_context(
        self,
        question: str,
        meeting_id: Optional[int] = None,
        document_ids: Optional[List[int]] = None,
        top_k: int = 5,
    ) -> List[SearchResult]:
        from app.core.config import settings
        
        # 从问题中提取明确的 document_id
        mentioned_ids = self._extract_document_ids_from_question(question)

        # 「文档全文摘要」意图：问题中明确提到 document_id 且是内容类问题
        if mentioned_ids and self._is_document_summary_intent(question):
            app_logger.info(f"[RETRIEVE] 检测到文档全文摘要意图，document_ids={mentioned_ids}")
            all_chunks: List[dict] = []
            for doc_id in mentioned_ids:
                chunks = await self.vector_search_service.get_document_chunks(doc_id)
                all_chunks.extend(chunks)
            if all_chunks:
                return self._raw_results_to_search_results(all_chunks)
            app_logger.warning(f"[RETRIEVE] 文档 {mentioned_ids} 无 chunk，回退向量检索")

        # 若问题中提到了 document_id，将其合并到过滤条件，扩大 top_k 提高覆盖率
        effective_doc_ids = document_ids or []
        if mentioned_ids:
            merged = list(dict.fromkeys(effective_doc_ids + mentioned_ids))
            effective_doc_ids = merged
            top_k = max(top_k, 10)

        # 使用多路召回（BM25 + 向量检索 + 重排序）
        if settings.ENABLE_MULTI_RETRIEVAL:
            app_logger.info(f"[RETRIEVE] 使用多路召回模式（BM25 + 向量 + 重排序）")
            search_results = await self.vector_search_service.search_with_multi_retrieval(
                query_text=question,
                top_k=top_k,
                document_ids=effective_doc_ids if effective_doc_ids else None,
                meeting_id=meeting_id,
                enable_bm25=settings.ENABLE_BM25,
                enable_vector=True,
                enable_rerank=settings.ENABLE_RERANK,
            )
        else:
            # 使用传统向量检索
            search_results = await self.vector_search_service.search_by_text(
                query_text=question,
                top_k=top_k,
                document_ids=effective_doc_ids if effective_doc_ids else None,
                meeting_id=meeting_id,
            )
        
        return self._raw_results_to_search_results(search_results)

    async def process_batch(
        self,
        questions: List[str],
        meeting_id: Optional[int] = None,
        document_ids: Optional[List[int]] = None,
    ) -> List[AgentResult]:
        results = []
        for question in questions:
            result = await self.process_query(
                question=question,
                meeting_id=meeting_id,
                document_ids=document_ids,
            )
            results.append(result)
        return results

    def get_memory_context(self, session_id: str, question: str) -> str:
        memory = self._get_session_memory(session_id)
        return memory.get_context_for_query(question)

    def get_memory_stats(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        if session_id:
            memory = self._get_session_memory(session_id)
            return memory.get_memory_stats()

        return {
            "sessions": len(self.session_memories),
            "total_short_term_turns": sum(
                len(m.short_term.raw_turns) for m in self.session_memories.values()
            ),
            "total_long_term_items": sum(
                len(m.long_term.items) for m in self.session_memories.values()
            )
        }

    def clear_session_memory(self, session_id: str):
        if session_id in self.session_memories:
            self.session_memories[session_id].clear_all()

    def save_checkpoint(self, session_id: str) -> Dict[str, Any]:
        """保存会话记忆检查点"""
        memory = self._get_session_memory(session_id)
        return memory.save_checkpoint(session_id)

    def load_checkpoint(self, session_id: str, checkpoint: Dict[str, Any]):
        """加载会话记忆检查点"""
        memory = self._get_session_memory(session_id)
        memory.load_checkpoint(checkpoint)

    def get_tools_info(self) -> Optional[Dict[str, Any]]:
        """获取工具信息"""
        if self.tool_manager:
            return self.tool_manager.get_tools_info()
        return None

    def get_tool_history(self) -> List[Dict[str, Any]]:
        """获取工具调用历史"""
        if self.tool_manager:
            return self.tool_manager.executor.get_history()
        return []

    def get_agent_architecture(self) -> Dict[str, Any]:
        return {
            "pattern": "Plan-Execute-Reflect + Tool Calling" if self.enable_tool_calling else "Plan-Execute-Reflect",
            "tool_calling_enabled": self.enable_tool_calling,
            "memory_enabled": self.enable_memory,
            "checkpointer_enabled": self.enable_checkpointer,
            "compression_enabled": self.enable_compression,
            "monitoring_enabled": self.enable_monitoring,
            "phases": [
                {
                    "name": "Plan",
                    "description": "分析问题，制定执行计划",
                    "capabilities": ["问题分析", "任务拆解", "工具选择"]
                },
                {
                    "name": "Execute",
                    "description": "根据计划执行任务",
                    "capabilities": ["任务执行", "工具调用", "并行处理"]
                },
                {
                    "name": "Reflect",
                    "description": "评估执行结果质量",
                    "capabilities": ["质量评估", "缺陷检测"]
                }
            ],
            "tools": self.get_tools_info() if self.enable_tool_calling else None
        }
        
    def get_prompt_templates(self) -> List[Dict[str, Any]]:
        """获取所有 Prompt 模板
        
        Returns:
            模板列表
        """
        return self.prompt_manager.list_templates()
        
    def get_error_stats(self) -> Dict[str, Any]:
        """获取错误统计
        
        Returns:
            统计信息
        """
        return self.error_manager.get_error_stats()
        
    def get_monitor_status(self) -> Dict[str, Any]:
        """获取监控状态
        
        Returns:
            监控状态
        """
        if self.monitor:
            return self.monitor.get_monitor_status()
        return {"monitoring_enabled": False}
        
    def get_recent_errors(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最近的错误
        
        Args:
            limit: 返回数量限制
            
        Returns:
            错误列表
        """
        return self.error_manager.get_recent_errors(limit)
    
    # ==================== 人机协作相关方法 ====================
    
    def respond_to_confirmation(self, request_id: str, response: str) -> bool:
        """
        响应用户确认请求
        
        Args:
            request_id: 请求ID
            response: 响应（approved/rejected）
            
        Returns:
            True: 响应成功
            False: 请求不存在或已处理
        """
        return self.hitl_service.respond_to_request(request_id, response)
    
    def get_pending_confirmations(self) -> List[Dict[str, Any]]:
        """
        获取所有待处理的确认请求
        
        Returns:
            待处理请求列表
        """
        return self.hitl_service.get_pending_requests()
    
    def get_confirmation_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取确认请求历史
        
        Args:
            limit: 返回数量限制
            
        Returns:
            请求历史列表
        """
        return self.hitl_service.get_request_history(limit)
    
    def get_confirmation_by_id(self, request_id: str) -> Optional[Dict[str, Any]]:
        """
        根据ID获取确认请求
        
        Args:
            request_id: 请求ID
            
        Returns:
            请求详情，不存在返回None
        """
        return self.hitl_service.get_request_by_id(request_id)