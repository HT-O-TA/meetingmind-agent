"""Verify cancellation and admission over real loopback HTTP with a synthetic Agent."""

import time
import uuid

import httpx

from bench_local_business import BOOTSTRAP, SETTINGS
from demo_http_business_flow import register_and_login
from run_local_acceptance import local_stack


def main():
    body = """callback = kwargs.get("event_callback")
    try:
        if callback:
            await callback("progress", {"phase": "started"})
        await asyncio.sleep(30)
    finally:
        counters["finished"] += 1"""
    bootstrap = BOOTSTRAP.replace("await asyncio.sleep(0.25)", body).replace(
        'uvicorn.run("app.main:app"',
        'from app.main import app\ncounters = {"finished": 0}\n'
        '@app.get("/_smoke_state")\nasync def smoke_state(): return counters\n'
        'uvicorn.run("app.main:app"',
    )
    with local_stack({**SETTINGS, "AGENT_HTTP_MAX_IN_FLIGHT": "1"}, bootstrap) as base:
        with httpx.Client(base_url=base, timeout=5, trust_env=False) as client:
            user = "disconnect_" + uuid.uuid4().hex[:8]
            bearer = register_and_login(client, user, user + "@example.com", "Smoke")
            client.headers["Authorization"] = "Bearer " + bearer
            path = "/api/v1/agents/query-stream"
            payload = {"question": "disconnect smoke"}
            with client.stream("POST", path, json=payload) as response:
                response.raise_for_status()
                # Retain the iterator so the socket stays open while testing a second request.
                lines = response.iter_lines()
                assert '"progress"' in next(lines)
                with client.stream("POST", path, json=payload) as blocked:
                    assert blocked.status_code == 503, blocked.status_code
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                if client.get("/_smoke_state").json()["finished"]:
                    break
                time.sleep(.05)
            else:
                raise AssertionError("disconnected Agent task did not exit")
            with client.stream("POST", path, json=payload) as response:
                assert response.status_code == 200
                assert '"progress"' in next(response.iter_lines())
            print("SSE 200, concurrent 503, disconnected task exited, next SSE 200")


if __name__ == "__main__":
    main()
