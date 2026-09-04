"""Agent 服务封装 - 支持 Tool Calling
"""
from typing import Optional, List, Dict, Any, TypedDict
import uuid
from app.agents.state import AgentState, AgentResult, ChunkMetadata, TaskType, RiskLevel, Plan, ReflectionResult
from app.agents.graph import create_agent_graph
from app.agents.checkpoint import get_default_checkpoint_saver
from app.agents.nodes import AgentNodes
from app.agents.memory import MemoryManager, SessionMemoryStore
from app.agents.tools import ToolManager
from app.agents.session_context import SessionContext
from app.agents.trace_integration import get_trace_store
from app.services.llm_service import LLMService
from app.services.token_budget_ledger import (
    TokenBudgetExceeded,
    TokenBudgetLedger,
    activate_token_budget_ledger,
    token_budget_node_scope,
)
from app.services.vector_search_service import VectorSearchService
from app.services.input_preprocessor import InputContractError, InputPreprocessor
from app.services.memory_repository import MemoryRepository
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
        enable_human_in_the_loop: bool = True,
        max_short_term_turns: int = 10,
        memory_store: Optional[SessionMemoryStore] = None,
        checkpointer: Optional[Any] = None,
        memory_repository: Optional[MemoryRepository] = None,
    ):
        self.llm_service = llm_service
        self.vector_search_service = vector_search_service
        self.enable_human_in_the_loop = enable_human_in_the_loop

        # 人机协作服务
        from app.agents.human_in_the_loop import get_hitl_service
        self.hitl_service = get_hitl_service()

        # 工具管理器（默认启用 Tool Calling）
        self.tool_manager = ToolManager(llm_service, vector_search_service)
        # create_agent_graph 是唯一编译入口，避免已编译图再次 compile。
        # 检查点负责任务恢复；短期对话仍由有界 SessionMemoryStore 管理。
        self.checkpointer = checkpointer if checkpointer is not None else get_default_checkpoint_saver()
        self.graph = create_agent_graph(
            llm_service,
            self.tool_manager,
            checkpointer=self.checkpointer,
        )
        app_logger.info("Agent 主线: route -> safety -> retrieve/business or policy/HITL/tool -> validate")
        self.app = self.graph

        self.max_short_term_turns = max_short_term_turns
        self.memory_store = memory_store or SessionMemoryStore(
            max_sessions=1000,
            max_raw_turns=max_short_term_turns,
        )
        # 长期事实仓库显式注入；默认保持进程内适配器，普通回答不会自动落长期事实。
        self.memory_repository = memory_repository
        self.resume_access_scope: Optional[Dict[str, Any]] = None

    def _get_session_memory(self, memory_key: str) -> MemoryManager:
        """按包含 user_id 的 thread_id 获取有界会话记忆。"""
        return self.memory_store.get(memory_key)

    async def remember_fact(
        self,
        *,
        context: SessionContext,
        key: str,
        value: str,
        confidence: float = 0.8,
        importance: float = 0.7,
        source: str = "user",
        source_ref: Optional[str] = None,
        meeting_id: Optional[int] = None,
        document_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Any]:
        """显式写入长期事实；不把普通 Agent 答案隐式升级成事实。"""

        if self.memory_repository is None:
            return None
        memory = self._get_session_memory(context.thread_id)
        namespace = memory.active_namespace
        if namespace == "default":
            namespace = memory.resolve_task_namespace(
                key,
                meeting_id=meeting_id if meeting_id is not None else context.meeting_id,
                document_ids=[document_id] if document_id is not None else None,
            )
        return await self.memory_repository.write_fact(
            namespace=namespace,
            key=key,
            value=value,
            user_id=context.user_id,
            thread_id=context.thread_id,
            meeting_id=meeting_id if meeting_id is not None else context.meeting_id,
            document_id=document_id,
            source=source,
            source_ref=source_ref,
            confidence=confidence,
            importance=importance,
            metadata=metadata,
        )

    async def search_long_term_memory(
        self,
        *,
        context: SessionContext,
        query: str,
        meeting_id: Optional[int] = None,
        document_id: Optional[int] = None,
        limit: int = 10,
    ) -> List[Any]:
        """按当前线程任务空间检索长期事实；未注入仓库时安全返回空列表。"""

        if self.memory_repository is None:
            return []
        memory = self._get_session_memory(context.thread_id)
        namespace = memory.active_namespace
        if namespace == "default":
            namespace = memory.resolve_task_namespace(
                query,
                meeting_id=meeting_id if meeting_id is not None else context.meeting_id,
                document_ids=[document_id] if document_id is not None else None,
            )
        return await self.memory_repository.search(
            query,
            namespace=namespace,
            user_id=context.user_id,
            thread_id=context.thread_id,
            meeting_id=meeting_id if meeting_id is not None else context.meeting_id,
            document_id=document_id,
            limit=limit,
        )

    async def forget_long_term_memory(
        self,
        *,
        context: SessionContext,
        namespace: Optional[str] = None,
        meeting_id: Optional[int] = None,
        document_id: Optional[int] = None,
    ) -> int:
        """按当前用户范围删除长期事实；不能删除其他用户的数据。"""

        if self.memory_repository is None or context.user_id is None:
            return 0
        return await self.memory_repository.delete_scope(
            user_id=context.user_id,
            thread_id=context.thread_id,
            namespace=namespace,
            meeting_id=meeting_id if meeting_id is not None else context.meeting_id,
            document_id=document_id,
        )

    async def process_query(
        self,
        question: str,
        meeting_id: Optional[int] = None,
        document_ids: Optional[List[int]] = None,
        config: Optional[Dict[str, Any]] = None,
        event_callback: Optional[callable] = None,
    ) -> AgentResult:
        """兼容入口；统一转入带 SessionContext 的执行主链。"""
        config = config or {}
        configurable = config.get("configurable", {})
        thread_id = config.get("thread_id") or configurable.get("thread_id") or ""
        session_id, conversation_id = SessionContext.parse_thread_id(thread_id)
        context = SessionContext(
            user_id=configurable.get("user_id"),
            session_id=session_id,
            conversation_id=conversation_id,
            meeting_id=meeting_id,
            access_scope=configurable.get("access_scope"),
            task_id=configurable.get("task_id"),
        )
        return await self.process_query_with_context(
            question=question,
            context=context,
            document_ids=document_ids,
            event_callback=event_callback,
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
        - thread_id: user_id:session_id:conversation_id（LangGraph 唯一标识）
        - session_id: 浏览器会话
        - meeting_id: 业务域过滤
        """
        trace_store = get_trace_store()
        span_id = trace_store.start("agent_query", "agent")
        agent_run_id = str(uuid.uuid4())
        budget_ledger = TokenBudgetLedger.from_settings(agent_run_id)

        memory = self._get_session_memory(context.thread_id)
        task_namespace = memory.resolve_task_namespace(
            question,
            task_id=context.task_id,
            meeting_id=context.meeting_id,
            document_ids=document_ids,
        )

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

            raw_context = memory.get_context_items_for_query(
                question,
                n_recent=3,
                namespace=task_namespace,
            )

            initial_state: AgentState = {
                "question": question,
                "agent_run_id": agent_run_id,
                "user_id": context.user_id,
                "session_id": context.session_id,
                "conversation_id": context.conversation_id,
                "input_envelope": None,
                "task_anchor": None,
                "input_blocked": False,
                "input_block_reason": None,
                "injection_check": None,
                "injection_blocked": False,
                "injection_block_reason": None,
                "approved_tool_call": None,
                "resume_from_tool_index": None,
                "thread_id": context.thread_id,
                "task_id": context.task_id,
                "task_namespace": task_namespace,
                "meeting_id": context.meeting_id,
                "document_ids": document_ids,
                "context": [],
                "raw_context": raw_context,
                "context_manifest": None,
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
                "structured_outputs": {},
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
            invoke_config = context.get_config(run_id=agent_run_id)
            with activate_token_budget_ledger(budget_ledger):
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
            budget_snapshot = budget_ledger.snapshot()
            envelope = final_state.get("input_envelope")
            if isinstance(envelope, dict):
                envelope.setdefault("budget", {})["token_ledger"] = budget_snapshot

            memory.set_active_namespace(task_namespace)
            memory.add_exchange(
                question,
                final_state.get("answer") or "",
                namespace=task_namespace,
            )

            await emit_event("complete", {
                "phase": "完成",
                "answer_length": len(str(final_state.get("answer", ""))),
            })

            trace_store.update(span_id, output=str(final_state.get("answer") or "")[:500])
            trace_store.finish(span_id)

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
                thoughts=None,
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
                budget_ledger=budget_snapshot,
                context_manifest=final_state.get("context_manifest"),
            )

        except TokenBudgetExceeded as e:
            app_logger.warning("Agent Token 预算门禁拒绝继续调用: %s", e)
            trace_store.finish(span_id, "token_budget_exceeded")
            return AgentResult(
                success=False,
                task_type=TaskType.QA,
                error="Agent token budget exceeded",
                budget_ledger=budget_ledger.snapshot(),
            )
        except Exception as e:
            app_logger.error(f"Agent 执行失败: {e}")
            trace_store.finish(span_id, str(e))
            return AgentResult(
                success=False,
                task_type=TaskType.QA,
                error="Agent execution failed",
                budget_ledger=budget_ledger.snapshot(),
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
        access_scope: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        响应确认请求，并在没有原始运行请求可继续时从确认点快照恢复执行。
        """
        access_scope = access_scope or self.resume_access_scope
        request = await self.hitl_service.get_request_status(request_id, user_id)
        if not request:
            return {"success": False, "mode": "not_found", "message": f"确认请求 {request_id} 不存在"}
        request_status = request.get("status")
        run_status = request.get("run_status", "pending")
        if request_status not in {"pending", "approved"} or (
            request_status == "approved" and run_status == "succeeded"
        ):
            return {"success": False, "mode": "already_processed", "message": "确认请求已处理"}

        snapshot = await self.hitl_service.get_resume_state(request_id, user_id)
        snapshot_source = "snapshot"
        if not snapshot:
            snapshot = await self._load_checkpoint_resume_state_async(request, user_id)
            snapshot_source = "checkpoint" if snapshot else snapshot_source

        if response != "approved":
            success = await self.hitl_service.respond_to_request(request_id, response, user_id)
            if success:
                await self._acleanup_checkpoint(request.get("details") or {})
            return {
                "success": success,
                "mode": "rejected",
                "message": "确认请求已拒绝" if success else "确认请求不存在或已处理",
            }

        if not snapshot:
            return {"success": False, "mode": "snapshot_missing", "message": "确认点恢复快照不存在"}

        details = request.get("details") or {}
        snapshot_user_id = snapshot.get("user_id")
        if snapshot_user_id is None:
            snapshot_user_id = (snapshot.get("access_scope") or {}).get("user_id")
        if user_id is not None and str(snapshot_user_id) != str(user_id):
            return {"success": False, "mode": "checkpoint_owner_mismatch", "message": "确认点不属于当前用户"}
        for key in ("thread_id", "agent_run_id"):
            expected = details.get(key)
            actual = snapshot.get(key)
            if expected and actual and str(expected) != str(actual):
                return {"success": False, "mode": "checkpoint_identity_mismatch", "message": f"确认点 {key} 不一致"}

        # Permissions are reconstructed from the current authenticated user;
        # the scope persisted in a checkpoint is diagnostic only.
        if access_scope is not None:
            state_for_scope = dict(snapshot)
            state_for_scope["access_scope"] = access_scope
            try:
                current_envelope = InputPreprocessor().build_envelope(state_for_scope)
            except InputContractError:
                return {"success": False, "mode": "checkpoint_scope_denied", "message": "当前用户已无权访问确认点资源"}
            snapshot["access_scope"] = access_scope
        else:
            current_envelope = None

        # 恢复前重新验证输入契约，防止篡改或旧版本快照绕过 input.v1。
        try:
            snapshot["input_envelope"] = InputPreprocessor.validate_envelope(
                snapshot.get("input_envelope")
            )
            if current_envelope is not None:
                snapshot["input_envelope"]["scope"] = current_envelope["scope"]
            snapshot["task_anchor"] = snapshot["input_envelope"]["task_anchor"]
        except InputContractError:
            return {
                "success": False,
                "mode": "invalid_input_envelope",
                "message": "确认点 InputEnvelope 无效，拒绝恢复执行",
            }

        pending_action = snapshot.get("pending_action") or {}
        if pending_action.get("source") != "tool":
            return {"success": False, "mode": "unsupported", "message": "当前仅支持从工具确认点恢复执行"}

        saved_ledger = (
            ((snapshot.get("input_envelope") or {}).get("budget") or {}).get("token_ledger")
        )
        if not isinstance(saved_ledger, dict):
            return {
                "success": False,
                "mode": "budget_snapshot_missing",
                "message": "确认点缺少 Token 预算快照，拒绝重置原运行预算",
            }
        try:
            budget_ledger = TokenBudgetLedger.from_snapshot(saved_ledger)
        except (KeyError, TypeError, ValueError):
            return {
                "success": False,
                "mode": "invalid_budget_snapshot",
                "message": "确认点 Token 预算快照无效，拒绝绕过原运行预算",
            }

        claimed = await self.hitl_service.claim_request(request_id, user_id)
        if not claimed:
            return {
                "success": False,
                "mode": "already_running",
                "message": "确认请求正在由其他执行器处理，或租约尚未到期",
            }
        claim_token = claimed.get("claim_token")

        nodes = AgentNodes(self.llm_service, self.tool_manager)
        resumed_state = snapshot.copy()
        resumed_state["confirmation_status"] = "approved"
        resumed_state["requires_confirmation"] = False
        resumed_state["enable_human_in_the_loop"] = True
        try:
            with activate_token_budget_ledger(budget_ledger):
                with token_budget_node_scope("execute_node"):
                    resumed_state = await nodes.execute_agent(resumed_state)
                with token_budget_node_scope("replan_node"):
                    resumed_state = await nodes.replan_agent(resumed_state)
                with token_budget_node_scope("validate_node"):
                    resumed_state = await nodes.validate_node(resumed_state)
        except TokenBudgetExceeded:
            await self.hitl_service.finish_claim(
                request_id, claim_token, success=False, error="token_budget_exceeded"
            )
            return {
                "success": False,
                "mode": "token_budget_exceeded",
                "message": "确认恢复后触发原运行 Token 预算上限，未继续调用模型",
                "budget_ledger": budget_ledger.snapshot(),
            }
        except Exception as exc:
            await self.hitl_service.finish_claim(
                request_id, claim_token, success=False, error=str(exc)
            )
            return {
                "success": False,
                "mode": "resume_failed",
                "message": "确认恢复执行失败，可在租约到期后重试",
                "error": str(exc),
                "budget_ledger": budget_ledger.snapshot(),
            }

        envelope = resumed_state.get("input_envelope")
        if isinstance(envelope, dict):
            envelope.setdefault("budget", {})["token_ledger"] = budget_ledger.snapshot()
            try:
                resumed_state["input_envelope"] = InputPreprocessor.validate_envelope(envelope)
                resumed_state["task_anchor"] = resumed_state["input_envelope"]["task_anchor"]
            except InputContractError:
                await self.hitl_service.finish_claim(
                    request_id, claim_token, success=False, error="invalid_input_envelope"
                )
                return {
                    "success": False,
                    "mode": "invalid_input_envelope",
                    "message": "确认恢复后的 InputEnvelope 无效，拒绝返回结果",
                    "budget_ledger": budget_ledger.snapshot(),
                }

        finished = await self.hitl_service.finish_claim(request_id, claim_token, success=True)
        if not finished:
            return {
                "success": False,
                "mode": "state_commit_failed",
                "message": "执行已完成，但确认状态提交失败；保留 checkpoint 供恢复",
                "budget_ledger": budget_ledger.snapshot(),
            }
        await self._acleanup_checkpoint(snapshot)
        return {
            "success": True,
            "mode": snapshot_source,
            "message": "已从确认点恢复执行",
            "result": self._state_to_result_payload(resumed_state),
            "budget_ledger": budget_ledger.snapshot(),
        }

    def _load_checkpoint_resume_state(
        self, request: Dict[str, Any], user_id: Optional[int]
    ) -> Optional[Dict[str, Any]]:
        """Load a pending run from the graph checkpoint when the HITL cache is gone."""
        saver = self.checkpointer
        details = request.get("details") or {}
        thread_id = details.get("thread_id")
        run_id = details.get("agent_run_id")
        if saver is None or not thread_id or not run_id or not hasattr(saver, "get_tuple"):
            return None
        try:
            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": run_id,
                    "user_id": user_id,
                }
            }
            if not hasattr(saver, "get_tuple"):
                return None
            checkpoint = saver.get_tuple(config)
        except PermissionError:
            return None
        if not checkpoint:
            return None
        state = dict(checkpoint.checkpoint.get("channel_values") or {})
        pending = state.get("pending_action") or {}
        if pending.get("source") != "tool":
            return None
        state["approved_tool_call"] = {
            "tool_name": pending.get("tool_name"),
            "idempotency_key": pending.get("idempotency_key"),
        }
        state["resume_from_tool_index"] = pending.get("tool_call_index")
        state["confirmation_status"] = "pending"
        state["requires_confirmation"] = True
        return state

    async def _load_checkpoint_resume_state_async(
        self, request: Dict[str, Any], user_id: Optional[int]
    ) -> Optional[Dict[str, Any]]:
        saver = self.checkpointer
        if saver is not None and hasattr(saver, "aget_tuple") and getattr(saver, "ASYNC_ONLY", False):
            details = request.get("details") or {}
            thread_id, run_id = details.get("thread_id"), details.get("agent_run_id")
            if not thread_id or not run_id:
                return None
            try:
                checkpoint = await saver.aget_tuple({"configurable": {"thread_id": thread_id, "checkpoint_ns": run_id, "user_id": user_id}})
            except PermissionError:
                return None
            if not checkpoint:
                return None
            state = dict(checkpoint.checkpoint.get("channel_values") or {})
            pending = state.get("pending_action") or {}
            if pending.get("source") != "tool":
                return None
            state["approved_tool_call"] = {"tool_name": pending.get("tool_name"), "idempotency_key": pending.get("idempotency_key")}
            state["resume_from_tool_index"] = pending.get("tool_call_index")
            state["confirmation_status"] = "pending"
            state["requires_confirmation"] = True
            return state
        return self._load_checkpoint_resume_state(request, user_id)

    def _cleanup_checkpoint(self, state: Dict[str, Any]) -> None:
        saver = self.checkpointer
        if saver is None or not hasattr(saver, "delete_namespace"):
            return
        thread_id = state.get("thread_id")
        run_id = state.get("agent_run_id")
        if thread_id and run_id:
            if hasattr(saver, "delete_namespace"):
                try:
                    saver.delete_namespace(str(thread_id), str(run_id), user_id=state.get("user_id"))
                except TypeError:
                    saver.delete_namespace(str(thread_id), str(run_id))

    async def _acleanup_checkpoint(self, state: Dict[str, Any]) -> None:
        saver = self.checkpointer
        if saver is None or not hasattr(saver, "adelete_namespace"):
            self._cleanup_checkpoint(state)
            return
        thread_id = state.get("thread_id")
        run_id = state.get("agent_run_id")
        if thread_id and run_id:
            await saver.adelete_namespace(str(thread_id), str(run_id), user_id=state.get("user_id"))

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
            "plan": state.get("plan"),
            "route_decision": state.get("route_decision").to_dict() if state.get("route_decision") and hasattr(state.get("route_decision"), "to_dict") else None,
            "route_confidence": state.get("route_confidence"),
            "route_candidates": state.get("route_candidates"),
            "route_decision_trace": state.get("route_decision_trace"),
            "budget_ledger": (
                ((state.get("input_envelope") or {}).get("budget") or {}).get("token_ledger")
            ),
            "context_manifest": state.get("context_manifest"),
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
