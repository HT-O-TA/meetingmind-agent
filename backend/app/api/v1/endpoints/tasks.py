"""任务队列 API 端点"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from app.services.task_queue import (
    task_queue_service,
    TaskStatus,
    TaskType,
    TaskInfo,
    create_document_process_task
)
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter(tags=["任务队列"])


class CreateTaskRequest(BaseModel):
    """创建任务请求"""
    document_id: int
    file_path: str
    metadata: Optional[dict] = None


class TaskResponse(BaseModel):
    """任务响应"""
    task_id: str
    task_type: str
    status: str
    progress: int
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str


class TaskListResponse(BaseModel):
    """任务列表响应"""
    total: int
    tasks: List[TaskResponse]


def task_info_to_response(task_info: TaskInfo) -> TaskResponse:
    """转换 TaskInfo 为响应模型"""
    return TaskResponse(
        task_id=task_info.task_id,
        task_type=task_info.task_type,
        status=task_info.status,
        progress=task_info.progress,
        result=task_info.result,
        error=task_info.error,
        created_at=task_info.created_at,
        updated_at=task_info.updated_at
    )


@router.post("/documents", response_model=TaskResponse, summary="创建文档处理任务")
async def create_document_task(
    request: CreateTaskRequest,
    current_user: User = Depends(get_current_user)
):
    """
    创建文档异步处理任务
    
    - **document_id**: 文档ID
    - **file_path**: 文件路径
    - **metadata**: 额外元数据
    """
    try:
        task_info = await create_document_process_task(
            document_id=request.document_id,
            file_path=request.file_path,
            user_id=current_user.id,
            metadata=request.metadata
        )
        return task_info_to_response(task_info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}", response_model=TaskResponse, summary="获取任务状态")
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取指定任务的状态
    
    - **task_id**: 任务ID
    """
    task_info = await task_queue_service.get_task_status(task_id)
    if not task_info:
        raise HTTPException(status_code=404, detail="Task not found")
    return task_info_to_response(task_info)


@router.get("/", response_model=TaskListResponse, summary="获取任务列表")
async def list_tasks(
    task_type: Optional[str] = Query(None, description="任务类型"),
    status: Optional[str] = Query(None, description="任务状态"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量"),
    current_user: User = Depends(get_current_user)
):
    """
    获取任务列表
    
    - **task_type**: 可选，按任务类型过滤
    - **status**: 可选，按任务状态过滤
    - **limit**: 返回数量限制
    """
    try:
        # 转换字符串到枚举
        task_type_enum = TaskType(task_type) if task_type else None
        status_enum = TaskStatus(status) if status else None
        
        tasks = await task_queue_service.list_tasks(
            task_type=task_type_enum,
            status=status_enum,
            limit=limit
        )
        
        return TaskListResponse(
            total=len(tasks),
            tasks=[task_info_to_response(t) for t in tasks]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{task_id}", summary="取消任务")
async def cancel_task(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    取消指定任务
    
    - **task_id**: 任务ID
    """
    success = await task_queue_service.cancel_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task cancelled successfully", "task_id": task_id}


@router.delete("/{task_id}/purge", summary="删除任务")
async def delete_task(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    删除指定任务
    
    - **task_id**: 任务ID
    """
    success = await task_queue_service.delete_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task deleted successfully", "task_id": task_id}


@router.get("/{task_id}/wait", summary="等待任务完成")
async def wait_task_complete(
    task_id: str,
    timeout: int = Query(300, ge=1, le=3600, description="超时时间（秒）"),
    current_user: User = Depends(get_current_user)
):
    """
    等待任务完成（长轮询）
    
    - **task_id**: 任务ID
    - **timeout**: 超时时间（秒）
    """
    import asyncio
    import time
    
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        task_info = await task_queue_service.get_task_status(task_id)
        
        if not task_info:
            raise HTTPException(status_code=404, detail="Task not found")
        
        if task_info.status in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value]:
            return task_info_to_response(task_info)
        
        await asyncio.sleep(1)
    
    # 超时
    return task_info_to_response(await task_queue_service.get_task_status(task_id))
