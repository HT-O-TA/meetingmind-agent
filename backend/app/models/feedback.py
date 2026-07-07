"""反馈与 Bad Case 数据模型"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, JSON, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum as PyEnum
from app.db.database import Base


class FeedbackType(PyEnum):
    """反馈类型"""
    USER_RATING = "user_rating"          # 用户评分
    USER_COMMENT = "user_comment"        # 用户评论
    SELF_EVALUATION = "self_evaluation"  # 自我评估
    CORRECTION = "correction"            # 修正建议
    SUCCESS = "success"                  # 成功案例
    FAILURE = "failure"                  # 失败案例


class BadCaseCategory(PyEnum):
    """Bad Case 分类"""
    FACTUAL_ERROR = "factual_error"      # 事实错误
    INCOMPLETE = "incomplete"            # 回答不完整
    IRRELEVANT = "irrelevant"            # 无关回答
    UNCLEAR = "unclear"                  # 表达不清
    LOGIC_ERROR = "logic_error"          # 逻辑错误
    TOOL_ERROR = "tool_error"            # 工具调用失败
    TIMEOUT = "timeout"                  # 超时
    OTHER = "other"                      # 其他


class ResolutionStatus(PyEnum):
    """解决状态"""
    PENDING = "pending"                  # 待处理
    ANALYZED = "analyzed"                # 已分析
    IMPROVED = "improved"                # 已改进
    VERIFIED = "verified"                # 已验证
    WONT_FIX = "wont_fix"                # 暂不处理


class Feedback(Base):
    """用户反馈模型"""
    __tablename__ = "feedbacks"
    
    id = Column(Integer, primary_key=True, index=True)
    feedback_id = Column(String(64), unique=True, index=True)
    type = Column(Enum(FeedbackType), nullable=False)
    input_text = Column(Text)
    output_text = Column(Text)
    rating = Column(Integer)  # 1-5
    comment = Column(Text)
    metrics = Column(JSON)
    corrections = Column(JSON)
    context = Column(JSON)
    timestamp = Column(DateTime, default=datetime.now)
    
    # 关联的 Bad Case
    bad_case_id = Column(Integer, ForeignKey("bad_cases.id"))
    bad_case = relationship("BadCase", back_populates="feedbacks")


class BadCase(Base):
    """Bad Case 模型"""
    __tablename__ = "bad_cases"
    
    id = Column(Integer, primary_key=True, index=True)
    bad_case_id = Column(String(64), unique=True, index=True)
    category = Column(Enum(BadCaseCategory), nullable=False)
    input_text = Column(Text, nullable=False)
    actual_output = Column(Text, nullable=False)
    expected_output = Column(Text)
    analysis = Column(Text)
    improvement_plan = Column(Text)
    resolution_status = Column(Enum(ResolutionStatus), default=ResolutionStatus.PENDING)
    priority = Column(String(16), default="medium")  # high, medium, low
    timestamp = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, onupdate=datetime.now)
    
    # 关联的反馈
    feedbacks = relationship("Feedback", back_populates="bad_case")
    
    # 关联的改进记录
    improvements = relationship("ImprovementRecord", back_populates="bad_case")


class ImprovementRecord(Base):
    """改进记录模型"""
    __tablename__ = "improvement_records"
    
    id = Column(Integer, primary_key=True, index=True)
    improvement_id = Column(String(64), unique=True, index=True)
    bad_case_id = Column(Integer, ForeignKey("bad_cases.id"))
    action_type = Column(String(64))  # prompt_update, rule_update, model_update, etc.
    description = Column(Text)
    details = Column(JSON)
    implemented_at = Column(DateTime, default=datetime.now)
    verified_at = Column(DateTime)
    verification_result = Column(String(64))  # passed, failed, pending
    
    # 关联的 Bad Case
    bad_case = relationship("BadCase", back_populates="improvements")


class PerformanceMetric(Base):
    """性能指标模型"""
    __tablename__ = "performance_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.now)
    total_interactions = Column(Integer, default=0)
    avg_rating = Column(Float, default=0.0)
    success_rate = Column(Float, default=0.0)
    bad_case_count = Column(Integer, default=0)
    improvement_score = Column(Float, default=0.0)
    metrics = Column(JSON)
