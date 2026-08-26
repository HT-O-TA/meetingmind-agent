"""反馈与 Bad Case API 端点"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any, Optional
from app.db.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.feedback import FeedbackType, BadCaseCategory, ResolutionStatus
from app.services.feedback_service import get_feedback_service, FeedbackService

router = APIRouter(tags=["用户反馈"])


@router.post("/feedback", response_model=Dict[str, Any])
async def submit_feedback(
    input_text: str,
    output_text: str,
    rating: Optional[int] = None,
    comment: Optional[str] = None,
    feedback_type: str = "user_comment",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    提交用户反馈
    """
    try:
        feedback_type_enum = FeedbackType(feedback_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的反馈类型")
    
    service = await get_feedback_service(db)
    feedback = await service.add_feedback(
        feedback_type=feedback_type_enum,
        input_text=input_text,
        output_text=output_text,
        rating=rating,
        comment=comment
    )
    
    return {
        "message": "反馈提交成功",
        "feedback_id": feedback.feedback_id,
        "created_bad_case": feedback.bad_case_id is not None
    }


@router.get("/feedback", response_model=List[Dict[str, Any]])
async def get_feedbacks(
    feedback_type: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    获取反馈列表
    """
    service = await get_feedback_service(db)
    
    feedback_type_enum = None
    if feedback_type:
        try:
            feedback_type_enum = FeedbackType(feedback_type)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的反馈类型")
    
    feedbacks = await service.get_feedbacks(
        feedback_type=feedback_type_enum,
        limit=limit,
        offset=offset
    )
    
    return [
        {
            "feedback_id": f.feedback_id,
            "type": f.type.value,
            "input_text": f.input_text,
            "output_text": f.output_text,
            "rating": f.rating,
            "comment": f.comment,
            "timestamp": f.timestamp.isoformat()
        }
        for f in feedbacks
    ]


@router.post("/bad-cases", response_model=Dict[str, Any])
async def add_bad_case(
    input_text: str,
    actual_output: str,
    category: str,
    expected_output: Optional[str] = None,
    priority: str = "medium",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    添加 Bad Case
    """
    try:
        category_enum = BadCaseCategory(category)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的分类类型")
    
    service = await get_feedback_service(db)
    bad_case = await service.add_bad_case(
        input_text=input_text,
        actual_output=actual_output,
        category=category_enum,
        expected_output=expected_output,
        priority=priority
    )
    
    return {
        "message": "Bad Case 添加成功",
        "bad_case_id": bad_case.bad_case_id,
        "category": bad_case.category.value
    }


@router.get("/bad-cases", response_model=List[Dict[str, Any]])
async def get_bad_cases(
    category: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    获取 Bad Case 列表
    """
    service = await get_feedback_service(db)
    
    category_enum = None
    if category:
        try:
            category_enum = BadCaseCategory(category)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的分类类型")
    
    status_enum = None
    if status:
        try:
            status_enum = ResolutionStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的状态类型")
    
    bad_cases = await service.get_bad_cases(
        category=category_enum,
        status=status_enum,
        priority=priority,
        limit=limit,
        offset=offset
    )
    
    return [
        {
            "bad_case_id": bc.bad_case_id,
            "category": bc.category.value,
            "input_text": bc.input_text,
            "actual_output": bc.actual_output,
            "expected_output": bc.expected_output,
            "analysis": bc.analysis,
            "improvement_plan": bc.improvement_plan,
            "resolution_status": bc.resolution_status.value,
            "priority": bc.priority,
            "timestamp": bc.timestamp.isoformat()
        }
        for bc in bad_cases
    ]


@router.get("/bad-cases/{bad_case_id}", response_model=Dict[str, Any])
async def get_bad_case(
    bad_case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    获取单个 Bad Case 详情
    """
    service = await get_feedback_service(db)
    bad_case = await service.get_bad_case(bad_case_id)
    
    if not bad_case:
        raise HTTPException(status_code=404, detail="Bad Case 不存在")
    
    return {
        "bad_case_id": bad_case.bad_case_id,
        "category": bad_case.category.value,
        "input_text": bad_case.input_text,
        "actual_output": bad_case.actual_output,
        "expected_output": bad_case.expected_output,
        "analysis": bad_case.analysis,
        "improvement_plan": bad_case.improvement_plan,
        "resolution_status": bad_case.resolution_status.value,
        "priority": bad_case.priority,
        "timestamp": bad_case.timestamp.isoformat(),
        "updated_at": bad_case.updated_at.isoformat() if bad_case.updated_at else None
    }


@router.put("/bad-cases/{bad_case_id}", response_model=Dict[str, Any])
async def update_bad_case(
    bad_case_id: str,
    expected_output: Optional[str] = None,
    analysis: Optional[str] = None,
    improvement_plan: Optional[str] = None,
    resolution_status: Optional[str] = None,
    priority: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    更新 Bad Case
    """
    update_data = {}
    if expected_output is not None:
        update_data["expected_output"] = expected_output
    if analysis is not None:
        update_data["analysis"] = analysis
    if improvement_plan is not None:
        update_data["improvement_plan"] = improvement_plan
    if resolution_status is not None:
        try:
            update_data["resolution_status"] = ResolutionStatus(resolution_status)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的状态类型")
    if priority is not None:
        update_data["priority"] = priority
    
    service = await get_feedback_service(db)
    bad_case = await service.update_bad_case(bad_case_id, **update_data)
    
    if not bad_case:
        raise HTTPException(status_code=404, detail="Bad Case 不存在")
    
    return {
        "message": "Bad Case 更新成功",
        "bad_case_id": bad_case.bad_case_id
    }


@router.post("/bad-cases/{bad_case_id}/analyze", response_model=Dict[str, Any])
async def analyze_bad_case(
    bad_case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    分析 Bad Case 并生成改进建议
    """
    service = await get_feedback_service(db)
    
    try:
        bad_case = await service.analyze_bad_case(bad_case_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    return {
        "message": "Bad Case 分析完成",
        "bad_case_id": bad_case.bad_case_id,
        "analysis": bad_case.analysis,
        "improvement_plan": bad_case.improvement_plan,
        "status": bad_case.resolution_status.value
    }


@router.post("/bad-cases/{bad_case_id}/improvements", response_model=Dict[str, Any])
async def add_improvement(
    bad_case_id: str,
    action_type: str,
    description: str,
    details: Optional[Dict[str, Any]] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    添加改进记录
    """
    service = await get_feedback_service(db)
    
    try:
        record = await service.add_improvement_record(
            bad_case_id=bad_case_id,
            action_type=action_type,
            description=description,
            details=details
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    return {
        "message": "改进记录添加成功",
        "improvement_id": record.improvement_id,
        "action_type": record.action_type
    }


@router.post("/improvements/{improvement_id}/verify", response_model=Dict[str, Any])
async def verify_improvement(
    improvement_id: str,
    result: str,  # passed, failed, pending
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    验证改进效果
    """
    if result not in ["passed", "failed", "pending"]:
        raise HTTPException(status_code=400, detail="无效的验证结果")
    
    service = await get_feedback_service(db)
    
    try:
        record = await service.verify_improvement(improvement_id, result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    return {
        "message": "改进验证完成",
        "improvement_id": record.improvement_id,
        "verification_result": record.verification_result,
        "verified_at": record.verified_at.isoformat() if record.verified_at else None
    }


@router.get("/bad-cases/patterns", response_model=List[Dict[str, Any]])
async def analyze_bad_case_patterns(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    分析 Bad Case 模式
    """
    service = await get_feedback_service(db)
    patterns = await service.analyze_bad_case_patterns(limit=limit)
    
    return patterns
