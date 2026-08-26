"""统一意图路由 - 收敛分散的分类决策逻辑

功能：
1. 统一入口：替代分散的 _classify_by_complexity / _detect_task_type 逻辑
2. 明确优先级：问候 > 复杂度 > 任务类型 > 冲突仲裁
3. 结构化输出：RouteDecision 包含完整决策链路
4. 可扩展：支持语义多任务检测轨道
"""
import time
from typing import Optional, List, Dict, Any, Tuple
from app.agents.state import (
    ExecutionMode, RouteDecision, WorkflowType, TaskType, ComplexityLevel
)
from app.core.config import settings
from app.core.logger import app_logger
from app.services.model_router import get_model_router


# 任务类型关键词映射
TASK_KEYWORDS = {
    TaskType.TODO: {
        "keywords": ["待办", "待办事项", "todo", "任务", "行动项", "follow up", "action item"],
        "label": "待办",
    },
    TaskType.MINUTES: {
        "keywords": ["纪要", "会议纪要", "会议总结", "总结会议", "minutes", "meeting notes"],
        "label": "会议纪要",
    },
    TaskType.CONTROVERSY: {
        "keywords": ["争议", "冲突", "矛盾", "分歧", "disagreement", "conflict"],
        "label": "争议点",
    },
    TaskType.QA: {
        "keywords": ["是什么", "定义", "介绍一下", "解释一下", "what is", "define"],
        "label": "问答",
    },
}


