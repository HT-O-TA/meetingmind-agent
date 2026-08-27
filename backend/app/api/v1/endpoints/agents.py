"""Agent 查询、流式事件与高风险工具确认端点。"""
import asyncio
import time
from typing import Annotated, Optional, List, Dict, Any
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.services.llm_service import LLMService
from app.services.vector_search_service import VectorSearchService
from app.agents.agent_service import AgentService
from app.agents.session_context import SessionContext, generate_session_id, generate_conversation_id
from app.core.dependencies import get_llm_service, get_vector_search_service
from app.core.logger import app_logger
from app.core.deps import get_current_user
from app.core.security import AccessContext
from app.models.user import User
from app.agents.memory import SessionMemoryStore
import json


class ConfirmationResponse(BaseModel):
    """确认响应请求"""
    request_id: str
    response: str


class ConfirmationResumeRequest(BaseModel):
    """确认并恢复执行请求"""
    request_id: str
    response: str = "approved"


router = APIRouter(tags=["Agent"])

# AgentService/ToolManager/VectorSearchService 都持有请求级依赖，禁止跨请求复用。
# 只共享不持有 db session 的有界短期会话容器。
_memory_store = SessionMemoryStore(max_sessions=1000, max_raw_turns=10)


async def get_agent_service(
    llm_service: LLMService,
    vector_search_service: VectorSearchService,
    enable_human_in_the_loop: bool = False,
) -> AgentService:
    """构造请求级 AgentService；只有短期记忆容器跨请求共享。"""
    return AgentService(
        llm_service=llm_service,
        vector_search_service=vector_search_service,
        enable_human_in_the_loop=enable_human_in_the_loop,
        max_short_term_turns=10,
        memory_store=_memory_store,
    )


