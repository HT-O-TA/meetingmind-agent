"""Agent 服务封装 - 支持 Tool Calling
"""
from typing import Optional, List, Dict, Any, TypedDict
import uuid
from app.agents.state import AgentState, AgentResult, ChunkMetadata, TaskType, RiskLevel, Plan, ReflectionResult
from app.agents.graph import create_agent_graph, print_agent_architecture
from app.agents.nodes import AgentNodes
from app.agents.memory import MemoryManager
from app.agents.tools import ToolManager
from app.agents.prompts import PromptManager
from app.agents.errors import ErrorRecoveryManager
from app.agents.monitor import AgentMonitor
from app.agents.session_context import SessionContext, generate_session_id, generate_conversation_id
from app.services.llm_service import LLMService
from app.services.vector_search_service import VectorSearchService
from app.services.unified_memory_service import get_unified_memory
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
        enable_human_in_the_loop: bool = True,
        enable_tool_calling: bool = True,
        max_short_term_turns: int = 20,
        max_long_term_items: int = 1000,
        enable_compression: bool = True,
        enable_monitoring: bool = True,
    ):
        self.llm_service = llm_service
        self.vector_search_service = vector_search_service
        self.enable_checkpointer = enable_checkpointer
        self.enable_memory = enable_memory
        self.enable_compression = enable_compression
        self.enable_monitoring = enable_monitoring
        self.enable_human_in_the_loop = enable_human_in_the_loop
        self.enable_tool_calling = enable_tool_calling

        # 初始化核心模块
        self.prompt_manager = PromptManager()
        self.error_manager = ErrorRecoveryManager()
        self.monitor = AgentMonitor() if enable_monitoring else None

        # 人机协作服务
        from app.agents.human_in_the_loop import get_hitl_service
        self.hitl_service = get_hitl_service()

        # 工具管理器（默认启用 Tool Calling）
        self.tool_manager = ToolManager(llm_service, vector_search_service)
        # create_agent_graph 是唯一编译入口，避免已编译图再次 compile。
        self.graph = create_agent_graph(
            llm_service,
            self.tool_manager,
            enable_react=False,
            enable_cot=False,
            enable_fallback=True,
            enable_reflection=False,
            use_checkpointer=enable_checkpointer,
        )
        print_agent_architecture()
        self.app = self.graph

        # 记忆管理
        self.memory_manager = MemoryManager(
            max_short_term_turns=max_short_term_turns,
            max_long_term_items=max_long_term_items,
            enable_compression=enable_compression,
            llm_service=llm_service if enable_compression else None
        )
        
        # 统一记忆服务（Phase 3: 替代旧 long_term_memory 接口）
        self.unified_memory = get_unified_memory()

        # 每个会话的记忆管理器
        self.session_memories: Dict[str, MemoryManager] = {}

        if enable_checkpointer:
            self.memory_manager.enable_checkpoint()

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
            self.monitor.info(f"Tool Calling: True (默认启用)")
            span_id = self.monitor.start_span("agent_process_query", attributes={"question": question[:50]})

        session_id = config.get("thread_id") if config else None
        memory = self._get_session_memory(session_id or "default")

        async def emit_event(event_type, data):
            if event_callback:
                await event_callback(event_type, data)

        try:
            await emit_event("start", {"question": question, "phase": "初始化"})

            # 获取会话记忆上下文
            memory_context = ""
            if self.enable_memory:
                memory_context = memory.get_context_for_query(question, n_recent=3)

            # 获取长期记忆上下文
            long_term_context = ""
            try:
                long_term_context = await self.unified_memory.generate_context_prompt(question)
            except Exception as e:
                app_logger.warning(f"获取长期记忆上下文失败: {e}")

            # 文档检索已迁移到图内 retrieve_node；这里仅注入会话记忆和长期记忆上下文。
            raw_context = []
            if long_term_context:
                raw_context.insert(0, long_term_context)
            if memory_context and self.enable_memory:
                raw_context.insert(0, f"【相关记忆】\n{memory_context}")

            # 初始化状态
            initial_state: AgentState = {
                "question": question,
                "agent_run_id": str(uuid.uuid4()),
                "approved_tool_call": None,
                "resume_from_tool_index": None,
                "meeting_id": meeting_id,
                "document_ids": document_ids,
                "context": [],
                "raw_context": raw_context,
                "current_phase": "plan",
                "task_type": TaskType.QA,
                "workflow_type": None,
                "reasoning_mode": None,
                "complexity_score": 0.0,
                "complexity_level": None,
                "is_multi_task": False,
                "route_reason": "",
                "retrieval_required": True,
                "retrieval_confidence": 0.0,
                "citations": [],
                "validation_errors": [],
                "policy_results": [],
                "repair_count": 0,
                "max_repair_attempts": 1,
                "risk_level": RiskLevel.LOW,
                "requires_confirmation": False,
                "confirmation_status": "not_required",
                "pending_action": None,
                "plan": None,
                "task_contexts": {},
                "minutes": None,
                "todos": None,
                "controversies": None,
                "answer": None,
                "reflection": None,
                "error": None,
                "cot_thoughts": [],
                "agents_involved": [],
                "last_strategy": None,
                "fallback_count": 0,
                "event_callback": event_callback,
                "human_confirmations": [],
                "enable_human_in_the_loop": self.enable_human_in_the_loop,
                "session_context": None,
                "access_scope": context.access_scope,
            }

            # 执行
            await emit_event("phase", {"phase": "execute", "message": "开始执行Agent..."})
            invoke_config = {"configurable": config} if config else None
            final_state = await self.app.ainvoke(initial_state, config=invoke_config)

            # 确保 final_state 中的关键字段类型正确
            if not isinstance(final_state.get("cot_thoughts"), list):
                final_state["cot_thoughts"] = []
            if not isinstance(final_state.get("agents_involved"), list):
                final_state["agents_involved"] = []
                
            # 构建结果 - 先全面清理状态
            # 确保 final_state 中的所有字段都是可哈希的
            safe_final_state = {}
            for key, value in final_state.items():
                if isinstance(value, slice):
                    app_logger.warning(f"⚠️ 检测到 slice 对象在字段 {key}，已重置")
                    if key == "cot_thoughts" or key == "agents_involved" or key == "human_confirmations":
                        safe_final_state[key] = []
                    elif key == "task_contexts":
                        safe_final_state[key] = {}
                    elif key == "todos" or key == "controversies":
                        safe_final_state[key] = None
                    else:
                        safe_final_state[key] = None
                else:
                    safe_final_state[key] = value
            final_state = safe_final_state
            
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
                    "tool_calls": plan.get("tool_calls", [])
                }

            # 确保 reflection 包含 quality_score 字段（向后兼容）
            if reflection and isinstance(reflection, dict):
                reflection = reflection.copy()
                # 确保所有数值字段都是 float 类型
                if 'overall_score' in reflection:
                    reflection['overall_score'] = float(reflection['overall_score'])
                    reflection['quality_score'] = reflection['overall_score']  # 向后兼容
                if 'confidence' in reflection:
                    reflection['confidence'] = float(reflection['confidence'])
                if 'metrics' in reflection and isinstance(reflection['metrics'], dict):
                    metrics = reflection['metrics']
                    for key in ['accuracy', 'relevance', 'completeness', 'coherence']:
                        if key in metrics:
                            metrics[key] = float(metrics[key])
            
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
                workflow_type=final_state.get("workflow_type"),
                route_reason=final_state.get("route_reason"),
                citations=final_state.get("citations"),
                validation_errors=final_state.get("validation_errors"),
                policy_results=final_state.get("policy_results"),
                retrieval_confidence=final_state.get("retrieval_confidence"),
                risk_level=final_state.get("risk_level"),
                requires_confirmation=bool(final_state.get("requires_confirmation", False)),
                confirmation_status=final_state.get("confirmation_status"),
                pending_action=final_state.get("pending_action"),
                route_decision=final_state.get("route_decision"),
                structured_outputs=final_state.get("structured_outputs"),
            )

            # 保存会话记忆
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

            # 保存长期记忆（会议总结、决策、待办）
            try:
                if result.minutes or result.todos:
                    await self.unified_memory.add_memory(
                        content=result.minutes or result.answer or question,
                        memory_type="meeting_summary",
                        meeting_id=meeting_id,
                        metadata={"topic": question},
                        importance_score=0.7,
                    )
                if result.todos:
                    for todo in result.todos:
                        content = todo.get("content", "")
                        if content:
                            await self.unified_memory.add_action_item(
                                content=content,
                                meeting_id=meeting_id,
                                entities=[todo.get("assignee", "")] if todo.get("assignee") else [],
                            )
            except Exception as e:
                app_logger.warning(f"保存长期记忆失败: {e}")

            # 统计
            thoughts = final_state.get("cot_thoughts", [])
            phases = {}
            for t in thoughts:
                phase = t.get("phase", "unknown")
                phases[phase] = phases.get(phase, 0) + 1

            self.monitor.info(f"[Agent] 处理完成 - 任务: {result.task_type.value}, 思维链: {len(thoughts)} 步") if self.monitor else app_logger.info(f"[Agent] 处理完成 - 任务: {result.task_type.value}, 思维链: {len(thoughts)} 步")
            if result.reflection:
                overall_score = result.reflection.get('overall_score', 0)
                metrics = result.reflection.get('metrics', {})
                confidence = result.reflection.get('confidence', 0)
                self.monitor.info(f"[Agent] 综合评分: {overall_score:.2f} (置:{confidence:.2f})") if self.monitor else app_logger.info(f"[Agent] 综合评分: {overall_score:.2f} (置:{confidence:.2f})")
                if metrics:
                    metrics_str = f"  准:{metrics.get('accuracy',0):.2f} 相:{metrics.get('relevance',0):.2f} 完:{metrics.get('completeness',0):.2f} 贯:{metrics.get('coherence',0):.2f}"
                    self.monitor.info(metrics_str) if self.monitor else app_logger.info(metrics_str)

            if span_id:
                self.monitor.finish_span(span_id, {"success": True, "task_type": result.task_type.value})
                
            return result

        except Exception as e:
            import traceback
            stack_trace = traceback.format_exc()
            self.monitor.error(f"[Agent] 处理失败: {e}\n{stack_trace}") if self.monitor else app_logger.error(f"[Agent] 处理失败: {e}\n{stack_trace}")
            
            # 记录错误
            error_info = self.error_manager.handle_error(e, {"question": question})
            
            if span_id:
                self.monitor.finish_span(span_id, {"success": False, "error": str(e)})
            
            return AgentResult(
                success=False,
                task_type=TaskType.QA,
                error=str(e),
            )

    async def process_query_with_context(
        self,
        question: str,
        context: SessionContext,
        document_ids: Optional[List[int]] = None,
        event_callback: Optional[callable] = None,
    ) -> AgentResult:
        """使用 SessionContext 处理用户查询（推荐入口）

        通过 SessionContext 统一管理四层 ID，确保会话隔离。
        - thread_id: session_id:conversation_id（LangGraph 唯一标识）
        - session_id: 浏览器会话（记忆系统隔离）
        - meeting_id: 业务域过滤
        """
        span_id = None
        if self.monitor:
            self.monitor.info(f"开始处理查询 (context): {question}")
            span_id = self.monitor.start_span(
                "agent_process_query_with_context",
                attributes={
                    "question": question[:50],
                    "thread_id": context.thread_id,
                    "session_id": context.session_id,
                }
            )

        memory = self._get_session_memory(context.session_id)

        async def emit_event(event_type, data):
            if event_callback:
                await event_callback(event_type, data)

        try:
            await emit_event("start", {
                "question": question,
                "phase": "初始化",
                "thread_id": context.thread_id,
                "session_id": context.session_id,
            })

            # 获取会话记忆上下文
            memory_context = ""
            if self.enable_memory:
                memory_context = memory.get_context_for_query(question, n_recent=3)

            # 获取长期记忆上下文
            long_term_context = ""
            try:
                long_term_context = await self.unified_memory.generate_context_prompt(
                    question,
                    meeting_id=context.meeting_id,
                )
            except Exception as e:
                app_logger.warning(f"获取长期记忆上下文失败: {e}")

            raw_context = []
            if long_term_context:
                raw_context.insert(0, long_term_context)
            if memory_context and self.enable_memory:
                raw_context.insert(0, f"【相关记忆】\n{memory_context}")

            initial_state: AgentState = {
                "question": question,
                "agent_run_id": str(uuid.uuid4()),
                "approved_tool_call": None,
                "resume_from_tool_index": None,
                "thread_id": context.thread_id,
                "meeting_id": context.meeting_id,
                "document_ids": document_ids,
                "context": [],
                "raw_context": raw_context,
                "current_phase": "plan",
                "task_type": TaskType.QA,
                "workflow_type": None,
                "reasoning_mode": None,
                "complexity_score": 0.0,
                "complexity_level": None,
                "is_multi_task": False,
                "route_reason": "",
                "retrieval_required": True,
                "retrieval_confidence": 0.0,
                "citations": [],
                "validation_errors": [],
                "policy_results": [],
                "repair_count": 0,
                "max_repair_attempts": 1,
                "risk_level": RiskLevel.LOW,
                "requires_confirmation": False,
                "confirmation_status": "not_required",
                "pending_action": None,
                "plan": None,
                "task_contexts": {},
                "minutes": None,
                "todos": None,
                "controversies": None,
                "answer": None,
                "reflection": None,
                "last_strategy": None,
                "fallback_count": 0,
                "session_context": None,
                "error": None,
                "cot_thoughts": [],
                "agents_involved": [],
                "event_callback": event_callback,
                "human_confirmations": [],
                "enable_human_in_the_loop": self.enable_human_in_the_loop,
                "access_scope": context.access_scope,
            }

            await emit_event("phase", {"phase": "execute", "message": "开始执行Agent..."})

            # 使用 SessionContext 生成 config
            invoke_config = context.get_config()
            final_state = await self.app.ainvoke(initial_state, config=invoke_config)

            # 安全处理 final_state
            safe_final_state = {}
            for key, value in final_state.items():
                if isinstance(value, slice):
                    app_logger.warning(f"检测到 slice 对象在字段 {key}，已重置")
                    if key in ("cot_thoughts", "agents_involved", "human_confirmations"):
                        safe_final_state[key] = []
                    elif key == "task_contexts":
                        safe_final_state[key] = {}
                    else:
                        safe_final_state[key] = None
                else:
                    safe_final_state[key] = value
            final_state = safe_final_state

            # 保存对话到会话记忆
            if self.enable_memory:
                try:
                    memory.add_exchange(question, final_state.get("answer", ""))
                except Exception as e:
                    app_logger.warning(f"保存会话记忆失败: {e}")

            # 异步写入长期记忆
            answer = final_state.get("answer")
            if answer and context.meeting_id:
                try:
                    import asyncio
                    asyncio.create_task(
                        self.unified_memory.add_meeting_memory(
                            meeting_id=str(context.meeting_id),
                            title=question[:80],
                            content=answer,
                            session_id=context.session_id,
                        )
                    )
                except Exception as e:
                    app_logger.warning(f"异步写入长期记忆失败: {e}")

            # 构建结果
            result_payload = self._state_to_result_payload(final_state)
            result_payload.update({
                "session_id": context.session_id,
                "conversation_id": context.conversation_id,
                "thread_id": context.thread_id,
                "meeting_id": context.meeting_id,
            })

            await emit_event("complete", {
                "phase": "完成",
                "answer_length": len(str(final_state.get("answer", ""))),
            })

            if span_id:
                self.monitor.finish_span(span_id, {"success": True})

            task_type = final_state.get("task_type") or TaskType.QA
            reflection = final_state.get("reflection")
            if reflection and isinstance(reflection, dict):
                reflection = reflection.copy()
                if 'overall_score' in reflection:
                    reflection['overall_score'] = float(reflection['overall_score'])
                    reflection['quality_score'] = reflection['overall_score']
                if 'confidence' in reflection:
                    reflection['confidence'] = float(reflection['confidence'])

            plan = final_state.get("plan")
            formatted_plan = None
            if plan:
                formatted_plan = {
                    "analysis": plan.get("analysis", ""),
                    "tasks": plan.get("tasks", []),
                    "execution_order": plan.get("execution_order", []),
                    "parallel_groups": plan.get("parallel_groups", []),
                    "tool_calls": plan.get("tool_calls", []),
                }

            return AgentResult(
                success=True,
                task_type=task_type,
                answer=final_state.get("answer"),
                minutes=final_state.get("minutes"),
                todos=final_state.get("todos"),
                controversies=final_state.get("controversies"),
                thoughts=final_state.get("cot_thoughts"),
                reflection=reflection,
                plan=formatted_plan,
                workflow_type=final_state.get("workflow_type"),
                route_reason=final_state.get("route_reason"),
                citations=final_state.get("citations"),
                validation_errors=final_state.get("validation_errors"),
                policy_results=final_state.get("policy_results"),
                retrieval_confidence=final_state.get("retrieval_confidence"),
                risk_level=final_state.get("risk_level"),
                requires_confirmation=bool(final_state.get("requires_confirmation", False)),
                confirmation_status=final_state.get("confirmation_status"),
                pending_action=final_state.get("pending_action"),
                route_decision=final_state.get("route_decision"),
                structured_outputs=final_state.get("structured_outputs"),
            )

        except Exception as e:
            app_logger.error(f"Agent 执行失败: {e}")
            if span_id:
                self.monitor.finish_span(span_id, {"success": False, "error": str(e)})
            return AgentResult(
                success=False,
                task_type=TaskType.QA,
                error=str(e),
            )

    async def process_batch(
        self,
        questions: List[str],
        meeting_id: Optional[int] = None,
        document_ids: Optional[List[int]] = None,
        context: Optional[SessionContext] = None,
    ) -> List[AgentResult]:
        results = []
        for question in questions:
            if context is not None:
                result = await self.process_query_with_context(
                    question=question,
                    context=context,
                    document_ids=document_ids,
                )
            else:
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

    def get_tools_info(self) -> Dict[str, Any]:
        """获取工具信息"""
        return self.tool_manager.get_tools_info()

    def get_tool_history(self) -> List[Dict[str, Any]]:
        """获取工具调用历史"""
        return self.tool_manager.executor.get_history()

    def get_agent_architecture(self) -> Dict[str, Any]:
        return {
            "pattern": "Plan-Execute-Replan + Tool Calling",
            "recommended_pattern": "Intent Routing + Direct Workflows + Plan-Execute-Replan for complex tasks",
            "tool_calling_enabled": True,
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
                    "description": "按计划执行任务",
                    "capabilities": ["任务执行", "工具调用", "并行处理"]
                },
                {
                    "name": "Replan",
                    "description": "评估执行结果质量，决定是否重新规划",
                    "capabilities": ["质量评估", "缺陷检测", "重新规划", "循环改进"]
                }
            ],
            "tools": self.get_tools_info()
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
    
    async def respond_to_confirmation(
        self, request_id: str, response: str, user_id: Optional[int] = None
    ) -> bool:
        """
        响应用户确认请求
        
        Args:
            request_id: 请求ID
            response: 响应（approved/rejected）
            
        Returns:
            True: 响应成功
            False: 请求不存在或已处理
        """
        return await self.hitl_service.respond_to_request(request_id, response, user_id)

    async def resume_confirmation(
        self,
        request_id: str,
        response: str = "approved",
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        响应确认请求，并在没有原始运行请求可继续时从确认点快照恢复执行。
        """
        request = await self.hitl_service.get_request_status(request_id, user_id)
        if not request:
            return {"success": False, "mode": "not_found", "message": f"确认请求 {request_id} 不存在"}
        if request.get("status") != "pending":
            return {"success": False, "mode": "already_processed", "message": "确认请求已处理"}

        snapshot = await self.hitl_service.get_resume_state(request_id, user_id)

        if response != "approved":
            success = await self.hitl_service.respond_to_request(request_id, response, user_id)
            return {
                "success": success,
                "mode": "rejected",
                "message": "确认请求已拒绝" if success else "确认请求不存在或已处理",
            }

        if not snapshot:
            return {"success": False, "mode": "snapshot_missing", "message": "确认点恢复快照不存在"}

        pending_action = snapshot.get("pending_action") or {}
        if pending_action.get("source") != "tool":
            return {"success": False, "mode": "unsupported", "message": "当前仅支持从工具确认点恢复执行"}

        success = await self.hitl_service.respond_to_request(request_id, "approved", user_id)
        if not success:
            return {"success": False, "mode": "respond_failed", "message": "确认请求批准失败"}

        nodes = AgentNodes(self.llm_service, self.tool_manager)
        resumed_state = snapshot.copy()
        resumed_state["confirmation_status"] = "approved"
        resumed_state["requires_confirmation"] = False
        resumed_state["enable_human_in_the_loop"] = True
        resumed_state = await nodes.execute_agent(resumed_state)
        resumed_state = await nodes.replan_agent(resumed_state)
        resumed_state = await nodes.validate_node(resumed_state)

        return {
            "success": True,
            "mode": "snapshot",
            "message": "已从确认点恢复执行",
            "result": self._state_to_result_payload(resumed_state),
        }

    def _state_to_result_payload(self, state: AgentState) -> Dict[str, Any]:
        task_type = state.get("task_type") or TaskType.QA
        workflow_type = state.get("workflow_type")
        risk_level = state.get("risk_level")
        return {
            "success": True,
            "task_type": task_type.value if hasattr(task_type, "value") else task_type,
            "workflow_type": workflow_type.value if hasattr(workflow_type, "value") else workflow_type,
            "route_reason": state.get("route_reason"),
            "retrieval_confidence": state.get("retrieval_confidence"),
            "citations": state.get("citations"),
            "validation_errors": state.get("validation_errors"),
            "policy_results": state.get("policy_results"),
            "risk_level": risk_level.value if hasattr(risk_level, "value") else risk_level,
            "requires_confirmation": bool(state.get("requires_confirmation", False)),
            "confirmation_status": state.get("confirmation_status"),
            "pending_action": state.get("pending_action"),
            "answer": state.get("answer"),
            "minutes": state.get("minutes"),
            "todos": state.get("todos"),
            "controversies": state.get("controversies"),
            "error": state.get("error"),
            "thoughts": state.get("cot_thoughts"),
            "reflection": state.get("reflection"),
            "plan": state.get("plan"),
            "route_decision": state.get("route_decision").to_dict() if state.get("route_decision") and hasattr(state.get("route_decision"), "to_dict") else None,
            "route_confidence": state.get("route_confidence"),
            "route_candidates": state.get("route_candidates"),
            "route_decision_trace": state.get("route_decision_trace"),
        }
    
    async def get_pending_confirmations(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        获取所有待处理的确认请求
        
        Returns:
            待处理请求列表
        """
        return await self.hitl_service.list_pending_requests(user_id)
    
    async def get_confirmation_history(
        self, limit: int = 50, user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        获取确认请求历史
        
        Args:
            limit: 返回数量限制
            
        Returns:
            请求历史列表
        """
        return await self.hitl_service.list_request_history(limit, user_id)
    
    async def get_confirmation_by_id(
        self, request_id: str, user_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        根据ID获取确认请求
        
        Args:
            request_id: 请求ID
            
        Returns:
            请求详情，不存在返回None
        """
        return await self.hitl_service.get_request_status(request_id, user_id)
