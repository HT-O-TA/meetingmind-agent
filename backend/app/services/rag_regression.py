"""RAG回归测试 + 基准数据集"""
import json
import time
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from app.core.logger import app_logger
from app.core.config import settings


class TestType(str, Enum):
    """测试类型"""
    UNIT = "unit"
    INTEGRATION = "integration"
    E2E = "e2e"
    REGRESSION = "regression"
    PERFORMANCE = "performance"


class TestStatus(str, Enum):
    """测试状态"""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TestCase:
    """测试用例"""
    case_id: str
    name: str
    description: str
    test_type: TestType
    query: str
    ground_truth: str
    expected_metrics: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "name": self.name,
            "description": self.description,
            "test_type": self.test_type.value,
            "query": self.query,
            "ground_truth": self.ground_truth,
            "expected_metrics": self.expected_metrics,
            "metadata": self.metadata
        }


@dataclass
class TestResult:
    """测试结果"""
    case_id: str
    status: TestStatus
    execution_time_ms: float
    answer: str
    contexts: List[str] = field(default_factory=list)
    actual_metrics: Dict[str, float] = field(default_factory=dict)
    error: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    
    def passed(self) -> bool:
        return self.status == TestStatus.PASSED
    
    def get_pass_rate(self, expected: Dict[str, float]) -> float:
        if not expected:
            return 1.0 if self.status == TestStatus.PASSED else 0.0
        
        rates = []
        for metric, expected_val in expected.items():
            actual_val = self.actual_metrics.get(metric, 0.0)
            if expected_val > 0:
                rate = min(actual_val / expected_val, 1.0)
            else:
                rate = 1.0 if actual_val == 0 else 0.0
            rates.append(rate)
        
        return sum(rates) / len(rates) if rates else 0.0


@dataclass
class RegressionReport:
    """回归测试报告"""
    report_id: str
    timestamp: datetime
    duration_ms: float
    total_cases: int
    passed_cases: int
    failed_cases: int
    results: List[TestResult]
    baseline_metrics: Dict[str, float] = field(default_factory=dict)
    current_metrics: Dict[str, float] = field(default_factory=dict)
    regressions: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "pass_rate": self.passed_cases / self.total_cases if self.total_cases > 0 else 0.0,
            "baseline_metrics": self.baseline_metrics,
            "current_metrics": self.current_metrics,
            "regressions": self.regressions,
            "improvements": self.improvements
        }


