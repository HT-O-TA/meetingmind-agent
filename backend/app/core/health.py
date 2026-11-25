"""轻量依赖就绪检查；响应不暴露异常或连接信息。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import text
from redis.asyncio import Redis

from app.core.cache_init import get_redis
from app.core.config import settings
from app.core.logger import app_logger
from app.core.rabbitmq import rabbitmq_manager
from app.db.database import engine


async def probe_postgres() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def probe_redis() -> None:
    client = get_redis()
    if client is None:
        async with Redis.from_url(settings.REDIS_URL) as probe_client:
            available = await probe_client.ping()
    else:
        available = await client.ping()
    if not available:
        raise RuntimeError("redis_unavailable")


async def probe_rabbitmq() -> None:
    connection = await rabbitmq_manager.connect()
    if connection.is_closed:
        raise RuntimeError("rabbitmq_unavailable")


async def _run_probe(
    name: str,
    probe: Callable[[], Awaitable[None]],
    *,
    critical: bool,
    timeout_seconds: float,
) -> tuple[str, dict[str, Any]]:
    started = time.perf_counter()
    try:
        await asyncio.wait_for(probe(), timeout=timeout_seconds)
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        status = "error" if critical else "degraded"
        app_logger.warning(
            f"[HEALTH] dependency={name} status={status} "
            f"error_type={exc.__class__.__name__}"
        )
        return name, {"status": status, "latency_ms": latency_ms}
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    return name, {"status": "ok", "latency_ms": latency_ms}


async def build_readiness_report(
    timeout_seconds: float | None = None,
) -> tuple[bool, dict[str, object]]:
    timeout = float(timeout_seconds or settings.HEALTH_CHECK_TIMEOUT_SECONDS)
    results = await asyncio.gather(
        _run_probe("postgres", probe_postgres, critical=True, timeout_seconds=timeout),
        _run_probe("redis", probe_redis, critical=True, timeout_seconds=timeout),
        _run_probe("rabbitmq", probe_rabbitmq, critical=False, timeout_seconds=timeout),
    )
    checks = dict(results)
    ready = all(checks[name]["status"] == "ok" for name in ("postgres", "redis"))
    if not ready:
        status = "error"
    elif checks["rabbitmq"]["status"] != "ok":
        status = "degraded"
    else:
        status = "ok"
    return ready, {"status": status, "checks": checks}


__all__ = [
    "build_readiness_report",
    "probe_postgres",
    "probe_rabbitmq",
    "probe_redis",
]
