"""Agent API 端点 - 支持 Tool Calling + 监控 + Prompt 管理 + 人机协作
"""
import asyncio
import time
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Body, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.services.llm_service import LLMService
from app.services.vector_search_service import VectorSearchService
from app.agents.agent_service import AgentService
from app.agents.session_context import SessionContext, generate_session_id, generate_conversation_id
from app.services.multimodal_gateway import get_multimodal_gateway, MultimodalStatus
from app.core.dependencies import get_llm_service, get_vector_search_service
from app.core.logger import app_logger
from app.services.performance_metrics import record_performance
from app.core.deps import get_current_user
from app.core.security import AccessContext
from app.models.user import User
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

# 进程级单例缓存，key = (enable_memory, enable_tool_calling)
# VectorSearchService 持有 db session，不能跨请求复用，每次请求注入新实例。
# AgentService 本身（含 session_memories）跨请求持久化。
_agent_service_cache: Dict[tuple, AgentService] = {}
_cache_lock = asyncio.Lock()


async def get_agent_service(
    llm_service: LLMService,
    vector_search_service: VectorSearchService,
    enable_memory: bool = True,
    enable_tool_calling: bool = False,
    enable_human_in_the_loop: bool = False,
) -> AgentService:
    """获取或复用 AgentService 实例，保证 session_memories 跨请求持久化"""
    cache_key = (enable_memory, enable_tool_calling, enable_human_in_the_loop)
    async with _cache_lock:
        if cache_key not in _agent_service_cache:
            _agent_service_cache[cache_key] = AgentService(
                llm_service=llm_service,
                vector_search_service=vector_search_service,
                enable_checkpointer=False,
                enable_memory=enable_memory,
                enable_tool_calling=enable_tool_calling,
                enable_human_in_the_loop=enable_human_in_the_loop,
                max_short_term_turns=10,
                max_long_term_items=1000,
            )
        else:
            # 更新底层服务（db session 每次请求不同）
            svc = _agent_service_cache[cache_key]
            svc.llm_service = llm_service
            svc.vector_search_service = vector_search_service
    return _agent_service_cache[cache_key]


class AgentQueryRequest(BaseModel):
    """Agent 查询请求

    ID 体系说明：
    - session_id: 浏览器会话（前端生成，隔离标签页）
    - conversation_id: 对话ID（可选，用于恢复对话）
    - thread_id 由后端自动生成: f"{session_id}:{conversation_id}"
    - meeting_id: 业务域过滤（可选）
    """
    question: str
    meeting_id: Optional[int] = None
    document_ids: Optional[List[int]] = None
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    user_id: Optional[int] = None
    enable_memory: bool = True
    enable_tool_calling: bool = True
    enable_human_in_the_loop: bool = False


class AgentBatchRequest(BaseModel):
    """Agent 批量查询请求"""
    questions: List[str]
    meeting_id: Optional[int] = None
    document_ids: Optional[List[int]] = None
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    user_id: Optional[int] = None
    enable_tool_calling: bool = False
    enable_memory: bool = True


class AgentMemoryRequest(BaseModel):
    """Agent 记忆操作请求"""
    session_id: str
    action: str
    checkpoint: Optional[Dict[str, Any]] = None


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
        enable_memory=request.enable_memory,
        enable_tool_calling=request.enable_tool_calling,
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

    app_logger.info(f"[API] Agent查询 - Tool Calling: {request.enable_tool_calling}, thread_id: {context.thread_id}")

    result = await agent_service.process_query_with_context(
        question=request.question,
        context=context,
        document_ids=request.document_ids,
    )
    
    latency_ms = (time.time() - start_time) * 1000
    await record_performance(latency_ms=latency_ms)

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
        "thoughts": result.thoughts,
        "reflection": result.reflection,
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
    }

    # 合并 metadata 中的额外信息
    if hasattr(result, 'metadata') and result.metadata:
        response_data["metadata"] = result.metadata

    return response_data