class RAGBenchmarkDataset:
    """RAG基准数据集"""
    
    def __init__(self):
        self._test_cases: List[TestCase] = []
        self._load_default_cases()
    
    def _load_default_cases(self):
        """加载默认测试用例"""
        self._test_cases = [
            TestCase(
                case_id="bench_001",
                name="会议总结-基本",
                description="测试会议总结生成能力",
                test_type=TestType.REGRESSION,
                query="总结今天会议的主要内容",
                ground_truth="会议主要讨论了项目进度和下一步计划",
                expected_metrics={
                    "faithfulness": 0.8,
                    "answer_relevancy": 0.8,
                    "context_precision": 0.7
                }
            ),
            TestCase(
                case_id="bench_002",
                name="待办提取-基本",
                description="测试待办事项提取能力",
                test_type=TestType.REGRESSION,
                query="会议中有哪些待办事项？谁负责？",
                ground_truth="待办：张三负责修复bug，李四负责准备PPT",
                expected_metrics={
                    "faithfulness": 0.85,
                    "answer_relevancy": 0.85
                }
            ),
            TestCase(
                case_id="bench_003",
                name="问答-事实性",
                description="测试事实性问题回答",
                test_type=TestType.REGRESSION,
                query="会议讨论了哪些项目？",
                ground_truth="讨论了项目A和项目B",
                expected_metrics={
                    "faithfulness": 0.9,
                    "answer_relevancy": 0.85,
                    "answer_correctness": 0.85
                }
            ),
            TestCase(
                case_id="bench_004",
                name="问答-对比性",
                description="测试对比性问题",
                test_type=TestType.INTEGRATION,
                query="项目A和项目B的进度有什么区别？",
                ground_truth="项目A已完成80%，项目B正在测试中",
                expected_metrics={
                    "faithfulness": 0.8,
                    "answer_relevancy": 0.8,
                    "context_recall": 0.75
                }
            ),
            TestCase(
                case_id="bench_005",
                name="问答-推理性",
                description="测试推理问题",
                test_type=TestType.INTEGRATION,
                query="为什么项目B需要优先修复？",
                ground_truth="因为项目B有bug影响上线，需要尽快修复",
                expected_metrics={
                    "faithfulness": 0.75,
                    "answer_relevancy": 0.75,
                    "context_recall": 0.7
                }
            ),
            TestCase(
                case_id="bench_006",
                name="搜索-精确",
                description="测试精确信息检索",
                test_type=TestType.REGRESSION,
                query="项目A的开发进度是多少？",
                ground_truth="项目A完成了80%",
                expected_metrics={
                    "context_precision": 0.85,
                    "faithfulness": 0.9
                }
            ),
            TestCase(
                case_id="bench_007",
                name="决策提取",
                description="测试会议决策提取",
                test_type=TestType.REGRESSION,
                query="会议做出了哪些决定？",
                ground_truth="决定：1.优先修复bug 2.发布会推迟",
                expected_metrics={
                    "faithfulness": 0.85,
                    "answer_relevancy": 0.85,
                    "context_recall": 0.8
                }
            ),
            TestCase(
                case_id="bench_008",
                name="人员识别",
                description="测试参会人员识别",
                test_type=TestType.UNIT,
                query="谁参加了会议？",
                ground_truth="张三、李四、王五",
                expected_metrics={
                    "answer_correctness": 0.9,
                    "faithfulness": 0.9
                }
            ),
            TestCase(
                case_id="bench_009",
                name="时间识别",
                description="测试关键时间点识别",
                test_type=TestType.UNIT,
                query="下次会议是什么时候？",
                ground_truth="下周三",
                expected_metrics={
                    "faithfulness": 0.85,
                    "answer_relevancy": 0.8
                }
            ),
            TestCase(
                case_id="bench_010",
                name="综合问答",
                description="测试综合信息问答",
                test_type=TestType.E2E,
                query="请详细介绍会议的各个方面",
                ground_truth="包含主题、参会人员、讨论内容、决议、待办等",
                expected_metrics={
                    "answer_relevancy": 0.75,
                    "context_recall": 0.7,
                    "context_precision": 0.7
                }
            )
        ]
    
    def add_case(self, case: TestCase):
        """添加测试用例"""
        self._test_cases.append(case)
    
    def get_cases(
        self,
        test_type: TestType = None,
        limit: int = None
    ) -> List[TestCase]:
        """获取测试用例"""
        cases = self._test_cases
        
        if test_type:
            cases = [c for c in cases if c.test_type == test_type]
        
        if limit:
            cases = cases[:limit]
        
        return cases
    
    def save(self, filepath: str):
        """保存到文件"""
        data = [case.to_dict() for case in self._test_cases]
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def load(self, filepath: str):
        """从文件加载"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self._test_cases = []
        for item in data:
            self._test_cases.append(TestCase(
                case_id=item["case_id"],
                name=item["name"],
                description=item["description"],
                test_type=TestType(item["test_type"]),
                query=item["query"],
                ground_truth=item["ground_truth"],
                expected_metrics=item.get("expected_metrics", {}),
                metadata=item.get("metadata", {})
            ))


class RAGRegressionTester:
    """RAG回归测试器"""
    
    def __init__(
        self,
        rag_pipeline: Callable = None,
        evaluator = None,
        baseline: Dict[str, float] = None
    ):
        self._pipeline = rag_pipeline or self._get_default_pipeline()
        self._evaluator = evaluator or self._get_default_evaluator()
        self._baseline = baseline or {}
        self._dataset = RAGBenchmarkDataset()
    
    def _get_default_pipeline(self) -> Callable:
        """获取默认的 RAG pipeline"""
        from app.services.rag_service import RAGService
        from app.services.vector_search_service import VectorSearchService
        
        async def rag_pipeline(query: str) -> Dict[str, Any]:
            """默认的 RAG pipeline 执行函数"""
            vector_service = VectorSearchService()
            rag_service = RAGService(vector_service)
            result = await rag_service.ask(question=query, top_k=settings.TOP_K_DEFAULT)
            return {
                "answer": result.get("answer", ""),
                "contexts": [c.get("chunk_text", "") for c in result.get("chunks", [])]
            }
        
        return rag_pipeline
    
    def _get_default_evaluator(self):
        """获取默认的评估器"""
        try:
            from app.services.ragas_evaluator import get_ragas_evaluator
            return get_ragas_evaluator()
        except Exception as e:
            app_logger.warning(f"无法加载 RAGAS 评估器: {e}")
            return None
    
    def set_baseline(self, metrics: Dict[str, float]):
        """设置基准指标"""
        self._baseline = metrics
    
    async def run_test(
        self,
        case: TestCase,
        enable_eval: bool = True
    ) -> TestResult:
        """运行单个测试"""
        start_time = time.time()
        
        try:
            result = await self._pipeline(case.query)
            
            answer = result.get("answer", "")
            contexts = result.get("contexts", [])
            
            execution_time = (time.time() - start_time) * 1000
            
            actual_metrics = {}
            
            if enable_eval and self._evaluator:
                metrics = await self._evaluator.evaluate(
                    query=case.query,
                    answer=answer,
                    contexts=contexts,
                    ground_truth=case.ground_truth
                )
                actual_metrics = metrics.to_dict()
            
            passed = True
            if case.expected_metrics:
                for metric, expected in case.expected_metrics.items():
                    actual = actual_metrics.get(metric, 0.0)
                    if actual < expected * 0.8:
                        passed = False
                        break
            
            return TestResult(
                case_id=case.case_id,
                status=TestStatus.PASSED if passed else TestStatus.FAILED,
                execution_time_ms=execution_time,
                answer=answer,
                contexts=contexts,
                actual_metrics=actual_metrics
            )
            
        except Exception as e:
            app_logger.error(f"Test case {case.case_id} failed: {e}")
            
            return TestResult(
                case_id=case.case_id,
                status=TestStatus.ERROR,
                execution_time_ms=(time.time() - start_time) * 1000,
                answer="",
                error=str(e)
            )
    
    async def run_regression(
        self,
        test_types: List[TestType] = None
    ) -> RegressionReport:
        """运行回归测试"""
        start_time = time.time()
        
        cases = self._dataset.get_cases()
        
        if test_types:
            cases = [c for c in cases if c.test_type in test_types]
        
        results = []
        
        for case in cases:
            result = await self.run_test(case)
            results.append(result)
        
        passed_cases = sum(1 for r in results if r.passed())
        failed_cases = len(results) - passed_cases
        
        current_metrics = self._calc_avg_metrics(results)
        
        regressions, improvements = self._compare_with_baseline(
            self._baseline,
            current_metrics
        )
        
        duration = (time.time() - start_time) * 1000
        
        return RegressionReport(
            report_id=f"reg_{int(time.time() * 1000)}",
            timestamp=datetime.now(),
            duration_ms=duration,
            total_cases=len(results),
            passed_cases=passed_cases,
            failed_cases=failed_cases,
            results=results,
            baseline_metrics=self._baseline,
            current_metrics=current_metrics,
            regressions=regressions,
            improvements=improvements
        )
    
    def _calc_avg_metrics(self, results: List[TestResult]) -> Dict[str, float]:
        """计算平均指标"""
        metrics_sum: Dict[str, float] = {}
        metrics_count: Dict[str, int] = {}
        
        for result in results:
            for metric, value in result.actual_metrics.items():
                metrics_sum[metric] = metrics_sum.get(metric, 0.0) + value
                metrics_count[metric] = metrics_count.get(metric, 0) + 1
        
        return {
            metric: metrics_sum[metric] / metrics_count[metric]
            for metric in metrics_sum
        }
    
    def _compare_with_baseline(
        self,
        baseline: Dict[str, float],
        current: Dict[str, float]
    ) -> tuple:
        """对比基准指标"""
        regressions = []
        improvements = []
        
        all_metrics = set(baseline.keys()) | set(current.keys())
        
        for metric in all_metrics:
            base = baseline.get(metric, 0)
            curr = current.get(metric, 0)
            
            if base > 0:
                change = (curr - base) / base
                
                if change < -0.05:
                    regressions.append(
                        f"{metric}: {base:.3f} -> {curr:.3f} ({change*100:.1f}%)"
                    )
                elif change > 0.05:
                    improvements.append(
                        f"{metric}: {base:.3f} -> {curr:.3f} ({change*100:+.1f}%)"
                    )
        
        return regressions, improvements
    
    def save_baseline(self, filepath: str):
        """保存基准"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self._baseline, f, indent=2)
    
    def load_baseline(self, filepath: str):
        """加载基准"""
        with open(filepath, 'r', encoding='utf-8') as f:
            self._baseline = json.load(f)


