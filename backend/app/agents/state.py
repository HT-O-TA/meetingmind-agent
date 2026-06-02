"""Agent 状态定义 - 支持复杂任务拆分（依赖分析 + 上下文传递 + 并行执行）"""
from typing import TypedDict, List, Dict, Optional, Any, Set
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


class CoTThought(TypedDict):
    """思维链记录"""
    step: int
    agent_id: str
    phase: str
    thought: str
    action: Optional[str]
    observation: Optional[str]


class ReflectionResult(TypedDict):
    """反思结果"""
    quality_score: float
    issues: List[str]
    suggestions: List[str]
    needs_retry: bool
    retry_count: int


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
    meeting_id: Optional[int]
    document_ids: Optional[List[int]]
    context: List[ChunkMetadata]
    raw_context: List[str]
    current_phase: str
    task_type: Optional[TaskType]
    
    # 计划阶段
    plan: Optional[Plan]
    
    # 执行阶段
    task_contexts: Dict[str, TaskContext]  # 任务间的上下文传递
    minutes: Optional[str]
    todos: Optional[List[TodoItem]]
    controversies: Optional[List[ControversyItem]]
    answer: Optional[str]
    
    # 反思阶段
    reflection: Optional[ReflectionResult]
    
    # 执行跟踪
    error: Optional[str]
    cot_thoughts: List[CoTThought]
    agents_involved: List[str]
    
    # 事件回调（用于流式输出）
    event_callback: Optional[callable]
    
    # 人机协作
    human_confirmations: List[HumanConfirmation]
    enable_human_in_the_loop: bool


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


def create_initial_state(
    question: str,
    meeting_id: Optional[int] = None,
    document_ids: Optional[List[int]] = None,
    enable_human_in_the_loop: bool = False,
) -> AgentState:
    """创建 Agent 初始状态"""
    return {
        "question": question,
        "meeting_id": meeting_id,
        "document_ids": document_ids or [],
        "context": [],
        "raw_context": [],
        "current_phase": "plan",
        "task_type": None,
        "plan": None,
        "task_contexts": {},
        "minutes": None,
        "todos": None,
        "controversies": None,
        "answer": None,
        "reflection": None,
        "error": None,
        "cot_thoughts": [],
        "agents_involved": [],
        "event_callback": None,
        "human_confirmations": [],
        "enable_human_in_the_loop": enable_human_in_the_loop,
    }