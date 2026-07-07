"""测试动态工具发现和反思系统"""
from app.agents.tools.dynamic_tool_discovery import get_dynamic_tool_discovery, get_tool_combination_engine, DiscoveryStrategy
from app.agents.reflection import get_reflection_system
import asyncio

async def test_dynamic_tool_discovery():
    print('=== Testing Dynamic Tool Discovery ===')
    
    discovery = get_dynamic_tool_discovery()
    
    results = await discovery.discover_tools(
        query='总结会议内容',
        strategy=DiscoveryStrategy.HYBRID,
        max_tools=5,
    )
    
    print(f'发现 {len(results)} 个工具:')
    for i, result in enumerate(results, 1):
        print(f'  {i}. {result.tool_id} ({result.name}) - 分数: {result.score:.2f} - {result.reason}')
    
    plan = await discovery.suggest_tool_combination('分析会议记录')
    print(f'\n工具组合计划:')
    print(f'  计划ID: {plan.plan_id}')
    print(f'  执行顺序: {plan.execution_order}')
    print(f'  工具数量: {len(plan.tools)}')
    for tool in plan.tools:
        print(f'    - {tool["tool_id"]} ({tool["name"]})')
    
    print('\n=== Dynamic Tool Discovery Tests Passed! ===')

async def test_tool_combination_engine():
    print('\n=== Testing Tool Combination Engine ===')
    
    engine = get_tool_combination_engine()
    
    rules = engine.get_combination_rules()
    print(f'组合规则数量: {len(rules)}')
    for rule in rules:
        print(f'  {rule.rule_id}: {rule.description}')
    
    matched = engine.match_combinations('会议分析')
    print(f'\n匹配规则: {[r.rule_id for r in matched]}')
    
    plan = await engine.generate_combination_plan('会议分析')
    print(f'生成计划: {plan.plan_id}')
    print(f'工具: {[t["tool_id"] for t in plan.tools]}')
    
    print('\n=== Tool Combination Engine Tests Passed! ===')

async def test_reflection_system():
    print('\n=== Testing Reflection System ===')
    
    reflection = get_reflection_system()
    
    evaluation = reflection.perform_self_evaluation(
        input_text='分析Q1产品规划会议的讨论内容',
        output_text='会议讨论了产品规划。张三负责用户模块。'
    )
    
    print('自我评估结果:')
    for metric, score in evaluation.items():
        metric_name = metric.value if hasattr(metric, 'value') else metric
        print(f'  {metric_name}: {score:.2f}')
    
    should_reflect = reflection.should_reflect({k.value if hasattr(k, 'value') else k: v for k, v in evaluation.items()})
    print(f'\n需要反思: {should_reflect}')
    
    result = await reflection.reflect_and_replan(
        input_text='分析Q1产品规划会议的讨论内容',
        output_text='会议讨论了产品规划。张三负责用户模块。',
        tools_used=['search_meeting'],
        max_iterations=2,
    )
    
    print(f'\n反思结果:')
    print(f'  迭代次数: {result["iterations"]}')
    print(f'  置信度: {result["confidence"]:.2f}')
    print(f'  新工具: {result["tools"]}')
    print(f'  新计划步骤: {[p["step"] for p in result["plan"]]}')
    
    stats = reflection.get_reflection_stats()
    print(f'\n反思统计:')
    print(f'  反思笔记总数: {stats["total_reflection_notes"]}')
    print(f'  活跃规则数: {stats["active_rules"]}')
    
    print('\n=== Reflection System Tests Passed! ===')

async def main():
    await test_dynamic_tool_discovery()
    await test_tool_combination_engine()
    await test_reflection_system()

if __name__ == '__main__':
    asyncio.run(main())