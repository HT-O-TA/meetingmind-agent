"""RAGAS评估指标集成 + 在线监控"""
import json
import time
import asyncio
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from app.core.logger import app_logger
from app.core.config import settings


class EvaluationMetric(str, Enum):
    """评估指标"""
    FAITHFULNESS = "faithfulness"
    ANSWER_RELEVANCY = "answer_relevancy"
    CONTEXT_PRECISION = "context_precision"
    CONTEXT_RECALL = "context_recall"
    ANSWER_SIMILARITY = "answer_similarity"
    ANSWER_CORRECTNESS = "answer_correctness"


@dataclass
class RAGASMetrics:
    """RAGAS评估指标"""
    faithfulness: float = 0.0
    answer_relevancy: float = 0.0
    context_precision: float = 0.0
    context_recall: float = 0.0
    answer_similarity: float = 0.0
    answer_correctness: float = 0.0
    
    def to_dict(self) -> Dict[str, float]:
        return {
            "faithfulness": self.faithfulness,
            "answer_relevancy": self.answer_relevancy,
            "context_precision": self.context_precision,
            "context_recall": self.context_recall,
            "answer_similarity": self.answer_similarity,
            "answer_correctness": self.answer_correctness
        }
    
    def avg_score(self) -> float:
        scores = [
            self.faithfulness,
            self.answer_relevancy,
            self.context_precision,
            self.context_recall,
            self.answer_similarity,
            self.answer_correctness
        ]
        valid_scores = [s for s in scores if s > 0]
        return sum(valid_scores) / len(valid_scores) if valid_scores else 0.0


@dataclass
class EvaluationRecord:
    """评估记录"""
    record_id: str
    timestamp: datetime
    query: str
    ground_truth: str
    answer: str
    contexts: List[str]
    metrics: RAGASMetrics
    latency_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MonitorMetrics:
    """监控指标"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_latency_ms: float = 0.0
    avg_metrics: RAGASMetrics = field(default_factory=RAGASMetrics)
    error_types: Dict[str, int] = field(default_factory=dict)
    last_update: datetime = field(default_factory=datetime.now)


class RAGASEvaluator:
    """RAGAS评估器"""
    
    def __init__(self, llm_service=None):
        self._llm = llm_service
        self._records: List[EvaluationRecord] = []
        self._max_records = 1000
    
    def _get_llm(self):
        if self._llm is None:
            try:
                from app.services.llm_service import LLMService
                self._llm = LLMService()
            except Exception as e:
                app_logger.warning(f"Could not load LLM service: {e}")
        return self._llm
    
    async def evaluate(
        self,
        query: str,
        answer: str,
        contexts: List[str],
        ground_truth: str = None
    ) -> RAGASMetrics:
        """
        综合评估RAG系统
        
        Args:
            query: 用户问题
            answer: 生成的答案
            contexts: 检索到的上下文
            ground_truth: 标准答案（可选）
            
        Returns:
            RAGASMetrics
        """
        llm = self._get_llm()
        
        if llm is None:
            return RAGASMetrics()
        
        metrics = RAGASMetrics()
        
        metrics.faithfulness = await self._evaluate_faithfulness(
            llm, answer, contexts
        )
        
        metrics.answer_relevancy = await self._evaluate_answer_relevancy(
            llm, query, answer
        )
        
        metrics.context_precision = await self._evaluate_context_precision(
            llm, query, contexts
        )
        
        if ground_truth:
            metrics.answer_similarity = await self._evaluate_answer_similarity(
                llm, answer, ground_truth
            )
            metrics.answer_correctness = await self._evaluate_answer_correctness(
                llm, answer, ground_truth
            )
            metrics.context_recall = await self._evaluate_context_recall(
                llm, ground_truth, contexts
            )
        
        return metrics
    
    async def _evaluate_faithfulness(
        self,
        llm,
        answer: str,
        contexts: List[str]
    ) -> float:
        """评估Faithfulness（答案对上下文的忠诚度）"""
        try:
            contexts_str = "\n".join(f"[{i+1}] {c}" for i, c in enumerate(contexts))
            
            prompt = f"""评估以下答案是否忠实于提供的上下文。

评估标准：
- 答案中的所有陈述是否都能在上下文中找到依据
- 不包含上下文之外的主观推测
- 保持上下文信息的原意

上下文：
{contexts_str}

答案：
{answer}

请评估答案的忠诚度，给出0-1之间的分数，并简要说明理由。

