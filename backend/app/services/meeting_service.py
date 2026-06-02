from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from app.models.meeting import Meeting, SpeechRecord
from app.schemas.meeting import MeetingCreate, MeetingUpdate, SpeechRecordCreate
from app.core.exceptions import AppException
from app.core.cache import cache_get, cache_set, cache_delete, cache_delete_pattern
from app.core.config import settings
from app.utils.cache_utils import make_cache_key, hash_params
import math


class MeetingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, meeting_id: int) -> Meeting:
        cache_key = make_cache_key("meetings", "detail", meeting_id)
        cached = await cache_get(cache_key)
        if cached:
            # 缓存命中时仍需返回 ORM 对象，直接查库但跳过序列化开销
            pass

        result = await self.db.execute(select(Meeting).where(Meeting.id == meeting_id))
        meeting = result.scalar_one_or_none()
        if not meeting:
            raise AppException("会议不存在", 404)
        return meeting

    async def get_by_id_cached(self, meeting_id: int) -> Optional[dict]:
        """返回字典（用于只读展示场景，命中缓存时不查库）"""
        cache_key = make_cache_key("meetings", "detail", meeting_id)
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        result = await self.db.execute(select(Meeting).where(Meeting.id == meeting_id))
        meeting = result.scalar_one_or_none()
        if not meeting:
            raise AppException("会议不存在", 404)

        from app.schemas.meeting import MeetingOut
        data = MeetingOut.model_validate(meeting).model_dump(mode="json")
        await cache_set(cache_key, data, ttl=300)
        return data

    async def list_meetings(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        keyword: str | None = None,
        department: str | None = None,
        meeting_type: str | None = None,
    ):
        # 有关键词搜索时不走缓存
        if not keyword:
            h = hash_params(page=page, page_size=page_size, status=status,
                            department=department, meeting_type=meeting_type)
            cache_key = make_cache_key("meetings", "list", h)
            cached = await cache_get(cache_key)
            if cached is not None:
                return cached["items"], cached["total"], cached["total_pages"]
        else:
            cache_key = None

        query = select(Meeting)
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

    async def update(self, meeting_id: int, data: MeetingUpdate) -> Meeting:
        meeting = await self.get_by_id(meeting_id)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(meeting, field, value)
        if meeting.start_time and meeting.end_time:
            delta = meeting.end_time - meeting.start_time
            meeting.duration_minutes = int(delta.total_seconds() / 60)
        await self.db.commit()
        await self.db.refresh(meeting)
        await self._invalidate_meeting(meeting_id)
        return meeting

    async def delete(self, meeting_id: int):
        meeting = await self.get_by_id(meeting_id)
        await self.db.delete(meeting)
        await self.db.commit()
        await self._invalidate_meeting(meeting_id)

    async def update_meeting_status(self, meeting_id: int, status: str) -> Meeting:
        meeting = await self.get_by_id(meeting_id)
        meeting.status = status
        await self.db.commit()
        await self.db.refresh(meeting)
        await self._invalidate_meeting(meeting_id)
        return meeting

    # ---- 发言记录 ----

    async def list_speeches(self, meeting_id: int):
        await self.get_by_id(meeting_id)
        result = await self.db.execute(
            select(SpeechRecord)
            .where(SpeechRecord.meeting_id == meeting_id)
            .order_by(SpeechRecord.sequence, SpeechRecord.id)
        )
        return result.scalars().all()

    async def create_speech(self, meeting_id: int, data: SpeechRecordCreate) -> SpeechRecord:
        await self.get_by_id(meeting_id)
        speech = SpeechRecord(**data.model_dump(), meeting_id=meeting_id)
        self.db.add(speech)
        await self.db.commit()
        await self.db.refresh(speech)
        await cache_delete(make_cache_key("meetings", "detail", meeting_id))
        return speech

    async def bulk_create_speeches(self, meeting_id: int, speeches: list[SpeechRecordCreate]) -> list[SpeechRecord]:
        await self.get_by_id(meeting_id)
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

    async def update_speech(self, speech_id: int, data):
        speech = await self.get_speech(speech_id)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(speech, field, value)
        await self.db.commit()
        await self.db.refresh(speech)
        meeting_id = speech.meeting_id
        await cache_delete(make_cache_key("meetings", "detail", meeting_id))
        return speech

    async def delete_speech(self, speech_id: int):
        result = await self.db.execute(select(SpeechRecord).where(SpeechRecord.id == speech_id))
        speech = result.scalar_one_or_none()
        if not speech:
            raise AppException("发言记录不存在", 404)
        meeting_id = speech.meeting_id
        await self.db.delete(speech)
        await self.db.commit()
        await cache_delete(make_cache_key("meetings", "detail", meeting_id))

    async def generate_vectors_from_speeches(self, meeting_id: int) -> None:
        """
        从会议的发言记录生成向量块
        
        Args:
            meeting_id: 会议ID
        """
        from app.models.vector import VectorChunk
        from app.services.embedding_service import EmbeddingService
        import json
        
        meeting = await self.get_by_id(meeting_id)
        
        # 获取会议的所有发言记录
        result = await self.db.execute(
            select(SpeechRecord)
            .where(SpeechRecord.meeting_id == meeting_id)
            .order_by(SpeechRecord.sequence, SpeechRecord.id)
        )
        speeches = result.scalars().all()
        
        if not speeches:
            return
        
        # 删除该会议现有的向量块
        await self.db.execute(
            VectorChunk.__table__.delete().where(VectorChunk.meeting_id == meeting_id)
        )
        
        # 准备发言数据
        speech_records = []
        for speech in speeches:
            speech_records.append({
                'speaker_name': speech.speaker_name,
                'content': speech.content,
                'start_time_offset': speech.start_time_offset,
            })
        
        # 批量向量化
        embedding_service = EmbeddingService()
        contents = [s['content'] for s in speech_records]
        embeddings = embedding_service.encode_batch(contents)
        
        # 创建向量块
        vector_chunks = []
        for idx, (speech, embedding) in enumerate(zip(speech_records, embeddings)):
            metadata = {
                'speaker_name': speech['speaker_name'],
                'start_time_offset': speech['start_time_offset'],
                'sequence': idx,
            }
            vector_chunk = VectorChunk(
                meeting_id=meeting_id,
                chunk_text=speech['content'],
                chunk_index=idx,
                speaker_name=speech['speaker_name'],
                time_offset=speech['start_time_offset'],
                embedding=json.dumps(embedding),
                embedding_array=embedding,
                embedding_model=settings.EMBEDDING_MODEL,
                department=meeting.department,
                metadata_json=json.dumps(metadata),
            )
            vector_chunks.append(vector_chunk)
        
        self.db.add_all(vector_chunks)
        await self.db.commit()
