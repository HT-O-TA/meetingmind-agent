from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, select, func, or_
from app.models.meeting import Meeting, SpeechRecord
from app.schemas.meeting import MeetingCreate, MeetingUpdate, SpeechRecordCreate
from app.core.exceptions import AppException
from app.core.cache import cache_get, cache_set, cache_delete, cache_delete_pattern
from app.utils.cache_utils import make_cache_key, hash_params
from app.core.security import is_admin_user, require_write_user
from app.models.user import User
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
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(meeting, field, value)
        if meeting.start_time and meeting.end_time:
            delta = meeting.end_time - meeting.start_time
            meeting.duration_minutes = int(delta.total_seconds() / 60)
        await self.db.commit()
        await self.db.refresh(meeting)
        await self._invalidate_meeting(meeting_id)
        return meeting

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
            .where(SpeechRecord.meeting_id == meeting_id)
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
        await self.get_for_user(meeting_id, user, write=True)
        speech = await self.get_speech(speech_id)
        if speech.meeting_id != meeting_id:
            raise AppException("发言记录不属于该会议", 404)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(speech, field, value)
        await self.db.commit()
        await self.db.refresh(speech)
        meeting_id = speech.meeting_id
        await cache_delete(make_cache_key("meetings", "detail", meeting_id))
        return speech

    async def delete_speech(self, meeting_id: int, speech_id: int, user: User):
        await self.get_for_user(meeting_id, user, write=True)
        result = await self.db.execute(select(SpeechRecord).where(SpeechRecord.id == speech_id))
        speech = result.scalar_one_or_none()
        if not speech or speech.meeting_id != meeting_id:
            raise AppException("发言记录不存在", 404)
        meeting_id = speech.meeting_id
        await self.db.delete(speech)
        await self.db.commit()
        await cache_delete(make_cache_key("meetings", "detail", meeting_id))