输出格式：
{{"score": 0.85, "reasoning": "理由"}}

只输出JSON："""
            
            response = await llm._call(prompt)
            data = self._parse_response(response)
            
            return data.get("score", 0.0) if data else 0.0
            
        except Exception as e:
            app_logger.error(f"Faithfulness evaluation failed: {e}")
            return 0.0
    
    async def _evaluate_answer_relevancy(
        self,
        llm,
        query: str,
        answer: str
    ) -> float:
        """评估Answer Relevancy（答案与问题的相关性）"""
        try:
            prompt = f"""评估以下答案与问题的相关性。

评估标准：
- 答案是否直接回答了问题
- 答案是否完整（不遗漏重要方面）
- 答案是否简洁（不包含无关信息）

问题：{query}

答案：
{answer}

请评估相关性，给出0-1之间的分数。

输出格式：
{{"score": 0.9, "reasoning": "理由"}}

只输出JSON："""
            
            response = await llm._call(prompt)
            data = self._parse_response(response)
            
            return data.get("score", 0.0) if data else 0.0
            
        except Exception as e:
            app_logger.error(f"Answer relevancy evaluation failed: {e}")
            return 0.0
    
    async def _evaluate_context_precision(
        self,
        llm,
        query: str,
        contexts: List[str]
    ) -> float:
        """评估Context Precision（上下文精确度）"""
        try:
            contexts_str = "\n".join(f"[{i+1}] {c}" for i, c in enumerate(contexts))
            
            prompt = f"""评估检索到的上下文与问题的相关性。

评估标准：
- 每个上下文片段是否都与问题相关
- 相关片段应该排在前面
- 不相关片段越少越好

问题：{query}

上下文：
{contexts_str}

请评估上下文精确度，给出0-1之间的分数。

输出格式：
{{"score": 0.85, "reasoning": "理由"}}

只输出JSON："""
            
            response = await llm._call(prompt)
            data = self._parse_response(response)
            
            return data.get("score", 0.0) if data else 0.0
            
        except Exception as e:
            app_logger.error(f"Context precision evaluation failed: {e}")
            return 0.0
    
    async def _evaluate_context_recall(
        self,
        llm,
        ground_truth: str,
        contexts: List[str]
    ) -> float:
        """评估Context Recall（上下文召回率）"""
        try:
            contexts_str = "\n".join(f"[{i+1}] {c}" for i, c in enumerate(contexts))
            
            prompt = f"""评估上下文是否覆盖了标准答案所需的信息。

评估标准：
- 标准答案中的关键信息是否都能在上下文中找到
- 上下文是否提供了足够的信息来回答问题

标准答案：
{ground_truth}

上下文：
{contexts_str}

请评估上下文召回率，给出0-1之间的分数。

输出格式：
{{"score": 0.9, "reasoning": "理由"}}

只输出JSON："""
            
            response = await llm._call(prompt)
            data = self._parse_response(response)
            
            return data.get("score", 0.0) if data else 0.0
            
        except Exception as e:
            app_logger.error(f"Context recall evaluation failed: {e}")
            return 0.0
    
    async def _evaluate_answer_similarity(
        self,
        llm,
        answer: str,
        ground_truth: str
    ) -> float:
        """评估Answer Similarity（答案相似度）"""
        try:
            prompt = f"""评估生成答案与标准答案的相似度。

标准答案：
{ground_truth}

生成答案：
{answer}

请评估两者的语义相似度，给出0-1之间的分数。

输出格式：
{{"score": 0.85, "reasoning": "理由"}}

只输出JSON："""
            
            response = await llm._call(prompt)
            data = self._parse_response(response)
            
            return data.get("score", 0.0) if data else 0.0
            
        except Exception as e:
            app_logger.error(f"Answer similarity evaluation failed: {e}")
            return 0.0
    
    async def _evaluate_answer_correctness(
        self,
        llm,
        answer: str,
        ground_truth: str
    ) -> float:
        """评估Answer Correctness（答案正确性）"""
        try:
            prompt = f"""评估生成答案相对于标准答案的正确性。

标准答案：
{ground_truth}

生成答案：
{answer}

评估维度：
- 事实正确性
- 完整性
- 准确性

请给出0-1之间的综合分数。

输出格式：
{{"score": 0.88, "reasoning": "理由"}}

