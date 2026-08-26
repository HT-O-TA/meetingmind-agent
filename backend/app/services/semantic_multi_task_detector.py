"""语义多任务检测服务 - 基于 LLM 的隐式多任务识别

功能：
1. 识别显式多任务（通过关键词）
2. 识别隐式多任务（通过 LLM 语义理解）
3. 输出多任务检测结果：is_multi_task + tasks 列表 + 置信度
"""
import json
import hashlib
import time
from typing import Optional, List, Dict, Any
from app.core.logger import app_logger


SEMANTIC_MULTI_TASK_PROMPT = """你是一个任务分析助手。请判断以下用户问题是否包含多个独立任务。

用户问题：{question}

分析规则：
1. 如果问题中包含多个独立的动作或目标，则为多任务
2. 即使没有明显的连接词（如"并"、"同时"），如果语义上涉及多个不同的操作，也算多任务
3. 识别出每个独立的任务，并用简短的短语描述

示例：
- "帮我生成纪要并提取待办" → 多任务，任务：["生成会议纪要", "提取待办事项"]
- "把上次会议的结论做成这次的待办" → 多任务，任务：["获取上次会议结论", "转换为待办事项"]
- "总结一下这次讨论" → 单任务，任务：["总结讨论内容"]

请输出 JSON：
{{
    "is_multi_task": true/false,
    "tasks": ["任务1描述", "任务2描述"],
    "confidence": 0.0-1.0,
    "reason": "简短说明判断理由"
}}"""


class SemanticMultiTaskDetector:
    """语义多任务检测器"""

    def __init__(self, model: str = "gpt-4o-mini", timeout_ms: int = 3000):
        self._model = model
        self._timeout_ms = timeout_ms
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_max_size: int = 500
        self._cache_ttl: float = 300  # 5 分钟

    async def detect(
        self,
        question: str,
        llm_service: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """检测问题是否为多任务"""
        if not question or not question.strip():
            return {
                "is_multi_task": False,
                "tasks": [],
                "confidence": 0.0,
                "reason": "空输入",
                "method": "none",
            }

        # 检查缓存
        cache_key = self._make_cache_key(question)
        cached = self._cache.get(cache_key)
        if cached:
            app_logger.debug(f"[SemanticMultiTask] 缓存命中: is_multi_task={cached['is_multi_task']}")
            return cached

        result = await self._detect_via_llm(question, llm_service)
        self._update_cache(cache_key, result)

        app_logger.info(
            f"[SemanticMultiTask] 检测完成: is_multi_task={result['is_multi_task']}, "
            f"tasks={result['tasks']}, confidence={result['confidence']:.2f}"
        )
        return result

    async def _detect_via_llm(
        self,
        question: str,
        llm_service: Optional[Any],
    ) -> Dict[str, Any]:
        """通过 LLM 检测多任务"""
        if llm_service is None:
            return self._rule_based_detect(question)

        prompt = SEMANTIC_MULTI_TASK_PROMPT.format(question=question)

        try:
            start_time = time.time()

            if hasattr(llm_service, 'agenerate'):
                response = await llm_service.agenerate(
                    messages=[{"role": "user", "content": prompt}],
                    model=self._model,
                )
            elif hasattr(llm_service, 'chat'):
                response = await llm_service.chat(
                    messages=[{"role": "user", "content": prompt}],
                )
            else:
                response = await llm_service.generate(
                    messages=[{"role": "user", "content": prompt}],
                )

            elapsed_ms = (time.time() - start_time) * 1000
            app_logger.debug(f"[SemanticMultiTask] LLM 调用耗时: {elapsed_ms:.0f}ms")

            # 解析响应
            content = self._extract_content(response)
            return self._parse_result(content)

        except Exception as e:
            app_logger.warning(f"[SemanticMultiTask] LLM 调用失败: {e}, 降级到规则检测")
            return self._rule_based_detect(question)

    def _extract_content(self, response: Any) -> str:
        """从 LLM 响应中提取文本内容"""
        if isinstance(response, dict):
            return response.get("content", response.get("answer", ""))
        elif hasattr(response, "content"):
            return response.content
        elif hasattr(response, "choices") and response.choices:
            return response.choices[0].message.content
        return ""

    def _parse_result(self, content: str) -> Dict[str, Any]:
        """解析 LLM 返回结果"""
        try:
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
                # 无法解析，降级为规则检测
                return self._rule_based_detect_from_text(content)

        tasks = data.get("tasks", [])
        if not isinstance(tasks, list):
            tasks = []

        return {
            "is_multi_task": bool(data.get("is_multi_task", False)),
            "tasks": tasks,
            "confidence": float(data.get("confidence", 0.5)),
            "reason": data.get("reason", ""),
            "method": "llm",
        }

    def _rule_based_detect(self, question: str) -> Dict[str, Any]:
        """纯规则检测（无 LLM 时的兜底）"""
        normalized = question.strip().lower()

        # 连接词检测
        multi_task_indicators = [
            "和", "与", "以及", "同时", "分别", "各", "所有", "每个",
            "还有", "另外", "除此之外", "再", "然后", "并"
        ]

        count = len([kw for kw in multi_task_indicators if kw in normalized])
        question_count = normalized.count("？") + normalized.count("?")

        has_parallel = any(
            kw in normalized
            for kw in ["一是", "二是", "首先", "其次", "第一", "第二", "第三"]
        )

        # 动作动词检测
        action_verbs = ["分析", "提取", "识别", "总结", "制定", "评估", "估算", "规划",
                        "生成", "创建", "制作", "整理", "撰写", "设计"]
        action_count = len([kw for kw in action_verbs if kw in normalized])

        is_multi = count >= 2 or question_count >= 2 or has_parallel or action_count >= 2

        tasks = []
        if is_multi:
            tasks = [f"任务{i+1}" for i in range(min(action_count or 2, 3))]

        confidence = 0.7
        if has_parallel or question_count >= 2:
            confidence = 0.9
        elif action_count >= 2:
            confidence = 0.8

        return {
            "is_multi_task": is_multi,
            "tasks": tasks,
            "confidence": confidence,
            "reason": "规则检测",
            "method": "rule",
        }

    def _rule_based_detect_from_text(self, text: str) -> Dict[str, Any]:
        """从 LLM 返回文本中做简单规则检测"""
        normalized = text.lower()
        if "true" in normalized and "multi" in normalized:
            return {
                "is_multi_task": True,
                "tasks": [],
                "confidence": 0.5,
                "reason": "LLM 返回解析失败，文本暗示多任务",
                "method": "rule_from_text",
            }
        return self._rule_based_detect(text)

    def _make_cache_key(self, question: str) -> str:
        return hashlib.sha256(question.encode("utf-8")).hexdigest()

    def _update_cache(self, key: str, result: Dict[str, Any]) -> None:
        if len(self._cache) >= self._cache_max_size:
            oldest_key = next(iter(self._cache))
            self._cache.pop(oldest_key, None)
        self._cache[key] = result

    def clear_cache(self) -> None:
        self._cache.clear()


_detector_instance: Optional[SemanticMultiTaskDetector] = None


def get_semantic_multi_task_detector() -> SemanticMultiTaskDetector:
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = SemanticMultiTaskDetector()
    return _detector_instance
