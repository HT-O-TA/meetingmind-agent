"""反思与自我改进系统 - 支持自我评估、重新规划和迭代改进"""
import json
from typing import Dict, List, Any, Optional, Callable
from enum import Enum
from datetime import datetime
from dataclasses import dataclass, asdict
from app.core.logger import app_logger
from app.agents.tools.dynamic_tool_discovery import get_dynamic_tool_discovery, get_tool_combination_engine, DiscoveryStrategy


class FeedbackType(str, Enum):
    """反馈类型"""
    USER_RATING = "user_rating"          # 用户评分
    USER_COMMENT = "user_comment"        # 用户评论
    SELF_EVALUATION = "self_evaluation"  # 自我评估
    CORRECTION = "correction"            # 修正建议
    SUCCESS = "success"                  # 成功案例
    FAILURE = "failure"                  # 失败案例


class EvaluationMetric(str, Enum):
    """评估指标"""
    ACCURACY = "accuracy"                # 准确性
    RELEVANCE = "relevance"              # 相关性
    COMPLETENESS = "completeness"        # 完整性
    COHERENCE = "coherence"              # 连贯性
    USEFULNESS = "usefulness"            # 有用性
    CONFIDENCE = "confidence"            # 置信度


class RatingLevel(str, Enum):
    """评分等级"""
    EXCELLENT = "excellent"  # 优秀 (5)
    GOOD = "good"            # 良好 (4)
    AVERAGE = "average"      # 一般 (3)
    POOR = "poor"            # 较差 (2)
    BAD = "bad"              # 差 (1)


