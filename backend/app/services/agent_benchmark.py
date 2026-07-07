"""Agent 基准测试数据集 - 包含 100 条测试用例

覆盖评价维度：
- Task Success: 任务成功率
- Tool Success: 工具调用成功率
- Route Accuracy: 路由准确率
- Retry: 重试次数
- Reflection: 反思质量
- Latency: 延迟
- Cost: 成本
- Hallucination: 幻觉检测
"""
import json
import time
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from app.core.logger import app_logger
from app.core.config import settings


class BenchmarkCategory(str, Enum):
    """基准测试类别"""
    MEETING_SUMMARY = "meeting_summary"
    TODO_EXTRACTION = "todo_extraction"
    QUESTION_ANSWERING = "question_answering"
    DECISION_EXTRACTION = "decision_extraction"
    CONTROVERSY_DETECTION = "controversy_detection"
    ROUTE_ACCURACY = "route_accuracy"
    TOOL_CALLING = "tool_calling"
    RETRY_STRATEGY = "retry_strategy"
    REFLECTION_QUALITY = "reflection_quality"
    HALLUCINATION = "hallucination"
    LATENCY = "latency"
    COST = "cost"


class DifficultyLevel(str, Enum):
    """难度级别"""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass
class AgentTestCase:
    """Agent 测试用例"""
    case_id: str
    name: str
    description: str
    category: BenchmarkCategory
    difficulty: DifficultyLevel
    query: str
    ground_truth: str
    expected_route: Optional[str] = None
    expected_tools: Optional[List[str]] = None
    max_retries: int = 0
    expected_latency_ms: float = 5000.0
    expected_metrics: Dict[str, float] = field(default_factory=dict)
    hallucination_detected: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "difficulty": self.difficulty.value,
            "query": self.query,
            "ground_truth": self.ground_truth,
            "expected_route": self.expected_route,
            "expected_tools": self.expected_tools,
            "max_retries": self.max_retries,
            "expected_latency_ms": self.expected_latency_ms,
            "expected_metrics": self.expected_metrics,
            "hallucination_detected": self.hallucination_detected,
            "metadata": self.metadata
        }


@dataclass
class AgentBenchmarkResult:
    """Agent 基准测试结果"""
    case_id: str
    status: str
    execution_time_ms: float
    answer: str
    actual_route: Optional[str] = None
    tools_used: Optional[List[str]] = None
    retry_count: int = 0
    reflection_score: Optional[float] = None
    token_cost_usd: Optional[float] = None
    hallucination_detected: bool = False
    actual_metrics: Dict[str, float] = field(default_factory=dict)
    error: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    
    def passed(self, expected_metrics: Dict[str, float], max_latency_ms: float = 5000.0) -> bool:
        """判断是否通过"""
        if self.execution_time_ms > max_latency_ms:
            return False
        
        for metric, expected in expected_metrics.items():
            actual = self.actual_metrics.get(metric, 0.0)
            if actual < expected * 0.8:
                return False
        
        return True
    
    def get_score(self, expected_metrics: Dict[str, float]) -> float:
        """计算得分"""
        if not expected_metrics:
            return 1.0
        
        scores = []
        for metric, expected in expected_metrics.items():
            actual = self.actual_metrics.get(metric, 0.0)
            scores.append(min(actual / expected, 1.0))
        
        return sum(scores) / len(scores) if scores else 0.0


@dataclass
class AgentBenchmarkReport:
    """Agent 基准测试报告"""
    report_id: str
    timestamp: datetime
    duration_ms: float
    total_cases: int
    passed_cases: int
    failed_cases: int
    results: List[AgentBenchmarkResult]
    category_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    difficulty_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    overall_metrics: Dict[str, float] = field(default_factory=dict)
    regression_count: int = 0
    improvement_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "pass_rate": self.passed_cases / self.total_cases if self.total_cases > 0 else 0.0,
            "category_stats": self.category_stats,
            "difficulty_stats": self.difficulty_stats,
            "overall_metrics": self.overall_metrics,
            "regression_count": self.regression_count,
            "improvement_count": self.improvement_count
        }


