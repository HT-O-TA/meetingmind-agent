"""Agent 状态定义 - 支持复杂任务拆分（依赖分析 + 上下文传递 + 并行执行）"""
from typing import TypedDict, List, Dict, Optional, Any, Set
import uuid
from dataclasses import dataclass
from enum import Enum


class AgentCard(TypedDict):
    """Agent 名片 - 描述 Agent 的能力和依赖"""
    agent_id: str
    name: str
    description: str
    capabilities: List[str]
    required_inputs: List[str]
    outputs: List[str]
    dependencies: Set[str]


class TaskType(str, Enum):
    """任务类型枚举"""
    QA = "qa"
    MINUTES = "minutes"
    TODO = "todo"
    CONTROVERSY = "controversy"
    RETRIEVE = "retrieve"
    COMBINE = "combine"
    MULTI = "multi"


class WorkflowType(str, Enum):
    """Agent 工作流类型，用于决定是否启用规划器"""
    SIMPLE_QA = "simple_qa"
    MINUTES = "minutes"
    TODO = "todo"
    CONTROVERSY = "controversy"
    COMPLEX = "complex"


class ReasoningMode(str, Enum):
    """推理模式枚举 - 决定使用哪种推理方式"""
    DEFAULT = "default"      # 默认模式，根据问题复杂度自动选择
    REACT = "react"          # ReAct 推理（思考-行动-观察循环）
    COT = "cot"              # CoT 思维链推理（详细链式推理）
    PLAN = "plan"            # 规划器模式（确定性工作流）


class ComplexityLevel(str, Enum):
    """复杂度级别枚举 - 4级分类"""
    SIMPLE = "simple"        # S: 0.0-0.3 - 简单问答，无需检索
    RETRIEVAL = "retrieval"  # R: 0.3-0.5 - 需要检索，无复杂推理
    COT = "cot"              # C: 0.5-0.75 - 需要思维链推理
    AGENT = "agent"           # A: 0.75-1.0 - 需要ReAct代理


class ModelTier(str, Enum):
    """双轴模型路由输出档位。"""
    TURBO = "turbo"
    PLUS = "plus"
    MAX = "max"


class ExecutionMode(str, Enum):
    """正式执行模式；通用 ReAct 当前不进入默认主链路。"""
    FALLBACK = "fallback"
    DETERMINISTIC = "deterministic"
    PLAN_EXECUTE = "plan_execute"


class AgentConfig(TypedDict):
    """Agent 配置参数 - 控制推理行为"""
    max_react_iterations: int        # ReAct 最大迭代次数
    max_plan_retries: int            # 计划最大重试次数
    max_context_length: int          # 上下文最大长度（字符）
    max_few_shot_examples: int       # 每个模板最大示例数


class RiskLevel(str, Enum):
    """操作风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TodoItem(TypedDict):
    """待办事项结构"""
    content: str
    assignee: str
    deadline: str


class ControversyItem(TypedDict):
    """争议点结构"""
    topic: str
    description: str
    parties: List[str]


class ChunkMetadata(TypedDict):
    """向量块元数据（用于引用溯源）"""
    chunk_id: int
    document_id: int
    meeting_id: Optional[int]
    content: str
    chunk_index: int
    similarity: float
    department: Optional[str]
    speaker_name: str
    time_offset: Optional[float]
    metadata_json: Optional[str]


class TaskContext(TypedDict):
    """任务间传递的上下文"""
    task_id: str
    data: Any
    metadata: Dict[str, Any]


class TaskItem(TypedDict):
    """任务项 - 支持依赖分析和上下文传递"""
    task_id: str
    task_type: str
    description: str
    priority: int
    status: str
    
    # 依赖分析
    dependencies: List[str]           # 直接依赖的任务ID列表
    can_parallel_with: List[str]      # 可以并行执行的任务ID列表
    
    # 上下文传递
    input_from: Optional[str]         # 从哪个任务获取输入
    output_key: Optional[str]         # 输出数据的键名
    
    # 执行结果
    result: Optional[Any]
    error: Optional[str]


class Plan(TypedDict):
    """执行计划 - 支持依赖分析和并行执行"""
    analysis: str
    tasks: List[TaskItem]
    execution_order: List[str]
    parallel_groups: List[List[str]]  # 可并行执行的任务分组
    tool_calls: List[Dict[str, Any]]


class CoTThought(TypedDict):
    """思维链记录"""
    step: int
    agent_id: str
    phase: str
    thought: str
    action: Optional[str]
    observation: Optional[str]


class EvaluationMetrics(TypedDict):
    """多维度质量评估指标（通用指标）"""
    task_completion: float      # 任务达成度
    correctness: float          # 正确性
    process_efficiency: float   # 流程效率
    expression: float           # 表达
    risk: float                 # 风险


class ReflectionResult(TypedDict):
    """反思结果"""
    overall_score: float         # 综合评分
    metrics: EvaluationMetrics   # 多维度评估
    confidence: float            # 评估置信度
    issues: List[str]            # 问题列表
    suggestions: List[str]       # 改进建议
    needs_retry: bool            # 是否需要重试
    retry_count: int             # 重试次数


class ConfirmationStatus(str, Enum):
    """人机确认状态"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"
    SKIPPED = "skipped"


