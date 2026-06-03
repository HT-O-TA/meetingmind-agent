"""LLM 服务封装"""
from typing import List, Dict, Optional
from openai import AsyncOpenAI
from httpx import Timeout
from app.core.config import settings
from app.core.logger import app_logger


class LLMService:
    """LLM 服务类，封装 OpenAI 兼容接口"""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_API_BASE,
            timeout=Timeout(
                connect=10,
                read=settings.LLM_TIMEOUT,
                write=10,
                pool=5,
            ),
            max_retries=0,  # 禁用自动重试，避免重试叠加超时
        )

    async def chat(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        调用 LLM 对话接口

        Args:
            messages: 消息列表
            model: 模型名称（可选，默认使用配置）
            temperature: 温度（可选，默认使用配置）
            max_tokens: 最大 token 数（可选，默认使用配置）

        Returns:
            LLM 生成的文本
        """
        try:
            response = await self.client.chat.completions.create(
                model=model or settings.LLM_MODEL,
                messages=messages,
                temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
                max_tokens=max_tokens if max_tokens is not None else settings.LLM_MAX_TOKENS,
            )
            return response.choices[0].message.content
        except Exception as e:
            app_logger.error(f"LLM 调用失败: {e}")
            raise

    async def generate_answer(
        self,
        question: str,
        context: List[str],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        基于上下文生成回答（RAG 问答）

        Args:
            question: 用户问题
            context: 检索到的上下文片段
            model: 模型名称（可选）
            temperature: 温度（可选）

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
        )

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