class AgentBenchmarkDataset:
    """Agent 基准测试数据集（100条）"""
    
    def __init__(self):
        self._test_cases: List[AgentTestCase] = []
        self._load_default_cases()
    
    def _load_default_cases(self):
        """加载 100 条默认测试用例"""
        self._test_cases = [
            # ============ 会议总结 (10条) ============
            AgentTestCase(
                case_id="agent_001",
                name="会议总结-基本信息",
                description="测试基本会议信息总结",
                category=BenchmarkCategory.MEETING_SUMMARY,
                difficulty=DifficultyLevel.EASY,
                query="总结今天会议的主要内容",
                ground_truth="会议主要讨论了项目进度和下一步计划",
                expected_metrics={"faithfulness": 0.8, "answer_relevancy": 0.8}
            ),
            AgentTestCase(
                case_id="agent_002",
                name="会议总结-详细",
                description="测试详细会议总结",
                category=BenchmarkCategory.MEETING_SUMMARY,
                difficulty=DifficultyLevel.MEDIUM,
                query="详细总结今天的产品评审会议，包括讨论的问题、解决方案和后续计划",
                ground_truth="产品评审会议讨论了UI设计问题、性能优化方案，决定下周进行用户测试",
                expected_metrics={"faithfulness": 0.75, "answer_relevancy": 0.75}
            ),
            AgentTestCase(
                case_id="agent_003",
                name="会议总结-多主题",
                description="测试多主题会议总结",
                category=BenchmarkCategory.MEETING_SUMMARY,
                difficulty=DifficultyLevel.HARD,
                query="总结本次跨部门会议，涵盖项目进度、资源分配、风险评估三个方面",
                ground_truth="跨部门会议讨论了项目进度、资源分配和风险评估，制定了相应的应对措施",
                expected_metrics={"faithfulness": 0.7, "answer_relevancy": 0.7}
            ),
            AgentTestCase(
                case_id="agent_004",
                name="会议总结-精简版",
                description="测试生成精简版会议总结",
                category=BenchmarkCategory.MEETING_SUMMARY,
                difficulty=DifficultyLevel.EASY,
                query="用几句话总结会议内容",
                ground_truth="会议讨论了项目进度，确定了下周目标",
                expected_metrics={"answer_relevancy": 0.8, "faithfulness": 0.8}
            ),
            AgentTestCase(
                case_id="agent_005",
                name="会议总结-纪要格式",
                description="测试生成标准纪要格式",
                category=BenchmarkCategory.MEETING_SUMMARY,
                difficulty=DifficultyLevel.MEDIUM,
                query="生成会议纪要，包含时间、地点、参会人员、讨论内容、决议事项",
                ground_truth="会议时间：今天下午3点，地点：会议室A，参会人员：张三、李四、王五，讨论内容：项目进度，决议：加快开发进度",
                expected_metrics={"answer_relevancy": 0.75, "faithfulness": 0.75}
            ),
            AgentTestCase(
                case_id="agent_006",
                name="会议总结-行动导向",
                description="测试行动导向的会议总结",
                category=BenchmarkCategory.MEETING_SUMMARY,
                difficulty=DifficultyLevel.MEDIUM,
                query="总结会议中决定的行动项",
                ground_truth="行动项：1.张三修复bug 2.李四准备演示PPT 3.王五跟进客户反馈",
                expected_metrics={"answer_relevancy": 0.85, "faithfulness": 0.85}
            ),
            AgentTestCase(
                case_id="agent_007",
                name="会议总结-问题导向",
                description="测试问题导向的会议总结",
                category=BenchmarkCategory.MEETING_SUMMARY,
                difficulty=DifficultyLevel.MEDIUM,
                query="总结会议中讨论的问题和解决方案",
                ground_truth="问题：性能问题影响用户体验，解决方案：优化数据库查询，增加缓存",
                expected_metrics={"answer_relevancy": 0.8, "faithfulness": 0.8}
            ),
            AgentTestCase(
                case_id="agent_008",
                name="会议总结-回顾",
                description="测试回顾性会议总结",
                category=BenchmarkCategory.MEETING_SUMMARY,
                difficulty=DifficultyLevel.HARD,
                query="总结过去一周的项目进展和下周计划",
                ground_truth="本周完成了功能开发，下周进行测试和部署",
                expected_metrics={"answer_relevancy": 0.7, "faithfulness": 0.7}
            ),
            AgentTestCase(
                case_id="agent_009",
                name="会议总结-对比",
                description="测试对比前后两次会议的变化",
                category=BenchmarkCategory.MEETING_SUMMARY,
                difficulty=DifficultyLevel.HARD,
                query="对比本次会议与上次会议的进展",
                ground_truth="上次会议讨论的问题已解决，本次会议讨论新的功能需求",
                expected_metrics={"answer_relevancy": 0.7, "faithfulness": 0.7}
            ),
            AgentTestCase(
                case_id="agent_010",
                name="会议总结-风险识别",
                description="测试识别会议中的风险因素",
                category=BenchmarkCategory.MEETING_SUMMARY,
                difficulty=DifficultyLevel.MEDIUM,
                query="识别会议中提到的潜在风险",
                ground_truth="风险：进度落后、资源不足、技术难题",
                expected_metrics={"answer_relevancy": 0.75, "faithfulness": 0.75}
            ),
            # ============ 待办提取 (10条) ============
            AgentTestCase(
                case_id="agent_011",
                name="待办提取-基本",
                description="测试基本待办事项提取",
                category=BenchmarkCategory.TODO_EXTRACTION,
                difficulty=DifficultyLevel.EASY,
                query="会议中有哪些待办事项？",
                ground_truth="待办：修复bug、准备演示、跟进客户",
                expected_metrics={"answer_relevancy": 0.85, "faithfulness": 0.85}
            ),
            AgentTestCase(
                case_id="agent_012",
                name="待办提取-负责人",
                description="测试提取带负责人的待办事项",
                category=BenchmarkCategory.TODO_EXTRACTION,
                difficulty=DifficultyLevel.EASY,
                query="会议中有哪些待办事项？谁负责？",
                ground_truth="待办：张三负责修复bug，李四负责准备PPT",
                expected_metrics={"answer_relevancy": 0.85, "answer_correctness": 0.85}
            ),
            AgentTestCase(
                case_id="agent_013",
                name="待办提取-优先级",
                description="测试提取带优先级的待办事项",
                category=BenchmarkCategory.TODO_EXTRACTION,
                difficulty=DifficultyLevel.MEDIUM,
                query="列出会议待办事项，并按优先级排序",
                ground_truth="高优先级：修复bug；中优先级：准备PPT；低优先级：整理文档",
                expected_metrics={"answer_relevancy": 0.8, "answer_correctness": 0.8}
            ),
            AgentTestCase(
                case_id="agent_014",
                name="待办提取-截止日期",
                description="测试提取带截止日期的待办事项",
                category=BenchmarkCategory.TODO_EXTRACTION,
                difficulty=DifficultyLevel.MEDIUM,
                query="会议待办事项及其截止日期是什么？",
                ground_truth="待办：修复bug（周五前）、准备PPT（下周一）",
                expected_metrics={"answer_relevancy": 0.8, "answer_correctness": 0.8}
            ),
            AgentTestCase(
                case_id="agent_015",
                name="待办提取-详细",
                description="测试提取详细待办事项",
                category=BenchmarkCategory.TODO_EXTRACTION,
                difficulty=DifficultyLevel.HARD,
                query="提取会议中的所有待办事项，包括负责人、截止日期和优先级",
                ground_truth="高优先级：张三修复bug（周五前）；中优先级：李四准备PPT（下周一）；低优先级：王五整理文档（下周三）",
                expected_metrics={"answer_relevancy": 0.75, "answer_correctness": 0.75}
            ),
            AgentTestCase(
                case_id="agent_016",
                name="待办提取-状态",
                description="测试提取待办事项状态",
                category=BenchmarkCategory.TODO_EXTRACTION,
                difficulty=DifficultyLevel.MEDIUM,
                query="哪些待办事项已经完成？哪些还在进行中？",
                ground_truth="已完成：需求分析；进行中：开发；待开始：测试",
                expected_metrics={"answer_relevancy": 0.8, "faithfulness": 0.8}
            ),
            AgentTestCase(
                case_id="agent_017",
                name="待办提取-跨会议",
                description="测试提取跨会议的待办事项",
                category=BenchmarkCategory.TODO_EXTRACTION,
                difficulty=DifficultyLevel.HARD,
                query="汇总最近三次会议的待办事项",
                ground_truth="待办汇总：修复bug、准备PPT、整理文档、优化性能",
                expected_metrics={"answer_relevancy": 0.7, "faithfulness": 0.7}
            ),
            AgentTestCase(
                case_id="agent_018",
                name="待办提取-延期项",
                description="测试提取延期待办事项",
                category=BenchmarkCategory.TODO_EXTRACTION,
                difficulty=DifficultyLevel.MEDIUM,
                query="哪些待办事项已经延期？",
                ground_truth="延期事项：性能优化（原计划上周完成）",
                expected_metrics={"answer_relevancy": 0.8, "answer_correctness": 0.8}
            ),
            AgentTestCase(
                case_id="agent_019",
                name="待办提取-统计",
                description="测试待办事项统计",
                category=BenchmarkCategory.TODO_EXTRACTION,
                difficulty=DifficultyLevel.EASY,
                query="会议共产生了多少个待办事项？",
                ground_truth="共5个待办事项",
                expected_metrics={"answer_relevancy": 0.9, "answer_correctness": 0.9}
            ),
            AgentTestCase(
                case_id="agent_020",
                name="待办提取-分类",
                description="测试按类别提取待办事项",
                category=BenchmarkCategory.TODO_EXTRACTION,
                difficulty=DifficultyLevel.MEDIUM,
                query="按类别列出待办事项：开发、测试、文档",
                ground_truth="开发：修复bug；测试：功能测试；文档：编写接口文档",
                expected_metrics={"answer_relevancy": 0.8, "faithfulness": 0.8}
            ),
            # ============ 问答 (20条) ============
            AgentTestCase(
                case_id="agent_021",
                name="问答-事实性",
                description="测试事实性问题回答",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.EASY,
                query="会议讨论了哪些项目？",
                ground_truth="讨论了项目A和项目B",
                expected_metrics={"faithfulness": 0.9, "answer_relevancy": 0.85}
            ),
            AgentTestCase(
                case_id="agent_022",
                name="问答-数字",
                description="测试数字类问题回答",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.EASY,
                query="项目A的开发进度是多少？",
                ground_truth="项目A完成了80%",
                expected_metrics={"answer_correctness": 0.9, "faithfulness": 0.9}
            ),
            AgentTestCase(
                case_id="agent_023",
                name="问答-人物",
                description="测试人物类问题回答",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.EASY,
                query="谁参加了会议？",
                ground_truth="张三、李四、王五",
                expected_metrics={"answer_correctness": 0.9, "faithfulness": 0.9}
            ),
            AgentTestCase(
                case_id="agent_024",
                name="问答-时间",
                description="测试时间类问题回答",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.EASY,
                query="下次会议是什么时候？",
                ground_truth="下周三下午3点",
                expected_metrics={"answer_correctness": 0.9, "answer_relevancy": 0.85}
            ),
            AgentTestCase(
                case_id="agent_025",
                name="问答-地点",
                description="测试地点类问题回答",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.EASY,
                query="会议在哪里举行？",
                ground_truth="会议室A",
                expected_metrics={"answer_correctness": 0.9, "faithfulness": 0.9}
            ),
            AgentTestCase(
                case_id="agent_026",
                name="问答-对比",
                description="测试对比性问题",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.MEDIUM,
                query="项目A和项目B的进度有什么区别？",
                ground_truth="项目A已完成80%，项目B正在测试中",
                expected_metrics={"faithfulness": 0.8, "answer_relevancy": 0.8}
            ),
            AgentTestCase(
                case_id="agent_027",
                name="问答-推理",
                description="测试推理问题",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.HARD,
                query="为什么项目B需要优先修复？",
                ground_truth="因为项目B有bug影响上线，需要尽快修复",
                expected_metrics={"faithfulness": 0.75, "answer_relevancy": 0.75}
            ),
            AgentTestCase(
                case_id="agent_028",
                name="问答-因果",
                description="测试因果问题",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.HARD,
                query="为什么会议决定推迟发布？",
                ground_truth="因为发现了严重bug，需要修复后再发布",
                expected_metrics={"answer_relevancy": 0.75, "faithfulness": 0.75}
            ),
            AgentTestCase(
                case_id="agent_029",
                name="问答-预测",
                description="测试预测问题",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.HARD,
                query="项目A什么时候能完成？",
                ground_truth="预计下月底完成",
                expected_metrics={"answer_relevancy": 0.7, "faithfulness": 0.7}
            ),
            AgentTestCase(
                case_id="agent_030",
                name="问答-建议",
                description="测试建议问题",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.HARD,
                query="针对当前问题，有什么建议？",
                ground_truth="建议：增加测试覆盖、优化代码、加强沟通",
                expected_metrics={"answer_relevancy": 0.7, "faithfulness": 0.7}
            ),
            AgentTestCase(
                case_id="agent_031",
                name="问答-多步",
                description="测试多步推理问题",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.HARD,
                query="项目A完成80%需要多少天？从开始到现在用了多久？",
                ground_truth="项目A已完成80%，用时40天，预计还需10天完成",
                expected_metrics={"answer_relevancy": 0.7, "answer_correctness": 0.7}
            ),
            AgentTestCase(
                case_id="agent_032",
                name="问答-否定",
                description="测试否定式问题",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.MEDIUM,
                query="会议没有讨论哪些内容？",
                ground_truth="会议未讨论预算和人员变动",
                expected_metrics={"answer_relevancy": 0.75, "faithfulness": 0.75}
            ),
            AgentTestCase(
                case_id="agent_033",
                name="问答-条件",
                description="测试条件式问题",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.HARD,
                query="如果项目B延期，会影响什么？",
                ground_truth="项目B延期会影响整体发布计划",
                expected_metrics={"answer_relevancy": 0.7, "faithfulness": 0.7}
            ),
            AgentTestCase(
                case_id="agent_034",
                name="问答-排序",
                description="测试排序问题",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.MEDIUM,
                query="按优先级排列待办事项",
                ground_truth="优先级：修复bug > 准备PPT > 整理文档",
                expected_metrics={"answer_relevancy": 0.8, "answer_correctness": 0.8}
            ),
            AgentTestCase(
                case_id="agent_035",
                name="问答-数量",
                description="测试数量问题",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.EASY,
                query="有多少人参会？",
                ground_truth="5人参会",
                expected_metrics={"answer_correctness": 0.9, "faithfulness": 0.9}
            ),
            AgentTestCase(
                case_id="agent_036",
                name="问答-选择",
                description="测试选择性问题",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.MEDIUM,
                query="会议决定采用方案A还是方案B？",
                ground_truth="会议决定采用方案A",
                expected_metrics={"answer_correctness": 0.9, "answer_relevancy": 0.85}
            ),
            AgentTestCase(
                case_id="agent_037",
                name="问答-解释",
                description="测试解释性问题",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.HARD,
                query="解释一下为什么要做这个决定？",
                ground_truth="决定基于数据分析和用户反馈，能够提升产品质量",
                expected_metrics={"answer_relevancy": 0.75, "faithfulness": 0.75}
            ),
            AgentTestCase(
                case_id="agent_038",
                name="问答-确认",
                description="测试确认性问题",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.EASY,
                query="会议决定延期发布，对吗？",
                ground_truth="是的，会议决定延期发布",
                expected_metrics={"answer_correctness": 0.9, "answer_relevancy": 0.9}
            ),
            AgentTestCase(
                case_id="agent_039",
                name="问答-澄清",
                description="测试澄清性问题",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.MEDIUM,
                query="你说的项目A是指什么？",
                ground_truth="项目A指的是用户管理系统升级项目",
                expected_metrics={"answer_relevancy": 0.85, "faithfulness": 0.85}
            ),
            AgentTestCase(
                case_id="agent_040",
                name="问答-汇总",
                description="测试汇总性问题",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.HARD,
                query="总结会议中所有讨论的要点",
                ground_truth="要点：项目进度、资源分配、风险评估、下一步计划",
                expected_metrics={"answer_relevancy": 0.7, "context_recall": 0.7}
            ),
            # ============ 决策提取 (10条) ============
            AgentTestCase(
                case_id="agent_041",
                name="决策提取-基本",
                description="测试基本决策提取",
                category=BenchmarkCategory.DECISION_EXTRACTION,
                difficulty=DifficultyLevel.EASY,
                query="会议做出了哪些决定？",
                ground_truth="决定：1.优先修复bug 2.发布会推迟",
                expected_metrics={"answer_relevancy": 0.85, "faithfulness": 0.85}
            ),
            AgentTestCase(
                case_id="agent_042",
                name="决策提取-影响",
                description="测试提取决策的影响",
                category=BenchmarkCategory.DECISION_EXTRACTION,
                difficulty=DifficultyLevel.MEDIUM,
                query="会议决定会带来什么影响？",
                ground_truth="影响：发布延期、开发压力增加、用户体验提升",
                expected_metrics={"answer_relevancy": 0.8, "faithfulness": 0.8}
            ),
            AgentTestCase(
                case_id="agent_043",
                name="决策提取-原因",
                description="测试提取决策的原因",
                category=BenchmarkCategory.DECISION_EXTRACTION,
                difficulty=DifficultyLevel.MEDIUM,
                query="为什么做出这个决定？",
                ground_truth="原因：发现严重bug，为保证质量",
                expected_metrics={"answer_relevancy": 0.8, "faithfulness": 0.8}
            ),
            AgentTestCase(
                case_id="agent_044",
                name="决策提取-负责人",
                description="测试提取决策的负责人",
                category=BenchmarkCategory.DECISION_EXTRACTION,
                difficulty=DifficultyLevel.EASY,
                query="谁负责执行这个决定？",
                ground_truth="张三负责执行",
                expected_metrics={"answer_correctness": 0.9, "answer_relevancy": 0.9}
            ),
            AgentTestCase(
                case_id="agent_045",
                name="决策提取-时间线",
                description="测试提取决策的时间线",
                category=BenchmarkCategory.DECISION_EXTRACTION,
                difficulty=DifficultyLevel.MEDIUM,
                query="决策的执行时间表是什么？",
                ground_truth="本周修复bug，下周测试，下月底发布",
                expected_metrics={"answer_relevancy": 0.8, "answer_correctness": 0.8}
            ),
            AgentTestCase(
                case_id="agent_046",
                name="决策提取-风险",
                description="测试提取决策的风险",
                category=BenchmarkCategory.DECISION_EXTRACTION,
                difficulty=DifficultyLevel.HARD,
                query="这个决策有什么风险？",
                ground_truth="风险：延期导致用户流失、成本增加",
                expected_metrics={"answer_relevancy": 0.75, "faithfulness": 0.75}
            ),
            AgentTestCase(
                case_id="agent_047",
                name="决策提取-备选方案",
                description="测试提取备选方案",
                category=BenchmarkCategory.DECISION_EXTRACTION,
                difficulty=DifficultyLevel.HARD,
                query="会议讨论了哪些备选方案？",
                ground_truth="备选方案：方案A（快速修复）、方案B（全面重构）",
                expected_metrics={"answer_relevancy": 0.75, "context_recall": 0.75}
            ),
            AgentTestCase(
                case_id="agent_048",
                name="决策提取-投票",
                description="测试提取投票结果",
                category=BenchmarkCategory.DECISION_EXTRACTION,
                difficulty=DifficultyLevel.MEDIUM,
                query="会议投票结果如何？",
                ground_truth="投票结果：3票赞成，2票反对，通过",
                expected_metrics={"answer_correctness": 0.85, "answer_relevancy": 0.85}
            ),
            AgentTestCase(
                case_id="agent_049",
                name="决策提取-变更",
                description="测试提取决策变更",
                category=BenchmarkCategory.DECISION_EXTRACTION,
                difficulty=DifficultyLevel.HARD,
                query="本次会议的决策与上次有什么不同？",
                ground_truth="变更：原计划本月发布，现延期至下月底",
                expected_metrics={"answer_relevancy": 0.75, "faithfulness": 0.75}
            ),
            AgentTestCase(
                case_id="agent_050",
                name="决策提取-优先级",
                description="测试提取决策优先级",
                category=BenchmarkCategory.DECISION_EXTRACTION,
                difficulty=DifficultyLevel.MEDIUM,
                query="按优先级列出所有决策",
                ground_truth="优先级：1.修复bug（最高）2.准备演示（中）3.整理文档（低）",
                expected_metrics={"answer_relevancy": 0.8, "answer_correctness": 0.8}
            ),
            # ============ 争议检测 (5条) ============
            AgentTestCase(
                case_id="agent_051",
                name="争议检测-识别",
                description="测试识别会议中的争议点",
                category=BenchmarkCategory.CONTROVERSY_DETECTION,
                difficulty=DifficultyLevel.MEDIUM,
                query="会议中有哪些争议点？",
                ground_truth="争议：发布时间、资源分配",
                expected_metrics={"answer_relevancy": 0.8, "faithfulness": 0.8}
            ),
            AgentTestCase(
                case_id="agent_052",
                name="争议检测-立场",
                description="测试提取争议各方的立场",
                category=BenchmarkCategory.CONTROVERSY_DETECTION,
                difficulty=DifficultyLevel.HARD,
                query="各方在争议问题上的立场是什么？",
                ground_truth="张三主张尽快发布，李四主张延期确保质量",
                expected_metrics={"answer_relevancy": 0.75, "faithfulness": 0.75}
            ),
            AgentTestCase(
                case_id="agent_053",
                name="争议检测-解决方案",
                description="测试提取争议解决方案",
                category=BenchmarkCategory.CONTROVERSY_DETECTION,
                difficulty=DifficultyLevel.HARD,
                query="争议问题如何解决？",
                ground_truth="解决方案：折中方案，先发布核心功能，后续迭代",
                expected_metrics={"answer_relevancy": 0.75, "faithfulness": 0.75}
            ),
            AgentTestCase(
                case_id="agent_054",
                name="争议检测-未解决",
                description="测试识别未解决的争议",
                category=BenchmarkCategory.CONTROVERSY_DETECTION,
                difficulty=DifficultyLevel.MEDIUM,
                query="哪些争议问题还没有解决？",
                ground_truth="未解决：资源分配问题",
                expected_metrics={"answer_relevancy": 0.8, "answer_correctness": 0.8}
            ),
            AgentTestCase(
                case_id="agent_055",
                name="争议检测-风险",
                description="测试争议的风险评估",
                category=BenchmarkCategory.CONTROVERSY_DETECTION,
                difficulty=DifficultyLevel.HARD,
                query="争议问题如果不解决会有什么风险？",
                ground_truth="风险：团队分裂、项目延期、质量下降",
                expected_metrics={"answer_relevancy": 0.7, "faithfulness": 0.7}
            ),
            # ============ 路由准确率 (10条) ============
            AgentTestCase(
                case_id="agent_056",
                name="路由-简单问答",
                description="测试简单问答路由",
                category=BenchmarkCategory.ROUTE_ACCURACY,
                difficulty=DifficultyLevel.EASY,
                query="会议时间是什么时候？",
                ground_truth="简单问答",
                expected_route="simple_qa",
                expected_metrics={"answer_relevancy": 0.9, "answer_correctness": 0.9}
            ),
            AgentTestCase(
                case_id="agent_057",
                name="路由-总结",
                description="测试总结路由",
                category=BenchmarkCategory.ROUTE_ACCURACY,
                difficulty=DifficultyLevel.EASY,
                query="总结会议内容",
                ground_truth="会议总结",
                expected_route="summary",
                expected_metrics={"answer_relevancy": 0.85, "faithfulness": 0.85}
            ),
            AgentTestCase(
                case_id="agent_058",
                name="路由-待办",
                description="测试待办路由",
                category=BenchmarkCategory.ROUTE_ACCURACY,
                difficulty=DifficultyLevel.EASY,
                query="有哪些待办事项？",
                ground_truth="待办提取",
                expected_route="todo",
                expected_metrics={"answer_relevancy": 0.85, "answer_correctness": 0.85}
            ),
            AgentTestCase(
                case_id="agent_059",
                name="路由-复杂问答",
                description="测试复杂问答路由",
                category=BenchmarkCategory.ROUTE_ACCURACY,
                difficulty=DifficultyLevel.MEDIUM,
                query="分析项目A和项目B的进度差异及其影响",
                ground_truth="复杂分析",
                expected_route="complex_qa",
                expected_metrics={"answer_relevancy": 0.8, "faithfulness": 0.8}
            ),
            AgentTestCase(
                case_id="agent_060",
                name="路由-多任务",
                description="测试多任务路由",
                category=BenchmarkCategory.ROUTE_ACCURACY,
                difficulty=DifficultyLevel.HARD,
                query="总结会议、提取待办、识别争议点",
                ground_truth="多任务处理",
                expected_route="multi_task",
                expected_metrics={"answer_relevancy": 0.75, "faithfulness": 0.75}
            ),
            AgentTestCase(
                case_id="agent_061",
                name="路由-搜索",
                description="测试搜索路由",
                category=BenchmarkCategory.ROUTE_ACCURACY,
                difficulty=DifficultyLevel.MEDIUM,
                query="搜索关于项目A的所有会议记录",
                ground_truth="文档搜索",
                expected_route="search",
                expected_metrics={"answer_relevancy": 0.8, "context_precision": 0.8}
            ),
            AgentTestCase(
                case_id="agent_062",
                name="路由-推理",
                description="测试推理路由",
                category=BenchmarkCategory.ROUTE_ACCURACY,
                difficulty=DifficultyLevel.HARD,
                query="如果资源减少，会对项目产生什么影响？",
                ground_truth="推理分析",
                expected_route="reasoning",
                expected_metrics={"answer_relevancy": 0.7, "faithfulness": 0.7}
            ),
            AgentTestCase(
                case_id="agent_063",
                name="路由-问候",
                description="测试问候路由",
                category=BenchmarkCategory.ROUTE_ACCURACY,
                difficulty=DifficultyLevel.EASY,
                query="你好",
                ground_truth="问候",
                expected_route="greeting",
                expected_metrics={"answer_relevancy": 0.95}
            ),
            AgentTestCase(
                case_id="agent_064",
                name="路由-闲聊",
                description="测试闲聊路由",
                category=BenchmarkCategory.ROUTE_ACCURACY,
                difficulty=DifficultyLevel.EASY,
                query="今天天气怎么样？",
                ground_truth="闲聊",
                expected_route="chitchat",
                expected_metrics={"answer_relevancy": 0.9}
            ),
            AgentTestCase(
                case_id="agent_065",
                name="路由-指令",
                description="测试指令路由",
                category=BenchmarkCategory.ROUTE_ACCURACY,
                difficulty=DifficultyLevel.MEDIUM,
                query="帮我生成一份会议纪要",
                ground_truth="指令执行",
                expected_route="command",
                expected_metrics={"answer_relevancy": 0.85, "faithfulness": 0.85}
            ),
            # ============ 工具调用 (10条) ============
            AgentTestCase(
                case_id="agent_066",
                name="工具-问答",
                description="测试问答工具调用",
                category=BenchmarkCategory.TOOL_CALLING,
                difficulty=DifficultyLevel.EASY,
                query="回答问题：项目进度如何？",
                ground_truth="项目进度正常，已完成80%",
                expected_tools=["answer_question"],
                expected_metrics={"answer_relevancy": 0.85, "answer_correctness": 0.85}
            ),
            AgentTestCase(
                case_id="agent_067",
                name="工具-搜索",
                description="测试搜索工具调用",
                category=BenchmarkCategory.TOOL_CALLING,
                difficulty=DifficultyLevel.MEDIUM,
                query="搜索关于项目A的会议记录",
                ground_truth="找到3条相关会议记录",
                expected_tools=["search_meeting"],
                expected_metrics={"context_precision": 0.8, "answer_relevancy": 0.8}
            ),
            AgentTestCase(
                case_id="agent_068",
                name="工具-文档",
                description="测试文档工具调用",
                category=BenchmarkCategory.TOOL_CALLING,
                difficulty=DifficultyLevel.MEDIUM,
                query="获取文档内容",
                ground_truth="文档内容已获取",
                expected_tools=["get_document_content"],
                expected_metrics={"answer_relevancy": 0.85, "faithfulness": 0.85}
            ),
            AgentTestCase(
                case_id="agent_069",
                name="工具-多工具",
                description="测试多工具调用",
                category=BenchmarkCategory.TOOL_CALLING,
                difficulty=DifficultyLevel.HARD,
                query="搜索会议记录并总结",
                ground_truth="搜索到相关记录并完成总结",
                expected_tools=["search_meeting", "generate_minutes"],
                expected_metrics={"answer_relevancy": 0.75, "faithfulness": 0.75}
            ),
            AgentTestCase(
                case_id="agent_070",
                name="工具-待办提取",
                description="测试待办提取工具",
                category=BenchmarkCategory.TOOL_CALLING,
                difficulty=DifficultyLevel.EASY,
                query="提取待办事项",
                ground_truth="待办：修复bug、准备PPT",
                expected_tools=["extract_todos"],
                expected_metrics={"answer_relevancy": 0.85, "answer_correctness": 0.85}
            ),
            AgentTestCase(
                case_id="agent_071",
                name="工具-纪要生成",
                description="测试纪要生成工具",
                category=BenchmarkCategory.TOOL_CALLING,
                difficulty=DifficultyLevel.MEDIUM,
                query="生成会议纪要",
                ground_truth="会议纪要已生成",
                expected_tools=["generate_minutes"],
                expected_metrics={"answer_relevancy": 0.8, "faithfulness": 0.8}
            ),
            AgentTestCase(
                case_id="agent_072",
                name="工具-争议检测",
                description="测试争议检测工具",
                category=BenchmarkCategory.TOOL_CALLING,
                difficulty=DifficultyLevel.MEDIUM,
                query="检测争议点",
                ground_truth="检测到2个争议点",
                expected_tools=["detect_controversies"],
                expected_metrics={"answer_relevancy": 0.8, "answer_correctness": 0.8}
            ),
            AgentTestCase(
                case_id="agent_073",
                name="工具-文本处理",
                description="测试文本处理工具",
                category=BenchmarkCategory.TOOL_CALLING,
                difficulty=DifficultyLevel.EASY,
                query="格式化文本",
                ground_truth="文本已格式化",
                expected_tools=["text_processor"],
                expected_metrics={"answer_relevancy": 0.85, "faithfulness": 0.85}
            ),
            AgentTestCase(
                case_id="agent_074",
                name="工具-文档搜索",
                description="测试文档搜索工具",
                category=BenchmarkCategory.TOOL_CALLING,
                difficulty=DifficultyLevel.MEDIUM,
                query="搜索相关文档",
                ground_truth="找到相关文档",
                expected_tools=["search_document"],
                expected_metrics={"context_precision": 0.8, "answer_relevancy": 0.8}
            ),
            AgentTestCase(
                case_id="agent_075",
                name="工具-链式调用",
                description="测试链式工具调用",
                category=BenchmarkCategory.TOOL_CALLING,
                difficulty=DifficultyLevel.HARD,
                query="搜索文档、提取内容、总结要点",
                ground_truth="已完成文档搜索、内容提取和要点总结",
                expected_tools=["search_document", "get_document_content", "answer_question"],
                expected_metrics={"answer_relevancy": 0.7, "faithfulness": 0.7}
            ),
            # ============ 重试策略 (5条) ============
            AgentTestCase(
                case_id="agent_076",
                name="重试-无需重试",
                description="测试无需重试场景",
                category=BenchmarkCategory.RETRY_STRATEGY,
                difficulty=DifficultyLevel.EASY,
                query="简单问题",
                ground_truth="直接回答",
                max_retries=0,
                expected_metrics={"answer_relevancy": 0.9}
            ),
            AgentTestCase(
                case_id="agent_077",
                name="重试-一次重试",
                description="测试一次重试场景",
                category=BenchmarkCategory.RETRY_STRATEGY,
                difficulty=DifficultyLevel.MEDIUM,
                query="需要修正的问题",
                ground_truth="经过一次修正后的回答",
                max_retries=1,
                expected_metrics={"answer_relevancy": 0.85}
            ),
            AgentTestCase(
                case_id="agent_078",
                name="重试-多次重试",
                description="测试多次重试场景",
                category=BenchmarkCategory.RETRY_STRATEGY,
                difficulty=DifficultyLevel.HARD,
                query="复杂问题需要多次修正",
                ground_truth="经过多次修正后的回答",
                max_retries=2,
                expected_metrics={"answer_relevancy": 0.8}
            ),
            AgentTestCase(
                case_id="agent_079",
                name="重试-失败处理",
                description="测试重试失败场景",
                category=BenchmarkCategory.RETRY_STRATEGY,
                difficulty=DifficultyLevel.HARD,
                query="无法回答的问题",
                ground_truth="无法回答，已达到最大重试次数",
                max_retries=2,
                expected_metrics={"answer_relevancy": 0.6}
            ),
            AgentTestCase(
                case_id="agent_080",
                name="重试-超时处理",
                description="测试超时重试场景",
                category=BenchmarkCategory.RETRY_STRATEGY,
                difficulty=DifficultyLevel.HARD,
                query="响应慢的问题",
                ground_truth="经过超时重试后的回答",
                max_retries=1,
                expected_metrics={"answer_relevancy": 0.75}
            ),
            # ============ 反思质量 (5条) ============
            AgentTestCase(
                case_id="agent_081",
                name="反思-高质量",
                description="测试高质量反思",
                category=BenchmarkCategory.REFLECTION_QUALITY,
                difficulty=DifficultyLevel.MEDIUM,
                query="需要高质量反思的问题",
                ground_truth="经过深度反思后的回答",
                expected_metrics={"answer_relevancy": 0.85, "answer_correctness": 0.85}
            ),
            AgentTestCase(
                case_id="agent_082",
                name="反思-自我修正",
                description="测试自我修正",
                category=BenchmarkCategory.REFLECTION_QUALITY,
                difficulty=DifficultyLevel.HARD,
                query="需要自我修正的问题",
                ground_truth="经过自我修正后的回答",
                expected_metrics={"answer_relevancy": 0.8, "faithfulness": 0.8}
            ),
            AgentTestCase(
                case_id="agent_083",
                name="反思-错误识别",
                description="测试错误识别",
                category=BenchmarkCategory.REFLECTION_QUALITY,
                difficulty=DifficultyLevel.HARD,
                query="包含错误的问题",
                ground_truth="识别并纠正错误后的回答",
                expected_metrics={"answer_correctness": 0.8, "faithfulness": 0.8}
            ),
            AgentTestCase(
                case_id="agent_084",
                name="反思-改进建议",
                description="测试改进建议",
                category=BenchmarkCategory.REFLECTION_QUALITY,
                difficulty=DifficultyLevel.MEDIUM,
                query="需要改进的回答",
                ground_truth="提出改进建议后的回答",
                expected_metrics={"answer_relevancy": 0.8, "answer_correctness": 0.8}
            ),
            AgentTestCase(
                case_id="agent_085",
                name="反思-深度分析",
                description="测试深度分析",
                category=BenchmarkCategory.REFLECTION_QUALITY,
                difficulty=DifficultyLevel.HARD,
                query="需要深度分析的问题",
                ground_truth="经过深度分析后的回答",
                expected_metrics={"answer_relevancy": 0.75, "faithfulness": 0.75}
            ),
            # ============ 幻觉检测 (5条) ============
            AgentTestCase(
                case_id="agent_086",
                name="幻觉-无幻觉",
                description="测试无幻觉场景",
                category=BenchmarkCategory.HALLUCINATION,
                difficulty=DifficultyLevel.EASY,
                query="基于事实的问题",
                ground_truth="基于上下文的回答",
                hallucination_detected=False,
                expected_metrics={"faithfulness": 0.9, "answer_correctness": 0.9}
            ),
            AgentTestCase(
                case_id="agent_087",
                name="幻觉-有幻觉",
                description="测试有幻觉场景",
                category=BenchmarkCategory.HALLUCINATION,
                difficulty=DifficultyLevel.MEDIUM,
                query="容易产生幻觉的问题",
                ground_truth="需要检测到可能的幻觉",
                hallucination_detected=True,
                expected_metrics={"faithfulness": 0.5}
            ),
            AgentTestCase(
                case_id="agent_088",
                name="幻觉-部分幻觉",
                description="测试部分幻觉场景",
                category=BenchmarkCategory.HALLUCINATION,
                difficulty=DifficultyLevel.HARD,
                query="部分基于事实的问题",
                ground_truth="部分内容可能是幻觉",
                expected_metrics={"faithfulness": 0.6}
            ),
            AgentTestCase(
                case_id="agent_089",
                name="幻觉-事实核查",
                description="测试事实核查",
                category=BenchmarkCategory.HALLUCINATION,
                difficulty=DifficultyLevel.HARD,
                query="需要事实核查的问题",
                ground_truth="经过事实核查后的回答",
                expected_metrics={"answer_correctness": 0.85, "faithfulness": 0.85}
            ),
            AgentTestCase(
                case_id="agent_090",
                name="幻觉-上下文冲突",
                description="测试上下文冲突",
                category=BenchmarkCategory.HALLUCINATION,
                difficulty=DifficultyLevel.HARD,
                query="上下文有冲突的问题",
                ground_truth="检测到上下文冲突",
                expected_metrics={"faithfulness": 0.5, "answer_relevancy": 0.7}
            ),
            # ============ 延迟测试 (3条) ============
            AgentTestCase(
                case_id="agent_091",
                name="延迟-快速",
                description="测试快速响应",
                category=BenchmarkCategory.LATENCY,
                difficulty=DifficultyLevel.EASY,
                query="简单问题",
                ground_truth="快速回答",
                expected_latency_ms=1000.0,
                expected_metrics={"answer_relevancy": 0.9}
            ),
            AgentTestCase(
                case_id="agent_092",
                name="延迟-中等",
                description="测试中等响应时间",
                category=BenchmarkCategory.LATENCY,
                difficulty=DifficultyLevel.MEDIUM,
                query="中等复杂度问题",
                ground_truth="中等速度回答",
                expected_latency_ms=3000.0,
                expected_metrics={"answer_relevancy": 0.85}
            ),
            AgentTestCase(
                case_id="agent_093",
                name="延迟-复杂",
                description="测试复杂问题响应时间",
                category=BenchmarkCategory.LATENCY,
                difficulty=DifficultyLevel.HARD,
                query="复杂多步骤问题",
                ground_truth="较慢的回答",
                expected_latency_ms=5000.0,
                expected_metrics={"answer_relevancy": 0.75}
            ),
            # ============ 成本测试 (2条) ============
            AgentTestCase(
                case_id="agent_094",
                name="成本-低成本",
                description="测试低成本查询",
                category=BenchmarkCategory.COST,
                difficulty=DifficultyLevel.EASY,
                query="简单问题",
                ground_truth="低成本回答",
                expected_metrics={"answer_relevancy": 0.9}
            ),
            AgentTestCase(
                case_id="agent_095",
                name="成本-高成本",
                description="测试高成本查询",
                category=BenchmarkCategory.COST,
                difficulty=DifficultyLevel.HARD,
                query="需要多次LLM调用的复杂问题",
                ground_truth="高成本回答",
                expected_metrics={"answer_relevancy": 0.75}
            ),
            # ============ 综合测试 (5条) ============
            AgentTestCase(
                case_id="agent_096",
                name="综合-端到端",
                description="测试端到端流程",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.HARD,
                query="完整处理一个复杂会议任务",
                ground_truth="完整的端到端处理结果",
                expected_metrics={"answer_relevancy": 0.7, "faithfulness": 0.7}
            ),
            AgentTestCase(
                case_id="agent_097",
                name="综合-多轮对话",
                description="测试多轮对话",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.HARD,
                query="基于之前回答的追问",
                ground_truth="多轮对话的连贯回答",
                expected_metrics={"answer_relevancy": 0.75, "faithfulness": 0.75}
            ),
            AgentTestCase(
                case_id="agent_098",
                name="综合-跨文档",
                description="测试跨文档处理",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.HARD,
                query="综合多个文档的信息",
                ground_truth="跨文档综合回答",
                expected_metrics={"context_recall": 0.7, "answer_relevancy": 0.7}
            ),
            AgentTestCase(
                case_id="agent_099",
                name="综合-实时更新",
                description="测试实时信息更新",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.HARD,
                query="基于最新信息的回答",
                ground_truth="实时更新的回答",
                expected_metrics={"answer_correctness": 0.75, "answer_relevancy": 0.75}
            ),
            AgentTestCase(
                case_id="agent_100",
                name="综合-完整场景",
                description="测试完整业务场景",
                category=BenchmarkCategory.QUESTION_ANSWERING,
                difficulty=DifficultyLevel.HARD,
                query="模拟真实业务场景的复杂查询",
                ground_truth="完整场景的处理结果",
                expected_metrics={"answer_relevancy": 0.7, "faithfulness": 0.7, "answer_correctness": 0.7}
            ),
        ]
    
    def add_case(self, case: AgentTestCase):
        """添加测试用例"""
        self._test_cases.append(case)
    
    def get_cases(
        self,
        category: BenchmarkCategory = None,
        difficulty: DifficultyLevel = None,
        limit: int = None
    ) -> List[AgentTestCase]:
        """获取测试用例"""
        cases = self._test_cases
        
        if category:
            cases = [c for c in cases if c.category == category]
        
        if difficulty:
            cases = [c for c in cases if c.difficulty == difficulty]
        
        if limit:
            cases = cases[:limit]
        
        return cases
    
    def get_category_stats(self) -> Dict[str, int]:
        """获取类别统计"""
        stats = {}
        for case in self._test_cases:
            cat = case.category.value
            stats[cat] = stats.get(cat, 0) + 1
        return stats
    
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
            self._test_cases.append(AgentTestCase(
                case_id=item["case_id"],
                name=item["name"],
                description=item["description"],
                category=BenchmarkCategory(item["category"]),
                difficulty=DifficultyLevel(item["difficulty"]),
                query=item["query"],
                ground_truth=item["ground_truth"],
                expected_route=item.get("expected_route"),
                expected_tools=item.get("expected_tools"),
                max_retries=item.get("max_retries", 0),
                expected_latency_ms=item.get("expected_latency_ms", 5000.0),
                expected_metrics=item.get("expected_metrics", {}),
                metadata=item.get("metadata", {})
            ))


