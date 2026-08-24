"""反馈服务 - 支持 Bad Case 管理和迭代改进"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logger import app_logger
from app.core.config import settings
from app.models.feedback import (
    Feedback, BadCase, ImprovementRecord, PerformanceMetric,
    FeedbackType, BadCaseCategory, ResolutionStatus
)
from app.agents.reflection import reflection_system, EvaluationMetric


class FeedbackService:
    """反馈服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def add_feedback(
        self,
        feedback_type: FeedbackType,
        input_text: str,
        output_text: str,
        rating: Optional[int] = None,
        comment: Optional[str] = None,
        metrics: Optional[Dict[str, float]] = None,
        corrections: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Feedback:
        """添加反馈"""
        feedback = Feedback(
            feedback_id=f"fb_{int(datetime.now().timestamp())}",
            type=feedback_type,
            input_text=input_text,
            output_text=output_text,
            rating=rating,
            comment=comment,
            metrics=metrics,
            corrections=corrections,
            context=context
        )
        
        self.db.add(feedback)
        await self.db.commit()
        await self.db.refresh(feedback)
        
        # 同步到内存反思系统
        reflection_system.add_feedback(
            type=feedback_type,
            input_text=input_text,
            output_text=output_text,
            rating=rating,
            comment=comment,
            metrics=metrics,
            corrections=corrections,
            context=context
        )
        
        # 自动创建 Bad Case（评分低于3分或失败类型）
        if (rating is not None and rating < 3) or feedback_type == FeedbackType.FAILURE:
            await self._auto_create_bad_case(feedback)
        
        app_logger.info(f"[Feedback] 添加反馈: {feedback.feedback_id}")
        return feedback
    
    async def _auto_create_bad_case(self, feedback: Feedback) -> Optional[BadCase]:
        """自动创建 Bad Case"""
        # 判断分类
        category = self._determine_category(feedback)
        
        bad_case = BadCase(
            bad_case_id=f"bc_{int(datetime.now().timestamp())}",
            category=category,
            input_text=feedback.input_text,
            actual_output=feedback.output_text,
            priority="high" if (feedback.rating is not None and feedback.rating <= 2) else "medium"
        )
        
        self.db.add(bad_case)
        await self.db.commit()
        await self.db.refresh(bad_case)
        
        # 关联反馈
        feedback.bad_case_id = bad_case.id
        await self.db.commit()
        
        app_logger.info(f"[Feedback] 自动创建 Bad Case: {bad_case.bad_case_id}")
        return bad_case
    
    def _determine_category(self, feedback: Feedback) -> BadCaseCategory:
        """确定 Bad Case 分类"""
        output = feedback.output_text.lower()
        
        if feedback.type == FeedbackType.CORRECTION or feedback.corrections:
            return BadCaseCategory.FACTUAL_ERROR
        
        if any(phrase in output for phrase in ["不知道", "无法回答", "缺少信息"]):
            return BadCaseCategory.INCOMPLETE
        
        if any(phrase in output for phrase in ["错误", "不正确", "不对"]):
            return BadCaseCategory.FACTUAL_ERROR
        
        return BadCaseCategory.OTHER
    
    async def add_bad_case(
        self,
        input_text: str,
        actual_output: str,
        category: BadCaseCategory,
        expected_output: Optional[str] = None,
        priority: str = "medium"
    ) -> BadCase:
        """手动添加 Bad Case"""
        bad_case = BadCase(
            bad_case_id=f"bc_{int(datetime.now().timestamp())}",
            category=category,
            input_text=input_text,
            actual_output=actual_output,
            expected_output=expected_output,
            priority=priority
        )
        
        self.db.add(bad_case)
        await self.db.commit()
        await self.db.refresh(bad_case)
        
        app_logger.info(f"[Feedback] 添加 Bad Case: {bad_case.bad_case_id}")
        return bad_case
    
    async def get_bad_case(self, bad_case_id: str) -> Optional[BadCase]:
        """获取 Bad Case"""
        result = await self.db.execute(
            select(BadCase).where(BadCase.bad_case_id == bad_case_id)
        )
        return result.scalars().first()
    
    async def get_bad_cases(
        self,
        category: Optional[BadCaseCategory] = None,
        status: Optional[ResolutionStatus] = None,
        priority: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[BadCase]:
        """获取 Bad Case 列表"""
        query = select(BadCase)
        
        if category:
            query = query.where(BadCase.category == category)
        if status:
            query = query.where(BadCase.resolution_status == status)
        if priority:
            query = query.where(BadCase.priority == priority)
        
        query = query.order_by(BadCase.timestamp.desc()).limit(limit).offset(offset)
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def update_bad_case(
        self,
        bad_case_id: str,
        **kwargs
    ) -> Optional[BadCase]:
        """更新 Bad Case"""
        bad_case = await self.get_bad_case(bad_case_id)
        if not bad_case:
            return None
        
        for key, value in kwargs.items():
            if hasattr(bad_case, key):
                setattr(bad_case, key, value)
        
        bad_case.updated_at = datetime.now()
        await self.db.commit()
        await self.db.refresh(bad_case)
        
        app_logger.info(f"[Feedback] 更新 Bad Case: {bad_case_id}")
        return bad_case
    
    async def analyze_bad_case(self, bad_case_id: str) -> BadCase:
        """分析 Bad Case 并生成改进建议"""
        bad_case = await self.get_bad_case(bad_case_id)
        if not bad_case:
            raise ValueError(f"Bad Case 不存在: {bad_case_id}")
        
        # 使用反思系统进行分析
        metrics = reflection_system.perform_self_evaluation(
            bad_case.input_text,
            bad_case.actual_output
        )
        
        # 生成分析报告
        analysis = self._generate_analysis(bad_case, metrics)
        improvement_plan = self._generate_improvement_plan(bad_case, metrics)
        
        bad_case.analysis = analysis
        bad_case.improvement_plan = improvement_plan
        bad_case.resolution_status = ResolutionStatus.ANALYZED
        
        await self.db.commit()
        await self.db.refresh(bad_case)
        
        app_logger.info(f"[Feedback] 分析 Bad Case: {bad_case_id}")
        return bad_case
    
    def _generate_analysis(self, bad_case: BadCase, metrics: Dict) -> str:
        """生成分析报告"""
        analysis_parts = []
        
        if bad_case.category == BadCaseCategory.FACTUAL_ERROR:
            analysis_parts.append("问题类型：事实错误")
        elif bad_case.category == BadCaseCategory.INCOMPLETE:
            analysis_parts.append("问题类型：回答不完整")
        else:
            analysis_parts.append(f"问题类型：{bad_case.category.value}")
        
        if metrics:
            analysis_parts.append(f"\n自我评估指标：")
            for metric, score in metrics.items():
                analysis_parts.append(f"  - {metric.value}: {score:.2f}")
        
        analysis_parts.append("\n建议：需要进一步分析根本原因并实施改进。")
        
        return "\n".join(analysis_parts)
    
    def _generate_improvement_plan(self, bad_case: BadCase, metrics: Dict) -> str:
        """生成改进计划"""
        plan_items = []
        
        if bad_case.category == BadCaseCategory.FACTUAL_ERROR:
            plan_items.append("1. 验证回答中的事实准确性")
            plan_items.append("2. 补充正确信息到知识库")
            plan_items.append("3. 优化检索策略确保获取准确信息")
        
        elif bad_case.category == BadCaseCategory.INCOMPLETE:
            plan_items.append("1. 分析回答缺失的信息")
            plan_items.append("2. 优化Prompt模板增加完整性检查")
            plan_items.append("3. 增加多轮追问能力")
        
        else:
            plan_items.append("1. 分析问题根本原因")
            plan_items.append("2. 根据具体问题制定改进措施")
            plan_items.append("3. 验证改进效果")
        
        plan_items.append("\n优先级：" + ("高" if bad_case.priority == "high" else "中"))
        
        return "\n".join(plan_items)
    
    async def add_improvement_record(
        self,
        bad_case_id: str,
        action_type: str,
        description: str,
        details: Optional[Dict[str, Any]] = None
    ) -> ImprovementRecord:
        """添加改进记录"""
        bad_case = await self.get_bad_case(bad_case_id)
        if not bad_case:
            raise ValueError(f"Bad Case 不存在: {bad_case_id}")
        
        record = ImprovementRecord(
            improvement_id=f"imp_{int(datetime.now().timestamp())}",
            bad_case_id=bad_case.id,
            action_type=action_type,
            description=description,
            details=details
        )
        
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        
        # 更新 Bad Case 状态
        bad_case.resolution_status = ResolutionStatus.IMPROVED
        await self.db.commit()
        
        app_logger.info(f"[Feedback] 添加改进记录: {record.improvement_id}")
        return record
    
    async def verify_improvement(self, improvement_id: str, verification_result: str) -> ImprovementRecord:
        """验证改进效果"""
        query_result = await self.db.execute(
            select(ImprovementRecord).where(ImprovementRecord.improvement_id == improvement_id)
        )
        record = query_result.scalars().first()
        
        if not record:
            raise ValueError(f"改进记录不存在: {improvement_id}")
        
        record.verification_result = verification_result
        record.verified_at = datetime.now()
        
        await self.db.commit()
        await self.db.refresh(record)
        
        # 如果验证通过，更新 Bad Case 状态
        if verification_result == "passed":
            bad_case = await self.get_bad_case_by_id(record.bad_case_id)
            if bad_case:
                bad_case.resolution_status = ResolutionStatus.VERIFIED
                await self.db.commit()
        
        app_logger.info(f"[Feedback] 验证改进记录: {improvement_id} -> {verification_result}")
        return record
    
    async def get_bad_case_by_id(self, id: int) -> Optional[BadCase]:
        """通过ID获取 Bad Case"""
        result = await self.db.execute(
            select(BadCase).where(BadCase.id == id)
        )
        return result.scalars().first()
    
    async def get_feedbacks(
        self,
        feedback_type: Optional[FeedbackType] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Feedback]:
        """获取反馈列表"""
        query = select(Feedback)
        
        if feedback_type:
            query = query.where(Feedback.type == feedback_type)
        
        query = query.order_by(Feedback.timestamp.desc()).limit(limit).offset(offset)
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def get_performance_report(self) -> Dict[str, Any]:
        """获取性能报告"""
        # 从数据库获取统计（分开查询避免隐式交叉连接）
        fb_result = await self.db.execute(
            select(
                func.count(Feedback.id).label("total_feedbacks"),
                func.avg(Feedback.rating).label("avg_rating"),
            )
        )
        fb_stats = fb_result.first()
        bc_result = await self.db.execute(
            select(func.count(BadCase.id).label("total_bad_cases"))
        )
        bc_stats = bc_result.first()

        class _Stats:
            def __init__(self):
                self.total_feedbacks = fb_stats[0] if fb_stats else 0
                self.avg_rating = fb_stats[1] if fb_stats else None
                self.total_bad_cases = bc_stats[0] if bc_stats else 0

        stats = _Stats()
        
        # 获取按评分分布
        rating_result = await self.db.execute(
            select(Feedback.rating, func.count(Feedback.id))
            .where(Feedback.rating.isnot(None))
            .group_by(Feedback.rating)
        )
        rating_dist = {r[0]: r[1] for r in rating_result.all()}
        
        # 获取按状态分布的 Bad Case
        status_result = await self.db.execute(
            select(BadCase.resolution_status, func.count(BadCase.id))
            .group_by(BadCase.resolution_status)
        )
        status_dist = {str(r[0]): r[1] for r in status_result.all()}
        
        return {
            "total_feedbacks": stats.total_feedbacks or 0,
            "avg_rating": round(stats.avg_rating, 2) if stats.avg_rating else 0.0,
            "rating_distribution": rating_dist,
            "total_bad_cases": stats.total_bad_cases or 0,
            "bad_case_status_distribution": status_dist,
            "success_rate": self._calculate_success_rate(rating_dist)
        }
    
    def _calculate_success_rate(self, rating_dist: Dict[int, int]) -> float:
        """计算成功率"""
        total = sum(rating_dist.values())
        if total == 0:
            return 0.0
        successful = rating_dist.get(4, 0) + rating_dist.get(5, 0)
        return round(successful / total, 2)
    
    async def analyze_bad_case_patterns(self, limit: int = 10) -> List[Dict[str, Any]]:
        """分析 Bad Case 模式"""
        # 获取按分类统计
        result = await self.db.execute(
            select(BadCase.category, func.count(BadCase.id))
            .group_by(BadCase.category)
            .order_by(func.count(BadCase.id).desc())
        )
        
        patterns = []
        for category, count in result.all()[:limit]:
            patterns.append({
                "category": category.value,
                "count": count,
                "percentage": round(count / (await self._get_total_bad_cases()) * 100, 2)
            })
        
        return patterns
    
    async def _get_total_bad_cases(self) -> int:
        """获取 Bad Case 总数"""
        result = await self.db.execute(select(func.count(BadCase.id)))
        return result.scalar() or 0


async def get_feedback_service(db: AsyncSession) -> FeedbackService:
    """获取反馈服务实例"""
    return FeedbackService(db)
