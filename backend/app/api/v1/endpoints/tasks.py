"""任务队列 API 端点"""
from pathlib import Path
import re
import uuid
from typing import Optional, List
import aiofiles
from fastapi import APIRouter, HTTPException, Depends, Query, Header, UploadFile, File, Form
from pydantic import BaseModel
from app.services.task_queue import (
    task_queue_service,
    TaskStatus,
    TaskType,
    TaskInfo,
    create_document_process_task,
    create_audio_transcribe_task,
)
from app.services.asr_service import InvalidAudioError, inspect_wav
from app.core.config import settings
from app.core.deps import get_current_user
from app.models.user import User
from app.models.document import Document
from app.models.meeting import Meeting
from app.db.database import get_db
from app.core.logger import app_logger
from app.core.security import require_write_user
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["任务队列"])


class CreateTaskRequest(BaseModel):
    """创建任务请求"""
    document_id: int
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
    attempt_count: int = 0
    max_attempts: int = 1
    error_category: Optional[str] = None
    published_at: Optional[str] = None


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
        updated_at=task_info.updated_at,
        attempt_count=task_info.attempt_count,
        max_attempts=task_info.max_attempts,
        error_category=task_info.error_category,
        published_at=task_info.published_at,
    )


@router.post("/documents", response_model=TaskResponse, status_code=202, summary="创建文档处理任务")
async def create_document_task(
    request: CreateTaskRequest,
    current_user: User = Depends(get_current_user),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
):
    """
    创建文档异步处理任务
    
    - **document_id**: 文档ID
    - **metadata**: 额外元数据
    """
    require_write_user(current_user)
    try:
        document = await db.get(Document, request.document_id)
        if not document or document.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Document not found")
        role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
        if document.uploader_id != current_user.id and role != "admin":
            raise HTTPException(status_code=403, detail="No permission to process this document")
        task_info = await create_document_process_task(
            document_id=request.document_id,
            file_path=document.file_path,
            user_id=current_user.id,
            metadata=request.metadata,
            idempotency_key=idempotency_key,
        )
        return task_info_to_response(task_info)
    except HTTPException:
        raise
    except Exception as e:
        app_logger.exception(f"Unable to queue document task: {e}")
        raise HTTPException(status_code=500, detail="Unable to queue document task") from e


def _is_admin(user: User) -> bool:
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return role == "admin"


def _safe_original_name(value: Optional[str]) -> str:
    name = Path(value or "audio.wav").name
    name = re.sub(r"[^\w.()\-\u4e00-\u9fff ]", "_", name, flags=re.UNICODE)
    return (name[:180] or "audio.wav")


@router.post("/audio", response_model=TaskResponse, status_code=202, summary="创建 WAV 转写任务")
async def create_audio_task(
    meeting_id: int = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
):
    """上传受管 WAV，异步产出带说话人/时间戳的会议证据。"""
    require_write_user(current_user)
    if not settings.ENABLE_ASR:
        raise HTTPException(status_code=503, detail="Local ASR is disabled (ENABLE_ASR=false)")
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if meeting.organizer_id != current_user.id and not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="No permission to transcribe this meeting")

    original_name = _safe_original_name(file.filename)
    allowed = {item.strip().lower() for item in settings.ASR_ALLOWED_EXTENSIONS.split(",") if item.strip()}
    extension = Path(original_name).suffix.lower().lstrip(".")
    if extension not in allowed or extension != "wav":
        raise HTTPException(status_code=415, detail="The formal ASR endpoint currently accepts WAV only")
    if file.content_type and file.content_type.lower() not in {
        "audio/wav", "audio/x-wav", "audio/wave", "application/octet-stream"
    }:
        raise HTTPException(status_code=415, detail="Unsupported audio content type")

    upload_root = (Path(settings.UPLOAD_DIR) / "audio" / str(current_user.id)).resolve()
    upload_root.mkdir(parents=True, exist_ok=True)
    destination = upload_root / f"{uuid.uuid4()}.wav"
    size = 0
    try:
        async with aiofiles.open(destination, "wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.ASR_MAX_AUDIO_SIZE_BYTES:
                    raise HTTPException(status_code=413, detail="Audio file is too large")
                await output.write(chunk)
        wav_info = inspect_wav(destination)
        if wav_info["duration_seconds"] > settings.ASR_MAX_DURATION_SECONDS:
            raise HTTPException(status_code=413, detail="Audio duration exceeds configured limit")
        task = await create_audio_transcribe_task(
            meeting_id=meeting_id,
            file_path=str(destination),
            original_filename=original_name,
            user_id=current_user.id,
            metadata={
                "content_type": file.content_type or "audio/wav",
                "size_bytes": size,
                "duration_seconds": round(wav_info["duration_seconds"], 3),
                "sample_rate_hz": wav_info["sample_rate_hz"],
                "channels": wav_info["channels"],
            },
            idempotency_key=idempotency_key,
        )
        # 幂等命中旧任务时，本次新上传未被引用，立即清理。
        if not task.payload or task.payload.get("file_path") != str(destination):
            destination.unlink(missing_ok=True)
        return task_info_to_response(task)
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    except InvalidAudioError as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        destination.unlink(missing_ok=True)
        app_logger.exception(f"Unable to queue audio task: {exc}")
        raise HTTPException(status_code=500, detail="Unable to queue audio task") from exc
    finally:
        await file.close()


@router.get("/{task_id}", response_model=TaskResponse, summary="获取任务状态")
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取指定任务的状态
    
    - **task_id**: 任务ID
    """
    task_info = await task_queue_service.get_task_status(task_id, current_user.id)
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
            limit=limit,
            user_id=current_user.id,
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
    require_write_user(current_user)
    success = await task_queue_service.cancel_task(task_id, current_user.id)
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
    require_write_user(current_user)
    success = await task_queue_service.delete_task(task_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task deleted successfully", "task_id": task_id}


@router.post("/{task_id}/retry-publish", response_model=TaskResponse, summary="重发发布失败任务")
async def retry_publish_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    require_write_user(current_user)
    try:
        task = await task_queue_service.republish_task(task_id, current_user.id)
        return task_info_to_response(task)
    except LookupError:
        raise HTTPException(status_code=404, detail="Task not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


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
        task_info = await task_queue_service.get_task_status(task_id, current_user.id)
        
        if not task_info:
            raise HTTPException(status_code=404, detail="Task not found")
        
        if task_info.status in [
            TaskStatus.COMPLETED.value,
            TaskStatus.CANCELLED.value,
            TaskStatus.DEAD_LETTER.value,
            TaskStatus.PUBLISH_FAILED.value,
        ]:
            return task_info_to_response(task_info)
        
        await asyncio.sleep(1)
    
    # 超时
    final_task = await task_queue_service.get_task_status(task_id, current_user.id)
    if not final_task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task_info_to_response(final_task)