@dataclass
class FeedbackItem:
    """反馈项"""
    feedback_id: str
    type: FeedbackType
    input_text: str
    output_text: str
    rating: Optional[int] = None
    rating_level: Optional[RatingLevel] = None
    comment: Optional[str] = None
    metrics: Optional[Dict[EvaluationMetric, float]] = None
    corrections: Optional[List[str]] = None
    timestamp: datetime = None
    context: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class ReflectionNote:
    """反思笔记"""
    reflection_id: str
    topic: str
    insight: str
    action_items: List[str]
    priority: str  # high, medium, low
    timestamp: datetime = None
    related_feedbacks: List[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.related_feedbacks is None:
            self.related_feedbacks = []


@dataclass
class ImprovementRule:
    """改进规则"""
    rule_id: str
    condition: str  # 触发条件描述
    action: str     # 执行动作描述
    confidence: float  # 规则置信度
    active: bool = True
    created_at: datetime = None
    last_used_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class ReflectionSystem:
    """反思与自我改进系统"""
    
    def __init__(self):
        self._feedbacks: List[FeedbackItem] = []
        self._reflection_notes: List[ReflectionNote] = []
        self._improvement_rules: List[ImprovementRule] = []
        self._model_performance: Dict[str, Any] = {
            "total_interactions": 0,
            "avg_rating": 0.0,
            "rating_distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
            "success_rate": 0.0,
            "improvement_trend": []
        }
        
        # 初始化内置改进规则
        self._init_default_rules()
    
    def _init_default_rules(self):
        """初始化默认改进规则"""
        default_rules = [
            ImprovementRule(
                rule_id="rule_1",
                condition="连续3次用户评分低于3分",
                action="触发更详细的反思分析，生成改进建议",
                confidence=0.9
            ),
            ImprovementRule(
                rule_id="rule_2",
                condition="特定主题多次出现失败",
                action="收集该主题的所有反馈，分析模式",
                confidence=0.85
            ),
            ImprovementRule(
                rule_id="rule_3",
                condition="用户反馈指出事实错误",
                action="将正确信息添加到长期记忆",
                confidence=0.95
            ),
            ImprovementRule(
                rule_id="rule_4",
                condition="回答不完整被用户指出",
                action="优化相关Prompt模板，增加完整性检查",
                confidence=0.8
            ),
            ImprovementRule(
                rule_id="rule_5",
                condition="多次使用相同的错误推理路径",
                action="识别并阻断该路径，尝试替代方案",
                confidence=0.75
            )
        ]
        
        for rule in default_rules:
            self._improvement_rules.append(rule)
            app_logger.info(f"[Reflection] 加载改进规则: {rule.rule_id}")
    
    def add_feedback(self, **kwargs) -> FeedbackItem:
        """添加反馈"""
        feedback = FeedbackItem(
            feedback_id=f"fb_{int(datetime.now().timestamp())}",
            **kwargs
        )
        
        self._feedbacks.append(feedback)
        
        # 更新性能统计
        self._update_performance(feedback)
        
        # 检查是否触发改进规则
        self._check_rules(feedback)
        
        app_logger.info(f"[Reflection] 添加反馈: {feedback.feedback_id}")
        return feedback
    
    def _update_performance(self, feedback: FeedbackItem):
        """更新性能统计"""
        self._model_performance["total_interactions"] += 1
        
        if feedback.rating is not None:
            # 更新评分分布
            if 1 <= feedback.rating <= 5:
                self._model_performance["rating_distribution"][feedback.rating] += 1
            
            # 计算平均评分
            total_ratings = sum(self._model_performance["rating_distribution"].values())
            weighted_sum = sum(
                rating * count 
                for rating, count in self._model_performance["rating_distribution"].items()
            )
            if total_ratings > 0:
                self._model_performance["avg_rating"] = weighted_sum / total_ratings
            
            # 更新成功率（评分>=4视为成功）
            successful = sum(self._model_performance["rating_distribution"][r] for r in [4, 5])
            self._model_performance["success_rate"] = successful / total_ratings if total_ratings > 0 else 0.0
            
            # 添加到改进趋势
            self._model_performance["improvement_trend"].append({
                "timestamp": feedback.timestamp.isoformat(),
                "rating": feedback.rating,
                "avg_rating": self._model_performance["avg_rating"]
            })
            
            # 保持趋势数据在最近100条
            if len(self._model_performance["improvement_trend"]) > 100:
                self._model_performance["improvement_trend"].pop(0)
    
    def _check_rules(self, feedback: FeedbackItem):
        """检查是否触发改进规则"""
        for rule in self._improvement_rules:
            if not rule.active:
                continue
            
            # 简单规则匹配（可扩展为更复杂的条件引擎）
            if rule.condition == "连续3次用户评分低于3分":
                recent_feedbacks = self._feedbacks[-3:]
                if len(recent_feedbacks) >= 3:
                    all_low = all(f.rating is not None and f.rating < 3 for f in recent_feedbacks)
                    if all_low:
                        self._trigger_rule(rule, feedback)
            
            elif rule.condition == "用户反馈指出事实错误":
                if feedback.type == FeedbackType.CORRECTION:
                    self._trigger_rule(rule, feedback)
    
    def _trigger_rule(self, rule: ImprovementRule, feedback: FeedbackItem):
        """触发改进规则"""
        rule.last_used_at = datetime.now()
        
        # 创建反思笔记
        note = ReflectionNote(
            reflection_id=f"ref_{int(datetime.now().timestamp())}",
            topic=f"规则触发: {rule.condition}",
            insight=f"检测到符合规则 '{rule.condition}' 的情况，建议: {rule.action}",
            action_items=[f"执行规则动作: {rule.action}"],
            priority="high" if rule.confidence > 0.8 else "medium",
            related_feedbacks=[feedback.feedback_id]
        )
        
        self._reflection_notes.append(note)
        app_logger.info(f"[Reflection] 规则触发: {rule.rule_id} -> 创建反思笔记: {note.reflection_id}")
    
    def perform_self_evaluation(
        self,
        input_text: str,
        output_text: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[EvaluationMetric, float]:
        """执行自我评估"""
        # 模拟自我评估逻辑（可扩展为调用LLM进行评估）
        metrics = {}
        
        # 基于启发式规则的评估
        metrics[EvaluationMetric.ACCURACY] = self._evaluate_accuracy(output_text)
        metrics[EvaluationMetric.RELEVANCE] = self._evaluate_relevance(input_text, output_text)
        metrics[EvaluationMetric.COMPLETENESS] = self._evaluate_completeness(output_text)
        metrics[EvaluationMetric.COHERENCE] = self._evaluate_coherence(output_text)
        metrics[EvaluationMetric.USEFULNESS] = self._evaluate_usefulness(output_text)
        metrics[EvaluationMetric.CONFIDENCE] = self._calculate_confidence(metrics)
        
        # 创建自我评估反馈
        self.add_feedback(
            type=FeedbackType.SELF_EVALUATION,
            input_text=input_text,
            output_text=output_text,
            metrics=metrics,
            context=context
        )
        
        return metrics
    
    def _evaluate_accuracy(self, output: str) -> float:
        """评估准确性"""
        # 简单启发式：检查是否有不确定的表述
        uncertainty_phrases = ["可能", "也许", "大概", "不确定", "可能是", "我认为"]
        uncertainty_count = sum(1 for phrase in uncertainty_phrases if phrase in output)
        
        base_score = 0.8
        deduction = min(uncertainty_count * 0.05, 0.3)
        return max(0.0, base_score - deduction)
    
    def _evaluate_relevance(self, input: str, output: str) -> float:
        """评估相关性"""
        input_tokens = set(input.lower().split())
        output_tokens = set(output.lower().split())
        
        if not input_tokens:
            return 0.5
        
        overlap = input_tokens.intersection(output_tokens)
        return len(overlap) / len(input_tokens)
    
    def _evaluate_completeness(self, output: str) -> float:
        """评估完整性"""
        # 检查是否有"需要更多信息"等不完整提示
        incomplete_phrases = ["需要更多", "缺少信息", "无法回答", "不知道", "不确定"]
        
        if any(phrase in output for phrase in incomplete_phrases):
            return 0.3
        
        # 根据长度评估
        length = len(output)
        if length < 50:
            return 0.4
        elif length < 150:
            return 0.6
        elif length < 300:
            return 0.8
        else:
            return 0.95
    
    def _evaluate_coherence(self, output: str) -> float:
        """评估连贯性"""
        sentences = output.split('。')
        if len(sentences) <= 1:
            return 0.8
        
        # 检查逻辑连接词
        connectives = ["但是", "因此", "所以", "然而", "此外", "首先", "其次", "最后"]
        connective_count = sum(1 for conn in connectives if conn in output)
        
        base_score = 0.7
        bonus = min(connective_count * 0.05, 0.3)
        return min(1.0, base_score + bonus)
    
    def _evaluate_usefulness(self, output: str) -> float:
        """评估有用性"""
        # 检查是否包含具体建议或步骤
        useful_patterns = ["建议", "应该", "可以", "步骤", "方法", "方案", "解决", "如何"]
        pattern_count = sum(1 for pattern in useful_patterns if pattern in output)
        
        if pattern_count == 0:
            return 0.5
        elif pattern_count == 1:
            return 0.7
        else:
            return 0.9
    
    def _calculate_confidence(self, metrics: Dict[EvaluationMetric, float]) -> float:
        """计算总体置信度"""
        weights = {
            EvaluationMetric.ACCURACY: 0.25,
            EvaluationMetric.RELEVANCE: 0.25,
            EvaluationMetric.COMPLETENESS: 0.2,
            EvaluationMetric.COHERENCE: 0.15,
            EvaluationMetric.USEFULNESS: 0.15
        }
        
        total = sum(metrics.get(m, 0.5) * weights.get(m, 0.2) for m in EvaluationMetric)
        return min(1.0, max(0.0, total))
    
    def generate_improvement_suggestions(self, limit: int = 5) -> List[ReflectionNote]:
        """生成改进建议"""
        # 基于反馈生成改进建议
        suggestions = []
        
        # 分析低评分反馈的模式
        low_ratings = [f for f in self._feedbacks if f.rating is not None and f.rating < 3]
        if low_ratings:
            note = ReflectionNote(
                reflection_id=f"ref_{int(datetime.now().timestamp())}",
                topic="低评分模式分析",
                insight=f"检测到 {len(low_ratings)} 条低评分反馈，需要关注用户满意度",
                action_items=[
                    "分析低评分反馈的共同主题",
                    "优化相关场景的Prompt",
                    "增加用户反馈收集机制"
                ],
                priority="high"
            )
            suggestions.append(note)
        
        # 检查规则触发情况
        triggered_rules = [r for r in self._improvement_rules if r.last_used_at is not None]
        if triggered_rules:
            note = ReflectionNote(
                reflection_id=f"ref_{int(datetime.now().timestamp())}",
                topic="规则触发汇总",
                insight=f"{len(triggered_rules)} 条改进规则被触发",
                action_items=[f"处理规则: {r.condition}" for r in triggered_rules],
                priority="medium"
            )
            suggestions.append(note)
        
        return suggestions[:limit]
    
    def get_performance_report(self) -> Dict[str, Any]:
        """获取性能报告"""
        return {
            **self._model_performance,
            "feedback_count": len(self._feedbacks),
            "reflection_note_count": len(self._reflection_notes),
            "active_rules": sum(1 for r in self._improvement_rules if r.active)
        }
    
    def get_feedbacks(self, feedback_type: Optional[FeedbackType] = None) -> List[FeedbackItem]:
        """获取反馈列表"""
        if feedback_type:
            return [f for f in self._feedbacks if f.type == feedback_type]
        return self._feedbacks

    def collect_feedback(
        self,
        agent_id: str,
        content: str,
        rating: Optional[int] = None,
        feedback_type: FeedbackType = FeedbackType.USER_COMMENT,
        **kwargs
    ) -> FeedbackItem:
        """兼容旧接口：收集某个 Agent 的反馈。"""
        return self.add_feedback(
            type=feedback_type,
            input_text=kwargs.get("input_text", ""),
            output_text=content,
            rating=rating,
            comment=kwargs.get("comment"),
            context={"agent_id": agent_id, **kwargs.get("context", {})},
        )

    def get_recent_feedbacks(self, limit: int = 10) -> List[FeedbackItem]:
        """兼容旧接口：获取最近反馈。"""
        return self._feedbacks[-limit:]
    
    def get_reflection_notes(self, priority: Optional[str] = None) -> List[ReflectionNote]:
        """获取反思笔记"""
        if priority:
            return [n for n in self._reflection_notes if n.priority == priority]
        return self._reflection_notes
    
    def add_improvement_rule(self, condition: str, action: str, confidence: float = 0.8) -> ImprovementRule:
        """添加改进规则"""
        rule = ImprovementRule(
            rule_id=f"rule_{int(datetime.now().timestamp())}",
            condition=condition,
            action=action,
            confidence=confidence
        )
        
        self._improvement_rules.append(rule)
        app_logger.info(f"[Reflection] 添加改进规则: {rule.rule_id}")
        return rule

    async def reflect_and_replan(
        self,
        input_text: str,
        output_text: str,
        context: Optional[Dict[str, Any]] = None,
        tools_used: Optional[List[str]] = None,
        max_iterations: int = 3,
    ) -> Dict[str, Any]:
        """
        反思并重新规划
        
        Args:
            input_text: 原始输入
            output_text: 当前输出
            context: 上下文信息
            tools_used: 之前使用的工具
            max_iterations: 最大迭代次数
            
        Returns:
            重新规划结果，包含新的计划、工具选择和重新生成的答案
        """
        context = context or {}
        iteration = 0
        best_result = {
            "output": output_text,
            "plan": [],
            "tools": tools_used or [],
            "confidence": 0.0,
            "iterations": 0,
        }
        
        while iteration < max_iterations:
            iteration += 1
            app_logger.info(f"[Reflection] 反思迭代 {iteration}/{max_iterations}")
            
            evaluation = self.perform_self_evaluation(input_text, output_text, context)
            evaluation_dict = {k.value if hasattr(k, 'value') else k: v for k, v in evaluation.items()}
            confidence = evaluation_dict.get("confidence", 0.5)
            
            if confidence >= 0.7:
                app_logger.info(f"[Reflection] 置信度 {confidence:.2f} 达到阈值，停止迭代")
                best_result.update({
                    "output": output_text,
                    "confidence": confidence,
                    "iterations": iteration,
                    "evaluation": evaluation_dict,
                })
                break
            
            new_plan = self._generate_new_plan(input_text, output_text, evaluation_dict, tools_used)
            new_tools = await self._select_new_tools(input_text, output_text, evaluation_dict, tools_used)
            output_text = await self._regenerate_answer(input_text, output_text, evaluation_dict, new_plan, new_tools)
            
            best_result.update({
                "output": output_text,
                "plan": new_plan,
                "tools": new_tools,
                "confidence": confidence,
                "iterations": iteration,
                "evaluation": evaluation_dict,
            })
            
            app_logger.info(f"[Reflection] 迭代 {iteration} 完成，置信度: {confidence:.2f}")
        
        return best_result

    def _generate_new_plan(
        self,
        input_text: str,
        output_text: str,
        evaluation: Dict[str, float],
        tools_used: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        根据评估结果生成新的执行计划
        
        Args:
            input_text: 原始输入
            output_text: 当前输出
            evaluation: 评估结果
            tools_used: 之前使用的工具
            
        Returns:
            新的执行计划步骤
        """
        plan = []
        
        if evaluation.get("accuracy", 0) < 0.5:
            plan.append({
                "step": "verify_facts",
                "description": "验证事实准确性",
                "priority": "high",
            })
        
        if evaluation.get("completeness", 0) < 0.6:
            plan.append({
                "step": "gather_more_info",
                "description": "收集更多信息",
                "priority": "high",
            })
        
        if evaluation.get("relevance", 0) < 0.5:
            plan.append({
                "step": "reanalyze_query",
                "description": "重新分析查询意图",
                "priority": "high",
            })
        
        if evaluation.get("coherence", 0) < 0.6:
            plan.append({
                "step": "restructure_response",
                "description": "重新组织回答结构",
                "priority": "medium",
            })
        
        plan.append({
            "step": "final_generation",
            "description": "生成最终回答",
            "priority": "high",
        })
        
        app_logger.info(f"[Reflection] 生成新计划: {[p['step'] for p in plan]}")
        return plan

    async def _select_new_tools(
        self,
        input_text: str,
        output_text: str,
        evaluation: Dict[str, float],
        tools_used: Optional[List[str]] = None,
    ) -> List[str]:
        """
        根据评估结果重新选择工具
        
        Args:
            input_text: 原始输入
            output_text: 当前输出
            evaluation: 评估结果
            tools_used: 之前使用的工具
            
        Returns:
            新的工具ID列表
        """
        tools_used = tools_used or []
        
        discovery = get_dynamic_tool_discovery()
        context = {
            "query": input_text,
            "current_output": output_text,
            "evaluation": evaluation,
            "tools_used": tools_used,
        }
        
        results = await discovery.discover_tools(
            query=input_text,
            context=context,
            strategy=DiscoveryStrategy.HYBRID,
            max_tools=10,
        )
        
        new_tools = []
        for result in results:
            tool_id = result.tool_id
            if tool_id not in tools_used:
                new_tools.append(tool_id)
        
        app_logger.info(f"[Reflection] 重新选择工具: {new_tools}")
        return new_tools

    async def _regenerate_answer(
        self,
        input_text: str,
        output_text: str,
        evaluation: Dict[str, float],
        new_plan: List[Dict[str, Any]],
        new_tools: List[str],
    ) -> str:
        """
        根据新计划和工具重新生成答案
        
        Args:
            input_text: 原始输入
            output_text: 当前输出
            evaluation: 评估结果
            new_plan: 新的执行计划
            new_tools: 新选择的工具
            
        Returns:
            重新生成的答案
        """
        from app.services.llm_service import LLMService
        
        llm_service = LLMService()
        
        evaluation_feedback = []
        for metric, score in evaluation.items():
            metric_name = metric.value if hasattr(metric, 'value') else metric
            if score < 0.6:
                evaluation_feedback.append(f"- {metric_name}: {score:.2f} (需要改进)")
        
        plan_steps = "\n".join([f"{i+1}. {p['description']} (优先级: {p['priority']})" for i, p in enumerate(new_plan)])
        
        prompt = f"""你是一位专业的会议助手。请根据以下信息重新生成回答：

【原始问题】
{input_text}

【当前回答】
{output_text}

【自我评估结果】
{"\n".join(evaluation_feedback) if evaluation_feedback else "所有指标达标"}

【评估指标】
{json.dumps({k.value if hasattr(k, 'value') else k: v for k, v in evaluation.items()}, indent=2)}

【新的执行计划】
{plan_steps}

【建议使用的新工具】
{', '.join(new_tools) if new_tools else '无'}

【要求】
1. 根据评估反馈改进回答质量
2. 提高准确性、完整性和相关性
3. 如果有建议使用的工具，请考虑如何利用它们改进回答
4. 输出格式保持专业、清晰

请重新生成回答：
"""
        
        try:
            messages = [
                {"role": "system", "content": "你是一位专业的会议助手，擅长分析会议内容并生成高质量的总结。"},
                {"role": "user", "content": prompt},
            ]
            response = await llm_service.chat(messages)
            app_logger.info("[Reflection] 答案重新生成成功")
            return response
        except Exception as e:
            app_logger.warning(f"[Reflection] 答案重新生成失败: {e}")
            return output_text

    def should_reflect(self, evaluation: Dict[str, float]) -> bool:
        """
        判断是否需要进行反思
        
        Args:
            evaluation: 评估结果
            
        Returns:
            是否需要反思
        """
        confidence = evaluation.get("confidence", 0.5)
        return confidence < 0.7

    def get_reflection_stats(self) -> Dict[str, Any]:
        """获取反思统计信息"""
        notes = self._reflection_notes
        high_priority = [n for n in notes if n.priority == "high"]
        medium_priority = [n for n in notes if n.priority == "medium"]
        low_priority = [n for n in notes if n.priority == "low"]
        
        return {
            "total_reflection_notes": len(notes),
            "high_priority_notes": len(high_priority),
            "medium_priority_notes": len(medium_priority),
            "low_priority_notes": len(low_priority),
            "active_rules": sum(1 for r in self._improvement_rules if r.active),
            "total_rules": len(self._improvement_rules),
        }


# 全局反思系统实例
reflection_system = ReflectionSystem()


def get_reflection_system() -> ReflectionSystem:
    """获取反思系统实例"""
    return reflection_system
