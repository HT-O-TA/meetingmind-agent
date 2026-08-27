"""LLM 服务封装"""
import asyncio
import uuid
from typing import Any, Dict, List, Mapping, Optional
from openai import AsyncOpenAI, RateLimitError
from httpx import Timeout
from app.core.config import settings
from app.core.logger import app_logger
from app.services.token_budget_ledger import (
    TokenBudgetExceeded,
    TokenBudgetLedger,
    get_active_token_budget_ledger,
    get_active_token_budget_node,
)

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
            app_logger.info("[LLMService] LLM_API_KEY 未配置；仅真实生成调用不可用")

        # 客户端延迟到首次真实调用时创建。这样 API 依赖注入和离线测试
        # 不会因为宿主机代理、网络后端等与请求无关的环境差异而失败。
        self.client: Optional[AsyncOpenAI] = None
        self.last_budget_snapshot: Optional[Dict[str, Any]] = None
        self.last_budget_decision: Optional[Dict[str, Any]] = None

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
            if not settings.LLM_API_KEY:
                raise ValueError("LLM_API_KEY must be set for model generation")
            self.client = self._create_client(settings.LLM_API_KEY, settings.LLM_API_BASE)
        return self.client

    @staticmethod
    def _usage_tokens(response: Any) -> tuple[Optional[int], Optional[int]]:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None, None
        if isinstance(usage, Mapping):
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
        else:
            prompt_tokens = getattr(usage, "prompt_tokens", None)
            completion_tokens = getattr(usage, "completion_tokens", None)
        if prompt_tokens is None or completion_tokens is None:
            return None, None
        return int(prompt_tokens), int(completion_tokens)

    def _complete_budget(
        self,
        ledger: TokenBudgetLedger,
        decision_id: str,
        response: Any,
    ) -> None:
        actual_input, actual_output = self._usage_tokens(response)
        self.last_budget_decision = ledger.complete(
            decision_id,
            actual_input_tokens=actual_input,
            actual_output_tokens=actual_output,
        )
        self.last_budget_snapshot = ledger.snapshot()

    def _fail_budget(
        self,
        ledger: TokenBudgetLedger,
        decision_id: str,
        error: BaseException,
    ) -> None:
        self.last_budget_decision = ledger.fail(decision_id, error)
        self.last_budget_snapshot = ledger.snapshot()

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
        selected_model = model or settings.LLM_MODEL
        selected_max_tokens = max_tokens if max_tokens is not None else settings.LLM_MAX_TOKENS
        ledger = get_active_token_budget_ledger() or TokenBudgetLedger.from_settings(
            f"standalone_{uuid.uuid4().hex}"
        )
        try:
            decision = ledger.reserve(
                messages=messages,
                model=selected_model,
                requested_output_tokens=selected_max_tokens,
                node=get_active_token_budget_node(),
            )
        except TokenBudgetExceeded:
            self.last_budget_snapshot = ledger.snapshot()
            self.last_budget_decision = self.last_budget_snapshot["decisions"][-1]
            raise
        decision_id = str(decision["decision_id"])
        self.last_budget_decision = decision
        self.last_budget_snapshot = ledger.snapshot()

        # 如果传入了不同的api_key或api_base，创建一个临时的client
        if api_key or api_base:
            selected_api_key = api_key or settings.LLM_API_KEY
            if not selected_api_key:
                error = ValueError("LLM_API_KEY must be set for model generation")
                self._fail_budget(ledger, decision_id, error)
                raise error
            try:
                temp_client = self._create_client(
                    selected_api_key,
                    api_base or settings.LLM_API_BASE,
                )
            except Exception as error:
                self._fail_budget(ledger, decision_id, error)
                raise
            try:
                response = await temp_client.chat.completions.create(
                    model=selected_model,
                    messages=messages,
                    temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
                    max_tokens=selected_max_tokens,
                )
                self._complete_budget(ledger, decision_id, response)
                return response.choices[0].message.content
            except asyncio.CancelledError as error:
                self._fail_budget(ledger, decision_id, error)
                raise
            except Exception as error:
                self._fail_budget(ledger, decision_id, error)
                raise
            finally:
                await temp_client.close()

        # 主路径：指数退避重试，专门处理 Rate Limit（429）
        last_error = None
        for attempt in range(_LLM_MAX_RETRIES):
            try:
                response = await self._get_client().chat.completions.create(
                    model=selected_model,
                    messages=messages,
                    temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
                    max_tokens=selected_max_tokens,
                )
                self._complete_budget(ledger, decision_id, response)
                return response.choices[0].message.content

            except asyncio.CancelledError as e:
                self._fail_budget(ledger, decision_id, e)
                raise
            except RateLimitError as e:
                last_error = e
                if attempt == _LLM_MAX_RETRIES - 1:
                    app_logger.error(f"[LLMService] Rate limit exceeded after {_LLM_MAX_RETRIES} retries: {e}")
                    self._fail_budget(ledger, decision_id, e)
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
                try:
                    await asyncio.sleep(wait)
                except asyncio.CancelledError as cancel_error:
                    self._fail_budget(ledger, decision_id, cancel_error)
                    raise

            except Exception as e:
                app_logger.error(f"[LLMService] LLM 调用失败: {e}")
                self._fail_budget(ledger, decision_id, e)
                raise

        # 不应到达这里，保险起见
        error = last_error or RuntimeError("LLM 调用未返回结果")
        self._fail_budget(ledger, decision_id, error)
        raise error

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
