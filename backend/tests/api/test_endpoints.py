from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.agents.state import AgentResult, TaskType, WorkflowType, RiskLevel
from app.core.deps import get_current_user
from app.core.dependencies import get_llm_service, get_vector_search_service
from app.db.database import get_db
from app.main import app


def make_user(**overrides):
    data = {
        "id": 1,
        "username": "tester",
        "email": "tester@example.com",
        "hashed_password": "hashed",
        "full_name": "Test User",
        "department": "QA",
        "role": "member",
        "is_active": True,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def make_meeting(**overrides):
    data = {
        "id": 10,
        "title": "Sprint Review",
        "description": "weekly review",
        "organizer_id": 1,
        "organizer_name": "Test User",
        "department": "QA",
        "meeting_type": "weekly",
        "status": "draft",
        "start_time": None,
        "end_time": None,
        "duration_minutes": None,
        "location": None,
        "participants": None,
        "summary": None,
        "minutes": None,
        "keywords": None,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def make_speech(**overrides):
    data = {
        "id": 20,
        "meeting_id": 10,
        "speaker_name": "Alice",
        "content": "Ship the release.",
        "start_time_offset": None,
        "end_time_offset": None,
        "sequence": 1,
        "sentiment": None,
        "is_key_point": 0,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def make_document(**overrides):
    data = {
        "id": 30,
        "meeting_id": 10,
        "uploader_id": 1,
        "filename": "stored.txt",
        "original_filename": "notes.txt",
        "file_size": 12,
        "file_type": "txt",
        "status": "uploaded",
        "department": "QA",
        "is_public": True,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def make_todo(**overrides):
    data = {
        "id": 40,
        "meeting_id": 10,
        "title": "Follow up",
        "description": "Send summary",
        "assignee_name": "Alice",
        "priority": "medium",
        "status": "pending",
        "due_date": None,
        "completed_at": None,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.fixture
def client():
    async def fake_db():
        yield SimpleNamespace()

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_llm_service] = lambda: SimpleNamespace()
    app.dependency_overrides[get_vector_search_service] = lambda: SimpleNamespace()
    test_client = TestClient(app)
    yield test_client
    test_client.close()
    app.dependency_overrides.clear()


@pytest.fixture
def authenticated_client(client):
    async def fake_current_user():
        return make_user()

    app.dependency_overrides[get_current_user] = fake_current_user
    return client


@pytest.fixture
def admin_client(client):
    async def fake_admin_user():
        return make_user(role="admin")

    app.dependency_overrides[get_current_user] = fake_admin_user
    return client


def test_mutating_meeting_and_document_routes_require_auth(client):
    meeting_payload = {"title": "No auth"}
    document_payload = {"department": "QA"}

    assert client.post("/api/v1/meetings", json=meeting_payload).status_code == 401
    assert client.put("/api/v1/meetings/1", json=meeting_payload).status_code == 401
    assert client.delete("/api/v1/meetings/1").status_code == 401
    assert client.post(
        "/api/v1/meetings/1/speeches",
        json={"speaker_name": "Alice", "content": "hello"},
    ).status_code == 401
    assert client.put("/api/v1/documents/1", json=document_payload).status_code == 401
    assert client.delete("/api/v1/documents/1").status_code == 401
    assert client.post("/api/v1/agents/query", json={"question": "检索私有文档"}).status_code == 401


def test_meeting_crud_and_speech_routes(authenticated_client, monkeypatch):
    from app.api.v1.endpoints import meetings as meetings_endpoint

    class FakeMeetingService:
        def __init__(self, db):
            pass

        async def list_meetings(self, page, page_size, status, keyword, department, meeting_type):
            return [make_meeting()], 1, 1

        async def create(self, data, organizer_id):
            assert organizer_id == 1
            return make_meeting(title=data.title, organizer_id=organizer_id)

        async def get_by_id(self, meeting_id):
            return make_meeting(id=meeting_id)

        async def update(self, meeting_id, data):
            return make_meeting(id=meeting_id, title=data.title or "updated")

        async def update_meeting_status(self, meeting_id, status):
            return make_meeting(id=meeting_id, status=status)

        async def delete(self, meeting_id):
            self.deleted_id = meeting_id

        async def list_speeches(self, meeting_id):
            return [make_speech(meeting_id=meeting_id)]

        async def create_speech(self, meeting_id, data):
            return make_speech(meeting_id=meeting_id, speaker_name=data.speaker_name)

        async def bulk_create_speeches(self, meeting_id, data):
            return [make_speech(meeting_id=meeting_id, speaker_name=item.speaker_name) for item in data]

        async def update_speech(self, speech_id, data):
            return make_speech(id=speech_id, speaker_name=data.speaker_name or "Alice")

        async def delete_speech(self, speech_id):
            self.deleted_speech_id = speech_id

    monkeypatch.setattr(meetings_endpoint, "MeetingService", FakeMeetingService)

    assert authenticated_client.get("/api/v1/meetings").json()["total"] == 1
    created = authenticated_client.post("/api/v1/meetings", json={"title": "Planning"}).json()
    assert created["code"] == 201
    assert created["data"]["title"] == "Planning"
    assert authenticated_client.put("/api/v1/meetings/10", json={"title": "Updated"}).json()["data"]["title"] == "Updated"
    assert authenticated_client.patch("/api/v1/meetings/10/status", params={"status": "completed"}).json()["data"]["status"] == "completed"
    assert authenticated_client.delete("/api/v1/meetings/10").json()["message"] == "删除成功"
    assert len(authenticated_client.get("/api/v1/meetings/10/speeches").json()["data"]) == 1
    assert authenticated_client.post(
        "/api/v1/meetings/10/speeches",
        json={"speaker_name": "Bob", "content": "done"},
    ).json()["data"]["speaker_name"] == "Bob"


def test_document_routes_cover_upload_metadata_and_delete(authenticated_client, monkeypatch):
    from app.api.v1.endpoints import documents as documents_endpoint

    class FakeDocumentService:
        def __init__(self, db):
            pass

        async def list_documents(self, page, page_size, meeting_id, department, file_type, status):
            return [make_document()], 1, 1

        async def upload(self, file, meeting_id, department, uploader_id):
            return make_document(
                original_filename=file.filename,
                meeting_id=meeting_id,
                department=department,
                uploader_id=uploader_id,
            )

        async def get_by_id(self, doc_id):
            return make_document(id=doc_id)

        async def update_content(self, doc_id, content):
            return make_document(id=doc_id, status="parsed")

        async def update_document_metadata(self, doc_id, meeting_id, department):
            return make_document(id=doc_id, meeting_id=meeting_id, department=department)

        async def delete(self, doc_id):
            self.deleted_id = doc_id

    monkeypatch.setattr(documents_endpoint, "DocumentService", FakeDocumentService)

    assert authenticated_client.get("/api/v1/documents").json()["total"] == 1
    uploaded = authenticated_client.post(
        "/api/v1/documents/upload",
        data={"meeting_id": "10", "department": "QA"},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    ).json()
    assert uploaded["code"] == 201
    assert uploaded["data"]["original_filename"] == "notes.txt"
    assert authenticated_client.get("/api/v1/documents/30").json()["data"]["id"] == 30
    assert authenticated_client.put("/api/v1/documents/30/content", json={"content": "parsed"}).json()["data"]["status"] == "parsed"
    assert authenticated_client.put("/api/v1/documents/30", json={"meeting_id": 11, "department": "Ops"}).json()["data"]["department"] == "Ops"
    assert authenticated_client.delete("/api/v1/documents/30").json()["message"] == "删除成功"


def test_todo_routes_cover_crud_bulk_and_stats(client, monkeypatch):
    from app.api.v1.endpoints import todos as todos_endpoint

    class FakeTodoService:
        def __init__(self, db):
            pass

        async def list_todos(self, page, page_size, meeting_id, status, assignee_name, priority):
            return [make_todo()], 1, 1

        async def create(self, data):
            return make_todo(title=data.title)

        async def bulk_create(self, data):
            return [make_todo(title=item.title) for item in data]

        async def get_stats(self, meeting_id):
            return {"total": 1, "pending": 1, "done": 0}

        async def get_by_id(self, todo_id):
            return make_todo(id=todo_id)

        async def update(self, todo_id, data):
            return make_todo(id=todo_id, status=data.status or "pending")

        async def delete(self, todo_id):
            self.deleted_id = todo_id

    monkeypatch.setattr(todos_endpoint, "TodoService", FakeTodoService)

    assert client.get("/api/v1/todos").json()["total"] == 1
    assert client.post("/api/v1/todos", json={"title": "One"}).json()["data"]["title"] == "One"
    assert len(client.post("/api/v1/todos/bulk", json=[{"title": "One"}, {"title": "Two"}]).json()["data"]) == 2
    assert client.get("/api/v1/todos/summary/stats").json()["data"]["pending"] == 1
    assert client.get("/api/v1/todos/40").json()["data"]["id"] == 40
    assert client.put("/api/v1/todos/40", json={"status": "done"}).json()["data"]["status"] == "done"
    assert client.delete("/api/v1/todos/40").json()["message"] == "删除成功"


def test_user_routes_cover_register_login_profile_and_list(admin_client, monkeypatch):
    from app.api.v1.endpoints import users as users_endpoint

    class FakeUserService:
        def __init__(self, db):
            pass

        async def create(self, data):
            return make_user(username=data.username, email=data.email)

        async def authenticate(self, username, password):
            return make_user(username=username)

        async def update(self, user_id, data):
            return make_user(id=user_id, full_name=data.full_name)

        async def list_users(self, page, page_size, keyword):
            return [make_user()], 1

    monkeypatch.setattr(users_endpoint, "UserService", FakeUserService)
    monkeypatch.setattr(users_endpoint, "create_access_token", lambda data: "token-for-test")

    registered = admin_client.post(
        "/api/v1/users/register",
        json={"username": "new", "email": "new@example.com", "password": "secret123"},
    ).json()
    assert registered["code"] == 201
    assert registered["data"]["username"] == "new"
    assert admin_client.post(
        "/api/v1/users/login",
        json={"username": "tester", "password": "secret123"},
    ).json()["data"]["access_token"] == "token-for-test"
    assert admin_client.get("/api/v1/users/me").json()["data"]["username"] == "tester"
    assert admin_client.put("/api/v1/users/me", json={"full_name": "Renamed"}).json()["data"]["full_name"] == "Renamed"
    assert admin_client.get("/api/v1/users").json()["total"] == 1


def test_rag_requires_auth_and_low_level_retrieval_routes_are_internal(client, authenticated_client):
    from app.api.v1.endpoints import rag

    fake_rag_service = SimpleNamespace(
        ask=AsyncMock(return_value={
            "schema_version": "rag.v1",
            "answer": "A",
            "chunks": [],
            "citations": [],
            "count": 0,
            "mode": "lightweight",
            "query_type": "standard",
            "original_query": "What?",
            "rewritten_query": ["What?"],
        })
    )
    app.dependency_overrides[rag.get_rag_service] = lambda: fake_rag_service

    app.dependency_overrides.pop(get_current_user, None)
    assert client.post("/api/v1/rag/ask", json={"question": "What?", "use_llm": False}).status_code == 401
    async def fake_current_user():
        return make_user()
    app.dependency_overrides[get_current_user] = fake_current_user
    response = authenticated_client.post("/api/v1/rag/ask", json={"question": "What?", "use_llm": False})
    assert response.status_code == 200
    assert response.json()["data"]["answer"] == "A"
    assert fake_rag_service.ask.await_args.kwargs["access_context"].user_id == 1
    assert client.post("/api/v1/vector-search/search", json={"content": "query"}).status_code == 404
    assert client.post("/api/v1/embedding/encode", json={"content": "hello"}).status_code == 404


def test_agent_query_returns_policy_and_pending_action(authenticated_client, monkeypatch):
    from app.api.v1.endpoints import agents as agents_endpoint

    class FakeAgentService:
        async def process_query_with_context(self, question, context, document_ids=None, event_callback=None):
            return AgentResult(
                success=True,
                task_type=TaskType.MULTI,
                workflow_type=WorkflowType.COMPLEX,
                answer="需要确认后执行",
                validation_errors=["confirmation_required: 高风险工具未获得人工确认"],
                policy_results=[
                    {
                        "tool_name": "send_notification",
                        "code": "confirmation_required",
                        "allowed": False,
                        "reason": "高风险工具未获得人工确认",
                        "source": "execute",
                        "risk_level": "high",
                        "workflow_type": "complex",
                        "confirmation_status": "not_required",
                        "retry_count": 0,
                    }
                ],
                risk_level=RiskLevel.HIGH,
                requires_confirmation=True,
                confirmation_status="required",
                pending_action={
                    "source": "tool",
                    "reason": "工具风险评估：send_notification:high",
                    "tool_calls": [{"tool_name": "send_notification", "arguments": {}}],
                },
            )

    async def fake_get_agent_service(*args, **kwargs):
        return FakeAgentService()

    monkeypatch.setattr(agents_endpoint, "get_agent_service", fake_get_agent_service)

    response = authenticated_client.post("/api/v1/agents/query", json={"question": "发送通知"}).json()

    assert response["policy_results"][0]["code"] == "confirmation_required"
    assert response["pending_action"]["source"] == "tool"
    assert response["requires_confirmation"] is True


def test_agent_confirmation_resume_endpoint(client, monkeypatch):
    from app.api.v1.endpoints import agents as agents_endpoint

    class FakeAgentService:
        async def resume_confirmation(self, request_id, response="approved"):
            return {
                "success": True,
                "mode": "snapshot",
                "message": "已从确认点恢复执行",
                "result": {
                    "answer": "已继续执行",
                    "confirmation_status": "approved",
                    "policy_results": [{"tool_name": "send_notification", "code": "allowed"}],
                },
            }

    async def fake_get_agent_service(*args, **kwargs):
        return FakeAgentService()

    monkeypatch.setattr(agents_endpoint, "get_agent_service", fake_get_agent_service)

    response = client.post(
        "/api/v1/agents/confirmations/resume",
        json={"request_id": "confirm_1", "response": "approved"},
    ).json()

    assert response["success"] is True
    assert response["mode"] == "snapshot"
    assert response["result"]["confirmation_status"] == "approved"
