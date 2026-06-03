"""Agent协作API端点 - Agent通信与任务分发"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List, Optional
from app.agents.agent_communication import (
    get_message_bus, get_task_dispatcher, TaskPriority, TaskStatus, MessageType
)

router = APIRouter(tags=["Agent协作"])


@router.get("/messages")
async def get_messages(limit: int = 50):
    """获取消息历史"""
    message_bus = get_message_bus()
    return {"messages": message_bus.get_message_history(limit)}


@router.post("/messages/broadcast")
async def broadcast_message(sender_id: str, content: Dict[str, Any]):
    """广播消息"""
    message_bus = get_message_bus()
    await message_bus.broadcast(sender_id, content)
    return {"message": "消息已广播"}


@router.post("/messages/send")
async def send_message(
    sender_id: str,
    receiver_id: str,
    message_type: str,
    content: Dict[str, Any],
    reply_to: Optional[str] = None
):
    """发送消息"""
    message_bus = get_message_bus()
    
    try:
        msg_type = MessageType(message_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的消息类型: {message_type}")
    
    from app.agents.agent_communication import AgentMessage
    
    message = AgentMessage(
        message_id=f"msg_{sender_id}_{int(__import__('time').time())}",
        sender_id=sender_id,
        receiver_id=receiver_id,
        message_type=msg_type,
        content=content,
        reply_to=reply_to
    )
    
    await message_bus.send(message)
    return {"message": "消息已发送"}


@router.post("/messages/clear")
async def clear_messages():
    """清空消息历史"""
    message_bus = get_message_bus()
    message_bus.clear_history()
    return {"message": "消息历史已清空"}


@router.post("/agents/register")
async def register_agent(agent_id: str, capabilities: List[str]):
    """注册Agent"""
    dispatcher = get_task_dispatcher()
    dispatcher.register_agent(agent_id, capabilities)
    return {"message": f"Agent {agent_id} 已注册"}


@router.post("/agents/unregister")
async def unregister_agent(agent_id: str):
    """注销Agent"""
    dispatcher = get_task_dispatcher()
    dispatcher.unregister_agent(agent_id)
    return {"message": f"Agent {agent_id} 已注销"}


@router.get("/agents/list")
async def list_agents():
    """获取已注册的Agent列表"""
    dispatcher = get_task_dispatcher()
    return {"agents": list(dispatcher._agent_capabilities.keys())}


@router.post("/tasks/create")
async def create_task(
    name: str,
    description: str,
    task_type: str,
    priority: str = "normal",
    input_data: Optional[Dict[str, Any]] = None,
    creator_id: Optional[str] = None,
    deadline: Optional[str] = None
):
    """创建任务"""
    dispatcher = get_task_dispatcher()
    
    try:
        task_priority = TaskPriority(priority)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的优先级: {priority}")
    
    # 解析截止日期
    import datetime
    deadline_dt = None
    if deadline:
        try:
            deadline_dt = datetime.datetime.fromisoformat(deadline)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的截止日期格式")
    
    task = dispatcher.create_task(
        name=name,
        description=description,
        task_type=task_type,
        priority=task_priority,
        input_data=input_data,
        creator_id=creator_id,
        deadline=deadline_dt
    )
    
    return {"task_id": task.task_id, "message": "任务已创建"}


@router.post("/tasks/{task_id}/dispatch")
async def dispatch_task(task_id: str):
    """分发任务"""
    dispatcher = get_task_dispatcher()
    success = await dispatcher.dispatch_task(task_id)
    
    if not success:
        raise HTTPException(status_code=400, detail="任务分发失败")
    
    return {"message": f"任务 {task_id} 已分发"}


@router.post("/tasks/{task_id}/update")
async def update_task(
    task_id: str,
    status: str,
    output_data: Optional[Dict[str, Any]] = None,
    error_info: Optional[str] = None
):
    """更新任务状态"""
    dispatcher = get_task_dispatcher()
    
    try:
        task_status = TaskStatus(status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的状态: {status}")
    
    success = await dispatcher.update_task_status(task_id, task_status, output_data, error_info)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    
    return {"message": f"任务 {task_id} 状态已更新"}


@router.get("/tasks")
async def list_tasks(status: Optional[str] = None):
    """获取任务列表"""
    dispatcher = get_task_dispatcher()
    
    if status:
        try:
            task_status = TaskStatus(status)
            tasks = dispatcher.get_tasks_by_status(task_status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的状态: {status}")
    else:
        tasks = dispatcher.get_all_tasks()
    
    return {"tasks": tasks}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """获取任务详情"""
    dispatcher = get_task_dispatcher()
    task = dispatcher.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    
    import datetime
    data = {
        "task_id": task.task_id,
        "name": task.name,
        "description": task.description,
        "task_type": task.task_type,
        "priority": task.priority.value,
        "status": task.status.value,
        "assignee_id": task.assignee_id,
        "creator_id": task.creator_id,
        "input_data": task.input_data,
        "output_data": task.output_data,
        "error_info": task.error_info,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "deadline": task.deadline.isoformat() if task.deadline else None,
        "dependencies": task.dependencies
    }
    
    return data


@router.get("/tasks/pending")
async def get_pending_tasks():
    """获取待处理任务"""
    dispatcher = get_task_dispatcher()
    tasks = dispatcher.get_pending_tasks()
    
    result = []
    for task in tasks:
        result.append({
            "task_id": task.task_id,
            "name": task.name,
            "priority": task.priority.value,
            "created_at": task.created_at.isoformat()
        })
    
    return {"tasks": result}


@router.get("/tasks/agent/{agent_id}")
async def get_agent_tasks(agent_id: str):
    """获取Agent的任务"""
    dispatcher = get_task_dispatcher()
    tasks = dispatcher.get_tasks_by_agent(agent_id)
    
    result = []
    for task in tasks:
        result.append({
            "task_id": task.task_id,
            "name": task.name,
            "status": task.status.value,
            "priority": task.priority.value
        })
    
    return {"tasks": result}