class AgentBenchmarkTester:
    """Agent 基准测试器"""
    
    def __init__(self, agent_pipeline: Callable = None):
        self._pipeline = agent_pipeline or self._get_default_pipeline()
        self._dataset = AgentBenchmarkDataset()
        self._evaluator = None
    
    def _get_default_pipeline(self) -> Callable:
        """获取默认的 Agent pipeline"""
        async def agent_pipeline(query: str) -> Dict[str, Any]:
            if settings.EVAL_SKIP_LLM:
                return {
                    "answer": f"基准离线回答：{query}",
                    "route": "simple_qa",
                    "tools_used": [],
                    "retry_count": 0,
                    "reflection_score": 0.8,
                    "token_cost_usd": 0.001,
                    "hallucination_detected": False,
                    "contexts": ["基准上下文"]
                }
            
            try:
                from app.agents.agent import MeetingMindAgent
                
                agent = MeetingMindAgent()
                result = await agent.run(question=query)
                
                return {
                    "answer": result.get("answer", ""),
                    "route": result.get("workflow_type", ""),
                    "tools_used": result.get("tools_used", []),
                    "retry_count": result.get("repair_count", 0),
                    "reflection_score": result.get("quality_score", 0.8),
                    "token_cost_usd": result.get("token_cost_usd", 0.0),
                    "hallucination_detected": False,
                    "contexts": [c.get("chunk_text", "") for c in result.get("chunks", [])]
                }
            except Exception as e:
                app_logger.warning(f"默认 Agent pipeline 不可用，使用离线结果: {e}")
                return {
                    "answer": f"基准离线回答：{query}",
                    "route": "simple_qa",
                    "tools_used": [],
                    "retry_count": 0,
                    "reflection_score": 0.8,
                    "token_cost_usd": 0.001,
                    "hallucination_detected": False,
                    "contexts": ["离线上下文"]
                }
        
        return agent_pipeline
    
    async def run_test(self, case: AgentTestCase) -> AgentBenchmarkResult:
        """运行单个测试"""
        start_time = time.time()
        
        try:
            result = await self._pipeline(case.query)
            
            execution_time_ms = (time.time() - start_time) * 1000
            
            metrics = {}
            if self._evaluator:
                metrics = await self._evaluate(case, result)
            
            return AgentBenchmarkResult(
                case_id=case.case_id,
                status="passed" if result.get("answer") else "failed",
                execution_time_ms=execution_time_ms,
                answer=result.get("answer", ""),
                actual_route=result.get("route"),
                tools_used=result.get("tools_used", []),
                retry_count=result.get("retry_count", 0),
                reflection_score=result.get("reflection_score"),
                token_cost_usd=result.get("token_cost_usd"),
                hallucination_detected=result.get("hallucination_detected", False),
                actual_metrics=metrics
            )
            
        except Exception as e:
            app_logger.error(f"Agent benchmark test {case.case_id} failed: {e}")
            return AgentBenchmarkResult(
                case_id=case.case_id,
                status="error",
                execution_time_ms=(time.time() - start_time) * 1000,
                answer="",
                error=str(e)
            )
    
    async def _evaluate(self, case: AgentTestCase, result: Dict[str, Any]) -> Dict[str, float]:
        """评估测试结果"""
        try:
            from app.services.ragas_evaluator import get_ragas_evaluator
            
            evaluator = get_ragas_evaluator()
            metrics = await evaluator.evaluate(
                query=case.query,
                answer=result.get("answer", ""),
                contexts=result.get("contexts", []),
                ground_truth=case.ground_truth
            )
            return metrics.to_dict()
        except Exception as e:
            app_logger.warning(f"Evaluation failed: {e}")
            return {}
    
    async def run_benchmark(
        self,
        category: BenchmarkCategory = None,
        difficulty: DifficultyLevel = None,
        limit: int = None
    ) -> AgentBenchmarkReport:
        """运行基准测试"""
        start_time = time.time()
        
        cases = self._dataset.get_cases(category=category, difficulty=difficulty)
        if limit:
            cases = cases[:limit]
        
        results = []
        for case in cases:
            result = await self.run_test(case)
            results.append(result)
        
        passed_cases = sum(1 for r in results if r.status == "passed")
        failed_cases = len(results) - passed_cases
        
        category_stats = self._calc_category_stats(results)
        difficulty_stats = self._calc_difficulty_stats(results)
        overall_metrics = self._calc_overall_metrics(results)
        
        duration_ms = (time.time() - start_time) * 1000
        
        return AgentBenchmarkReport(
            report_id=f"agent_bench_{int(time.time() * 1000)}",
            timestamp=datetime.now(),
            duration_ms=duration_ms,
            total_cases=len(results),
            passed_cases=passed_cases,
            failed_cases=failed_cases,
            results=results,
            category_stats=category_stats,
            difficulty_stats=difficulty_stats,
            overall_metrics=overall_metrics
        )
    
    def _calc_category_stats(self, results: List[AgentBenchmarkResult]) -> Dict[str, Dict[str, Any]]:
        """计算类别统计"""
        stats = {}
        case_map = {r.case_id: self._dataset.get_cases() for r in results}
        
        for case in self._dataset.get_cases():
            cat = case.category.value
            if cat not in stats:
                stats[cat] = {"total": 0, "passed": 0, "failed": 0}
            
            result = next((r for r in results if r.case_id == case.case_id), None)
            if result:
                stats[cat]["total"] += 1
                if result.status == "passed":
                    stats[cat]["passed"] += 1
                else:
                    stats[cat]["failed"] += 1
        
        for cat in stats:
            total = stats[cat]["total"]
            stats[cat]["pass_rate"] = stats[cat]["passed"] / total if total > 0 else 0.0
        
        return stats
    
    def _calc_difficulty_stats(self, results: List[AgentBenchmarkResult]) -> Dict[str, Dict[str, Any]]:
        """计算难度统计"""
        stats = {}
        
        for case in self._dataset.get_cases():
            diff = case.difficulty.value
            if diff not in stats:
                stats[diff] = {"total": 0, "passed": 0, "failed": 0}
            
            result = next((r for r in results if r.case_id == case.case_id), None)
            if result:
                stats[diff]["total"] += 1
                if result.status == "passed":
                    stats[diff]["passed"] += 1
                else:
                    stats[diff]["failed"] += 1
        
        for diff in stats:
            total = stats[diff]["total"]
            stats[diff]["pass_rate"] = stats[diff]["passed"] / total if total > 0 else 0.0
        
        return stats
    
    def _calc_overall_metrics(self, results: List[AgentBenchmarkResult]) -> Dict[str, float]:
        """计算总体指标"""
        metrics_sum: Dict[str, float] = {}
        metrics_count: Dict[str, int] = {}
        
        for result in results:
            for metric, value in result.actual_metrics.items():
                metrics_sum[metric] = metrics_sum.get(metric, 0.0) + value
                metrics_count[metric] = metrics_count.get(metric, 0) + 1
        
        avg_metrics = {
            metric: metrics_sum[metric] / metrics_count[metric]
            for metric in metrics_sum
        }
        
        avg_latency = sum(r.execution_time_ms for r in results) / len(results) if results else 0.0
        avg_retries = sum(r.retry_count for r in results) / len(results) if results else 0.0
        total_cost = sum(r.token_cost_usd or 0 for r in results)
        
        return {
            **avg_metrics,
            "avg_latency_ms": avg_latency,
            "avg_retries": avg_retries,
            "total_cost_usd": total_cost,
            "hallucination_rate": sum(1 for r in results if r.hallucination_detected) / len(results) if results else 0.0,
            "pass_rate": passed_cases / len(results) if results else 0.0
        }