class ContinuousMonitor:
    """持续监控"""
    
    def __init__(self, regression_tester: RAGRegressionTester):
        self._tester = regression_tester
        self._history: List[RegressionReport] = []
        self._alert_callbacks: List[Callable] = []
    
    def register_alert(self, callback: Callable):
        """注册告警回调"""
        self._alert_callbacks.append(callback)
    
    async def run_periodic_check(
        self,
        interval_seconds: int = 3600
    ):
        """定期检查"""
        while True:
            report = await self._tester.run_regression()
            self._history.append(report)
            
            if report.regressions:
                self._trigger_alerts(report)
            
            if len(self._history) > 100:
                self._history = self._history[-100:]
            
            await self._sleep(interval_seconds)
    
    def _trigger_alerts(self, report: RegressionReport):
        """触发告警"""
        alert = {
            "type": "regression_detected",
            "report": report.to_dict(),
            "timestamp": datetime.now().isoformat()
        }
        
        for callback in self._alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                app_logger.error(f"Alert callback failed: {e}")
    
    def _sleep(self, seconds: int):
        """休眠"""
        import asyncio
        return asyncio.sleep(seconds)
    
    def get_trends(self, metric: str, limit: int = 30) -> List[float]:
        """获取指标趋势"""
        values = []
        
        for report in self._history[-limit:]:
            value = report.current_metrics.get(metric, 0.0)
            values.append(value)
        
        return values
    
    def get_summary(self) -> Dict[str, Any]:
        """获取监控摘要"""
        if not self._history:
            return {"message": "No data available"}
        
        latest = self._history[-1]
        
        return {
            "latest_report": latest.to_dict(),
            "total_checks": len(self._history),
            "avg_pass_rate": sum(
                r.passed_cases / r.total_cases
                for r in self._history
            ) / len(self._history),
            "regression_count": sum(len(r.regressions) for r in self._history)
        }


