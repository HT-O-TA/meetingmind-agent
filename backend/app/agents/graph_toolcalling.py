"""LangGraph 图定义 - Tool Calling 版本"""
from langgraph.graph import StateGraph, START, END
from app.agents.state import AgentState
from app.agents.nodes_toolcalling import ToolCallingNodes
from app.agents.tools import ToolManager
from app.services.llm_service import LLMService
from app.core.logger import app_logger


def create_tool_calling_graph(
    llm_service: LLMService,
    tool_manager: ToolManager
) -> StateGraph:
    """
    创建支持 Tool Calling 的 Agent 图

    Args:
        llm_service: LLM 服务实例
        tool_manager: 工具管理器

    Returns:
        配置好的 StateGraph
    """
    nodes = ToolCallingNodes(llm_service, tool_manager)

    graph = StateGraph(AgentState)

    graph.add_node("plan", nodes.plan_agent)
    graph.add_node("execute", nodes.execute_agent)
    graph.add_node("reflect", nodes.reflect_agent)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "execute")
    graph.add_edge("execute", "reflect")
    graph.add_edge("reflect", END)

    return graph


def print_tool_calling_architecture():
    """打印 Tool Calling 架构信息"""
    app_logger.info("=" * 70)
    app_logger.info("Agent Tool Calling 架构")
    app_logger.info("=" * 70)
    
    app_logger.info("\n📋 PLAN 阶段 - 规划 + 工具选择")
    app_logger.info("   能力: 问题分析 | 任务拆解 | 工具选择 | 依赖分析")
    app_logger.info("   输出: 执行计划 | 工具调用列表")
    
    app_logger.info("\n⚡ EXECUTE 阶段 - 工具执行")
    app_logger.info("   能力: 工具调用 | 并行执行 | 上下文传递 | 依赖管理")
    app_logger.info("   工具: search_meeting | extract_todos | generate_minutes | detect_controversies | answer_question")
    
    app_logger.info("\n🔍 REFLECT 阶段 - 反思评估")
    app_logger.info("   能力: 质量评估 | 缺陷检测 | 改进建议")
    
    app_logger.info("\n" + "=" * 70)
    app_logger.info("Tool Calling 流程:")
    app_logger.info("  1. LLM 分析问题，决定调用哪些工具")
    app_logger.info("  2. Plan Agent 生成执行计划 + 工具调用列表")
    app_logger.info("  3. Execute Agent 按计划调用工具")
    app_logger.info("  4. 工具执行结果存储到上下文")
    app_logger.info("  5. Reflect Agent 评估结果质量")
    app_logger.info("=" * 70)