class HumanConfirmation(TypedDict):
    """人机确认记录"""
    request_id: str
    type: str
    title: str
    message: str
    status: ConfirmationStatus
    user_response: Optional[str]
    timestamp: str


class AgentState(TypedDict):
    """Agent 执行状态 - 支持复杂任务拆分"""
    question: str
    agent_run_id: str
    user_id: Optional[int]
    session_id: Optional[str]
    conversation_id: Optional[str]
    thread_id: Optional[str]
    task_id: Optional[str]
    task_namespace: str
    input_envelope: Optional[Dict[str, Any]]
    task_anchor: Optional[Dict[str, Any]]
    input_blocked: bool
    planning_blocked: bool
    input_block_reason: Optional[str]
    injection_check: Optional[Dict[str, Any]]
    injection_blocked: bool
    injection_block_reason: Optional[str]
    approved_tool_call: Optional[Dict[str, Any]]
    resume_from_tool_index: Optional[int]
    meeting_id: Optional[int]
    document_ids: Optional[List[int]]
    context: List[ChunkMetadata]
    raw_context: List[str]
    context_manifest: Optional[Dict[str, Any]]
    current_phase: str
    task_type: Optional[TaskType]

    # 路由阶段
    workflow_type: Optional[WorkflowType]
    reasoning_mode: Optional[ReasoningMode]
    complexity_score: float
    complexity_level: Optional[ComplexityLevel]
    is_multi_task: bool
    route_reason: str
    retrieval_required: bool
    retrieval_confidence: float
    plan_confidence: float
    uncertainty_flags: List[Dict[str, Any]]
    planner_iterations: int
    last_plan_fingerprint: Optional[str]
    repeated_failure_count: int
    last_failure_fingerprint: Optional[str]
    citations: List[Dict[str, Any]]
    validation_errors: List[str]
    policy_results: List[Dict[str, Any]]
    repair_count: int
    max_repair_attempts: int
    risk_level: RiskLevel
    requires_confirmation: bool
    confirmation_status: str
    pending_action: Optional[Dict[str, Any]]
    
    # 计划阶段
    plan: Optional[Plan]
    
    # 执行阶段
    task_contexts: Dict[str, TaskContext]  # 任务间的上下文传递
    minutes: Optional[str]
    todos: Optional[List[TodoItem]]
    controversies: Optional[List[ControversyItem]]
    answer: Optional[str]
    structured_outputs: Dict[str, Any]
    
    # 反思阶段
    reflection: Optional[ReflectionResult]
    
    # 执行跟踪
    execution_steps: Dict[str, Dict[str, Any]]
    error: Optional[str]
    cot_thoughts: List[CoTThought]
    agents_involved: List[str]
    
    # 策略回退
    last_strategy: Optional[str]
    fallback_count: int
    
    # 事件回调（用于流式输出）
    event_callback: Optional[callable]
    
    # 人机协作
    human_confirmations: List[HumanConfirmation]
    enable_human_in_the_loop: bool

    # P1 #4: 会话记忆上下文（route_agent 预注入，供所有路径使用）
    session_context: Optional[str]
    access_scope: Optional[Dict[str, Any]]


@dataclass
class AgentResult:
    """Agent 执行结果"""
    success: bool
    task_type: TaskType
    answer: Optional[str] = None
    minutes: Optional[str] = None
    todos: Optional[List[Dict[str, Any]]] = None
    controversies: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None
    thoughts: Optional[List[CoTThought]] = None
    reflection: Optional[ReflectionResult] = None
    plan: Optional[Dict[str, Any]] = None
    workflow_type: Optional[WorkflowType] = None
    route_reason: Optional[str] = None
    citations: Optional[List[Dict[str, Any]]] = None
    validation_errors: Optional[List[str]] = None
    policy_results: Optional[List[Dict[str, Any]]] = None
    retrieval_confidence: Optional[float] = None
    plan_confidence: Optional[float] = None
    uncertainty_flags: Optional[List[Dict[str, Any]]] = None
    risk_level: Optional[RiskLevel] = None
    requires_confirmation: bool = False
    confirmation_status: Optional[str] = None
    pending_action: Optional[Dict[str, Any]] = None
    route_decision: Optional["RouteDecision"] = None
    structured_outputs: Optional[Dict[str, Any]] = None
    budget_ledger: Optional[Dict[str, Any]] = None
    context_manifest: Optional[Dict[str, Any]] = None


