"""工作流API端点 - 支持会议→审批→任务→提醒→跟踪全流程"""
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, Depends, Body, Query
from pydantic import BaseModel
from app.workflows.enterprise_workflow import (
    get_workflow_engine, WorkflowStatus, TaskStatus, TaskPriority, WorkflowStepType
)
from app.core.logger import app_logger

router = APIRouter(prefix="/workflows", tags=["Workflows"])


class CreateWorkflowRequest(BaseModel):
    """创建工作流请求"""
    name: str
    type: str = "meeting_to_task"
    context: Dict[str, Any] = {}
    creator: Optional[str] = None


class UpdateTaskStatusRequest(BaseModel):
    """更新任务状态请求"""
    task_id: str
    status: str


class ApprovalRequest(BaseModel):
    """审批请求"""
    workflow_id: str
    step_id: str


@router.post("/")
async def create_workflow(request: CreateWorkflowRequest):
    """创建工作流"""
    engine = get_workflow_engine()
    workflow = engine.create_workflow(
        name=request.name,
        type=request.type,
        context=request.context,
        creator=request.creator
    )
    app_logger.info(f"[API] 创建工作流: {workflow.workflow_id}")
    return {"success": True, "workflow": workflow.to_dict()}


@router.get("/")
async def get_workflows(status: Optional[str] = Query(None)):
    """获取工作流列表"""
    engine = get_workflow_engine()
    
    if status:
        try:
            workflow_status = WorkflowStatus(status)
            workflows = engine.get_workflows_by_status(workflow_status)
        except ValueError:
            return {"success": False, "error": f"无效状态: {status}"}
    else:
        workflows = engine.get_all_workflows()
    
    return {
        "success": True,
        "workflows": [w.to_dict() for w in workflows]
    }


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str):
    """获取工作流详情"""
    engine = get_workflow_engine()
    workflow = engine.get_workflow(workflow_id)
    
    if not workflow:
        return {"success": False, "error": f"工作流不存在: {workflow_id}"}
    
    return {"success": True, "workflow": workflow.to_dict()}


@router.post("/{workflow_id}/start")
async def start_workflow(workflow_id: str):
    """启动工作流"""
    engine = get_workflow_engine()
    result = await engine.start_workflow(workflow_id)
    
    if result:
        workflow = engine.get_workflow(workflow_id)
        return {"success": True, "workflow": workflow.to_dict()}
    else:
        return {"success": False, "error": f"启动工作流失败: {workflow_id}"}


@router.post("/{workflow_id}/approve")
async def approve_workflow(workflow_id: str, request: ApprovalRequest = Body(...)):
    """审批工作流"""
    engine = get_workflow_engine()
    result = await engine.approve_workflow(workflow_id, request.step_id)
    
    if result:
        workflow = engine.get_workflow(workflow_id)
        return {"success": True, "workflow": workflow.to_dict()}
    else:
        return {"success": False, "error": f"审批失败: {workflow_id}"}


@router.post("/{workflow_id}/reject")
async def reject_workflow(workflow_id: str, request: ApprovalRequest = Body(...)):
    """拒绝工作流"""
    engine = get_workflow_engine()
    result = await engine.reject_workflow(workflow_id, request.step_id)
    
    if result:
        workflow = engine.get_workflow(workflow_id)
        return {"success": True, "workflow": workflow.to_dict()}
    else:
        return {"success": False, "error": f"拒绝失败: {workflow_id}"}


@router.get("/tasks")
async def get_tasks(status: Optional[str] = Query(None)):
    """获取任务列表"""
    engine = get_workflow_engine()
    
    if status:
        try:
            task_status = TaskStatus(status)
            tasks = engine.get_tasks_by_status(task_status)
        except ValueError:
            return {"success": False, "error": f"无效状态: {status}"}
    else:
        tasks = engine.get_all_tasks()
    
    return {
        "success": True,
        "tasks": [t.to_dict() for t in tasks]
    }


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """获取任务详情"""
    engine = get_workflow_engine()
    task = engine.get_task(task_id)
    
    if not task:
        return {"success": False, "error": f"任务不存在: {task_id}"}
    
    return {"success": True, "task": task.to_dict()}


@router.post("/tasks/{task_id}/status")
async def update_task_status(task_id: str, status: str = Body(..., embed=True)):
    """更新任务状态"""
    engine = get_workflow_engine()
    
    try:
        task_status = TaskStatus(status)
    except ValueError:
        return {"success": False, "error": f"无效状态: {status}"}
    
    result = engine.update_task_status(task_id, task_status)
    
    if result:
        task = engine.get_task(task_id)
        return {"success": True, "task": task.to_dict()}
    else:
        return {"success": False, "error": f"更新任务状态失败: {task_id}"}


@router.get("/approvals")
async def get_pending_approvals():
    """获取待审批请求"""
    engine = get_workflow_engine()
    approvals = engine.get_pending_approvals()
    
    return {
        "success": True,
        "approvals": [a.to_dict() for a in approvals]
    }


