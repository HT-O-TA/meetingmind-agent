"""RAG 对外契约：版本化回答、引用、降级信息和时延。"""
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from app.core.response import Response


class RAGAskRequest(BaseModel):
    """RAG 问答请求。"""

    question: str = Field(..., description="用户问题", min_length=1, max_length=20000)
    top_k: Optional[int] = Field(None, description="检索返回数量", ge=1, le=50)
    meeting_id: Optional[int] = Field(None, description="指定会议 ID")
    department: Optional[str] = Field(None, description="指定部门")
    similarity_threshold: Optional[float] = Field(
        None, description="相似度阈值", ge=0.0, le=1.0
    )
    use_llm: bool = Field(True, description="是否使用 LLM 生成回答")


class Citation(BaseModel):
    citation_id: str
    source_id: str
    source_type: str = "document_chunk"
    chunk_id: Optional[Union[int, str]] = None
    document_id: Optional[Union[int, str]] = None
    meeting_id: Optional[Union[int, str]] = None
    chunk_index: Optional[int] = None
    speaker: Optional[str] = None
    time_offset: Optional[float] = None
    score: float = 0.0
    retrieval_sources: List[str] = Field(default_factory=list)
    retrieval_stage_metrics: Dict[str, Any] = Field(default_factory=dict)
    text_excerpt: str = ""


class DegradationInfo(BaseModel):
    applied: bool = False
    reasons: List[str] = Field(default_factory=list)
    actions: List[str] = Field(default_factory=list)


class RAGResult(BaseModel):
    schema_version: str = "rag.v1"
    answer: str
    chunks: List[Dict[str, Any]] = Field(default_factory=list)
    citations: List[Citation] = Field(default_factory=list)
    count: int = 0
    mode: str
    query_type: str = "standard"
    original_query: str
    rewritten_query: List[str] = Field(default_factory=list)
    expanded_query_count: int = 1
    retrieval_strategy: str = "A"
    retrieval_sources: List[str] = Field(default_factory=list)
    retrieval_stage_metrics: Dict[str, Any] = Field(default_factory=dict)
    retrieval_latency_ms: float = 0.0
    generation_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    degradation: DegradationInfo = Field(default_factory=DegradationInfo)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    evaluation: Optional[Dict[str, Any]] = None


class RAGAPIResponse(Response):
    data: RAGResult