class IntentRouter:
    """统一意图路由 - 单一入口，明确优先级"""

    def __init__(
        self,
        complexity_classifier: Optional[Any] = None,
        multi_task_detector: Optional[Any] = None,
        task_confidence_threshold: Optional[float] = None,
        complexity_confidence_threshold: Optional[float] = None,
    ):
        self._complexity_classifier = complexity_classifier
        self._multi_task_detector = multi_task_detector
        self._last_decision: Optional[RouteDecision] = None
        self._task_confidence_threshold = (
            task_confidence_threshold
            if task_confidence_threshold is not None
            else settings.ROUTE_TASK_CONFIDENCE_THRESHOLD
        )
        self._complexity_confidence_threshold = (
            complexity_confidence_threshold
            if complexity_confidence_threshold is not None
            else settings.ROUTE_COMPLEXITY_CONFIDENCE_THRESHOLD
        )

    async def route(
        self,
        question: str,
        llm_service: Optional[Any] = None,
    ) -> RouteDecision:
        """执行完整的意图路由决策链

        优先级：
        Step 1: 问候语检测（最高优先级）
        Step 2: 复杂度分类（complexity_classifier）
        Step 3: 任务类型检测（关键词 + 语义）
        Step 4: 冲突仲裁
        Step 5: 输出 RouteDecision
        """
        decision_trace: List[str] = []
        candidates: List[Dict[str, Any]] = []
        detected_tasks: List[str] = []

        start_time = time.time()

        # Step 1: 问候语检测
        if self._is_greeting(question):
            tier, model_name = get_model_router().select(
                TaskType.QA, ComplexityLevel.SIMPLE
            )
            decision = RouteDecision(
                workflow_type=WorkflowType.SIMPLE_QA,
                task_type=TaskType.QA,
                complexity_level=ComplexityLevel.SIMPLE,
                complexity_score=0.1,
                confidence=1.0,
                reason="问候语，直接响应",
                detected_tasks=[],
                task_confidence=0.0,
                is_multi_task=False,
                requires_retrieval=False,
                requires_reasoning=False,
                candidates=[{"type": "SIMPLE_QA", "confidence": 1.0}],
                decision_trace=["Step1: 检测为问候语 → SIMPLE_QA"],
                model_tier=tier,
                model_name=model_name,
                execution_mode=ExecutionMode.DETERMINISTIC,
                complexity_confidence=1.0,
                rule_matched=True,
                threshold_policy=self._threshold_policy(),
            )
            self._last_decision = decision
            self._log_decision(decision, start_time)
            return decision

        decision_trace.append("Step1: 非问候语，继续")

        # Step 2: 复杂度分类
        complexity_result = await self._classify_complexity(question)
        complexity_score = complexity_result.get("score", 0.5)
        complexity_level = complexity_result.get("level", ComplexityLevel.RETRIEVAL)
        is_multi_task_complexity = complexity_result.get("is_multi_task", False)
        requires_retrieval = complexity_result.get("requires_retrieval", False)
        requires_reasoning = complexity_result.get("requires_reasoning", False)
        complexity_confidence = complexity_result.get("confidence", 0.7)

        decision_trace.append(
            f"Step2: 复杂度={complexity_level.value}(score={complexity_score:.2f}, "
            f"multi={is_multi_task_complexity}, conf={complexity_confidence:.2f})"
        )

        # Step 3: 任务类型检测
        detected_type, task_confidence, detected_labels = await self._detect_tasks(
            question, llm_service
        )
        detected_tasks = detected_labels

        if detected_type:
            decision_trace.append(
                f"Step3: 任务检测={detected_type.value if detected_type else 'none'}, "
                f"labels={detected_labels}, conf={task_confidence:.2f}"
            )
        else:
            decision_trace.append("Step3: 未检测到特定任务类型")

        # Step 4: 冲突仲裁（传入置信度用于熔断判断）
        workflow_type, task_type, final_is_multi, final_reason = self._arbitrate(
            complexity_level=complexity_level,
            is_multi_task_complexity=is_multi_task_complexity,
            detected_type=detected_type,
            detected_labels=detected_labels,
            question=question,
            complexity_confidence=complexity_confidence,
            task_confidence=task_confidence,
        )

        decision_trace.append(f"Step4: 仲裁结果 → {workflow_type.value}/{task_type.value}")

        # 构建候选项
        candidates = self._build_candidates(
            workflow_type, task_type, complexity_level, complexity_score,
            detected_type, task_confidence
        )

        # 计算最终置信度
        final_confidence = self._calculate_confidence(
            complexity_confidence, task_confidence, complexity_level, task_type
        )

        # Step 5: 分层置信度策略。阈值是可配置初值，需由路由评测集标定。
        rule_matched = detected_type is not None
        effective_complexity = complexity_level
        degradation_actions: List[str] = []
        if (
            complexity_confidence < self._complexity_confidence_threshold
            and complexity_level in (ComplexityLevel.COT, ComplexityLevel.AGENT)
        ):
            effective_complexity = ComplexityLevel.RETRIEVAL
            degradation_actions.append(
                f"complexity_degraded:{complexity_level.value}->retrieval"
            )
            decision_trace.append(
                "Step5: 复杂度置信度不足，降为 retrieval；业务任务类型保持不变"
            )

        task_uncertain = (
            task_confidence < self._task_confidence_threshold and not rule_matched
        )
        if task_uncertain:
            execution_mode = ExecutionMode.FALLBACK
            degradation_actions.append("task_uncertain:external_write_disabled")
            requires_retrieval = True
            decision_trace.append("Step5: 任务类型置信度不足，进入保守 fallback")
        elif final_is_multi or workflow_type == WorkflowType.COMPLEX:
            execution_mode = ExecutionMode.PLAN_EXECUTE
        else:
            execution_mode = ExecutionMode.DETERMINISTIC

        tier, model_name = get_model_router().select(task_type, effective_complexity)
        sub_tasks = [
            {
                "task_id": f"route-task-{index}",
                "task_type": self._task_type_for_label(label).value,
                "description": label,
                "priority": index,
            }
            for index, label in enumerate(detected_tasks, start=1)
        ] if final_is_multi else []

        # Step 6: 输出唯一 RouteDecision
        decision = RouteDecision(
            workflow_type=workflow_type,
            task_type=task_type,
            complexity_level=effective_complexity,
            complexity_score=complexity_score,
            confidence=final_confidence,
            reason=final_reason,
            detected_tasks=detected_tasks,
            task_confidence=task_confidence,
            is_multi_task=final_is_multi,
            requires_retrieval=requires_retrieval,
            requires_reasoning=requires_reasoning,
            candidates=candidates,
            decision_trace=decision_trace,
            model_tier=tier,
            model_name=model_name,
            execution_mode=execution_mode,
            complexity_confidence=complexity_confidence,
            rule_matched=rule_matched,
            sub_tasks=sub_tasks,
            degradation_actions=degradation_actions,
            threshold_policy=self._threshold_policy(),
        )

        self._last_decision = decision
        self._log_decision(decision, start_time)
        return decision

    async def _classify_complexity(self, question: str) -> Dict[str, Any]:
        """复杂度分类"""
        if self._complexity_classifier:
            try:
                result = await self._complexity_classifier.classify(question)
                # 确保结果字段完整
                if isinstance(result, dict):
                    return result
            except Exception as e:
                app_logger.warning(f"[IntentRouter] complexity_classifier 异常: {e}")

        # 兜底分类
        return self._fallback_complexity(question)

    async def _detect_tasks(
        self,
        question: str,
        llm_service: Optional[Any],
    ) -> Tuple[Optional[TaskType], float, List[str]]:
        """检测任务类型"""
        normalized = question.strip().lower()
        detected_types: List[Tuple[TaskType, str]] = []

        # 关键词检测
        for task_type, config in TASK_KEYWORDS.items():
            if any(kw in normalized for kw in config["keywords"]):
                detected_types.append((task_type, config["label"]))

        # 多任务检测
        semantic_multi = False
        if self._multi_task_detector and not detected_types:
            try:
                multi_result = await self._multi_task_detector.detect(question, llm_service)
                semantic_multi = multi_result.get("is_multi_task", False)
                # 如果语义检测返回了任务列表，尝试匹配任务类型
                for task_desc in multi_result.get("tasks", []):
                    task_desc_lower = task_desc.lower()
                    for task_type, config in TASK_KEYWORDS.items():
                        if any(kw in task_desc_lower for kw in config["keywords"]):
                            detected_types.append((task_type, config["label"]))
                            break
            except Exception as e:
                app_logger.debug(f"[IntentRouter] multi_task_detector 异常: {e}")

        if len(detected_types) >= 2:
            labels = [t[1] for t in detected_types]
            return TaskType.MULTI, 0.9, labels

        if detected_types:
            return detected_types[0][0], 0.85, [detected_types[0][1]]

        if semantic_multi:
            return TaskType.MULTI, 0.7, ["语义多任务检测"]

        return None, 0.0, []

    def _arbitrate(
        self,
        complexity_level: ComplexityLevel,
        is_multi_task_complexity: bool,
        detected_type: Optional[TaskType],
        detected_labels: List[str],
        question: str,
        complexity_confidence: float = 0.7,
        task_confidence: float = 0.0,
    ) -> Tuple[WorkflowType, TaskType, bool, str]:
        """冲突仲裁 - 解决复杂度分类和任务检测的冲突

        本方法只做业务意图仲裁；置信度降级由 route() 的统一策略处理。
        """

        # === 核心仲裁逻辑 ===
        if detected_type:
            if detected_type == TaskType.MULTI:
                result = (WorkflowType.COMPLEX, TaskType.MULTI, True, f"检测到多任务：{'、'.join(detected_labels)}")
            elif complexity_level in (ComplexityLevel.COT, ComplexityLevel.AGENT):
                result = (WorkflowType.COMPLEX, detected_type, False, f"检测到{detected_labels[0]}，需要深度推理")
            else:
                task_to_workflow = {
                    TaskType.MINUTES: WorkflowType.MINUTES,
                    TaskType.TODO: WorkflowType.TODO,
                    TaskType.CONTROVERSY: WorkflowType.CONTROVERSY,
                    TaskType.QA: WorkflowType.SIMPLE_QA,
                }
                wf = task_to_workflow.get(detected_type, WorkflowType.SIMPLE_QA)
                result = (wf, detected_type, False, f"检测到{detected_labels[0]}意图")
        elif is_multi_task_complexity:
            result = (WorkflowType.COMPLEX, TaskType.MULTI, True, "复杂度判断为多任务")
        else:
            level_to_workflow = {
                ComplexityLevel.SIMPLE: (WorkflowType.SIMPLE_QA, TaskType.QA, False, "简单问答"),
                ComplexityLevel.RETRIEVAL: (WorkflowType.SIMPLE_QA, TaskType.QA, False, "需要检索的事实型问题"),
                ComplexityLevel.COT: (WorkflowType.COMPLEX, TaskType.MULTI, True, "需要思维链推理"),
                ComplexityLevel.AGENT: (WorkflowType.COMPLEX, TaskType.MULTI, True, "需要ReAct代理推理"),
            }
            result = level_to_workflow.get(
                complexity_level,
                (WorkflowType.SIMPLE_QA, TaskType.QA, False, "默认简单问答")
            )

        return result

    def _threshold_policy(self) -> Dict[str, Any]:
        return {
            "task_confidence": self._task_confidence_threshold,
            "complexity_confidence": self._complexity_confidence_threshold,
            "source": "config_provisional_until_route_eval",
        }

    @staticmethod
    def _task_type_for_label(label: str) -> TaskType:
        for task_type, config in TASK_KEYWORDS.items():
            if config["label"] == label:
                return task_type
        return TaskType.QA

    def _build_candidates(
        self,
        final_wf: WorkflowType,
        final_task: TaskType,
        complexity_level: ComplexityLevel,
        complexity_score: float,
        detected_type: Optional[TaskType],
        task_confidence: float,
    ) -> List[Dict[str, Any]]:
        """构建候选分类列表"""
        candidates = []

        # 最终选择
        candidates.append({
            "type": final_wf.value,
            "confidence": max(0.5, task_confidence if detected_type else 0.6),
            "is_selected": True,
        })

        # 如果检测到特定任务类型，也加入候选项
        if detected_type and detected_type != final_task:
            candidates.append({
                "type": detected_type.value,
                "confidence": task_confidence * 0.8,
                "is_selected": False,
            })

        # 基于复杂度的候选项
        if complexity_score > 0.7:
            candidates.append({
                "type": "complex",
                "confidence": complexity_score,
                "is_selected": False,
            })
        elif complexity_score > 0.3:
            candidates.append({
                "type": "retrieval",
                "confidence": complexity_score,
                "is_selected": False,
            })

        return sorted(candidates, key=lambda c: c["confidence"], reverse=True)

    def _calculate_confidence(
        self,
        complexity_confidence: float,
        task_confidence: float,
        complexity_level: ComplexityLevel,
        task_type: TaskType,
    ) -> float:
        """计算最终置信度"""
        if task_confidence > 0:
            # 有任务检测结果时，取两者较高值
            return max(complexity_confidence, task_confidence)
        return complexity_confidence

    def _is_greeting(self, question: str) -> bool:
        """判断是否为问候语"""
        normalized = question.strip().lower()
        greeting_keywords = [
            "你好", "hello", "hi", "您好", "嗨", "早上好", "下午好",
            "晚上好", "早安", "晚安", "good morning", "good afternoon",
            "good evening", "how are you", "最近怎么样"
        ]
        return any(kw in normalized for kw in greeting_keywords)

    def _fallback_complexity(self, question: str) -> Dict[str, Any]:
        """兜底复杂度分类（无分类器时使用）"""
        normalized = question.strip().lower()
        score = 0.2
        is_multi = False
        requires_retrieval = False
        requires_reasoning = False
        confidence = 0.5

        # 多任务检测
        multi_indicators = ["和", "与", "以及", "同时", "分别", "各", "所有", "每个", "并"]
        multi_count = len([kw for kw in multi_indicators if kw in normalized])
        parallel_markers = ["一是", "二是", "三是", "首先", "其次", "再次", "最后", "第一", "第二"]
        has_parallel = any(marker in normalized for marker in parallel_markers)
        question_count = normalized.count("？") + normalized.count("?")

        if has_parallel or question_count >= 2 or (multi_count >= 2 and len(question) > 25):
            is_multi = True
            score = 0.85

        # 推理检测
        reasoning_keywords = ["为什么", "怎么", "如何", "分析", "总结", "比较", "对比", "原因", "解释"]
        if any(kw in normalized for kw in reasoning_keywords):
            requires_reasoning = True
            score = max(score, 0.6)

        # 检索检测
        retrieval_keywords = ["多少", "什么时间", "什么时候", "哪个", "谁", "价格", "数据", "统计"]
        if any(kw in normalized for kw in retrieval_keywords):
            requires_retrieval = True
            score = max(score, 0.4)

        if len(question) > 100:
            score = min(0.95, score + 0.2)

        level = self._score_to_level(score)
        if is_multi:
            level = ComplexityLevel.AGENT
            confidence = 0.9

        return {
            "score": score,
            "level": level,
            "is_multi_task": is_multi,
            "requires_retrieval": requires_retrieval,
            "requires_reasoning": requires_reasoning,
            "confidence": confidence,
        }

    def _score_to_level(self, score: float) -> ComplexityLevel:
        """将分数转换为复杂度级别"""
        if score < 0.3:
            return ComplexityLevel.SIMPLE
        elif score < 0.5:
            return ComplexityLevel.RETRIEVAL
        elif score < 0.75:
            return ComplexityLevel.COT
        else:
            return ComplexityLevel.AGENT

    def _log_decision(self, decision: RouteDecision, start_time: float) -> None:
        """记录路由决策日志"""
        elapsed_ms = (time.time() - start_time) * 1000
        app_logger.info(
            f"[IntentRouter] 路由完成: "
            f"workflow={decision.workflow_type.value}, "
            f"task={decision.task_type.value}, "
            f"confidence={decision.confidence:.2f}, "
            f"tier={decision.model_tier.value}, mode={decision.execution_mode.value}, "
            f"multi={decision.is_multi_task}, "
            f"耗时={elapsed_ms:.1f}ms"
        )
        app_logger.debug(
            f"[IntentRouter] 决策链路: {' → '.join(decision.decision_trace)}"
        )

    def get_last_decision(self) -> Optional[RouteDecision]:
        """获取最近一次决策"""
        return self._last_decision


_router_instance: Optional[IntentRouter] = None


async def get_intent_router() -> IntentRouter:
    """获取全局 IntentRouter 实例"""
    global _router_instance
    if _router_instance is None:
        from app.services.complexity_classifier import get_complexity_classifier
        from app.services.semantic_multi_task_detector import get_semantic_multi_task_detector

        classifier = await get_complexity_classifier()
        detector = get_semantic_multi_task_detector()
        _router_instance = IntentRouter(
            complexity_classifier=classifier,
            multi_task_detector=detector,
        )
    return _router_instance
