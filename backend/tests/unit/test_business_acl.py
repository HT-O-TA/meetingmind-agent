from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import AppException
from app.models.document import Document
from app.services.document_service import DocumentService
from app.services.meeting_service import MeetingService
from app.services.todo_service import TodoService


def user(user_id: int, *, department: str | None = None, role: str = "user"):
    return SimpleNamespace(id=user_id, department=department, role=role)


def test_new_documents_are_private_by_default():
    assert Document.__table__.c.is_public.default.arg is False


@pytest.mark.asyncio
async def test_meeting_write_is_limited_to_organizer_or_admin():
    service = MeetingService(MagicMock())
    service.get_by_id = AsyncMock(
        return_value=SimpleNamespace(id=10, organizer_id=1, department="研发部")
    )

    assert (await service.get_for_user(10, user(2, department="研发部"))).id == 10
    with pytest.raises(AppException, match="无权"):
        await service.get_for_user(10, user(2, department="研发部"), write=True)
    assert (await service.get_for_user(10, user(9, role="admin"), write=True)).id == 10


@pytest.mark.asyncio
async def test_document_private_acl_and_readonly_write_guard():
    service = DocumentService(MagicMock())
    service.get_by_id = AsyncMock(
        return_value=SimpleNamespace(
            id=20, uploader_id=1, department="研发部", is_public=False
        )
    )

    assert (await service.get_for_user(20, user(2, department="研发部"))).id == 20
    with pytest.raises(AppException, match="无权"):
        await service.get_for_user(20, user(3, department="市场部"))
    with pytest.raises(AppException, match="只读"):
        await service.get_for_user(20, user(1, role="readonly"), write=True)


def test_todo_access_query_excludes_department_from_write_rule():
    service = TodoService(MagicMock())

    read_sql = str(service._access_query(user(2, department="研发部")))
    write_sql = str(service._access_query(user(2, department="研发部"), write=True))

    assert "todo_items.assignee_id" in read_sql
    assert "meetings.organizer_id" in read_sql
    assert "meetings.department" in read_sql
    assert "meetings.department" not in write_sql


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,read_access,write_access",
    [
        ("admin", (True, True, True, True), (True, True, True, True)),
        ("user", (True, True, True, False), (True, False, False, False)),
        ("readonly", (True, True, True, False), (False, False, False, False)),
    ],
)
@pytest.mark.parametrize("scope", range(4), ids=["owner", "department", "public", "private"])
@pytest.mark.parametrize("write", [False, True], ids=["read", "write"])
async def test_document_acl_matrix(role, read_access, write_access, scope, write):
    caller = user(1, department="engineering", role=role)
    document = SimpleNamespace(
        id=42,
        uploader_id=1 if scope == 0 else 2,
        department="engineering" if scope == 1 else "finance",
        is_public=scope == 2,
    )
    service = DocumentService(MagicMock())
    service.get_by_id = AsyncMock(return_value=document)

    if (write_access if write else read_access)[scope]:
        assert await service.get_for_user(document.id, caller, write=write) is document
    else:
        with pytest.raises(AppException) as error:
            await service.get_for_user(document.id, caller, write=write)
        assert error.value.code == 403
