"""服务端请求ID和HTTP日志关联契约。"""

import re
import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core import middleware
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    global_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.core.middleware import AccessLogMiddleware


@pytest.mark.asyncio
async def test_agent_capacity_is_shared_and_released_after_cancellation(monkeypatch):
    monkeypatch.setattr(middleware.settings, "AGENT_HTTP_MAX_IN_FLIGHT", 1)
    entered = asyncio.Event()

    async def streaming_app(scope, receive, send):
        entered.set()
        await asyncio.Future()

    gate = middleware.AgentConcurrencyMiddleware(streaming_app)
    receive = MagicMock()
    messages = []

    async def send(message):
        messages.append(message)

    scope = {"type": "http", "method": "POST"}
    running = asyncio.create_task(
        gate({**scope, "path": "/api/v1/agents/query-stream"}, receive, send)
    )
    await asyncio.wait_for(entered.wait(), timeout=1)
    try:
        await gate({**scope, "path": "/api/v1/agents/query"}, receive, send)
        assert messages[0]["status"] == 503
    finally:
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
    assert gate.in_flight == 0


def _probe_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(AccessLogMiddleware)

    @app.get("/probe")
    async def probe(request: Request):
        return {
            "request_id": middleware.current_request_id(),
            "correlation_id": middleware.current_correlation_id(),
            "state_request_id": request.state.request_id,
        }

    return app


def _exception_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(AccessLogMiddleware)
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)

    @app.get("/business")
    async def business_error():
        raise AppException("business failed", 409)

    @app.get("/http")
    async def http_error():
        raise HTTPException(status_code=429, detail="limited", headers={"Retry-After": "3"})

    @app.get("/validation")
    async def validation_error(value: int):
        return {"value": value}

    @app.get("/unhandled")
    async def unhandled_error():
        raise RuntimeError("boom")

    return app


def test_server_generates_unique_request_id_and_keeps_external_as_correlation():
    client = TestClient(_probe_app())

    first = client.get("/probe", headers={"X-Request-ID": "client-123"})
    second = client.get("/probe", headers={"X-Request-ID": "client-123"})
    client.close()

    first_id = first.headers["X-Request-ID"]
    assert re.fullmatch(r"[0-9a-f]{32}", first_id)
    assert first_id != second.headers["X-Request-ID"]
    assert first.json() == {
        "request_id": first_id,
        "correlation_id": "client-123",
        "state_request_id": first_id,
    }


def test_concurrent_requests_receive_distinct_server_request_ids():
    def invoke() -> str:
        client = TestClient(_probe_app())
        response = client.get("/probe", headers={"X-Request-ID": "shared-client-id"})
        client.close()
        return response.headers["X-Request-ID"]

    with ThreadPoolExecutor(max_workers=8) as executor:
        request_ids = list(executor.map(lambda _: invoke(), range(8)))

    assert len(set(request_ids)) == 8
    assert all(re.fullmatch(r"[0-9a-f]{32}", value) for value in request_ids)


@pytest.mark.parametrize("external_id", ["contains space", "x" * 65])
def test_invalid_external_request_id_is_not_used_as_correlation(external_id):
    client = TestClient(_probe_app())
    response = client.get("/probe", headers={"X-Request-ID": external_id})
    client.close()

    assert response.json()["correlation_id"] is None
    assert response.headers["X-Request-ID"] != external_id


def test_access_log_contains_the_same_server_request_id(monkeypatch):
    log = MagicMock()
    monkeypatch.setattr(middleware, "logger", log)
    client = TestClient(_probe_app())

    response = client.get("/probe")
    client.close()

    request_id = response.headers["X-Request-ID"]
    logged = " ".join(str(call) for call in log.info.call_args_list)
    assert request_id in logged


@pytest.mark.parametrize(
    ("path", "expected_status"),
    [
        ("/business", 409),
        ("/http", 429),
        ("/validation", 422),
        ("/unhandled", 500),
    ],
)
def test_all_error_responses_include_server_request_id(path, expected_status):
    client = TestClient(_exception_app(), raise_server_exceptions=False)
    response = client.get(path)
    client.close()

    assert response.status_code == expected_status
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])
    if path == "/http":
        assert response.headers["Retry-After"] == "3"
