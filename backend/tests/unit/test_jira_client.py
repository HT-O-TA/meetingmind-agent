import json

import httpx
import pytest

from app.agents.tools.enterprise_tools import (
    JiraAPIError,
    JiraClient,
    JiraConfigurationError,
)


def _client(handler, **kwargs):
    transport = httpx.MockTransport(handler)
    return JiraClient(
        base_url="https://example.atlassian.net",
        username="learner@example.com",
        api_token="test-token",
        transport=transport,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_create_issue_uses_v3_adf_and_never_fabricates_result():
    captured = {}

    def handler(request: httpx.Request):
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["payload"] = json.loads(request.content)
        captured["authorization"] = request.headers.get("Authorization")
        return httpx.Response(
            201,
            json={"id": "10001", "key": "MM-7", "self": "https://example/10001"},
        )

    client = _client(handler)
    result = await client.create_issue(
        "MM", "Task", "整理会议待办", "从会议纪要创建", "account-123"
    )

    assert captured["method"] == "POST"
    assert captured["path"] == "/rest/api/3/issue"
    assert captured["authorization"].startswith("Basic ")
    fields = captured["payload"]["fields"]
    assert fields["project"] == {"key": "MM"}
    assert fields["description"]["type"] == "doc"
    assert fields["assignee"] == {"accountId": "account-123"}
    assert result["issue_key"] == "MM-7"
    assert result["external_id"] == "MM-7"
    await client.aclose()


@pytest.mark.asyncio
async def test_missing_configuration_fails_closed():
    client = JiraClient(base_url="", username="", api_token="")
    with pytest.raises(JiraConfigurationError, match="配置缺失"):
        await client.get_issue("MM-1")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "category"),
    [(401, "authentication"), (403, "permission"), (404, "not_found")],
)
async def test_api_errors_have_stable_category(status, category):
    client = _client(lambda request: httpx.Response(status, json={"errorMessages": ["no"]}))
    with pytest.raises(JiraAPIError) as exc_info:
        await client.get_issue("MM-1")
    assert exc_info.value.category == category
    assert exc_info.value.status_code == status
    await client.aclose()


@pytest.mark.asyncio
async def test_idempotent_get_retries_429_with_retry_after():
    calls = 0
    delays = []

    def handler(request: httpx.Request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "2"}, json={})
        return httpx.Response(200, json={"id": "1", "key": "MM-1", "fields": {}})

    async def fake_sleep(delay):
        delays.append(delay)

    client = _client(handler, sleep=fake_sleep, max_retries=1)
    result = await client.get_issue("MM-1")
    assert result["issue_key"] == "MM-1"
    assert calls == 2
    assert delays == [2.0]
    await client.aclose()


@pytest.mark.asyncio
async def test_non_idempotent_create_does_not_retry_timeout():
    calls = 0

    def handler(request: httpx.Request):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("unknown upstream outcome", request=request)

    client = _client(handler, max_retries=3)
    with pytest.raises(JiraAPIError) as exc_info:
        await client.create_issue("MM", "Task", "do once")
    assert exc_info.value.category == "timeout"
    assert calls == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_issue_key_path_injection_is_rejected_before_http():
    calls = 0

    def handler(request: httpx.Request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client = _client(handler)
    with pytest.raises(JiraAPIError) as exc_info:
        await client.get_issue("MM-1/../../users")
    assert exc_info.value.category == "invalid_request"
    assert calls == 0
    await client.aclose()