@dataclass
class RouteDecision:
    """路由决策结果 - 结构化的路由决策信息

    包含完整的路由决策链路、置信度、候选项等信息，便于前端展示和调试。
    """
    workflow_type: WorkflowType
    task_type: TaskType
    complexity_level: ComplexityLevel
    complexity_score: float
    confidence: float
    reason: str
    detected_tasks: List[str] = None
    task_confidence: float = 0.0
    is_multi_task: bool = False
    requires_retrieval: bool = False
    requires_reasoning: bool = False
    candidates: List[Dict[str, Any]] = None
    decision_trace: List[str] = None
    model_tier: ModelTier = ModelTier.PLUS
    model_name: str = ""
    execution_mode: ExecutionMode = ExecutionMode.DETERMINISTIC
    complexity_confidence: float = 0.0
    rule_matched: bool = False
    sub_tasks: List[Dict[str, Any]] = None
    degradation_actions: List[str] = None
    threshold_policy: Dict[str, Any] = None
    schema_version: str = "route.v1"

    def __post_init__(self):
        if self.detected_tasks is None:
            self.detected_tasks = []
        if self.candidates is None:
            self.candidates = []
        if self.decision_trace is None:
            self.decision_trace = []
        if self.sub_tasks is None:
            self.sub_tasks = []
        if self.degradation_actions is None:
            self.degradation_actions = []
        if self.threshold_policy is None:
            self.threshold_policy = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_type": self.workflow_type.value,
            "task_type": self.task_type.value,
            "complexity_level": self.complexity_level.value,
            "complexity_score": self.complexity_score,
            "confidence": self.confidence,
            "reason": self.reason,
            "detected_tasks": self.detected_tasks,
            "task_confidence": self.task_confidence,
            "is_multi_task": self.is_multi_task,
            "requires_retrieval": self.requires_retrieval,
            "requires_reasoning": self.requires_reasoning,
            "candidates": self.candidates,
            "decision_trace": self.decision_trace,
            "model_tier": self.model_tier.value,
            "model_name": self.model_name,
            "execution_mode": self.execution_mode.value,
            "complexity_confidence": self.complexity_confidence,
            "rule_matched": self.rule_matched,
            "sub_tasks": self.sub_tasks,
            "degradation_actions": self.degradation_actions,
            "threshold_policy": self.threshold_policy,
            "schema_version": self.schema_version,
        }


def create_initial_state(
    question: str,
    meeting_id: Optional[int] = None,
    document_ids: Optional[List[int]] = None,
    enable_human_in_the_loop: bool = False,
    reasoning_mode: Optional[ReasoningMode] = None,
) -> AgentState:
    """创建 Agent 初始状态"""
    return {
        "question": question,
        "agent_run_id": str(uuid.uuid4()),
        "user_id": None,
        "session_id": None,
        "conversation_id": None,
        "thread_id": None,
        "task_id": None,
        "task_namespace": "default",
        "input_envelope": None,
        "task_anchor": None,
        "input_blocked": False,
        "planning_blocked": False,
        "input_block_reason": None,
        "injection_check": None,
        "injection_blocked": False,
        "injection_block_reason": None,
        "meeting_id": meeting_id,
        "document_ids": document_ids or [],
        "context": [],
        "raw_context": [],
        "context_manifest": None,
        "current_phase": "plan",
        "task_type": None,
        "workflow_type": None,
        "reasoning_mode": reasoning_mode or ReasoningMode.DEFAULT,
        "complexity_score": 0.0,
        "complexity_level": None,
        "is_multi_task": False,
        "route_reason": "",
        "retrieval_required": True,
        "retrieval_confidence": 0.0,
        "plan_confidence": 1.0,
        "uncertainty_flags": [],
        "planner_iterations": 0,
        "last_plan_fingerprint": None,
        "repeated_failure_count": 0,
        "last_failure_fingerprint": None,
        "citations": [],
        "validation_errors": [],
        "policy_results": [],
        "repair_count": 0,
        "max_repair_attempts": 1,
        "risk_level": RiskLevel.LOW,
        "requires_confirmation": False,
        "confirmation_status": "not_required",
        "pending_action": None,
        "plan": None,
        "task_contexts": {},
        "minutes": None,
        "todos": None,
        "controversies": None,
        "answer": None,
        "structured_outputs": {},
        "reflection": None,
        "error": None,
        "execution_steps": {},
        "cot_thoughts": [],
        "agents_involved": [],
        "last_strategy": None,
        "fallback_count": 0,
        "event_callback": None,
        "human_confirmations": [],
        "enable_human_in_the_loop": enable_human_in_the_loop,
        "session_context": None,
        "access_scope": None,
        "approved_tool_call": None,
        "resume_from_tool_index": None,
    }
