"""反思与自我改进系统 - 支持自我评估和迭代改进"""
import json
from typing import Dict, List, Any, Optional
from enum import Enum
from datetime import datetime
from dataclasses import dataclass, asdict
from app.core.logger import app_logger


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


# 全局反思系统实例
reflection_system = ReflectionSystem()


def get_reflection_system() -> ReflectionSystem:
    """获取反思系统实例"""
    return reflection_system
