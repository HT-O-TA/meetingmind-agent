"""Liveness、Readiness和兼容健康接口契约。"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core import health
from app.core.config import Settings
from app import main


@pytest.mark.asyncio
async def test_redis_readiness_uses_only_ping(monkeypatch):
    class PingOnlyClient:
        ping = AsyncMock(return_value=True)

    client = PingOnlyClient()
    monkeypatch.setattr(health, "get_redis", lambda: client)
    await health.probe_redis()
    client.ping.assert_awaited_once()


def test_cross_origin_unhandled_failure_exposes_request_id(monkeypatch):
    monkeypatch.setattr(main, "build_readiness_report", AsyncMock(side_effect=RuntimeError))
    origin = main.settings.cors_origins_list[0]
    client = TestClient(main.app, raise_server_exceptions=False)
    response = client.get("/ready", headers={"Origin": origin})
    client.close()
    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == origin
    assert "x-request-id" in response.headers["access-control-expose-headers"].lower()
    assert response.headers["x-request-id"]


@pytest.mark.asyncio
async def test_readiness_is_ok_when_all_dependencies_are_available(monkeypatch):
    monkeypatch.setattr(health, "probe_postgres", AsyncMock(return_value=None))
    monkeypatch.setattr(health, "probe_redis", AsyncMock(return_value=None))
    monkeypatch.setattr(health, "probe_rabbitmq", AsyncMock(return_value=None))

    ready, report = await health.build_readiness_report(timeout_seconds=0.1)

    assert ready is True
    assert report["status"] == "ok"
    assert {name: item["status"] for name, item in report["checks"].items()} == {
        "postgres": "ok",
        "redis": "ok",
        "rabbitmq": "ok",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("critical_probe", ["probe_postgres", "probe_redis"])
async def test_readiness_fails_when_a_critical_dependency_fails(monkeypatch, critical_probe):
    monkeypatch.setattr(health, "probe_postgres", AsyncMock(return_value=None))
    monkeypatch.setattr(health, "probe_redis", AsyncMock(return_value=None))
    monkeypatch.setattr(health, "probe_rabbitmq", AsyncMock(return_value=None))
    monkeypatch.setattr(
        health,
        critical_probe,
        AsyncMock(side_effect=RuntimeError("postgresql://user:secret@private-host/db")),
    )

    ready, report = await health.build_readiness_report(timeout_seconds=0.1)

    assert ready is False
    assert report["status"] == "error"
    assert "secret" not in str(report)
    assert "private-host" not in str(report)


@pytest.mark.asyncio
async def test_readiness_marks_rabbitmq_failure_degraded_without_failing(monkeypatch):
    monkeypatch.setattr(health, "probe_postgres", AsyncMock(return_value=None))
    monkeypatch.setattr(health, "probe_redis", AsyncMock(return_value=None))
    monkeypatch.setattr(
        health,
        "probe_rabbitmq",
        AsyncMock(side_effect=RuntimeError("broker secret detail")),
    )

    ready, report = await health.build_readiness_report(timeout_seconds=0.1)

    assert ready is True
    assert report["status"] == "degraded"
    assert report["checks"]["rabbitmq"]["status"] == "degraded"
    assert "broker secret detail" not in str(report)


@pytest.mark.asyncio
async def test_dependency_timeout_is_reported_without_leaking_details(monkeypatch):
    async def slow_probe():
        import asyncio
        await asyncio.sleep(0.1)

    monkeypatch.setattr(health, "probe_postgres", slow_probe)
    monkeypatch.setattr(health, "probe_redis", AsyncMock(return_value=None))
    monkeypatch.setattr(health, "probe_rabbitmq", AsyncMock(return_value=None))

    ready, report = await health.build_readiness_report(timeout_seconds=0.001)

    assert ready is False
    assert report["checks"]["postgres"]["status"] == "error"
    assert set(report["checks"]["postgres"]) == {"status", "latency_ms"}


@pytest.mark.asyncio
async def test_failed_probe_log_is_readable_without_leaking_exception_details(monkeypatch):
    log = MagicMock()
    monkeypatch.setattr(health, "app_logger", log)
    monkeypatch.setattr(
        health,
        "probe_postgres",
        AsyncMock(side_effect=RuntimeError("postgresql://user:secret@private-host/db")),
    )
    monkeypatch.setattr(health, "probe_redis", AsyncMock(return_value=None))
    monkeypatch.setattr(health, "probe_rabbitmq", AsyncMock(return_value=None))

    await health.build_readiness_report(timeout_seconds=0.1)

    message = log.warning.call_args.args[0]
    assert "dependency=postgres" in message
    assert "status=error" in message
    assert "error_type=RuntimeError" in message
    assert "secret" not in message


@pytest.mark.parametrize("value", [0, -1, 31])
def test_health_timeout_configuration_rejects_unsafe_values(value):
    with pytest.raises(ValidationError):
        Settings(HEALTH_CHECK_TIMEOUT_SECONDS=value, _env_file=None)


def test_live_does_not_run_dependency_checks(monkeypatch):
    check = AsyncMock()
    monkeypatch.setattr(main, "build_readiness_report", check)

    client = TestClient(main.app, raise_server_exceptions=False)
    response = client.get("/live")
    client.close()

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    check.assert_not_awaited()


def test_ready_returns_503_when_critical_dependency_fails(monkeypatch):
    monkeypatch.setattr(
        main,
        "build_readiness_report",
        AsyncMock(return_value=(False, {"status": "error", "checks": {}})),
    )

    client = TestClient(main.app, raise_server_exceptions=False)
    response = client.get("/ready")
    client.close()

    assert response.status_code == 503
    assert response.json()["status"] == "error"


def test_health_is_a_compatibility_alias_for_readiness(monkeypatch):
    result = (True, {"status": "degraded", "checks": {}})
    monkeypatch.setattr(main, "build_readiness_report", AsyncMock(return_value=result))
    client = TestClient(main.app, raise_server_exceptions=False)

    ready = client.get("/ready")
    compatibility = client.get("/health")
    client.close()

    assert ready.status_code == compatibility.status_code == 200
    assert compatibility.json()["compatibility_alias"] == "/ready"
    assert ready.json()["checks"] == compatibility.json()["checks"]
