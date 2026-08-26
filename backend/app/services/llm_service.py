"""LLM 服务封装"""
import asyncio
import time
from typing import List, Dict, Optional
from openai import AsyncOpenAI, RateLimitError
from httpx import Timeout
from app.core.config import settings
from app.core.logger import app_logger
from app.services.performance_metrics import get_performance_metrics

# LLM 限流重试配置
_LLM_MAX_RETRIES = 3
_LLM_RETRY_BASE_WAIT = 5  # 初始等待秒数，指数退避：5s, 10s, 20s


class LLMService:
    """LLM 服务类，封装 OpenAI 兼容接口"""

    def __init__(self):
        api_key = settings.LLM_API_KEY
        base_url = settings.LLM_API_BASE
        app_logger.info(f"[LLMService] Initializing with api_key length: {len(api_key) if api_key else 0}, base_url: {base_url}")

        if not api_key:
            app_logger.error("[LLMService] LLM_API_KEY is empty!")
            raise ValueError("LLM_API_KEY must be set")

        # 客户端延迟到首次真实调用时创建。这样 API 依赖注入和离线测试
        # 不会因为宿主机代理、网络后端等与请求无关的环境差异而失败。
        self.client: Optional[AsyncOpenAI] = None

    def _create_client(self, api_key: str, base_url: str) -> AsyncOpenAI:
        return AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=Timeout(
                connect=10,
                read=settings.LLM_TIMEOUT,
                write=10,
                pool=5,
            ),
            max_retries=0,  # 禁用自动重试，避免重试叠加超时；由本层指数退避接管
        )

    def _get_client(self) -> AsyncOpenAI:
        if self.client is None:
            self.client = self._create_client(settings.LLM_API_KEY, settings.LLM_API_BASE)
        return self.client

    async def chat(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
    ) -> str:
        """
        调用 LLM 对话接口

        Args:
            messages: 消息列表
            model: 模型名称（可选，默认使用配置）
            temperature: 温度（可选，默认使用配置）
            max_tokens: 最大 token 数（可选，默认使用配置）
            api_key: API密钥（可选，默认使用配置）
            api_base: API地址（可选，默认使用配置）

        Returns:
            LLM 生成的文本
        """
        # 如果传入了不同的api_key或api_base，创建一个临时的client
        if api_key or api_base:
            temp_client = self._create_client(
                api_key or settings.LLM_API_KEY,
                api_base or settings.LLM_API_BASE,
            )
            try:
                response = await temp_client.chat.completions.create(
                    model=model or settings.LLM_MODEL,
                    messages=messages,
                    temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
                    max_tokens=max_tokens if max_tokens is not None else settings.LLM_MAX_TOKENS,
                )
                return response.choices[0].message.content
            finally:
                await temp_client.close()

        # 主路径：指数退避重试，专门处理 Rate Limit（429）
        last_error = None
        for attempt in range(_LLM_MAX_RETRIES):
            try:
                llm_start_time = time.time()
                response = await self._get_client().chat.completions.create(
                    model=model or settings.LLM_MODEL,
                    messages=messages,
                    temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
                    max_tokens=max_tokens if max_tokens is not None else settings.LLM_MAX_TOKENS,
                )
                llm_latency_ms = (time.time() - llm_start_time) * 1000

                # 记录真实 Token 消耗
                usage = getattr(response, "usage", None)
                if usage:
                    get_performance_metrics().record_token_usage(
                        prompt_tokens=getattr(usage, "prompt_tokens", 0),
                        completion_tokens=getattr(usage, "completion_tokens", 0),
                        latency_ms=llm_latency_ms,
                        model=model or settings.LLM_MODEL,
                    )
                else:
                    get_performance_metrics().record_request(latency_ms=llm_latency_ms)

                return response.choices[0].message.content

            except RateLimitError as e:
                last_error = e
                if attempt == _LLM_MAX_RETRIES - 1:
                    app_logger.error(f"[LLMService] Rate limit exceeded after {_LLM_MAX_RETRIES} retries: {e}")
                    raise
                # 解析 Retry-After 头（如果有），否则用指数退避
                retry_after = None
                if hasattr(e, "response") and e.response is not None:
                    retry_after = e.response.headers.get("retry-after")
                wait = float(retry_after) if retry_after else _LLM_RETRY_BASE_WAIT * (2 ** attempt)
                app_logger.warning(
                    f"[LLMService] Rate limited (attempt {attempt + 1}/{_LLM_MAX_RETRIES}), "
                    f"waiting {wait:.1f}s before retry"
                )
                await asyncio.sleep(wait)

            except Exception as e:
                app_logger.error(f"[LLMService] LLM 调用失败: {e}")
                raise

        # 不应到达这里，保险起见
        raise last_error

    async def generate_answer(
        self,
        question: str,
        context: List[str],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
    ) -> str:
        """
        基于上下文生成回答（RAG 问答）

        Args:
            question: 用户问题
            context: 检索到的上下文片段
            model: 模型名称（可选）
            temperature: 温度（可选）
            api_key: API密钥（可选）
            api_base: API地址（可选）

        Returns:
            生成的回答
        """
        # 构建系统提示和用户消息
        system_prompt = """你是 MeetingMind 的智能助手，专门回答关于会议记录和文档库的问题。
如果参考信息中没有相关内容，请坦诚告知用户，不要编造信息。
回答要简洁明了，重点突出。"""

        # 构建上下文（限制总长度，避免超出API限制）
        max_context_chars = settings.LLM_MAX_CONTEXT_CHARS

        context_parts = []
        total_chars = 0
        for i, ctx in enumerate(context):
            ctx_with_header = f"[参考信息 {i+1}]:\n{ctx}"
            if total_chars + len(ctx_with_header) <= max_context_chars:
                context_parts.append(ctx_with_header)
                total_chars += len(ctx_with_header)
            else:
                # 如果剩余空间足够，放一部分
                remaining = max_context_chars - total_chars
                if remaining > 100:  # 至少还有100字符的空间
                    context_parts.append(ctx_with_header[:remaining])
                break

        context_text = "\n\n".join(context_parts)

        user_message = f"""用户问题：{question}

参考信息：
{context_text}

请基于以上参考信息回答用户的问题。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        return await self.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=api_key,
            api_base=api_base,
        )

    async def generate_text(self, prompt: str, **kwargs) -> str:
        """
        生成文本（单轮，无上下文）

        Args:
            prompt: 提示文本
            **kwargs: 额外参数传递给 chat()

        Returns:
            生成的文本
        """
        messages = [{"role": "user", "content": prompt}]
        return await self.chat(messages=messages, **kwargs)

    async def _call(self, prompt: str, **kwargs) -> str:
        """
        简单的文本调用接口（兼容旧版调用方式）

        Args:
            prompt: 提示文本
            **kwargs: 额外参数

        Returns:
            生成的文本
        """
        messages = [
            {"role": "user", "content": prompt}
        ]
        return await self.chat(messages=messages, **kwargs)
