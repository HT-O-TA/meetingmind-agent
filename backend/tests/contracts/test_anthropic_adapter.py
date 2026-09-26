"""Anthropic 适配器：请求转换与响应归一化（不发网络请求）。"""
import httpx
import pytest

from app.services.anthropic_adapter import AnthropicCompatClient, _split_system


def test_system_and_consecutive_roles_are_normalized():
    system, turns = _split_system([
        {"role": "system", "content": "规则"},
        {"role": "user", "content": "a"},
        {"role": "user", "content": "b"},
    ])
    assert system == "规则"
    assert turns == [{"role": "user", "content": "a\n\nb"}]


@pytest.mark.asyncio
async def test_response_is_wrapped_in_openai_shape_and_key_stays_in_header():
    seen = {}

    def handler(request: httpx.Request):
        seen["path"] = request.url.path
        seen["key"] = request.headers.get("x-api-key")
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={
            "content": [{"type": "text", "text": "2"}], "stop_reason": "end_turn",
            "usage": {"input_tokens": 11, "output_tokens": 1}})

    client = AnthropicCompatClient(api_key="k-test", base_url="http://proxy/v1", timeout=httpx.Timeout(5))
    client.http = httpx.AsyncClient(base_url="http://proxy", transport=httpx.MockTransport(handler),
                                    headers=client.http.headers)
    resp = await client.chat.completions.create(model="m", messages=[{"role": "user", "content": "1+1"}], max_tokens=8)
    await client.close()

    assert resp.choices[0].message.content == "2"
    assert (resp.usage.prompt_tokens, resp.usage.completion_tokens) == (11, 1)
    assert seen["path"] == "/v1/messages" and seen["key"] == "k-test"
    assert "k-test" not in seen["body"]
