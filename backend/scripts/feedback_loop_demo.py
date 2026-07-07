"""用户反馈闭环演示脚本"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.db.database import init_db, AsyncSessionLocal
from app.services.feedback_service import get_feedback_service
from app.models.feedback import FeedbackType, BadCaseCategory


async def feedback_loop_demo():
    """演示完整的用户反馈闭环流程"""
    print("=" * 70)
    print("    用户反馈闭环演示 - Bad Case + 迭代机制")
    print("=" * 70)
    
    # 1. 初始化数据库
    print("\n📦 步骤1: 初始化数据库...")
    await init_db()
    
    # 2. 获取数据库会话和服务
    async with AsyncSessionLocal() as db:
        service = await get_feedback_service(db)
        
        # 3. 模拟用户反馈（低评分触发 Bad Case）
        print("\n📝 步骤2: 模拟用户提交低评分反馈...")
        feedback = await service.add_feedback(
            feedback_type=FeedbackType.USER_RATING,
            input_text="2025年公司的营收目标是多少？",
            output_text="抱歉，我无法回答这个问题。",
            rating=2,  # 低评分
            comment="回答太敷衍了，完全没有帮助"
        )
        print(f"   ✅ 反馈提交成功: {feedback.feedback_id}")
        print(f"   评分: {feedback.rating} 分")
        print(f"   是否创建 Bad Case: {'✅ 是' if feedback.bad_case_id else '❌ 否'}")
        
        # 4. 获取自动创建的 Bad Case
        print("\n🔍 步骤3: 查看自动创建的 Bad Case...")
        bad_cases = await service.get_bad_cases(limit=5)
        if bad_cases:
            bc = bad_cases[0]
            print(f"   Bad Case ID: {bc.bad_case_id}")
            print(f"   分类: {bc.category.value}")
            print(f"   问题: {bc.input_text[:50]}...")
            print(f"   当前状态: {bc.resolution_status.value}")
        else:
            print("   ⚠️ 未找到 Bad Case")
            return
        
        # 5. 分析 Bad Case
        print("\n🔬 步骤4: 分析 Bad Case 并生成改进建议...")
        analyzed_bc = await service.analyze_bad_case(bc.bad_case_id)
        print(f"   ✅ 分析完成")
        print(f"   分析结果:\n{analyzed_bc.analysis}")
        print(f"\n   改进计划:\n{analyzed_bc.improvement_plan}")
        
        # 6. 添加改进记录
        print("\n🛠️ 步骤5: 实施改进措施...")
        improvement = await service.add_improvement_record(
            bad_case_id=bc.bad_case_id,
            action_type="prompt_update",
            description="优化回答模板，增加信息检索失败时的友好提示",
            details={
                "template_name": "qa_prompt",
                "changes": ["添加信息不足时的追问逻辑", "优化错误提示话术"],
                "version": "v2.1"
            }
        )
        print(f"   ✅ 改进记录添加成功: {improvement.improvement_id}")
        print(f"   改进类型: {improvement.action_type}")
        
        # 7. 验证改进效果
        print("\n✅ 步骤6: 验证改进效果...")
        verified = await service.verify_improvement(improvement.improvement_id, "passed")
        print(f"   ✅ 验证完成")
        print(f"   验证结果: {verified.verification_result}")
        
        # 8. 获取性能报告
        print("\n📊 步骤7: 查看性能报告...")
        report = await service.get_performance_report()
        print(f"   总反馈数: {report['total_feedbacks']}")
        print(f"   平均评分: {report['avg_rating']}")
        print(f"   Bad Case 总数: {report['total_bad_cases']}")
        print(f"   成功率: {report['success_rate'] * 100}%")
        
        # 9. 分析 Bad Case 模式
        print("\n📈 步骤8: 分析 Bad Case 模式...")
        patterns = await service.analyze_bad_case_patterns()
        print("   Bad Case 分类分布:")
        for pattern in patterns:
            print(f"     - {pattern['category']}: {pattern['count']} 个 ({pattern['percentage']}%)")
    
    print("\n" + "=" * 70)
    print("    🎉 反馈闭环演示完成!")
    print("=" * 70)
    print("\n闭环流程:")
    print("  用户反馈 → Bad Case 创建 → 分析 → 改进 → 验证 → 持续迭代")


if __name__ == "__main__":
    asyncio.run(feedback_loop_demo())
