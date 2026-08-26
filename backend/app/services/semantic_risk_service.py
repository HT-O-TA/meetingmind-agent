"""语义风险感知服务 - 基于 LLM 的深度风险判断

功能：
1. 关键词未命中时，调用 LLM 做语义理解
2. 支持快速模式（小模型）和深度模式（大模型）
3. 结果缓存，避免重复调用
"""
import json
import time
import hashlib
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass
from app.core.logger import app_logger


SEMANTIC_RISK_PROMPT = """你是一个安全风险评估助手。请分析以下用户问题的意图，判断是否包含高风险操作。

用户问题：{question}

请从以下维度分析：
1. 是否意图删除/销毁数据（如删除、清空、移除等）
2. 是否意图创建/修改数据（如创建、更新、修改等）
3. 是否意图导出/分享数据（如导出、下载、分享等）
4. 是否包含越权或危险操作

请输出 JSON 格式：
{{
    "risk_level": "LOW|MEDIUM|HIGH|CRITICAL",
    "is_destructive": true/false,
    "is_write": true/false,
    "is_export": true/false,
    "confidence": 0.0-1.0,
    "reason": "简短理由",
    "suggested_action": "allow|warn|block"
}}"""


@dataclass
class SemanticRiskResult:
    risk_level: str = "LOW"
    confidence: float = 0.0
    is_destructive: bool = False
    is_write: bool = False
    is_export: bool = False
    reason: str = ""
    suggested_action: str = "allow"

    @property
    def requires_confirmation(self) -> bool:
        return self.risk_level in ("HIGH", "CRITICAL")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_level": self.risk_level,
            "confidence": self.confidence,
            "is_destructive": self.is_destructive,
            "is_write": self.is_write,
            "is_export": self.is_export,
            "reason": self.reason,
            "suggested_action": self.suggested_action,
        }


class SemanticRiskService:
    """语义风险感知服务"""

    def __init__(self, model: str = "gpt-4o-mini", timeout_ms: int = 3000):
        self._model = model
        self._timeout_ms = timeout_ms
        self._cache: Dict[str, SemanticRiskResult] = {}
        self._cache_max_size: int = 1000
        self._cache_ttl: float = 300  # 5 分钟

    async def assess_risk(
        self,
        question: str,
        llm_service: Optional[Any] = None,
    ) -> SemanticRiskResult:
        """使用 LLM 做语义风险评估"""
        if not question or not question.strip():
            return SemanticRiskResult(risk_level="LOW", reason="空输入")

        # 检查缓存
        cache_key = self._make_cache_key(question)
        cached = self._cache.get(cache_key)
        if cached:
            app_logger.debug(f"[SemanticRisk] 缓存命中: {cached.risk_level}")
            return cached

        # 调用 LLM
        result = await self._call_llm(question, llm_service)
        self._update_cache(cache_key, result)

        app_logger.info(f"[SemanticRisk] 语义评估完成: level={result.risk_level}, "
                        f"confidence={result.confidence:.2f}, reason={result.reason}")
        return result

    async def _call_llm(
        self,
        question: str,
        llm_service: Optional[Any],
    ) -> SemanticRiskResult:
        """调用 LLM 进行风险评估"""
        if llm_service is None:
            # 没有 LLM 服务，返回低风险兜底
            return SemanticRiskResult(
                risk_level="LOW",
                confidence=0.0,
                reason="LLM 服务不可用，降级为低风险",
                suggested_action="allow",
            )

        prompt = SEMANTIC_RISK_PROMPT.format(question=question)

        try:
            start_time = time.time()

            if hasattr(llm_service, 'agenerate'):
                response = await llm_service.agenerate(
                    messages=[{"role": "user", "content": prompt}],
                    model=self._model,
                )
            elif hasattr(llm_service, 'generate'):
                response = await llm_service.generate(
                    messages=[{"role": "user", "content": prompt}],
                )
            else:
                # 通用调用方式
                response = await llm_service.chat(
                    messages=[{"role": "user", "content": prompt}],
                    model=self._model,
                )

            elapsed_ms = (time.time() - start_time) * 1000
            app_logger.debug(f"[SemanticRisk] LLM 调用耗时: {elapsed_ms:.0f}ms")

            # 解析结果
            content = ""
            if isinstance(response, dict):
                content = response.get("content", response.get("answer", ""))
            elif hasattr(response, "content"):
                content = response.content
            elif hasattr(response, "choices") and response.choices:
                content = response.choices[0].message.content

            return self._parse_llm_response(content)

        except Exception as e:
            app_logger.error(f"[SemanticRisk] LLM 调用失败: {e}")
            return SemanticRiskResult(
                risk_level="LOW",
                confidence=0.0,
                reason=f"LLM 调用失败: {str(e)}",
                suggested_action="allow",
            )

    def _parse_llm_response(self, content: str) -> SemanticRiskResult:
        """解析 LLM 返回的 JSON"""
        try:
            # 尝试直接解析
            data = json.loads(content)
        except json.JSONDecodeError:
            # 尝试从 markdown 代码块中提取
            try:
                json_str = content.strip()
                if json_str.startswith("```"):
                    json_str = json_str.split("\n", 1)[-1]
                    if json_str.endswith("```"):
                        json_str = json_str[:-3]
                data = json.loads(json_str.strip())
            except (json.JSONDecodeError, IndexError):
                # 无法解析，按低风险处理
                return SemanticRiskResult(
                    risk_level="LOW",
                    confidence=0.3,
                    reason=f"LLM 返回格式异常: {content[:100]}",
                    suggested_action="allow",
                )

        risk_level = data.get("risk_level", "LOW").upper()
        if risk_level not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
            risk_level = "LOW"

        return SemanticRiskResult(
            risk_level=risk_level,
            confidence=float(data.get("confidence", 0.5)),
            is_destructive=bool(data.get("is_destructive", False)),
            is_write=bool(data.get("is_write", False)),
            is_export=bool(data.get("is_export", False)),
            reason=data.get("reason", ""),
            suggested_action=data.get("suggested_action", "allow"),
        )

    def _make_cache_key(self, question: str) -> str:
        return hashlib.sha256(question.encode("utf-8")).hexdigest()

    def _update_cache(self, key: str, result: SemanticRiskResult) -> None:
        if len(self._cache) >= self._cache_max_size:
            # 淘汰最早的缓存
            oldest_key = next(iter(self._cache))
            self._cache.pop(oldest_key, None)
        self._cache[key] = result

    def clear_cache(self) -> None:
        self._cache.clear()


_semantic_risk_instance: Optional[SemanticRiskService] = None


def get_semantic_risk_service() -> SemanticRiskService:
    global _semantic_risk_instance
    if _semantic_risk_instance is None:
        _semantic_risk_instance = SemanticRiskService()
    return _semantic_risk_instance
