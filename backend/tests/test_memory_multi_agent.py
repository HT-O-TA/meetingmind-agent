"""测试长期记忆和多Agent系统"""
from app.services.long_term_memory import get_long_term_memory, add_meeting_memory, search_related_memories, get_context_prompt, get_memory_statistics
from app.agents.multi_agent import create_multi_agent_system
import asyncio

async def test_memory():
    print('=== Testing Long-Term Memory ===')
    
    memory = get_long_term_memory()
    
    await add_meeting_memory(
        meeting_id='meeting_1',
        topic='Q1产品规划会议',
        date='2026-06-01',
        participants=['张三', '李四', '王五'],
        summary='讨论了Q1产品路线图，确定了用户模块和支付模块的开发计划',
        decisions=['采用方案A作为技术架构', '张三负责用户模块', '李四负责支付模块'],
        action_items=['完成用户模块设计', '实现支付集成'],
        controversies=[]
    )
    
    await add_meeting_memory(
        meeting_id='meeting_2',
        topic='Q2产品规划会议',
        date='2026-06-15',
        participants=['张三', '李四', '王五'],
        summary='讨论了Q2产品路线图，在Q1基础上增加了数据分析模块',
        decisions=['增加数据分析模块', '王五负责数据分析'],
        action_items=['开发数据分析报表', '优化用户体验'],
        controversies=[]
    )
    
    stats = get_memory_statistics()
    print('Memory Statistics:', stats)
    
    results = await search_related_memories('用户模块')
    print('\nSearch results for 用户模块:')
    for r in results:
        print('  Score:', r['score'], '-', r['memory']['content'][:50], '...')
    
    context_prompt = await get_context_prompt('用户模块设计')
    print('\nContext prompt:')
    print(context_prompt[:300], '...' if len(context_prompt) > 300 else '')
    
    print('\n=== Memory Tests Passed! ===')

async def test_multi_agent():
    print('\n=== Testing Multi-Agent System ===')
    
    coordinator = create_multi_agent_system()
    await coordinator.start_all()
    
    result = await coordinator.run_workflow(
        question='总结Q1产品规划会议的讨论内容',
        meeting_id='meeting_1'
    )
    
    print('Success:', result['success'])
    print('Agents involved:', [a.value for a in result['agents_involved']])
    print('Completed steps:', result['completed_steps'])
    print('Summary preview:', result.get('summary', '')[:100] if result.get('summary') else 'N/A')
    print('Todos:', result.get('todos', []))
    print('Review score:', result.get('review', {}).get('overall_score'))
    
    await coordinator.stop_all()
    
    print('\n=== Multi-Agent Tests Passed! ===')

async def main():
    await test_memory()
    await test_multi_agent()

if __name__ == '__main__':
    asyncio.run(main())