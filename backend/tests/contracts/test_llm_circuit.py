import asyncio

import httpx
import pytest
from openai import APIConnectionError, InternalServerError

from app.services.llm_circuit import LLMCircuitBreaker, LLMCircuitOpen


@pytest.mark.asyncio
async def test_open_blocks_calls_and_half_open_allows_only_one_probe():
    now = [0.0]
    breaker = LLMCircuitBreaker(clock=lambda: now[0])
    request = httpx.Request("POST", "https://fixture.invalid")
    calls = 0

    async def fail():
        nonlocal calls
        calls += 1
        if calls % 2:
            raise APIConnectionError(request=request)
        raise InternalServerError("fixture", response=httpx.Response(503, request=request), body=None)

    for _ in range(3):
        with pytest.raises((APIConnectionError, InternalServerError)):
            await breaker.call(fail)
    assert breaker.state == "open"
    with pytest.raises(LLMCircuitOpen):
        await breaker.call(fail)
    assert calls == 3

    now[0] = 30
    entered = asyncio.Event()
    release = asyncio.Event()

    async def recover():
        entered.set()
        await release.wait()
        return "healthy"

    probe = asyncio.create_task(breaker.call(recover))
    await entered.wait()
    assert breaker.state == "half-open"
    with pytest.raises(LLMCircuitOpen):
        await breaker.call(fail)
    release.set()
    assert await probe == "healthy"
    assert breaker.state == "closed"
    assert calls == 3


@pytest.mark.asyncio
async def test_failed_or_cancelled_probe_reopens_circuit():
    now = [0.0]
    breaker = LLMCircuitBreaker(threshold=1, cooldown=5, clock=lambda: now[0])
    request = httpx.Request("POST", "https://fixture.invalid")

    async def fail():
        raise APIConnectionError(request=request)

    for current in (0, 5):
        now[0] = current
        with pytest.raises(APIConnectionError):
            await breaker.call(fail)
        assert breaker.state == "open"

    now[0] = 10
    entered = asyncio.Event()

    async def block():
        entered.set()
        await asyncio.Event().wait()

    probe = asyncio.create_task(breaker.call(block))
    await entered.wait()
    probe.cancel()
    with pytest.raises(asyncio.CancelledError):
        await probe
    assert breaker.state == "open"
    assert breaker.open_until == 15
