from fastapi import APIRouter, Depends, Query, UploadFile, File, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, cast, List
from pydantic import BaseModel, Field
from app.db.database import get_db
from app.services.document_service import DocumentService
from app.schemas.document import DocumentOut, DocumentUpdate
from app.core.response import Response, PageResponse
from app.core.deps import get_current_user
from app.models.user import User
from app.core.config import settings
from app.core.exceptions import AppException
from app.core.security import is_admin_user, require_write_user
from app.services.meeting_service import MeetingService

router = APIRouter()


class ContentUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=2_000_000)


class BatchUploadResponse(BaseModel):
    success_count: int
    fail_count: int
    results: List[dict]


@router.get("", response_model=PageResponse)
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    meeting_id: Optional[int] = None,
    department: Optional[str] = None,
    file_type: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = DocumentService(db)
    docs, total, total_pages = await svc.list_documents(
        page, page_size, meeting_id, department, file_type, status, current_user
    )
    return PageResponse(
        data=[DocumentOut.model_validate(d) for d in docs],
        total=total or 0, page=page, page_size=page_size, total_pages=total_pages,
    )


@router.post("/upload", response_model=Response)
async def upload_document(
    file: UploadFile = File(...),
    meeting_id: Optional[int] = Form(None),
    department: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_write_user(current_user)
    if meeting_id is not None:
        await MeetingService(db).get_for_user(meeting_id, current_user, write=True)
    if not is_admin_user(current_user):
        if department is not None and department != current_user.department:
            raise AppException("不能为其他部门上传文档", 403)
        department = current_user.department
    svc = DocumentService(db)
    uploader_id = cast(int, current_user.id)
    doc = await svc.upload(file, meeting_id, department, uploader_id)
    return Response.created(DocumentOut.model_validate(doc), "上传成功")


@router.get("/{doc_id}", response_model=Response)
async def get_document(doc_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    svc = DocumentService(db)
    doc = await svc.get_for_user(doc_id, current_user)
    return Response.ok(DocumentOut.model_validate(doc))


@router.put("/{doc_id}/content", response_model=Response)
async def update_content(
    doc_id: int,
    data: ContentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_write_user(current_user)
    svc = DocumentService(db)
    await svc.get_for_user(doc_id, current_user, write=True)
    doc = await svc.update_content(doc_id, data.content)
    return Response.ok(DocumentOut.model_validate(doc))


@router.put("/{doc_id}", response_model=Response)
async def update_document(
    doc_id: int,
    data: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_write_user(current_user)
    svc = DocumentService(db)
    await svc.get_for_user(doc_id, current_user, write=True)
    if data.meeting_id is not None:
        await MeetingService(db).get_for_user(data.meeting_id, current_user, write=True)
    department = data.department
    if not is_admin_user(current_user):
        if department is not None and department != current_user.department:
            raise AppException("不能把文档转移到其他部门", 403)
        department = current_user.department
    doc = await svc.update_document_metadata(
        doc_id,
        meeting_id=data.meeting_id,
        department=department,
        is_public=data.is_public,
    )
    return Response.ok(DocumentOut.model_validate(doc))


@router.delete("/{doc_id}", response_model=Response)
async def delete_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_write_user(current_user)
    svc = DocumentService(db)
    await svc.get_for_user(doc_id, current_user, write=True)
    await svc.delete(doc_id)
    return Response.ok(message="删除成功")


@router.post("/batch-upload", response_model=Response)
async def batch_upload_documents(
    files: List[UploadFile] = File(...),
    meeting_id: Optional[int] = Form(None),
    department: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量上传多个文档"""
    import time
    from app.core.logger import app_logger
    
    start_time = time.time()
    uploader_id = cast(int, current_user.id)
    require_write_user(current_user)
    if meeting_id is not None:
        await MeetingService(db).get_for_user(meeting_id, current_user, write=True)
    if not is_admin_user(current_user):
        if department is not None and department != current_user.department:
            raise AppException("不能为其他部门上传文档", 403)
        department = current_user.department
    
    app_logger.info(f"=== 批量上传开始 ===")
    app_logger.info(f"上传用户: {current_user.id} ({current_user.username if hasattr(current_user, 'username') else '未知'})")
    app_logger.info(f"文件数量: {len(files)}")
    app_logger.info(f"会议ID: {meeting_id}")
    app_logger.info(f"部门: {department}")
    
    # 验证文件数量
    if not files:
        raise HTTPException(status_code=400, detail="至少选择一个文件")
    if len(files) > settings.MAX_FILE_COUNT:
        error_msg = f"单次上传文件数量不能超过 {settings.MAX_FILE_COUNT} 个"
        app_logger.error(f"批量上传失败: {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
    
    # 验证文件格式
    allowed_extensions = settings.allowed_file_extensions_list
    invalid_files = []
    for file in files:
        if file.filename:
            ext = file.filename.split('.')[-1].lower()
            if ext not in allowed_extensions:
                invalid_files.append(f"{file.filename} ({ext})")
    
    if invalid_files:
        error_msg = f"文件格式不支持: {', '.join(invalid_files)}，支持的格式：{', '.join(allowed_extensions)}"
        app_logger.error(f"批量上传失败: {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
    
    svc = DocumentService(db)
    
    success_count = 0
    fail_count = 0
    results = []
    failed_files = []
    
    for idx, file in enumerate(files, 1):
        try:
            app_logger.debug(f"[{idx}/{len(files)}] 开始处理: {file.filename}")
            doc = await svc.upload(file, meeting_id, department, uploader_id)
            results.append({
                "filename": file.filename,
                "document_id": doc.id,
                "status": "success",
                "message": "上传成功"
            })
            success_count += 1
            app_logger.info(f"[{idx}/{len(files)}] ✅ 上传成功: {file.filename} -> ID: {doc.id}")
        except Exception as e:
            error_detail = e.message if isinstance(e, AppException) and e.code < 500 else "上传失败"
            results.append({
                "filename": file.filename,
                "document_id": None,
                "status": "failed",
                "message": error_detail
            })
            failed_files.append(f"{file.filename}: {error_detail}")
            fail_count += 1
            app_logger.exception(f"[{idx}/{len(files)}] 上传失败: {file.filename}: {e}")
    
    end_time = time.time()
    duration = end_time - start_time
    
    app_logger.info(f"=== 批量上传完成 ===")
    app_logger.info(f"成功: {success_count}, 失败: {fail_count}")
    app_logger.info(f"耗时: {duration:.2f}秒 ({(duration/len(files)):.2f}秒/文件)")
    
    if failed_files:
        app_logger.warning(f"失败文件列表: {'; '.join(failed_files)}")
    
    message = f"批量上传完成，成功 {success_count} 个，失败 {fail_count} 个"
    if fail_count > 0:
        message += "（查看日志获取详细错误信息）"
    
    return Response.ok(
        data={
            "success_count": success_count,
            "fail_count": fail_count,
            "results": results,
            "duration_seconds": round(duration, 2)
        },
        message=message
    )