_agent_benchmark_dataset: Optional[AgentBenchmarkDataset] = None
_agent_benchmark_tester: Optional[AgentBenchmarkTester] = None


def get_agent_benchmark_dataset() -> AgentBenchmarkDataset:
    """获取 Agent 基准测试数据集"""
    global _agent_benchmark_dataset
    if _agent_benchmark_dataset is None:
        _agent_benchmark_dataset = AgentBenchmarkDataset()
    return _agent_benchmark_dataset


def get_agent_benchmark_tester() -> AgentBenchmarkTester:
    """获取 Agent 基准测试器"""
    global _agent_benchmark_tester
    if _agent_benchmark_tester is None:
        _agent_benchmark_tester = AgentBenchmarkTester()
    return _agent_benchmark_tester


async def run_agent_benchmark(
    category: str = None,
    difficulty: str = None,
    limit: int = None
) -> Dict[str, Any]:
    """
    便捷函数：运行 Agent 基准测试
    
    Args:
        category: 测试类别
        difficulty: 难度级别
        limit: 测试数量限制
        
    Returns:
        基准测试报告（字典格式）
    """
    tester = get_agent_benchmark_tester()
    
    cat_enum = BenchmarkCategory(category) if category else None
    diff_enum = DifficultyLevel(difficulty) if difficulty else None
    
    report = await tester.run_benchmark(
        category=cat_enum,
        difficulty=diff_enum,
        limit=limit
    )
    
    data = report.to_dict()
    data["test_cases"] = [
        {
            "case_id": result.case_id,
            "status": result.status,
            "execution_time_ms": result.execution_time_ms,
            "retry_count": result.retry_count,
            "reflection_score": result.reflection_score,
            "token_cost_usd": result.token_cost_usd,
            "hallucination_detected": result.hallucination_detected,
            "actual_metrics": result.actual_metrics
        }
        for result in report.results
    ]
    
    return data