只输出JSON："""
            
            response = await llm._call(prompt)
            data = self._parse_response(response)
            
            return data.get("score", 0.0) if data else 0.0
            
        except Exception as e:
            app_logger.error(f"Answer correctness evaluation failed: {e}")
            return 0.0
    
    def _parse_response(self, response: str) -> Optional[Dict]:
        """解析JSON响应"""
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start != -1 and end != 0:
                return json.loads(response[start:end])
        except:
            pass
        return None
    
    def record_evaluation(
        self,
        query: str,
        answer: str,
        contexts: List[str],
        ground_truth: str,
        metrics: RAGASMetrics,
        latency_ms: float,
        metadata: Dict[str, Any] = None
    ) -> EvaluationRecord:
        """记录评估结果"""
        record = EvaluationRecord(
            record_id=f"eval_{int(time.time() * 1000)}",
            timestamp=datetime.now(),
            query=query,
            ground_truth=ground_truth,
            answer=answer,
            contexts=contexts,
            metrics=metrics,
            latency_ms=latency_ms,
            metadata=metadata or {}
        )
        
        self._records.append(record)
        
        if len(self._records) > self._max_records:
            self._records = self._records[-self._max_records:]
        
        return record
    
    def get_statistics(self, limit: int = 100) -> Dict[str, Any]:
        """获取统计信息"""
        recent = self._records[-limit:]
        
        if not recent:
            return {"message": "No evaluation records"}
        
        total = len(recent)
        
        avg_metrics = RAGASMetrics()
        
        for record in recent:
            m = record.metrics
            avg_metrics.faithfulness += m.faithfulness
            avg_metrics.answer_relevancy += m.answer_relevancy
            avg_metrics.context_precision += m.context_precision
            avg_metrics.context_recall += m.context_recall
            avg_metrics.answer_similarity += m.answer_similarity
            avg_metrics.answer_correctness += m.answer_correctness
        
        avg_metrics.faithfulness /= total
        avg_metrics.answer_relevancy /= total
        avg_metrics.context_precision /= total
        avg_metrics.context_recall /= total
        avg_metrics.answer_similarity /= total
        avg_metrics.answer_correctness /= total
        
        return {
            "total_records": total,
            "avg_metrics": avg_metrics.to_dict(),
            "overall_score": avg_metrics.avg_score(),
            "avg_latency_ms": sum(r.latency_ms for r in recent) / total,
            "time_range": {
                "start": recent[0].timestamp.isoformat(),
                "end": recent[-1].timestamp.isoformat()
            }
        }


class RAGMonitor:
    """RAG在线监控器"""
    
    def __init__(self):
        self._metrics = MonitorMetrics()
        self._callbacks: List[Callable] = []
        self._alert_thresholds = {
            "error_rate": 0.1,
            "avg_latency_ms": 5000,
            "faithfulness": 0.5,
            "answer_relevancy": 0.5
        }
    
    def register_callback(self, callback: Callable):
        """注册回调"""
        self._callbacks.append(callback)
    
    def record_request(
        self,
        success: bool,
        latency_ms: float,
        error_type: str = None,
        metrics: RAGASMetrics = None
    ):
        """记录请求"""
        self._metrics.total_requests += 1
        
        if success:
            self._metrics.successful_requests += 1
        else:
            self._metrics.failed_requests += 1
            if error_type:
                self._metrics.error_types[error_type] = \
                    self._metrics.error_types.get(error_type, 0) + 1
        
        self._update_avg_latency(latency_ms)
        
        if metrics:
            self._update_metrics(metrics)
        
        self._metrics.last_update = datetime.now()
        
        self._check_alerts()
    
    def _update_avg_latency(self, latency_ms: float):
        """更新平均延迟"""
        total = self._metrics.total_requests
        current_avg = self._metrics.avg_latency_ms
        
        self._metrics.avg_latency_ms = (
            (current_avg * (total - 1) + latency_ms) / total
        )
    
    def _update_metrics(self, metrics: RAGASMetrics):
        """更新评估指标"""
        total = len(self._records) + 1
        
        m = self._metrics.avg_metrics
        rec = metrics
        
        m.faithfulness = (m.faithfulness * (total - 1) + rec.faithfulness) / total
        m.answer_relevancy = (m.answer_relevancy * (total - 1) + rec.answer_relevancy) / total
        m.context_precision = (m.context_precision * (total - 1) + rec.context_precision) / total
    
    def _check_alerts(self):
        """检查告警条件"""
        total = self._metrics.total_requests
        if total == 0:
            return
        
        error_rate = self._metrics.failed_requests / total
        
        if error_rate > self._alert_thresholds["error_rate"]:
            self._trigger_alert("error_rate", error_rate)
        
        if self._metrics.avg_latency_ms > self._alert_thresholds["avg_latency_ms"]:
            self._trigger_alert("latency", self._metrics.avg_latency_ms)
    
    def _trigger_alert(self, alert_type: str, value: float):
        """触发告警"""
        alert = {
            "type": alert_type,
            "value": value,
            "timestamp": datetime.now().isoformat()
        }
        
        app_logger.warning(f"RAG Alert: {alert}")
        
        for callback in self._callbacks:
            try:
                callback(alert)
            except Exception as e:
                app_logger.error(f"Alert callback failed: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """获取监控状态"""
        total = self._metrics.total_requests
        error_rate = self._metrics.failed_requests / total if total > 0 else 0
        success_rate = self._metrics.successful_requests / total if total > 0 else 0
        
        return {
            "status": "healthy" if error_rate < 0.1 else "degraded",
            "total_requests": total,
            "successful_requests": self._metrics.successful_requests,
            "failed_requests": self._metrics.failed_requests,
            "success_rate": success_rate,
            "error_rate": error_rate,
            "avg_latency_ms": self._metrics.avg_latency_ms,
            "avg_metrics": self._metrics.avg_metrics.to_dict(),
            "error_types": self._metrics.error_types,
            "last_update": self._metrics.last_update.isoformat()
        }
    
    def reset(self):
        """重置监控数据"""
        self._metrics = MonitorMetrics()


_ragas_evaluator: Optional[RAGASEvaluator] = None
_rag_monitor: Optional[RAGMonitor] = None


def get_ragas_evaluator() -> RAGASEvaluator:
    """获取RAGAS评估器"""
    global _ragas_evaluator
    if _ragas_evaluator is None:
        _ragas_evaluator = RAGASEvaluator()
    return _ragas_evaluator


def get_rag_monitor() -> RAGMonitor:
    """获取RAG监控器"""
    global _rag_monitor
    if _rag_monitor is None:
        _rag_monitor = RAGMonitor()
    return _rag_monitor


async def evaluate_rag_response(
    query: str,
    answer: str,
    contexts: List[str],
    ground_truth: str = None,
    record: bool = True
) -> Dict[str, Any]:
    """
    便捷函数：评估 RAG 响应质量
    
    Args:
        query: 用户问题
        answer: 生成的答案
        contexts: 检索到的上下文
        ground_truth: 标准答案（可选）
        record: 是否记录评估结果
        
    Returns:
        评估结果字典
    """
    evaluator = get_ragas_evaluator()
    monitor = get_rag_monitor()
    
    start_time = time.time()
    metrics = await evaluator.evaluate(
        query=query,
        answer=answer,
        contexts=contexts,
        ground_truth=ground_truth
    )
    latency_ms = (time.time() - start_time) * 1000
    
    # 记录评估结果
    if record:
        evaluator.record_evaluation(
            query=query,
            answer=answer,
            contexts=contexts,
            ground_truth=ground_truth or "",
            metrics=metrics,
            latency_ms=latency_ms
        )
    
    # 更新监控指标
    monitor.record_request(
        success=True,
        latency_ms=latency_ms,
        metrics=metrics
    )
    
    return {
        "query": query,
        "answer": answer,
        "metrics": metrics.to_dict(),
        "avg_score": metrics.avg_score(),
        "latency_ms": latency_ms,
        "timestamp": datetime.now().isoformat()
    }


async def evaluate_batch(
    items: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    批量评估
    
    Args:
        items: 待评估的项目列表，每个项目包含 query, answer, contexts, ground_truth
        
    Returns:
        评估结果列表
    """
    results = []
    for item in items:
        result = await evaluate_rag_response(
            query=item["query"],
            answer=item["answer"],
            contexts=item["contexts"],
            ground_truth=item.get("ground_truth"),
            record=item.get("record", True)
        )
        results.append(result)
    return results


def get_evaluation_statistics(limit: int = 100) -> Dict[str, Any]:
    """
    获取评估统计信息
    
    Args:
        limit: 最近记录数限制
        
    Returns:
        统计信息字典
    """
    evaluator = get_ragas_evaluator()
    monitor = get_rag_monitor()
    
    return {
        "statistics": evaluator.get_statistics(limit=limit),
        "monitor_status": monitor.get_status()
    }
