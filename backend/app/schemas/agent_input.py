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
    content_ref: str = Field(min_length=1)
    checksum: Optional[str] = None
    security_status: ArtifactSecurityStatus = ArtifactSecurityStatus.UNCHECKED
    metadata: Dict[str, Any] = Field(default_factory=dict)


class InputScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meeting_id: Optional[int] = None
    document_ids: List[int] = Field(default_factory=list)
    allowed_meeting_ids: List[int] = Field(default_factory=list)
    allowed_document_ids: Optional[List[int]] = None
    is_admin: bool = False
    can_write: bool = True


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


class TaskAnchor(BaseModel):
    """跨规划和校验保持稳定的任务目标。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["task-anchor.v1"] = "task-anchor.v1"
    goal: str = Field(min_length=1)
    required_outputs: List[str] = Field(default_factory=list)
    hard_constraints: List[str] = Field(default_factory=list)
    forbidden_actions: List[str] = Field(default_factory=list)
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
    "InputArtifact",
    "InputBudget",
    "InputEnvelope",
    "InputRouting",
    "InputScope",
    "InputSecurity",
    "TaskAnchor",
    "TrustLevel",
]