@router.get("/approvals/{approval_id}")
async def get_approval(approval_id: str):
    """获取审批详情"""
    engine = get_workflow_engine()
    approval = engine.get_approval(approval_id)
    
    if not approval:
        return {"success": False, "error": f"审批请求不存在: {approval_id}"}
    
    return {"success": True, "approval": approval.to_dict()}


@router.post("/process-follow-up")
async def process_follow_up():
    """处理跟进提醒"""
    engine = get_workflow_engine()
    await engine.process_follow_up()
    return {"success": True, "message": "跟进提醒处理完成"}


@router.get("/health")
async def workflow_health():
    """工作流服务健康检查"""
    return {"status": "ok", "service": "workflow"}


class ApprovalActionRequest(BaseModel):
    """审批操作请求"""
    user: str
    comment: Optional[str] = ""


class DelegateRequest(BaseModel):
    """转派请求"""
    new_approver: str
    user: str


class SyncTaskRequest(BaseModel):
    """同步任务请求"""
    system: str = "feishu"


@router.get("/templates")
async def get_workflow_templates():
    """获取工作流模板列表"""
    engine = get_workflow_engine()
    templates = engine.get_workflow_templates()
    
    return {"success": True, "templates": templates}


@router.get("/templates/{template_id}")
async def get_workflow_template(template_id: str):
    """获取工作流模板详情"""
    engine = get_workflow_engine()
    template = engine.get_workflow_template(template_id)
    
    if not template:
        return {"success": False, "error": f"模板不存在: {template_id}"}
    
    return {"success": True, "template": template}


@router.post("/approvals/{approval_id}/approve")
async def approve_approval(approval_id: str, request: ApprovalActionRequest = Body(...)):
    """审批通过"""
    engine = get_workflow_engine()
    result = await engine.approve_approval(approval_id, request.user, request.comment)
    
    if result:
        approval = engine.get_approval(approval_id)
        return {"success": True, "approval": approval.to_dict()}
    else:
        return {"success": False, "error": f"审批失败: {approval_id}"}


@router.post("/approvals/{approval_id}/reject")
async def reject_approval(approval_id: str, request: ApprovalActionRequest = Body(...)):
    """拒绝审批"""
    engine = get_workflow_engine()
    result = await engine.reject_approval(approval_id, request.user, request.comment)
    
    if result:
        approval = engine.get_approval(approval_id)
        return {"success": True, "approval": approval.to_dict()}
    else:
        return {"success": False, "error": f"拒绝失败: {approval_id}"}


@router.post("/approvals/{approval_id}/delegate")
async def delegate_approval(approval_id: str, request: DelegateRequest = Body(...)):
    """转派审批"""
    engine = get_workflow_engine()
    result = await engine.delegate_approval(approval_id, request.new_approver, request.user)
    
    if result:
        approval = engine.get_approval(approval_id)
        return {"success": True, "approval": approval.to_dict()}
    else:
        return {"success": False, "error": f"转派失败: {approval_id}"}


@router.post("/approvals/create")
async def create_approval_flow(
    title: str = Body(...),
    description: str = Body(...),
    approvers: List[str] = Body(...),
    details: Optional[Dict[str, Any]] = Body(None),
    creator: Optional[str] = Body(None)
):
    """创建审批流程"""
    engine = get_workflow_engine()
    approval = engine.create_approval_flow(
        title=title,
        description=description,
        approvers=approvers,
        details=details,
        creator=creator
    )
    
    return {"success": True, "approval": approval.to_dict()}


@router.post("/tasks/{task_id}/sync")
async def sync_task_to_external(task_id: str, request: SyncTaskRequest = Body(...)):
    """同步任务到外部系统"""
    engine = get_workflow_engine()
    external_id = await engine.sync_task_to_external(task_id, request.system)
    
    if external_id:
        task = engine.get_task(task_id)
        return {"success": True, "task": task.to_dict()}
    else:
        return {"success": False, "error": f"同步失败: {task_id}"}


@router.get("/tasks/assignee/{assignee}")
async def get_tasks_by_assignee(assignee: str):
    """按负责人获取任务"""
    engine = get_workflow_engine()
    tasks = engine.get_tasks_by_assignee(assignee)
    
    return {
        "success": True,
        "tasks": [t.to_dict() for t in tasks]
    }


@router.get("/tasks/overdue")
async def get_overdue_tasks():
    """获取逾期任务"""
    engine = get_workflow_engine()
    tasks = engine.get_overdue_tasks()
    
    return {
        "success": True,
        "tasks": [t.to_dict() for t in tasks]
    }


@router.get("/statistics/tasks")
async def get_task_statistics():
    """获取任务统计"""
    engine = get_workflow_engine()
    stats = engine.get_task_statistics()
    
    return {"success": True, "statistics": stats}


@router.get("/statistics/workflows")
async def get_workflow_statistics():
    """获取工作流统计"""
    engine = get_workflow_engine()
    stats = engine.get_workflow_statistics()
    
    return {"success": True, "statistics": stats}