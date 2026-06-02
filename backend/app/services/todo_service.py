from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.todo import TodoItem
from app.schemas.todo import TodoCreate, TodoUpdate
from app.core.exceptions import AppException
from app.core.cache import cache_get, cache_set, cache_delete
from app.utils.cache_utils import make_cache_key
from datetime import datetime
import math


class TodoService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, todo_id: int) -> TodoItem:
        result = await self.db.execute(select(TodoItem).where(TodoItem.id == todo_id))
        todo = result.scalar_one_or_none()
        if not todo:
            raise AppException("待办不存在", 404)
        return todo

    async def list_todos(
        self,
        page: int = 1,
        page_size: int = 50,
        meeting_id: Optional[int] = None,
        status: Optional[str] = None,
        assignee_name: Optional[str] = None,
        priority: Optional[str] = None,
    ):
        query = select(TodoItem)
        if meeting_id:
            query = query.where(TodoItem.meeting_id == meeting_id)
        if status:
            query = query.where(TodoItem.status == status)
        if assignee_name:
            query = query.where(TodoItem.assignee_name.ilike(f"%{assignee_name}%"))
        if priority:
            query = query.where(TodoItem.priority == priority)

        total = (await self.db.execute(select(func.count()).select_from(query.subquery()))).scalar()
        query = query.order_by(TodoItem.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        todos = (await self.db.execute(query)).scalars().all()
        return todos, total, math.ceil(total / page_size) if total else 0

    async def _invalidate_stats(self, meeting_id: int = None):
        await cache_delete(make_cache_key("todos", "stats", meeting_id or "global"))

    async def create(self, data: TodoCreate) -> TodoItem:
        todo = TodoItem(**data.model_dump())
        self.db.add(todo)
        await self.db.commit()
        await self.db.refresh(todo)
        await self._invalidate_stats(todo.meeting_id)
        return todo

    async def bulk_create(self, items: list[TodoCreate]) -> list[TodoItem]:
        todos = [TodoItem(**item.model_dump()) for item in items]
        self.db.add_all(todos)
        await self.db.commit()
        for t in todos:
            await self.db.refresh(t)
        # 批量失效所有 stats 缓存
        meeting_ids = {t.meeting_id for t in todos}
        for mid in meeting_ids:
            await self._invalidate_stats(mid)
        return todos

    async def update(self, todo_id: int, data: TodoUpdate) -> TodoItem:
        todo = await self.get_by_id(todo_id)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(todo, field, value)
        if data.status == "done" and not todo.completed_at:
            todo.completed_at = datetime.utcnow()
        elif data.status and data.status != "done":
            todo.completed_at = None
        await self.db.commit()
        await self.db.refresh(todo)
        await self._invalidate_stats(todo.meeting_id)
        return todo

    async def delete(self, todo_id: int):
        todo = await self.get_by_id(todo_id)
        meeting_id = todo.meeting_id
        await self.db.delete(todo)
        await self.db.commit()
        await self._invalidate_stats(meeting_id)

    async def delete_by_meeting(self, meeting_id: int):
        result = await self.db.execute(select(TodoItem).where(TodoItem.meeting_id == meeting_id))
        todos = result.scalars().all()
        for t in todos:
            await self.db.delete(t)
        await self.db.commit()
        await self._invalidate_stats(meeting_id)

    async def get_stats(self, meeting_id: int | None = None) -> dict:
        cache_key = make_cache_key("todos", "stats", meeting_id or "global")
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        query = select(TodoItem)
        if meeting_id:
            query = query.where(TodoItem.meeting_id == meeting_id)
        todos = (await self.db.execute(query)).scalars().all()
        total = len(todos)
        done = sum(1 for t in todos if t.status == "done")
        pending = sum(1 for t in todos if t.status == "pending")
        in_progress = sum(1 for t in todos if t.status == "in_progress")
        result = {
            "total": total,
            "done": done,
            "pending": pending,
            "in_progress": in_progress,
            "completion_rate": round(done / total * 100, 1) if total else 0,
        }
        await cache_set(cache_key, result, ttl=120)
        return result
