"""Agent API 端点 - 支持 Tool Calling + 监控 + Prompt 管理 + 人机协作
"""
import asyncio
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.services.llm_service import LLMService
from app.services.vector_search_service import VectorSearchService
from app.agents.agent_service import AgentService
from app.core.dependencies import get_llm_service, get_vector_search_service
from app.core.logger import app_logger
import json


class ConfirmationResponse(BaseModel):
    """确认响应请求"""
    request_id: str
    response: str


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
    """Agent 查询请求"""
    question: str
    meeting_id: Optional[int] = None
    document_ids: Optional[List[int]] = None
    session_id: Optional[str] = None
    enable_memory: bool = True
    enable_tool_calling: bool = False
    enable_human_in_the_loop: bool = False


class AgentBatchRequest(BaseModel):
    """Agent 批量查询请求"""
    questions: List[str]
    meeting_id: Optional[int] = None
    document_ids: Optional[List[int]] = None
    session_id: Optional[str] = None
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
):
    agent_service = await get_agent_service(
        llm_service=llm_service,
        vector_search_service=vector_search_service,
        enable_memory=request.enable_memory,
        enable_tool_calling=request.enable_tool_calling,
        enable_human_in_the_loop=request.enable_human_in_the_loop
    )

    config = {}
    if request.session_id:
        config["thread_id"] = request.session_id

    app_logger.info(f"[API] Agent查询 - Tool Calling: {request.enable_tool_calling}")

    result = await agent_service.process_query(
        question=request.question,
        meeting_id=request.meeting_id,
        document_ids=request.document_ids,
        config=config,
    )

    return {
        "success": result.success,
        "task_type": result.task_type.value if result.task_type else "qa",
        "answer": result.answer,
        "minutes": result.minutes,
        "todos": result.todos,
        "controversies": result.controversies,
        "error": result.error,
        "thoughts": result.thoughts,
        "reflection": result.reflection,
        "plan": result.plan,
    }


@router.post("/query-stream")
async def agent_query_stream(
    request: AgentQueryRequest,
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
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

        config = {}
        if request.session_id:
            config["thread_id"] = request.session_id

        app_logger.info(f"[API] Agent流式查询 - Tool Calling: {request.enable_tool_calling}")

        try:
            task = asyncio.create_task(agent_service.process_query(
                question=request.question,
                meeting_id=request.meeting_id,
                document_ids=request.document_ids,
                config=config,
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
                "answer": result.answer,
                "minutes": result.minutes,
                "todos": result.todos,
                "controversies": result.controversies,
                "error": result.error,
                "thoughts": result.thoughts,
                "reflection": result.reflection,
                "plan": result.plan,
            }
            message = json.dumps({"type": "final", "data": final_result}, ensure_ascii=False)
            yield f"data: {message}\n\n"
            yield "data: [DONE]\n\n"
        except asyncio.CancelledError:
            if task and not task.done():
                task.cancel()
            raise
    
    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/batch")
async def agent_batch_query(
    request: AgentBatchRequest,
    llm_service: LLMService = Depends(get_llm_service),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
):
    agent_service = await get_agent_service(
        llm_service=llm_service,
        vector_search_service=vector_search_service,
        enable_memory=request.enable_memory,
        enable_tool_calling=request.enable_tool_calling
    )

    results = await agent_service.process_batch(
        questions=request.questions,
        meeting_id=request.meeting_id,
        document_ids=request.document_ids,
    )

    return {
        "results": [
            {
                "success": r.success,
                "task_type": r.task_type.value if r.task_type else "qa",
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
    return {"pending_requests": agent_service.get_pending_confirmations()}


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
    return {"history": agent_service.get_confirmation_history(limit)}


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
    result = agent_service.get_confirmation_by_id(request_id)
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
    
    success = agent_service.respond_to_confirmation(request.request_id, request.response)
    
    if success:
        return {"message": f"已响应确认请求 {request.request_id}", "response": request.response}
    return {"error": f"响应失败，请求 {request.request_id} 不存在或已处理"}
