from pydantic import BaseModel, Field
from typing import List, Dict, Optional


class TextProcessRequest(BaseModel):
    """文本处理请求模型"""
    content: str = Field(..., description="要处理的文本内容")
    chunk_size: int = Field(512, description="切片大小", ge=100, le=2048)
    overlap: int = Field(64, description="切片重叠大小", ge=0, le=200)


class TextExtractRequest(BaseModel):
    """文本提取请求模型"""
    content: str = Field(..., description="要分析的文本内容")


class VectorSearchRequest(BaseModel):
    """向量检索请求模型"""
    content: str = Field(..., description="查询文本")
    top_k: Optional[int] = Field(None, description="返回结果数量", ge=1, le=50)
    meeting_id: Optional[int] = Field(None, description="指定会议ID")
    department: Optional[str] = Field(None, description="指定部门")
    similarity_threshold: Optional[float] = Field(None, description="相似度阈值", ge=0.0, le=1.0)


class TextProcessResponse(BaseModel):
    """文本处理响应模型"""
    original_text: str
    cleaned_text: str
    sentences: List[str]
    chunks: List[str]
    keywords: List[Dict[str, str]]
    summary: str
    sentence_count: int
    chunk_count: int
    word_count: int


class KeywordResponse(BaseModel):
    """关键词响应模型"""
    word: str
    count: int


class SummaryResponse(BaseModel):
    """摘要响应模型"""
    summary: str


class TodoItemResponse(BaseModel):
    """待办事项响应模型"""
    title: str
    assignee: Optional[str] = None


class SentencesResponse(BaseModel):
    """分句响应模型"""
    sentences: List[str]
    count: int


class RAGAskRequest(BaseModel):
    """RAG 问答请求模型"""
    question: str = Field(..., description="用户问题", min_length=1)
    top_k: Optional[int] = Field(None, description="检索返回数量", ge=1, le=50)
    meeting_id: Optional[int] = Field(None, description="指定会议ID")
    department: Optional[str] = Field(None, description="指定部门")
    similarity_threshold: Optional[float] = Field(None, description="相似度阈值", ge=0.0, le=1.0)
    use_llm: bool = Field(True, description="是否使用 LLM 生成回答")


class CleanTextResponse(BaseModel):
    """文本清洗响应模型"""
    original_length: int
    cleaned_length: int
    cleaned_text: str