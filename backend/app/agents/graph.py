"""LangGraph 图定义 - 复杂任务拆分（依赖分析 + 上下文传递 + 并行执行）"""
from langgraph.graph import StateGraph, START, END
from app.agents.state import AgentState, TaskType
from app.agents.nodes import AgentNodes, AgentCards
from app.services.llm_service import LLMService
from app.core.logger import app_logger


def create_agent_graph(llm_service: LLMService, vector_search_service=None) -> StateGraph:
    """
    创建 Agent 图 - 复杂任务拆分
    
    支持：
    1. 依赖分析：识别任务间的依赖关系
    2. 上下文传递：一个任务的输出作为另一个任务的输入
    3. 并行执行：可并行执行的任务同时处理
    
    Args:
        llm_service: LLM 服务实例
        vector_search_service: 向量检索服务实例（可选）

    Returns:
        配置好的 StateGraph
    """
    nodes = AgentNodes(llm_service, vector_search_service)

    graph = StateGraph(AgentState)

    graph.add_node("plan", nodes.plan_agent)
    graph.add_node("execute", nodes.execute_agent)
    graph.add_node("reflect", nodes.reflect_agent)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "execute")
    graph.add_edge("execute", "reflect")
    graph.add_edge("reflect", END)

    return graph


def print_agent_architecture():
    """打印 Agent 架构信息"""
    app_logger.info("=" * 70)
    app_logger.info("Plan-Execute-Reflect 复杂任务拆分架构")
    app_logger.info("=" * 70)
    
    app_logger.info("\n📋 PLAN 阶段 - 规划 Agent")
    app_logger.info("   能力: 问题分析 | 任务拆解 | 依赖分析 | 并行规划")
    app_logger.info("   输出: 任务列表 | 依赖关系 | 并行分组 | 上下文传递计划")
    
    app_logger.info("\n⚡ EXECUTE 阶段 - 执行 Agent")
    app_logger.info("   能力: 顺序执行 | 并行执行 | 上下文传递 | 依赖管理")
    app_logger.info("   子任务: retrieve | qa | minutes | todo | controversy | combine")
    
    app_logger.info("\n🔍 REFLECT 阶段 - 反思 Agent")
    app_logger.info("   能力: 质量评估 | 缺陷检测 | 改进建议")
    
    app_logger.info("\n" + "=" * 70)
    app_logger.info("任务拆分示例:")
    app_logger.info("  用户问题: '这个会议有哪些待办和争议点？'")
    app_logger.info("  拆分结果:")
    app_logger.info("    Group-1 (并行): [task_1: 抽取待办] + [task_2: 识别争议]")
    app_logger.info("    Group-2 (顺序): [task_3: 整合结果]")
    app_logger.info("=" * 70)