from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List, cast
from app.db.database import get_db
from app.services.meeting_service import MeetingService
from app.schemas.meeting import (
    MeetingCreate, MeetingUpdate, MeetingOut,
    SpeechRecordCreate, SpeechRecordUpdate, SpeechRecordOut,
)
from app.core.response import Response, PageResponse
from app.core.deps import get_current_user, get_optional_user
from app.models.user import User

router = APIRouter()


@router.get("", response_model=PageResponse)
async def list_meetings(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    department: Optional[str] = None,
    meeting_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    svc = MeetingService(db)
    meetings, total, total_pages = await svc.list_meetings(
        page, page_size, status, keyword, department, meeting_type
    )
    return PageResponse(
        data=[MeetingOut.model_validate(m) for m in meetings],
        total=total or 0, page=page, page_size=page_size, total_pages=total_pages,
    )


@router.post("", response_model=Response)
async def create_meeting(
    data: MeetingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    svc = MeetingService(db)
    organizer_id = cast(int, current_user.id) if current_user else None
    meeting = await svc.create(data, organizer_id)
    return Response.created(MeetingOut.model_validate(meeting))


@router.get("/{meeting_id}", response_model=Response)
async def get_meeting(meeting_id: int, db: AsyncSession = Depends(get_db)):
    svc = MeetingService(db)
    meeting = await svc.get_by_id(meeting_id)
    return Response.ok(MeetingOut.model_validate(meeting))


@router.put("/{meeting_id}", response_model=Response)
async def update_meeting(meeting_id: int, data: MeetingUpdate, db: AsyncSession = Depends(get_db)):
    svc = MeetingService(db)
    meeting = await svc.update(meeting_id, data)
    return Response.ok(MeetingOut.model_validate(meeting))


@router.patch("/{meeting_id}/status", response_model=Response)
async def update_status(meeting_id: int, status: str, db: AsyncSession = Depends(get_db)):
    allowed = {"draft", "processing", "completed", "archived"}
    if status not in allowed:
        from app.core.exceptions import AppException
        raise AppException(f"无效状态，可选: {', '.join(allowed)}", 400)
    svc = MeetingService(db)
    meeting = await svc.update_meeting_status(meeting_id, status)
    return Response.ok(MeetingOut.model_validate(meeting))


@router.delete("/{meeting_id}", response_model=Response)
async def delete_meeting(meeting_id: int, db: AsyncSession = Depends(get_db)):
    svc = MeetingService(db)
    await svc.delete(meeting_id)
    return Response.ok(message="删除成功")


# ---- 发言记录 ----

@router.get("/{meeting_id}/speeches", response_model=Response)
async def list_speeches(meeting_id: int, db: AsyncSession = Depends(get_db)):
    svc = MeetingService(db)
    speeches = await svc.list_speeches(meeting_id)
    return Response.ok([SpeechRecordOut.model_validate(s) for s in speeches])


@router.post("/{meeting_id}/speeches", response_model=Response)
async def create_speech(meeting_id: int, data: SpeechRecordCreate, db: AsyncSession = Depends(get_db)):
    svc = MeetingService(db)
    speech = await svc.create_speech(meeting_id, data)
    return Response.created(SpeechRecordOut.model_validate(speech))


@router.post("/{meeting_id}/speeches/bulk", response_model=Response)
async def bulk_create_speeches(
    meeting_id: int,
    data: List[SpeechRecordCreate],
    db: AsyncSession = Depends(get_db),
):
    svc = MeetingService(db)
    speeches = await svc.bulk_create_speeches(meeting_id, data)
    return Response.created([SpeechRecordOut.model_validate(s) for s in speeches])


@router.put("/{meeting_id}/speeches/{speech_id}", response_model=Response)
async def update_speech(
    meeting_id: int, speech_id: int, data: SpeechRecordUpdate, db: AsyncSession = Depends(get_db)
):
    svc = MeetingService(db)
    speech = await svc.update_speech(speech_id, data)
    return Response.ok(SpeechRecordOut.model_validate(speech))


@router.delete("/{meeting_id}/speeches/{speech_id}", response_model=Response)
async def delete_speech(meeting_id: int, speech_id: int, db: AsyncSession = Depends(get_db)):
    svc = MeetingService(db)
    await svc.delete_speech(speech_id)
    return Response.ok(message="删除成功")