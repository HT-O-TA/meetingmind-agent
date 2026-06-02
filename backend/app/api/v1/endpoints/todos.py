from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from app.db.database import get_db
from app.services.todo_service import TodoService
from app.schemas.todo import TodoCreate, TodoUpdate, TodoOut
from app.core.response import Response, PageResponse

router = APIRouter()


@router.get("", response_model=PageResponse)
async def list_todos(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    meeting_id: Optional[int] = None,
    status: Optional[str] = None,
    assignee_name: Optional[str] = None,
    priority: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    svc = TodoService(db)
    todos, total, total_pages = await svc.list_todos(page, page_size, meeting_id, status, assignee_name, priority)
    return PageResponse(
        data=[TodoOut.model_validate(t) for t in todos],
        total=total, page=page, page_size=page_size, total_pages=total_pages,
    )


@router.post("", response_model=Response)
async def create_todo(data: TodoCreate, db: AsyncSession = Depends(get_db)):
    svc = TodoService(db)
    todo = await svc.create(data)
    return Response.created(TodoOut.model_validate(todo))


@router.post("/bulk", response_model=Response)
async def bulk_create_todos(data: List[TodoCreate], db: AsyncSession = Depends(get_db)):
    svc = TodoService(db)
    todos = await svc.bulk_create(data)
    return Response.created([TodoOut.model_validate(t) for t in todos])


@router.get("/summary/stats", response_model=Response)
async def get_stats(meeting_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    svc = TodoService(db)
    stats = await svc.get_stats(meeting_id)
    return Response.ok(stats)


@router.get("/{todo_id}", response_model=Response)
async def get_todo(todo_id: int, db: AsyncSession = Depends(get_db)):
    svc = TodoService(db)
    todo = await svc.get_by_id(todo_id)
    return Response.ok(TodoOut.model_validate(todo))


@router.put("/{todo_id}", response_model=Response)
async def update_todo(todo_id: int, data: TodoUpdate, db: AsyncSession = Depends(get_db)):
    svc = TodoService(db)
    todo = await svc.update(todo_id, data)
    return Response.ok(TodoOut.model_validate(todo))


@router.delete("/{todo_id}", response_model=Response)
async def delete_todo(todo_id: int, db: AsyncSession = Depends(get_db)):
    svc = TodoService(db)
    await svc.delete(todo_id)
    return Response.ok(message="删除成功")
