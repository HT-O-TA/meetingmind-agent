"""Anthropic Messages API 适配器，外形模仿 OpenAI SDK 的 chat.completions.create。

LLMService 的预算、重试与测试替身都依赖 OpenAI 客户端形状（response.choices[0].message.content、
response.usage.prompt_tokens）。本适配器把 OpenAI 风格的 messages 转成 Anthropic 请求，再把响应
包装回同样的形状，调用方无需改动。密钥只放在请求头，不写日志。
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import httpx
from openai import RateLimitError

ANTHROPIC_VERSION = "2023-06-01"


def _split_system(messages: List[Dict[str, Any]]):
    """OpenAI 的 system 消息 → Anthropic 顶层 system；连续同角色消息合并。"""
    system_parts, turns = [], []
    for message in messages:
        role, content = message.get("role"), str(message.get("content") or "")
        if role == "system":
            system_parts.append(content)
            continue
        role = "assistant" if role == "assistant" else "user"
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"] += "\n\n" + content
        else:
            turns.append({"role": role, "content": content})
    if not turns or turns[0]["role"] != "user":
        turns.insert(0, {"role": "user", "content": "请继续。"})
    return "\n\n".join(system_parts), turns


class _Completions:
    def __init__(self, client: "AnthropicCompatClient"):
        self._client = client

    async def create(self, *, model: str, messages: List[Dict[str, Any]], temperature: Optional[float] = None,
                     max_tokens: Optional[int] = None, **_: Any):
        system, turns = _split_system(messages)
        body: Dict[str, Any] = {"model": model, "max_tokens": int(max_tokens or 1024), "messages": turns}
        if system:
            body["system"] = system
        if temperature is not None:
            body["temperature"] = max(0.0, min(1.0, float(temperature)))
        response = await self._client.http.post("/v1/messages", json=body)
        if response.status_code == 429:
            raise RateLimitError("rate limited", response=response, body=None)
        if response.status_code >= 400:
            raise RuntimeError(f"Anthropic API HTTP {response.status_code}: {response.text[:300]}")
        data = response.json()
        text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
        usage = data.get("usage") or {}
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason=data.get("stop_reason"))],
            usage=SimpleNamespace(prompt_tokens=usage.get("input_tokens"), completion_tokens=usage.get("output_tokens")),
            model=data.get("model", model),
        )


class AnthropicCompatClient:
    """最小的 OpenAI 形状客户端：只实现 chat.completions.create 与 close。"""

    def __init__(self, *, api_key: str, base_url: str, timeout: httpx.Timeout):
        root = base_url.rstrip("/")
        if root.endswith("/v1"):
            root = root[:-3]
        self.http = httpx.AsyncClient(
            base_url=root,
            timeout=timeout,
            headers={"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"},
        )
        self.chat = SimpleNamespace(completions=_Completions(self))

    async def close(self) -> None:
        await self.http.aclose()
