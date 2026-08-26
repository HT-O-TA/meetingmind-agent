"""Agent 相关 Schema"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class AgentQueryRequest(BaseModel):
    """Agent 查询请求"""
    question: str = Field(..., description="用户问题")
    meeting_id: Optional[int] = Field(None, description="关联的会议ID")
    document_ids: Optional[List[int]] = Field(None, description="关联的文档ID列表")


class AgentBatchRequest(BaseModel):
    """Agent 批量查询请求"""
    questions: List[str] = Field(..., description="问题列表")
    meeting_id: Optional[int] = Field(None, description="关联的会议ID")
    document_ids: Optional[List[int]] = Field(None, description="关联的文档ID列表")


class AgentQueryResponse(BaseModel):
    """Agent 查询响应"""
    success: bool = Field(..., description="是否成功")
    task_type: str = Field(..., description="任务类型")
    answer: Optional[str] = Field(None, description="回答（qa任务）")
    minutes: Optional[str] = Field(None, description="会议纪要（minutes任务）")
    todos: Optional[List[Dict[str, Any]]] = Field(None, description="待办事项（todo任务）")
    controversies: Optional[List[Dict[str, Any]]] = Field(None, description="争议点（controversy任务）")
    structured_outputs: Optional[Dict[str, Any]] = Field(None, description="带版本、证据和降级信息的结构化结果")
    error: Optional[str] = Field(None, description="错误信息")