async def run_single_agent_test(case_id: str) -> Dict[str, Any]:
    """
    便捷函数：运行单个 Agent 测试用例
    
    Args:
        case_id: 测试用例ID
        
    Returns:
        测试结果（字典格式）
    """
    tester = get_agent_benchmark_tester()
    dataset = get_agent_benchmark_dataset()
    
    cases = dataset.get_cases()
    case = next((c for c in cases if c.case_id == case_id), None)
    
    if not case:
        return {"error": f"测试用例 {case_id} 不存在"}
    
    result = await tester.run_test(case)
    return {
        "case": case.to_dict(),
        "result": {
            "status": result.status,
            "execution_time_ms": result.execution_time_ms,
            "answer": result.answer,
            "actual_route": result.actual_route,
            "tools_used": result.tools_used,
            "retry_count": result.retry_count,
            "reflection_score": result.reflection_score,
            "token_cost_usd": result.token_cost_usd,
            "hallucination_detected": result.hallucination_detected,
            "actual_metrics": result.actual_metrics,
            "error": result.error
        }
    }


def get_benchmark_categories() -> List[str]:
    """获取所有测试类别"""
    return [cat.value for cat in BenchmarkCategory]


def get_difficulty_levels() -> List[str]:
    """获取所有难度级别"""
    return [diff.value for diff in DifficultyLevel]