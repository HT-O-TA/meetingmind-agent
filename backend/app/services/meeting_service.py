from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, select, func, or_, update
from app.models.meeting import Meeting, SpeechRecord
from app.schemas.meeting import MeetingCreate, MeetingUpdate, SpeechRecordCreate
from app.core.exceptions import AppException
from app.core.cache import cache_get, cache_set, cache_delete, cache_delete_pattern
from app.utils.cache_utils import make_cache_key, hash_params
from app.core.security import is_admin_user, require_write_user
from app.models.user import User
from app.services.asr_evidence_service import (
    apply_human_correction_metadata,
    format_index_text,
    text_sha256,
)
from app.services.document_service import DocumentService
from app.services.prompt_injection_guard import get_prompt_injection_guard
import math


class MeetingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, meeting_id: int) -> Meeting:
        result = await self.db.execute(select(Meeting).where(Meeting.id == meeting_id))
        meeting = result.scalar_one_or_none()
        if not meeting:
            raise AppException("会议不存在", 404)
        return meeting

    async def get_for_user(self, meeting_id: int, user: User, *, write: bool = False) -> Meeting:
        meeting = await self.get_by_id(meeting_id)
        if write:
            require_write_user(user)
            allowed = is_admin_user(user) or meeting.organizer_id == user.id
        else:
            same_department = bool(user.department) and meeting.department == user.department
            allowed = is_admin_user(user) or meeting.organizer_id == user.id or same_department
        if not allowed:
            raise AppException("无权访问该会议", 403)
        return meeting

    async def list_meetings(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        keyword: str | None = None,
        department: str | None = None,
        meeting_type: str | None = None,
        current_user: User | None = None,
    ):
        if current_user is None:
            raise AppException("需要登录后访问会议", 401)
        # 有关键词搜索时不走缓存
        if not keyword:
            h = hash_params(page=page, page_size=page_size, status=status,
                            department=department, meeting_type=meeting_type,
                            user_id=current_user.id, user_role=str(current_user.role),
                            user_department=current_user.department)
            cache_key = make_cache_key("meetings", "list", h)
            cached = await cache_get(cache_key)
            if cached is not None:
                return cached["items"], cached["total"], cached["total_pages"]
        else:
            cache_key = None

        query = select(Meeting)
        if not is_admin_user(current_user):
            access_rules = [Meeting.organizer_id == current_user.id]
            if current_user.department:
                access_rules.append(
                    and_(Meeting.department.is_not(None), Meeting.department == current_user.department)
                )
            query = query.where(or_(*access_rules))
        if status:
            query = query.where(Meeting.status == status)
        if keyword:
            query = query.where(
                or_(
                    Meeting.title.ilike(f"%{keyword}%"),
                    Meeting.description.ilike(f"%{keyword}%"),
                )
            )
        if department:
            query = query.where(Meeting.department == department)
        if meeting_type:
            query = query.where(Meeting.meeting_type == meeting_type)

        total = (await self.db.execute(select(func.count()).select_from(query.subquery()))).scalar()
        query = query.order_by(Meeting.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        meetings = (await self.db.execute(query)).scalars().all()
        total_pages = math.ceil(total / page_size) if total else 0

        if cache_key:
            from app.schemas.meeting import MeetingOut
            await cache_set(cache_key, {
                "items": [MeetingOut.model_validate(m).model_dump(mode="json") for m in meetings],
                "total": total,
                "total_pages": total_pages,
            }, ttl=60)

        return meetings, total, total_pages

    async def _invalidate_meeting(self, meeting_id: int):
        await cache_delete(make_cache_key("meetings", "detail", meeting_id))
        await cache_delete_pattern("meetings:list:*")

    async def create(self, data: MeetingCreate, organizer_id: int | None = None) -> Meeting:
        meeting = Meeting(**data.model_dump(), organizer_id=organizer_id)
        if meeting.start_time and meeting.end_time:
            delta = meeting.end_time - meeting.start_time
            meeting.duration_minutes = int(delta.total_seconds() / 60)
        self.db.add(meeting)
        await self.db.commit()
        await self.db.refresh(meeting)
        await cache_delete_pattern("meetings:list:*")
        return meeting

    async def update(self, meeting_id: int, data: MeetingUpdate, user: User) -> Meeting:
        meeting = await self.get_for_user(meeting_id, user, write=True)
        updates = data.model_dump(exclude_none=True)
        raw_changed = (
            "raw_transcript" in updates
            and updates["raw_transcript"] != meeting.raw_transcript
        )
        has_asr_evidence = bool(
            meeting.asr_original_transcript
            or (meeting.transcript_metadata or {}).get("task_id")
        )
        if raw_changed and has_asr_evidence:
            check = await get_prompt_injection_guard().check(
                str(updates["raw_transcript"] or ""), llm_service=None
            )
            if check.should_block:
                raise AppException(
                    "修订后的转写命中间接注入规则；请按发言片段核对后再提交",
                    422,
                )

        for field, value in updates.items():
            setattr(meeting, field, value)
        if meeting.start_time and meeting.end_time:
            delta = meeting.end_time - meeting.start_time
            meeting.duration_minutes = int(delta.total_seconds() / 60)
        await self.db.commit()
        await self.db.refresh(meeting)
        if raw_changed and has_asr_evidence:
            # 完整文本修订不再假装保留原句级对齐；旧 ASR 片段留作审计但不参与当前证据。
            await self.db.execute(
                update(SpeechRecord)
                .where(
                    SpeechRecord.meeting_id == meeting_id,
                    SpeechRecord.source_type.in_(["asr", "asr_corrected"]),
                )
                .values(source_type="asr_superseded")
            )
            await self.db.commit()
            await self._rebuild_corrected_asr_evidence(
                meeting,
                user,
                corrected_text=str(meeting.raw_transcript or ""),
                index_text=str(meeting.raw_transcript or ""),
                reason="full_transcript_correction",
            )
        await self._invalidate_meeting(meeting_id)
        return meeting

    async def _rebuild_corrected_asr_evidence(
        self,
        meeting: Meeting,
        user: User,
        *,
        corrected_text: str,
        index_text: str,
        reason: str,
    ) -> None:
        """修订后递增证据版本，先失效旧块，再重建当前安全证据。"""
        revision = int(meeting.transcript_revision or 0) + 1
        metadata = apply_human_correction_metadata(
            meeting.transcript_metadata,
            corrected_text=corrected_text,
            revision=revision,
            user_id=getattr(user, "id", None),
            reason=reason,
        )
        meeting.raw_transcript = corrected_text or None
        meeting.transcript_revision = revision
        meeting.transcript_status = "completed"
        meeting.transcript_metadata = metadata
        await self.db.commit()

        document_service = DocumentService(self.db)
        index_text = index_text.strip()
        if index_text:
            document = await document_service.upsert_asr_evidence_document(
                meeting_id=meeting.id,
                uploader_id=int(meeting.organizer_id or getattr(user, "id", 0)),
                department=meeting.department,
                original_filename=str(metadata.get("source_filename") or "meeting.wav"),
                content=index_text,
                task_id=str(metadata.get("task_id") or f"manual-revision-{revision}"),
                evidence_version=revision,
                audio_sha256=str(metadata.get("audio_sha256") or "unknown"),
            )
            chunks = await document_service.get_vector_chunks(document.id)
            metadata["index"] = {
                "status": "indexed" if chunks else "rebuild_required",
                "document_id": document.id,
                "indexed_revision": revision if chunks else None,
                "chunk_count": len(chunks),
                "reason": None if chunks else "no_vector_chunks_created",
            }
        else:
            await document_service.invalidate_asr_evidence_document(
                meeting.id, "human_correction_empty"
            )
            metadata["index"] = {
                "status": "not_created",
                "document_id": (metadata.get("index") or {}).get("document_id"),
                "indexed_revision": None,
                "chunk_count": 0,
                "reason": "human_correction_empty",
            }
        meeting.transcript_metadata = metadata
        await self.db.commit()

    async def delete(self, meeting_id: int, user: User):
        meeting = await self.get_for_user(meeting_id, user, write=True)
        await self.db.delete(meeting)
        await self.db.commit()
        await self._invalidate_meeting(meeting_id)

    async def update_meeting_status(self, meeting_id: int, status: str, user: User) -> Meeting:
        meeting = await self.get_for_user(meeting_id, user, write=True)
        meeting.status = status
        await self.db.commit()
        await self.db.refresh(meeting)
        await self._invalidate_meeting(meeting_id)
        return meeting

    # ---- 发言记录 ----

    async def list_speeches(self, meeting_id: int, user: User):
        await self.get_for_user(meeting_id, user)
        result = await self.db.execute(
            select(SpeechRecord)
            .where(
                SpeechRecord.meeting_id == meeting_id,
                or_(
                    SpeechRecord.source_type.is_(None),
                    SpeechRecord.source_type != "asr_superseded",
                ),
            )
            .order_by(SpeechRecord.sequence, SpeechRecord.id)
        )
        return result.scalars().all()

    async def create_speech(self, meeting_id: int, data: SpeechRecordCreate, user: User) -> SpeechRecord:
        await self.get_for_user(meeting_id, user, write=True)
        speech = SpeechRecord(**data.model_dump(), meeting_id=meeting_id)
        self.db.add(speech)
        await self.db.commit()
        await self.db.refresh(speech)
        await cache_delete(make_cache_key("meetings", "detail", meeting_id))
        return speech

    async def bulk_create_speeches(
        self, meeting_id: int, speeches: list[SpeechRecordCreate], user: User
    ) -> list[SpeechRecord]:
        await self.get_for_user(meeting_id, user, write=True)
        records = [SpeechRecord(**s.model_dump(), meeting_id=meeting_id) for s in speeches]
        self.db.add_all(records)
        await self.db.commit()
        for r in records:
            await self.db.refresh(r)
        await cache_delete(make_cache_key("meetings", "detail", meeting_id))
        return records

    async def get_speech(self, speech_id: int) -> SpeechRecord:
        result = await self.db.execute(select(SpeechRecord).where(SpeechRecord.id == speech_id))
        speech = result.scalar_one_or_none()
        if not speech:
            raise AppException("发言记录不存在", 404)
        return speech

    async def update_speech(self, meeting_id: int, speech_id: int, data, user: User):
        meeting = await self.get_for_user(meeting_id, user, write=True)
        speech = await self.get_speech(speech_id)
        if speech.meeting_id != meeting_id:
            raise AppException("发言记录不属于该会议", 404)
        was_asr = speech.source_type in {"asr", "asr_corrected"}
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(speech, field, value)
        if was_asr:
            check = await get_prompt_injection_guard().check(
                str(speech.content or ""), llm_service=None
            )
            speech.source_type = "asr_corrected"
            speech.content_sha256 = text_sha256(speech.content)
            speech.security_status = "quarantined" if check.should_block else (
                "warning" if check.should_warn else "passed"
            )
            speech.security_reason = (
                check.injection_type.value if check.injection_type else None
            )
        await self.db.commit()
        await self.db.refresh(speech)
        meeting_id = speech.meeting_id
        if was_asr:
            result = await self.db.execute(
                select(SpeechRecord)
                .where(
                    SpeechRecord.meeting_id == meeting_id,
                    SpeechRecord.source_type.in_(["asr", "asr_corrected"]),
                    or_(
                        SpeechRecord.security_status.is_(None),
                        SpeechRecord.security_status != "quarantined",
                    ),
                )
                .order_by(SpeechRecord.sequence, SpeechRecord.id)
            )
            safe_records = list(result.scalars().all())
            await self._rebuild_corrected_asr_evidence(
                meeting,
                user,
                corrected_text="\n".join(record.content for record in safe_records).strip(),
                index_text=format_index_text(safe_records),
                reason=f"speech_record_corrected:{speech_id}",
            )
        await cache_delete(make_cache_key("meetings", "detail", meeting_id))
        return speech

    async def delete_speech(self, meeting_id: int, speech_id: int, user: User):
        meeting = await self.get_for_user(meeting_id, user, write=True)
        result = await self.db.execute(select(SpeechRecord).where(SpeechRecord.id == speech_id))
        speech = result.scalar_one_or_none()
        if not speech or speech.meeting_id != meeting_id:
            raise AppException("发言记录不存在", 404)
        was_asr = speech.source_type in {"asr", "asr_corrected"}
        meeting_id = speech.meeting_id
        await self.db.delete(speech)
        await self.db.commit()
        if was_asr:
            result = await self.db.execute(
                select(SpeechRecord)
                .where(
                    SpeechRecord.meeting_id == meeting_id,
                    SpeechRecord.source_type.in_(["asr", "asr_corrected"]),
                    or_(
                        SpeechRecord.security_status.is_(None),
                        SpeechRecord.security_status != "quarantined",
                    ),
                )
                .order_by(SpeechRecord.sequence, SpeechRecord.id)
            )
            safe_records = list(result.scalars().all())
            await self._rebuild_corrected_asr_evidence(
                meeting,
                user,
                corrected_text="\n".join(record.content for record in safe_records).strip(),
                index_text=format_index_text(safe_records),
                reason=f"speech_record_deleted:{speech_id}",
            )
        await cache_delete(make_cache_key("meetings", "detail", meeting_id))
