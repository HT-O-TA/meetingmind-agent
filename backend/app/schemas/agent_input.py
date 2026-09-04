"""Agent 输入预处理层的版本化契约。"""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ArtifactSource(str, Enum):
    """进入 Agent 上下文的数据来源。"""

    USER_QUERY = "user_query"
    SELECTED_DOCUMENT = "selected_document"
    SESSION_CONTEXT = "session_context"
    RETRIEVAL = "retrieval"
    TOOL_RESULT = "tool_result"


class SourceAuthority(str, Enum):
    """输入来源的权限层级；这是执行权限，不是内容真实性评分。"""

    SYSTEM = "system"
    USER = "user"
    TOOL = "tool"
    KNOWLEDGE = "knowledge"
    SESSION = "session"


# 权限只允许由来源推导，调用方不能把普通资料自报成用户指令。
SOURCE_AUTHORITY_BY_ARTIFACT_SOURCE = {
    ArtifactSource.USER_QUERY: (SourceAuthority.USER, 90),
    ArtifactSource.TOOL_RESULT: (SourceAuthority.TOOL, 40),
    ArtifactSource.SELECTED_DOCUMENT: (SourceAuthority.KNOWLEDGE, 30),
    ArtifactSource.RETRIEVAL: (SourceAuthority.KNOWLEDGE, 30),
    ArtifactSource.SESSION_CONTEXT: (SourceAuthority.SESSION, 20),
}


class TrustLevel(str, Enum):
    """来源信任分区；名称表达用途，不代表内容已经过事实验证。"""

    USER_INSTRUCTION = "user_instruction"
    UNTRUSTED_UPLOAD = "untrusted_upload"
    UNTRUSTED_SESSION = "untrusted_session"
    UNTRUSTED_RETRIEVAL = "untrusted_retrieval"
    UNTRUSTED_TOOL_RESULT = "untrusted_tool_result"


class ArtifactSecurityStatus(str, Enum):
    UNCHECKED = "unchecked"
    PASSED = "passed"
    WARNING = "warning"
    QUARANTINED = "quarantined"


class InputArtifact(BaseModel):
    """只保存来源和摘要，不在 Envelope 中复制大段正文。"""

    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    source: ArtifactSource
    trust_level: TrustLevel
    # authority/rank 是来源隔离的不可变投影，默认值仅用于兼容旧的 input.v1 数据。
    authority: SourceAuthority = SourceAuthority.KNOWLEDGE
    authority_rank: int = Field(default=30, ge=0, le=100)
    content_ref: str = Field(min_length=1)
    checksum: Optional[str] = None
    security_status: ArtifactSecurityStatus = ArtifactSecurityStatus.UNCHECKED
    metadata: Dict[str, Any] = Field(default_factory=dict)


class InputScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meeting_id: Optional[int] = None
    document_ids: List[int] = Field(default_factory=list)
    # 会议范围：空列表表示认证上下文没有额外的会议白名单，按用户可访问范围处理。
    allowed_meeting_ids: List[int] = Field(default_factory=list)
    # 文档范围：None 表示不限制，空列表表示没有文档权限，非空列表表示白名单。
    allowed_document_ids: Optional[List[int]] = None
    is_admin: bool = False
    # 最小权限：只有认证上下文明确授予写能力时才允许外部写操作。
    can_write: bool = False


class InputBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_input_chars: int = Field(ge=1)
    max_context_chars: int = Field(ge=1)
    max_plan_steps: int = Field(ge=1)
    max_tool_calls: int = Field(ge=0)
    plan_output_tokens: int = Field(ge=1)
    default_model_context_tokens: int = Field(ge=1)
    max_run_tokens: int = Field(ge=1)
    max_node_tokens: int = Field(ge=1)
    max_llm_calls: int = Field(ge=1)
    token_safety_margin_ratio: float = Field(ge=0.0, lt=1.0)
    token_ledger: Optional[Dict[str, Any]] = None
    context_manifest: Optional[Dict[str, Any]] = None


class InputSecurity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direct_injection_status: Literal["pending", "passed", "warning", "blocked", "error"] = "pending"
    direct_injection_reason: str = ""
    policy_flags: List[str] = Field(default_factory=list)
    quarantined_artifact_ids: List[str] = Field(default_factory=list)


class InputRouting(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    task_type: Optional[str] = None
    workflow_type: Optional[str] = None
    complexity_level: Optional[str] = None
    complexity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    model_tier: Optional[str] = None
    route_evidence: List[str] = Field(default_factory=list)


class TaskIntent(BaseModel):
    """从一段混合输入中拆出的一个可追踪意图。"""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    order: int = Field(ge=0)
    source: Literal["user_query"] = "user_query"


class TaskConstraint(BaseModel):
    """用户明确说出的限制条件，供规划和工具执行前复核。"""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    kind: Literal["negation", "threshold", "exclusion", "scope", "preference", "other"] = "other"
    polarity: Literal["must", "must_not"] = "must"
    value: Optional[str] = None
    source: Literal["user_query", "system"] = "user_query"


class TaskAnchor(BaseModel):
    """跨规划和校验保持稳定的任务目标。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["task-anchor.v1"] = "task-anchor.v1"
    goal: str = Field(min_length=1)
    required_outputs: List[str] = Field(default_factory=list)
    hard_constraints: List[str] = Field(default_factory=list)
    forbidden_actions: List[str] = Field(default_factory=list)
    intents: List[TaskIntent] = Field(default_factory=list)
    constraints: List[TaskConstraint] = Field(default_factory=list)
    completion_criteria: List[str] = Field(default_factory=list)
    ambiguities: List[str] = Field(default_factory=list)


class InputEnvelope(BaseModel):
    """MeetingMind 输入层的内部统一契约。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["input.v1"] = "input.v1"
    request_id: str = Field(min_length=1)
    user_id: Optional[int] = None
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    thread_id: Optional[str] = None
    task_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    raw_query: str = Field(min_length=1)
    normalized_query: str = Field(min_length=1)
    scope: InputScope
    artifacts: List[InputArtifact] = Field(default_factory=list)
    task_anchor: TaskAnchor
    routing: InputRouting = Field(default_factory=InputRouting)
    budget: InputBudget
    security: InputSecurity = Field(default_factory=InputSecurity)


__all__ = [
    "ArtifactSecurityStatus",
    "ArtifactSource",
    "SOURCE_AUTHORITY_BY_ARTIFACT_SOURCE",
    "SourceAuthority",
    "InputArtifact",
    "InputBudget",
    "InputEnvelope",
    "InputRouting",
    "InputScope",
    "InputSecurity",
    "TaskAnchor",
    "TaskConstraint",
    "TaskIntent",
    "TrustLevel",
]
