"""反思系统API端点"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from app.agents.reflection import get_reflection_system, FeedbackType, EvaluationMetric

router = APIRouter(prefix="/reflection", tags=["反思系统"])


@router.post("/evaluate", response_model=Dict[str, Any])
async def evaluate(
    input_text: str,
    output_text: str,
):
    """
    自我评估
    
    Args:
        input_text: 输入文本
        output_text: 输出文本
    """
    try:
        reflection = get_reflection_system()
        metrics = reflection.perform_self_evaluation(input_text, output_text)
        
        return {
            "success": True,
            "data": {k.value: v for k, v in metrics.items()} if hasattr(list(metrics.keys())[0], 'value') else metrics,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reflect", response_model=Dict[str, Any])
async def reflect_and_replan(
    input_text: str,
    output_text: str,
    tools_used: Optional[List[str]] = Query(None),
    max_iterations: int = 3,
):
    """
    反思并重新规划
    
    Args:
        input_text: 输入文本
        output_text: 输出文本
        tools_used: 之前使用的工具
        max_iterations: 最大迭代次数
    """
    try:
        reflection = get_reflection_system()
        result = await reflection.reflect_and_replan(
            input_text=input_text,
            output_text=output_text,
            tools_used=tools_used,
            max_iterations=max_iterations,
        )
        
        return {
            "success": True,
            "data": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback", response_model=Dict[str, Any])
async def add_feedback(
    input_text: str,
    output_text: str,
    feedback_type: str = "user_comment",
    rating: Optional[int] = None,
    comment: Optional[str] = None,
):
    """
    添加反馈
    
    Args:
        input_text: 输入文本
        output_text: 输出文本
        feedback_type: 反馈类型 (user_rating, user_comment, self_evaluation, correction, success, failure)
        rating: 评分 (1-5)
        comment: 评论
    """
    try:
        reflection = get_reflection_system()
        feedback_type_enum = FeedbackType(feedback_type.lower())
        
        feedback = reflection.add_feedback(
            type=feedback_type_enum,
            input_text=input_text,
            output_text=output_text,
            rating=rating,
            comment=comment,
        )
        
        return {
            "success": True,
            "data": {
                "feedback_id": feedback.feedback_id,
                "type": feedback.type.value,
                "rating": feedback.rating,
                "timestamp": feedback.timestamp.isoformat(),
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedbacks", response_model=Dict[str, Any])
async def get_feedbacks(
    feedback_type: Optional[str] = None,
    limit: int = 20,
):
    """
    获取反馈列表
    
    Args:
        feedback_type: 反馈类型
        limit: 返回数量
    """
    try:
        reflection = get_reflection_system()
        
        if feedback_type:
            feedback_type_enum = FeedbackType(feedback_type.lower())
            feedbacks = reflection.get_feedbacks(feedback_type_enum)
        else:
            feedbacks = reflection.get_feedbacks()
        
        feedbacks = feedbacks[-limit:]
        
        return {
            "success": True,
            "data": [
                {
                    "feedback_id": f.feedback_id,
                    "type": f.type.value,
                    "input_text": f.input_text,
                    "output_text": f.output_text,
                    "rating": f.rating,
                    "comment": f.comment,
                    "timestamp": f.timestamp.isoformat(),
                }
                for f in feedbacks
            ],
            "count": len(feedbacks),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/notes", response_model=Dict[str, Any])
async def get_reflection_notes(
    priority: Optional[str] = None,
):
    """
    获取反思笔记
    
    Args:
        priority: 优先级 (high, medium, low)
    """
    try:
        reflection = get_reflection_system()
        notes = reflection.get_reflection_notes(priority)
        
        return {
            "success": True,
            "data": [
                {
                    "reflection_id": n.reflection_id,
                    "topic": n.topic,
                    "insight": n.insight,
                    "action_items": n.action_items,
                    "priority": n.priority,
                    "timestamp": n.timestamp.isoformat(),
                }
                for n in notes
            ],
            "count": len(notes),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=Dict[str, Any])
async def get_reflection_stats():
    """获取反思统计信息"""
    try:
        reflection = get_reflection_system()
        stats = reflection.get_reflection_stats()
        
        return {
            "success": True,
            "data": stats,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance", response_model=Dict[str, Any])
async def get_performance_report():
    """获取性能报告"""
    try:
        reflection = get_reflection_system()
        report = reflection.get_performance_report()
        
        return {
            "success": True,
            "data": report,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/improvement-rule", response_model=Dict[str, Any])
async def add_improvement_rule(
    condition: str,
    action: str,
    confidence: float = 0.8,
):
    """
    添加改进规则
    
    Args:
        condition: 触发条件
        action: 执行动作
        confidence: 置信度
    """
    try:
        reflection = get_reflection_system()
        rule = reflection.add_improvement_rule(condition, action, confidence)
        
        return {
            "success": True,
            "data": {
                "rule_id": rule.rule_id,
                "condition": rule.condition,
                "action": rule.action,
                "confidence": rule.confidence,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/should-reflect", response_model=Dict[str, Any])
async def should_reflect(
    evaluation: Dict[str, float],
):
    """
    判断是否需要反思
    
    Args:
        evaluation: 评估结果
    """
    try:
        reflection = get_reflection_system()
        should = reflection.should_reflect(evaluation)
        
        return {
            "success": True,
            "data": {
                "should_reflect": should,
                "confidence": evaluation.get("confidence", 0.5),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))