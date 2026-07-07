"""多Agent系统API端点"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from app.agents.multi_agent import create_multi_agent_system, CoordinatorAgent, AgentRole

router = APIRouter(prefix="/multi-agent", tags=["multi-agent"])

_coordinator: Optional[CoordinatorAgent] = None


def get_coordinator() -> CoordinatorAgent:
    """获取或创建协调器"""
    global _coordinator
    if _coordinator is None:
        _coordinator = create_multi_agent_system()
    return _coordinator


@router.post("/start", response_model=Dict[str, Any])
async def start_multi_agent():
    """启动多Agent系统"""
    try:
        coordinator = get_coordinator()
        await coordinator.start_all()
        return {"success": True, "message": "多Agent系统启动成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop", response_model=Dict[str, Any])
async def stop_multi_agent():
    """停止多Agent系统"""
    try:
        global _coordinator
        if _coordinator:
            await _coordinator.stop_all()
            _coordinator = None
        return {"success": True, "message": "多Agent系统停止成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workflow", response_model=Dict[str, Any])
async def run_workflow(
    question: str,
    meeting_id: Optional[str] = None,
    document_ids: Optional[List[int]] = Query(None),
):
    """运行多Agent工作流"""
    try:
        coordinator = get_coordinator()
        await coordinator.start_all()
        
        result = await coordinator.run_workflow(
            question=question,
            meeting_id=meeting_id,
            document_ids=document_ids or []
        )
        
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents", response_model=Dict[str, Any])
async def list_agents():
    """获取已注册的Agent列表"""
    coordinator = get_coordinator()
    agents = []
    for role, agent in coordinator._agents.items():
        agents.append({
            "role": role.value,
            "name": agent.role.value,
        })
    return {"success": True, "data": agents}


@router.post("/plan", response_model=Dict[str, Any])
async def plan_task(
    question: str,
    meeting_id: Optional[str] = None,
    document_ids: Optional[List[int]] = Query(None),
):
    """仅执行规划步骤"""
    try:
        from app.agents.multi_agent import PlannerAgent, AgentTask
        
        planner = PlannerAgent()
        await planner.start()
        
        task = AgentTask(
            task_id="plan",
            type="plan",
            description=f"规划任务: {question}",
            input_data={"question": question, "meeting_id": meeting_id, "document_ids": document_ids}
        )
        
        result = await planner.process(task)
        await planner.stop()
        
        return {"success": True, "data": result.result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/summarize", response_model=Dict[str, Any])
async def summarize_meeting(
    question: str,
    context: Optional[str] = None,
    context_prompt: Optional[str] = None,
):
    """仅执行总结步骤"""
    try:
        from app.agents.multi_agent import SummarizerAgent, AgentTask
        
        summarizer = SummarizerAgent()
        await summarizer.start()
        
        task = AgentTask(
            task_id="summarize",
            type="summarize",
            description=f"总结任务: {question}",
            input_data={"question": question, "context": context or "", "context_prompt": context_prompt or ""}
        )
        
        result = await summarizer.process(task)
        await summarizer.stop()
        
        return {"success": True, "data": result.result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract-todos", response_model=Dict[str, Any])
async def extract_todos(
    content: str,
):
    """仅执行待办提取步骤"""
    try:
        from app.agents.multi_agent import TodoExtractorAgent, AgentTask
        
        extractor = TodoExtractorAgent()
        await extractor.start()
        
        task = AgentTask(
            task_id="extract_todos",
            type="extract_todos",
            description="提取待办事项",
            input_data={"question": content, "summary": content}
        )
        
        result = await extractor.process(task)
        await extractor.stop()
        
        return {"success": True, "data": result.result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/review", response_model=Dict[str, Any])
async def review_result(
    summary: str,
    todos: Optional[List[Dict[str, Any]]] = None,
):
    """仅执行审查步骤"""
    try:
        from app.agents.multi_agent import ReviewerAgent, AgentTask
        
        reviewer = ReviewerAgent()
        await reviewer.start()
        
        task = AgentTask(
            task_id="review",
            type="review",
            description="审查结果质量",
            input_data={"summary": summary, "todos": todos or []}
        )
        
        result = await reviewer.process(task)
        await reviewer.stop()
        
        return {"success": True, "data": result.result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retrieve", response_model=Dict[str, Any])
async def retrieve_documents(
    question: str,
    meeting_id: Optional[str] = None,
    document_ids: Optional[List[int]] = Query(None),
):
    """仅执行检索步骤"""
    try:
        from app.agents.multi_agent import RetrieverAgent, AgentTask
        
        retriever = RetrieverAgent()
        await retriever.start()
        
        task = AgentTask(
            task_id="retrieve",
            type="retrieve",
            description=f"检索任务: {question}",
            input_data={"question": question, "meeting_id": meeting_id, "document_ids": document_ids}
        )
        
        result = await retriever.process(task)
        await retriever.stop()
        
        return {"success": True, "data": result.result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))