@router.post("/query-multimodal")
async def agent_query_multimodal(
    question: str = Form(...),
    file: Optional[UploadFile] = File(None),
    meeting_id: Optional[int] = Form(None),
    document_ids: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
    conversation_id: Optional[str] = Form(None),
    user_id: Optional[int] = Form(None),
    enable_memory: bool = Form(True),
    enable_tool_calling: bool = Form(True),
    enable_human_in_the_loop: bool = Form(False),
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
    current_user: User = Depends(get_current_user),
):
    """多模态查询 - 支持上传图片/音频/文档"""
    start_time = time.time()

    # 处理 document_ids
    doc_ids = None
    if document_ids:
        try:
            doc_ids = json.loads(document_ids)
        except json.JSONDecodeError:
            doc_ids = None

    agent_service = await get_agent_service(
        llm_service=llm_service,
        vector_search_service=vector_search_service,
        enable_memory=enable_memory,
        enable_tool_calling=enable_tool_calling,
        enable_human_in_the_loop=enable_human_in_the_loop,
    )

    # 处理多模态文件
    gateway = get_multimodal_gateway()
    multimodal_text = ""

    if file:
        file_content = await file.read()
        file_result = await gateway.process_upload(
            filename=file.filename or "unknown",
            content=file_content,
            content_type=file.content_type,
        )

        if file_result.status == MultimodalStatus.SUCCESS:
            multimodal_text = file_result.text_description
            app_logger.info(f"[多模态] 文件处理成功: {file.filename}, 耗时: {file_result.processing_time_ms:.0f}ms")
        elif file_result.status == MultimodalStatus.SKIPPED:
            app_logger.warning(f"[多模态] {file_result.error_message}")
        else:
            app_logger.warning(f"[多模态] 文件处理失败: {file_result.error_message}")
            # 失败时继续，但不包含文件内容

    # 合并问题描述
    full_question = question
    if multimodal_text:
        full_question = f"{question}\n\n[附件内容]:\n{multimodal_text}"

    # 构建 SessionContext
    context = SessionContext(
        user_id=current_user.id,
        session_id=session_id or generate_session_id(),
        conversation_id=conversation_id or generate_conversation_id(),
        meeting_id=meeting_id,
        access_scope=AccessContext.from_user(current_user).cache_scope(),
    )

    app_logger.info(f"[API] 多模态查询 - thread_id: {context.thread_id}, has_file: {bool(file)}")

    result = await agent_service.process_query_with_context(
        question=full_question,
        context=context,
        document_ids=doc_ids,
    )

    latency_ms = (time.time() - start_time) * 1000
    await record_performance(latency_ms=latency_ms)

    return {
        "success": result.success,
        "answer": result.answer,
        "task_type": result.task_type.value if result.task_type else "qa",
        "citations": result.citations,
        "error": result.error,
        "latency_ms": round(latency_ms, 2),
        "session_id": context.session_id,
        "conversation_id": context.conversation_id,
        "thread_id": context.thread_id,
        "meeting_id": context.meeting_id,
        # 多模态处理信息
        "multimodal": {
            "file_processed": bool(file and multimodal_text),
            "file_description": multimodal_text[:200] if multimodal_text else "",
        },
    }


@router.post("/query-stream")
async def agent_query_stream(
    request: AgentQueryRequest,
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
    current_user: User = Depends(get_current_user),
):
    """Agent流式查询 - 实时返回思维链和中间结果"""
    
    async def generate():
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        task: Optional[asyncio.Task] = None

        async def event_callback(event_type, data):
            await queue.put({"type": event_type, "data": data})

        agent_service = await get_agent_service(
            llm_service=llm_service,
            vector_search_service=vector_search_service,
            enable_memory=request.enable_memory,
            enable_tool_calling=request.enable_tool_calling,
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

        app_logger.info(f"[API] Agent流式查询 - Tool Calling: {request.enable_tool_calling}, thread_id: {context.thread_id}")

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
                "thoughts": result.thoughts,
                "reflection": result.reflection,
                "plan": result.plan,
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
            error = json.dumps({"type": "error", "data": {"message": str(e)}}, ensure_ascii=False)
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
        enable_memory=request.enable_memory,
        enable_tool_calling=request.enable_tool_calling
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
            }
            for r in results
        ]
    }