class AgentQueryRequest(BaseModel):
    """Agent 查询请求

    ID 体系说明：
    - session_id: 浏览器会话（前端生成，隔离标签页）
    - conversation_id: 对话ID（可选，用于恢复对话）
    - thread_id 由后端自动生成: f"{user_id}:{session_id}:{conversation_id}"
    - meeting_id: 业务域过滤（可选）
    """
    question: str = Field(min_length=1, max_length=20000)
    meeting_id: Optional[int] = None
    document_ids: Optional[List[int]] = None
    session_id: Optional[str] = Field(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    conversation_id: Optional[str] = Field(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    enable_human_in_the_loop: bool = False


class AgentBatchRequest(BaseModel):
    """Agent 批量查询请求"""
    questions: List[Annotated[str, Field(min_length=1, max_length=20000)]] = Field(
        min_length=1, max_length=20
    )
    meeting_id: Optional[int] = None
    document_ids: Optional[List[int]] = None
    session_id: Optional[str] = Field(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    conversation_id: Optional[str] = Field(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


@router.post("/query")
async def agent_query(
    request: AgentQueryRequest,
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
    current_user: User = Depends(get_current_user),
):
    start_time = time.time()
    
    agent_service = await get_agent_service(
        llm_service=llm_service,
        vector_search_service=vector_search_service,
        enable_human_in_the_loop=request.enable_human_in_the_loop
    )

    # 构建 SessionContext（统一四层 ID）
    context = SessionContext(
        user_id=current_user.id,
        session_id=request.session_id or generate_session_id(),
        conversation_id=request.conversation_id or generate_conversation_id(),
        meeting_id=request.meeting_id,
        access_scope=AccessContext.from_user(current_user).cache_scope(),
    )

    app_logger.info(f"[API] Agent查询 - thread_id: {context.thread_id}")

    result = await agent_service.process_query_with_context(
        question=request.question,
        context=context,
        document_ids=request.document_ids,
    )
    
    latency_ms = (time.time() - start_time) * 1000
    response_data = {
        "success": result.success,
        "task_type": result.task_type.value if result.task_type else "qa",
        "workflow_type": result.workflow_type.value if result.workflow_type else None,
        "route_reason": result.route_reason,
        "retrieval_confidence": result.retrieval_confidence,
        "citations": result.citations,
        "validation_errors": result.validation_errors,
        "policy_results": result.policy_results,
        "risk_level": result.risk_level.value if result.risk_level else None,
        "requires_confirmation": result.requires_confirmation,
        "confirmation_status": result.confirmation_status,
        "pending_action": result.pending_action,
        "answer": result.answer,
        "minutes": result.minutes,
        "todos": result.todos,
        "controversies": result.controversies,
        "error": result.error,
        "plan": result.plan,
        "latency_ms": round(latency_ms, 2),
        # 返回会话上下文信息，供前端保存
        "session_id": context.session_id,
        "conversation_id": context.conversation_id,
        "thread_id": context.thread_id,
        "meeting_id": context.meeting_id,
        # 结构化路由决策结果
        "route_decision": result.route_decision.to_dict() if result.route_decision and hasattr(result.route_decision, "to_dict") else None,
        "route_confidence": result.route_decision.confidence if result.route_decision else None,
        "route_candidates": result.route_decision.candidates if result.route_decision else None,
        "route_decision_trace": result.route_decision.decision_trace if result.route_decision else None,
        "structured_outputs": result.structured_outputs,
        "budget_ledger": result.budget_ledger,
    }

    # 合并 metadata 中的额外信息
    if hasattr(result, 'metadata') and result.metadata:
        response_data["metadata"] = result.metadata

    return response_data


@router.post("/query-stream")
async def agent_query_stream(
    request: AgentQueryRequest,
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
    current_user: User = Depends(get_current_user),
):
    """Agent 流式查询；仅返回可公开进度、确认请求和最终结果。"""
    
    async def generate():
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        task: Optional[asyncio.Task] = None

        async def event_callback(event_type, data):
            if event_type == "thought":
                event_type = "progress"
                data = {
                    "phase": data.get("phase"),
                    "action": data.get("action"),
                    "step": data.get("step"),
                }
            await queue.put({"type": event_type, "data": data})

        agent_service = await get_agent_service(
            llm_service=llm_service,
            vector_search_service=vector_search_service,
            enable_human_in_the_loop=request.enable_human_in_the_loop
        )

        # 构建 SessionContext（统一四层 ID）
        context = SessionContext(
            user_id=current_user.id,
            session_id=request.session_id or generate_session_id(),
            conversation_id=request.conversation_id or generate_conversation_id(),
            meeting_id=request.meeting_id,
            access_scope=AccessContext.from_user(current_user).cache_scope(),
        )

        app_logger.info(f"[API] Agent流式查询 - thread_id: {context.thread_id}")

        try:
            task = asyncio.create_task(agent_service.process_query_with_context(
                question=request.question,
                context=context,
                document_ids=request.document_ids,
                event_callback=event_callback,
            ))

            while not task.done() or not queue.empty():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue

                message = json.dumps(event, ensure_ascii=False)
                yield f"data: {message}\n\n"

            result = await task

            # 返回最终结果
            final_result = {
                "success": result.success,
                "task_type": result.task_type.value if result.task_type else "qa",
                "workflow_type": result.workflow_type.value if result.workflow_type else None,
                "route_reason": result.route_reason,
                "retrieval_confidence": result.retrieval_confidence,
                "citations": result.citations,
                "validation_errors": result.validation_errors,
                "policy_results": result.policy_results,
                "risk_level": result.risk_level.value if result.risk_level else None,
                "requires_confirmation": result.requires_confirmation,
                "confirmation_status": result.confirmation_status,
                "pending_action": result.pending_action,
                "answer": result.answer,
                "minutes": result.minutes,
                "todos": result.todos,
                "controversies": result.controversies,
                "error": result.error,
                "plan": result.plan,
                "budget_ledger": result.budget_ledger,
                # 返回会话上下文信息，供前端保存
                "session_id": context.session_id,
                "conversation_id": context.conversation_id,
                "thread_id": context.thread_id,
                "meeting_id": context.meeting_id,
            }
            message = json.dumps({"type": "final", "data": final_result}, ensure_ascii=False)
            yield f"data: {message}\n\n"
            yield "data: [DONE]\n\n"
        except asyncio.CancelledError:
            if task and not task.done():
                task.cancel()
            raise
        except Exception as e:
            app_logger.exception(f"[API] Agent流式查询失败: {e}")
            if task and not task.done():
                task.cancel()
            error = json.dumps(
                {"type": "error", "data": {"message": "Agent stream failed"}},
                ensure_ascii=False,
            )
            yield f"data: {error}\n\n"
            yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/batch")
async def agent_batch_query(
    request: AgentBatchRequest,
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
    current_user: User = Depends(get_current_user),
):
    agent_service = await get_agent_service(
        llm_service=llm_service,
        vector_search_service=vector_search_service,
    )

    context = SessionContext(
        user_id=current_user.id,
        session_id=request.session_id or generate_session_id(),
        conversation_id=request.conversation_id or generate_conversation_id(),
        meeting_id=request.meeting_id,
        access_scope=AccessContext.from_user(current_user).cache_scope(),
    )
    results = await agent_service.process_batch(
        questions=request.questions,
        meeting_id=request.meeting_id,
        document_ids=request.document_ids,
        context=context,
    )

    return {
        "results": [
            {
                "success": r.success,
                "task_type": r.task_type.value if r.task_type else "qa",
                "workflow_type": r.workflow_type.value if r.workflow_type else None,
                "risk_level": r.risk_level.value if r.risk_level else None,
                "confirmation_status": r.confirmation_status,
                "policy_results": r.policy_results,
                "answer": r.answer,
                "error": r.error,
                "budget_ledger": r.budget_ledger,
            }
            for r in results
        ]
    }


# ==================== 人机协作 API 端点 ====================

@router.get("/confirmations/pending")
async def get_pending_confirmations(
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
    current_user: User = Depends(get_current_user),
):
    """获取所有待处理的确认请求"""
    agent_service = await get_agent_service(
        llm_service=llm_service,
        vector_search_service=vector_search_service,
    )
    return {"pending_requests": await agent_service.get_pending_confirmations(current_user.id)}


@router.get("/confirmations/history")
async def get_confirmation_history(
    limit: int = 50,
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
    current_user: User = Depends(get_current_user),
):
    """获取确认请求历史"""
    agent_service = await get_agent_service(
        llm_service=llm_service,
        vector_search_service=vector_search_service,
    )
    return {"history": await agent_service.get_confirmation_history(limit, current_user.id)}


@router.get("/confirmations/{request_id}")
async def get_confirmation_by_id(
    request_id: str,
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
    current_user: User = Depends(get_current_user),
):
    """根据ID获取确认请求详情"""
    agent_service = await get_agent_service(
        llm_service=llm_service,
        vector_search_service=vector_search_service,
    )
    result = await agent_service.get_confirmation_by_id(request_id, current_user.id)
    if result:
        return result
    return {"error": f"确认请求 {request_id} 不存在"}


@router.post("/confirmations/respond")
async def respond_to_confirmation(
    request: ConfirmationResponse,
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
    current_user: User = Depends(get_current_user),
):
    """响应用户确认请求"""
    agent_service = await get_agent_service(
        llm_service=llm_service,
        vector_search_service=vector_search_service,
    )
    
    success = await agent_service.respond_to_confirmation(
        request.request_id, request.response, current_user.id
    )
    
    if success:
        return {"message": f"已响应确认请求 {request.request_id}", "response": request.response}
    return {"error": f"响应失败，请求 {request.request_id} 不存在或已处理"}


@router.post("/confirmations/resume")
async def resume_confirmation(
    request: ConfirmationResumeRequest,
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
    current_user: User = Depends(get_current_user),
):
    """确认后恢复 Agent 执行"""
    agent_service = await get_agent_service(
        llm_service=llm_service,
        vector_search_service=vector_search_service,
        enable_human_in_the_loop=True,
    )
    return await agent_service.resume_confirmation(
        request.request_id, request.response, current_user.id
    )
