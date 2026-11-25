"""Redis 限流的原子计数和 HTTP 门禁契约。"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core import cache_init
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.dependencies import get_llm_service, get_vector_search_service
from app.db.database import get_db
from app.main import app
from app.api.v1.endpoints.rag import get_rag_service
from app.services.user_service import UserService


class ScriptedRedis:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def eval(self, script, key_count, key, window):
        self.calls.append((script, key_count, key, window))
        return self.result


@pytest.mark.asyncio
async def test_rate_limit_atomically_returns_count_limit_and_retry_after(monkeypatch):
    redis = ScriptedRedis([3, 41])
    monkeypatch.setattr(cache_init, "_redis", redis)

    decision = await cache_init.rate_limit("rate_limit:rag:user", limit=5, window=60)

    assert decision == (True, 3, 5, 41)
    assert redis.calls[0][1:] == (1, "rate_limit:rag:user", 60)


@pytest.fixture
def limited_client(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    async def fake_db():
        yield SimpleNamespace()

    async def fake_user():
        return SimpleNamespace(id=7, username="limited-user")

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_current_user] = fake_user
    app.dependency_overrides[get_llm_service] = lambda: SimpleNamespace()
    app.dependency_overrides[get_vector_search_service] = lambda: SimpleNamespace()
    client = TestClient(app)
    yield client
    client.close()
    app.dependency_overrides.clear()


def test_login_rate_limit_returns_429_with_retry_after(limited_client, monkeypatch):
    monkeypatch.setattr(
        cache_init,
        "rate_limit",
        AsyncMock(return_value=(False, 6, 5, 120)),
    )
    monkeypatch.setattr(
        UserService,
        "authenticate",
        AsyncMock(return_value=SimpleNamespace(
            id=7,
            username="limited-user",
            email="limited@example.com",
            full_name=None,
            department=None,
            role="user",
            is_active=True,
            permissions=None,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )),
    )

    response = limited_client.post(
        "/api/v1/users/login",
        json={"username": "limited-user", "password": "password123"},
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "120"
    assert response.headers["X-RateLimit-Limit"] == "5"


def test_rag_rate_limit_blocks_before_expensive_service(limited_client, monkeypatch):
    rag_service = SimpleNamespace(ask=AsyncMock(return_value={
        "answer": "should not run",
        "mode": "extractive",
        "original_query": "项目进度是什么？",
    }))
    app.dependency_overrides[get_rag_service] = lambda: rag_service
    monkeypatch.setattr(
        cache_init,
        "rate_limit",
        AsyncMock(return_value=(False, 21, 20, 17)),
    )

    response = limited_client.post(
        "/api/v1/rag/ask",
        json={"question": "项目进度是什么？", "use_llm": False},
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "17"
    rag_service.ask.assert_not_awaited()


def test_rag_rate_limit_fails_closed_when_redis_is_unavailable(
    limited_client, monkeypatch
):
    rag_service = SimpleNamespace(ask=AsyncMock(return_value={
        "answer": "should not run",
        "mode": "extractive",
        "original_query": "项目进度是什么？",
    }))
    app.dependency_overrides[get_rag_service] = lambda: rag_service
    monkeypatch.setattr(
        cache_init,
        "rate_limit",
        AsyncMock(side_effect=RuntimeError("redis unavailable")),
    )

    response = limited_client.post(
        "/api/v1/rag/ask",
        json={"question": "项目进度是什么？", "use_llm": False},
    )

    assert response.status_code == 503
    rag_service.ask.assert_not_awaited()


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/v1/agents/query", {"question": "总结会议"}),
        ("/api/v1/agents/query-stream", {"question": "总结会议"}),
        ("/api/v1/agents/batch", {"questions": ["总结会议"]}),
    ],
)
@pytest.mark.parametrize("expected_status", [401, 429])
def test_agent_cost_endpoints_reject_before_initializing_services(
    limited_client, monkeypatch, path, payload, expected_status
):
    if expected_status == 401:
        app.dependency_overrides.pop(get_current_user)
    expensive = AsyncMock()

    async def expensive_dependency():
        return await expensive()

    app.dependency_overrides[get_vector_search_service] = expensive_dependency
    app.dependency_overrides[get_llm_service] = expensive_dependency
    monkeypatch.setattr(
        cache_init,
        "rate_limit",
        AsyncMock(return_value=(False, 11, 10, 23)),
    )

    response = limited_client.post(path, json=payload)

    assert response.status_code == expected_status
    expensive.assert_not_awaited()


def test_task_creation_is_rate_limited_before_queue_or_database_work(
    limited_client, monkeypatch
):
    monkeypatch.setattr(
        cache_init,
        "rate_limit",
        AsyncMock(return_value=(False, 11, 10, 23)),
    )

    response = limited_client.post(
        "/api/v1/tasks/documents",
        json={"document_id": 123},
    )

    assert response.status_code == 429


@pytest.mark.parametrize(
    ("method", "path", "request_kwargs"),
    [
        (
            "post",
            "/api/v1/documents/batch-upload",
            {"files": {"files": ("meeting.txt", b"hello", "text/plain")}},
        ),
        ("post", "/api/v1/tasks/missing/retry-publish", {}),
        ("get", "/api/v1/tasks/missing/wait?timeout=1", {}),
    ],
)
def test_uncovered_expensive_endpoints_are_rate_limited_before_work(
    limited_client, monkeypatch, method, path, request_kwargs
):
    limiter = AsyncMock(return_value=(False, 6, 5, 19))
    monkeypatch.setattr(cache_init, "rate_limit", limiter)

    response = getattr(limited_client, method)(path, **request_kwargs)

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "19"
    limiter.assert_awaited_once()