@router.post("/memory")
async def agent_memory_operation(
    request: AgentMemoryRequest,
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
):
    agent_service = await get_agent_service(
        llm_service=llm_service,
        vector_search_service=vector_search_service,
    )

    if request.action == "clear":
        agent_service.clear_session_memory(request.session_id)
        return {"message": f"会话 {request.session_id} 记忆已清空"}
    elif request.action == "stats":
        stats = agent_service.get_memory_stats(request.session_id)
        return {"stats": stats}
    elif request.action == "save_checkpoint":
        checkpoint = agent_service.save_checkpoint(request.session_id)
        return {"checkpoint": checkpoint}
    elif request.action == "load_checkpoint" and request.checkpoint:
        agent_service.load_checkpoint(request.session_id, request.checkpoint)
        return {"message": "检查点已加载"}
    else:
        return {"error": f"未知操作: {request.action}"}


@router.get("/memory/stats")
async def get_memory_stats(
    session_id: Optional[str] = None,
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
):
    agent_service = await get_agent_service(
        llm_service=llm_service,
        vector_search_service=vector_search_service,
    )
    return agent_service.get_memory_stats(session_id)


@router.get("/architecture")
async def get_agent_architecture(
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
):
    agent_service = await get_agent_service(
        llm_service=llm_service,
        vector_search_service=vector_search_service,
    )
    return agent_service.get_agent_architecture()


@router.get("/prompts")
async def get_prompt_templates(
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
):
    agent_service = await get_agent_service(
        llm_service=llm_service,
        vector_search_service=vector_search_service,
    )
    return {"templates": agent_service.get_prompt_templates()}


@router.get("/tools")
async def get_tools_info(
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
):
    agent_service = await get_agent_service(
        llm_service=llm_service,
        vector_search_service=vector_search_service,
        enable_tool_calling=True,
    )
    return agent_service.get_tools_info() or {"tools": []}


@router.get("/errors/recent")
async def get_recent_errors(
    limit: int = 20,
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
):
    agent_service = await get_agent_service(
        llm_service=llm_service,
        vector_search_service=vector_search_service,
    )
    return {"errors": agent_service.get_recent_errors(limit)}


@router.get("/monitor/status")
async def get_monitor_status(
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
):
    agent_service = await get_agent_service(
        llm_service=llm_service,
        vector_search_service=vector_search_service,
    )
    return agent_service.get_monitor_status()


# ==================== 人机协作 API 端点 ====================

@router.get("/confirmations/pending")
async def get_pending_confirmations(
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
):
    """获取所有待处理的确认请求"""
    agent_service = await get_agent_service(
        llm_service=llm_service,
        vector_search_service=vector_search_service,
    )
    return {"pending_requests": await agent_service.get_pending_confirmations()}


@router.get("/confirmations/history")
async def get_confirmation_history(
    limit: int = 50,
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
):
    """获取确认请求历史"""
    agent_service = await get_agent_service(
        llm_service=llm_service,
        vector_search_service=vector_search_service,
    )
    return {"history": await agent_service.get_confirmation_history(limit)}


@router.get("/confirmations/{request_id}")
async def get_confirmation_by_id(
    request_id: str,
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
):
    """根据ID获取确认请求详情"""
    agent_service = await get_agent_service(
        llm_service=llm_service,
        vector_search_service=vector_search_service,
    )
    result = await agent_service.get_confirmation_by_id(request_id)
    if result:
        return result
    return {"error": f"确认请求 {request_id} 不存在"}


@router.post("/confirmations/respond")
async def respond_to_confirmation(
    request: ConfirmationResponse,
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
):
    """响应用户确认请求"""
    agent_service = await get_agent_service(
        llm_service=llm_service,
        vector_search_service=vector_search_service,
    )
    
    success = await agent_service.respond_to_confirmation(request.request_id, request.response)
    
    if success:
        return {"message": f"已响应确认请求 {request.request_id}", "response": request.response}
    return {"error": f"响应失败，请求 {request.request_id} 不存在或已处理"}


@router.post("/confirmations/resume")
async def resume_confirmation(
    request: ConfirmationResumeRequest,
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
):
    """确认后恢复 Agent 执行"""
    agent_service = await get_agent_service(
        llm_service=llm_service,
        vector_search_service=vector_search_service,
        enable_tool_calling=True,
        enable_human_in_the_loop=True,
    )
    return await agent_service.resume_confirmation(request.request_id, request.response)
