"""Agent 结构化输出的唯一 Pydantic 契约与轻量修复入口。"""
import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError


class EvidenceFields(BaseModel):
    """所有业务证据共享的溯源字段。"""
    source_id: Optional[str] = None
    source_type: str = "unknown"
    speaker: Optional[str] = None
    timestamp: Optional[float] = None
    uncertainties: List[str] = Field(default_factory=list)
    degradation_info: List[str] = Field(default_factory=list)


class TodoOutput(EvidenceFields):
    content: str = Field(min_length=1)
    assignee: str = ""
    deadline: str = ""
    priority: Literal["high", "medium", "low", "unknown"] = "unknown"


class DecisionOutput(EvidenceFields):
    content: str = Field(min_length=1)
    owner: str = ""
    status: Literal["proposed", "approved", "rejected", "unknown"] = "unknown"


class ControversyOutput(EvidenceFields):
    topic: str = Field(min_length=1)
    description: str = ""
    parties: List[str] = Field(default_factory=list)
    resolved: bool = False


class MinutesOutput(EvidenceFields):
    content: str = Field(min_length=1)
    meeting_topic: str = ""
    participants: List[str] = Field(default_factory=list)
    discussion_points: List[str] = Field(default_factory=list)
    decisions: List[DecisionOutput] = Field(default_factory=list)
    action_items: List[TodoOutput] = Field(default_factory=list)


class ToolCallOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_name: str = Field(min_length=1)
    arguments: Dict[str, Any] = Field(default_factory=dict)


class PlanTaskOutput(BaseModel):
    model_config = ConfigDict(extra="allow")
    task_id: str = Field(min_length=1)
    task_type: str = Field(min_length=1)
    description: str = Field(min_length=1)
    priority: int = Field(default=1, ge=1, le=5)
    dependencies: List[str] = Field(default_factory=list)
    tool_to_use: Optional[str] = None


class AgentPlanOutput(BaseModel):
    model_config = ConfigDict(extra="allow")
    analysis: str
    tasks: List[PlanTaskOutput]
    tool_calls: List[ToolCallOutput] = Field(default_factory=list)
    execution_order: List[str]


class ReflectionMetricsOutput(BaseModel):
    model_config = ConfigDict(extra="allow")
    task_completion: float = Field(default=0.5, ge=0.0, le=1.0)
    correctness: float = Field(default=0.5, ge=0.0, le=1.0)
    process_efficiency: float = Field(default=0.5, ge=0.0, le=1.0)
    expression: float = Field(default=0.5, ge=0.0, le=1.0)
    risk: float = Field(default=0.5, ge=0.0, le=1.0)


class ReflectionOutput(BaseModel):
    model_config = ConfigDict(extra="allow")
    overall_score: float = Field(ge=0.0, le=1.0)
    metrics: ReflectionMetricsOutput
    confidence: float = Field(ge=0.0, le=1.0)
    issues: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    needs_retry: bool = False


class StructuredOutputEnvelope(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    schema_version: str = "extraction.v1"
    output_type: str
    data: Any
    prompt_version: str
    model_version: str
    source_id: Optional[str] = None
    source_type: str = "unknown"
    speaker: Optional[str] = None
    timestamp: Optional[float] = None
    uncertainties: List[str] = Field(default_factory=list)
    degradation_info: List[str] = Field(default_factory=list)


_VALIDATORS = {
    "待办事项": TypeAdapter(List[TodoOutput]),
    "争议点": TypeAdapter(List[ControversyOutput]),
    "执行计划": TypeAdapter(AgentPlanOutput),
    "评估结果": TypeAdapter(ReflectionOutput),
}


def repair_json_text(value: str) -> str:
    """只做确定性、低风险修复：去代码围栏和对象/数组尾逗号。"""
    text = value.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    candidate = re.search(r"\[[\s\S]*\]|\{[\s\S]*\}", text)
    if candidate:
        text = candidate.group()
    return re.sub(r",\s*([}\]])", r"\1", text)


def validate_structured_data(data: Any, expected_type: str) -> Any:
    """按输出类型验证并返回规范化 Python 数据；未知类型保持兼容。"""
    validator = _VALIDATORS.get(expected_type)
    if validator is None:
        return data
    validated = validator.validate_python(data)
    if isinstance(validated, list):
        return [item.model_dump() for item in validated]
    return validated.model_dump()


def validate_tool_call(tool_name: Any, arguments: Any) -> ToolCallOutput:
    """工具调用进入 ToolPolicy 前的统一参数外壳校验。"""
    return ToolCallOutput.model_validate({"tool_name": tool_name, "arguments": arguments})


__all__ = [
    "AgentPlanOutput",
    "ControversyOutput",
    "DecisionOutput",
    "EvidenceFields",
    "MinutesOutput",
    "ReflectionOutput",
    "StructuredOutputEnvelope",
    "TodoOutput",
    "ToolCallOutput",
    "ValidationError",
    "repair_json_text",
    "validate_structured_data",
    "validate_tool_call",
]