_rag_benchmark_dataset: Optional[RAGBenchmarkDataset] = None
_rag_regression_tester: Optional[RAGRegressionTester] = None


def get_rag_benchmark_dataset() -> RAGBenchmarkDataset:
    """获取RAG基准数据集"""
    global _rag_benchmark_dataset
    if _rag_benchmark_dataset is None:
        _rag_benchmark_dataset = RAGBenchmarkDataset()
    return _rag_benchmark_dataset


def get_rag_regression_tester() -> RAGRegressionTester:
    """获取RAG回归测试器"""
    global _rag_regression_tester
    if _rag_regression_tester is None:
        _rag_regression_tester = RAGRegressionTester()
    return _rag_regression_tester


async def run_regression_test(test_types: List[TestType] = None) -> Dict[str, Any]:
    """
    便捷函数：运行回归测试
    
    Args:
        test_types: 测试类型列表（可选）
        
    Returns:
        回归测试报告（字典格式）
    """
    tester = get_rag_regression_tester()
    report = await tester.run_regression(test_types=test_types)
    return report.to_dict()


async def run_single_test(case_id: str) -> Dict[str, Any]:
    """
    便捷函数：运行单个测试用例
    
    Args:
        case_id: 测试用例ID
        
    Returns:
        测试结果（字典格式）
    """
    tester = get_rag_regression_tester()
    dataset = get_rag_benchmark_dataset()
    cases = dataset.get_cases()
    case = next((c for c in cases if c.case_id == case_id), None)
    
    if not case:
        return {"error": f"测试用例 {case_id} 不存在"}
    
    result = await tester.run_test(case)
    return {
        "case": case.to_dict(),
        "result": {
            "status": result.status.value,
            "execution_time_ms": result.execution_time_ms,
            "answer": result.answer,
            "actual_metrics": result.actual_metrics,
            "error": result.error
        }
    }


async def establish_baseline() -> Dict[str, Any]:
    """
    建立基准指标
    
    Returns:
        基准指标字典
    """
    tester = get_rag_regression_tester()
    report = await tester.run_regression()
    baseline = report.current_metrics
    tester.set_baseline(baseline)
    
    # 保存基准到文件
    baseline_path = settings.BASELINE_FILE or "rag_baseline.json"
    tester.save_baseline(baseline_path)
    
    app_logger.info(f"基准已建立并保存到 {baseline_path}")
    return {"baseline": baseline, "report": report.to_dict()}
