"""LangGraph 图定义 - 统一版本（使用 Tool Calling + ReAct + CoT + 4级复杂度）

支持功能：
- 工具调用系统
- 复杂任务拆分
- 依赖分析
- 并行执行
- 上下文传递
- 质量评估
- ReAct 推理引擎（思考-行动-观察循环）
- CoT 思维链推理（详细链式推理）
- 4级复杂度分类（S/R/C/A）
- 策略回退机制
"""
from langgraph.graph import StateGraph, START, END
from app.agents.state import AgentState, WorkflowType, ReasoningMode, ComplexityLevel
from app.agents.nodes import AgentNodes
from app.agents.tools import ToolManager
from app.services.llm_service import LLMService
from app.core.logger import app_logger


def create_agent_graph(
    llm_service: LLMService,
    tool_manager: ToolManager,
    enable_react: bool = True,
    enable_cot: bool = True,
    enable_fallback: bool = True
) -> StateGraph:
    """
    创建统一的 Agent 图，支持 ReAct 和 CoT 推理模式，以及策略回退机制

    Args:
        llm_service: LLM 服务实例
        tool_manager: 工具管理器实例
        enable_react: 是否启用 ReAct 推理
        enable_cot: 是否启用 CoT 推理
        enable_fallback: 是否启用策略回退机制

    Returns:
        配置好的 StateGraph
    """
    nodes = AgentNodes(llm_service, tool_manager)

    graph = StateGraph(AgentState)

    # 核心节点
    graph.add_node("route_node", nodes.route_agent)
    graph.add_node("risk_node", nodes.risk_node)
    graph.add_node("tool_risk_node", nodes.tool_risk_node)
    graph.add_node("confirmation_node", nodes.confirmation_node)
    graph.add_node("retrieve_node", nodes.retrieve_node)
    graph.add_node("validate_node", nodes.validate_node)
    graph.add_node("repair_node", nodes.repair_node)
    
    # 确定性工作流节点
    graph.add_node("simple_qa_node", nodes.simple_qa_node)
    graph.add_node("minutes_node", nodes.minutes_node)
    graph.add_node("todos_node", nodes.todos_node)
    graph.add_node("controversy_node", nodes.controversy_node)
    graph.add_node("plan_node", nodes.plan_agent)
    graph.add_node("execute_node", nodes.execute_agent)
    graph.add_node("replan_node", nodes.replan_agent)
    
    # ReAct 和 CoT 推理节点
    if enable_react:
        graph.add_node("react_node", nodes.react_reasoning_node)
    if enable_cot:
        graph.add_node("cot_node", nodes.cot_reasoning_node)

    def should_retrieve(state: AgentState):
        if state.get("retrieval_required", True):
            return "retrieve_node"
        return route_workflow(state)

    def should_confirm(state: AgentState):
        if state.get("requires_confirmation", False):
            return "confirmation_node"
        return should_retrieve(state)

    def after_confirmation(state: AgentState):
        if state.get("confirmation_status") == "approved":
            pending_action = state.get("pending_action") or {}
            if pending_action.get("source") == "tool":
                return "execute_node"
            return should_retrieve(state)
        return "validate_node"

    def after_tool_risk(state: AgentState):
        if state.get("requires_confirmation", False):
            return "confirmation_node"
        return "execute_node"

    def route_workflow(state: AgentState):
        """根据复杂度级别和推理模式路由（4级分类）"""
        reasoning_mode = state.get("reasoning_mode", ReasoningMode.DEFAULT)
        complexity_level = state.get("complexity_level")
        
        # 如果指定了推理模式，优先使用
        if reasoning_mode == ReasoningMode.REACT and enable_react:
            return "react_node"
        if reasoning_mode == ReasoningMode.COT and enable_cot:
            return "cot_node"
        if reasoning_mode == ReasoningMode.PLAN:
            return "plan_node"
        
        # 否则按复杂度级别路由
        if complexity_level == ComplexityLevel.SIMPLE:
            return "simple_qa_node"
        elif complexity_level == ComplexityLevel.RETRIEVAL:
            return "simple_qa_node"
        elif complexity_level == ComplexityLevel.COT and enable_cot:
            return "cot_node"
        elif complexity_level == ComplexityLevel.AGENT and enable_react:
            return "react_node"
        
        # 按工作流类型回退
        workflow_type = state.get("workflow_type")
        if workflow_type == WorkflowType.MINUTES:
            return "minutes_node"
        if workflow_type == WorkflowType.TODO:
            return "todos_node"
        if workflow_type == WorkflowType.CONTROVERSY:
            return "controversy_node"
        if workflow_type == WorkflowType.COMPLEX:
            return "plan_node"
        
        return "simple_qa_node"

    def should_replan(state: AgentState):
        """判断是否需要重新规划"""
        reflection = state.get("reflection")
        if not reflection:
            return "validate_node"
        if reflection.get("needs_retry", False):
            return "plan_node"
        return "validate_node"

    def should_repair(state: AgentState):
        if state.get("confirmation_status") in ["required_but_disabled", "rejected"]:
            return END
        validation_errors = state.get("validation_errors") or []
        repair_count = int(state.get("repair_count", 0))
        max_repair_attempts = int(state.get("max_repair_attempts", 1))
        if validation_errors and repair_count < max_repair_attempts:
            return "repair_node"
        return END

    def fallback_strategy(state: AgentState):
        """策略回退机制：高级策略失败后降级到低级策略"""
        if not enable_fallback:
            return "validate_node"
        
        last_strategy = state.get("last_strategy")
        fallback_count = state.get("fallback_count", 0)
        
        # ReAct 失败 -> 降级到 CoT
        if last_strategy == "react" and enable_cot and fallback_count == 0:
            state["fallback_count"] = 1
            state["last_strategy"] = "cot"
            return "cot_node"
        
        # CoT 失败 -> 降级到简单问答（带检索）
        if last_strategy == "cot" and fallback_count == 1:
            state["fallback_count"] = 2
            state["last_strategy"] = "simple_qa"
            return "simple_qa_node"
        
        return "validate_node"

    # 主流程
    graph.add_edge(START, "route_node")
    graph.add_edge("route_node", "risk_node")
    
    # 风险评估后的分支
    risk_destinations = {
        "confirmation_node": "confirmation_node",
        "retrieve_node": "retrieve_node",
        "simple_qa_node": "simple_qa_node",
        "minutes_node": "minutes_node",
        "todos_node": "todos_node",
        "controversy_node": "controversy_node",
        "plan_node": "plan_node",
    }
    if enable_react:
        risk_destinations["react_node"] = "react_node"
    if enable_cot:
        risk_destinations["cot_node"] = "cot_node"
    
    graph.add_conditional_edges(
        "risk_node",
        should_confirm,
        risk_destinations,
    )
    
    # 确认后的分支
    confirmation_destinations = {
        "retrieve_node": "retrieve_node",
        "simple_qa_node": "simple_qa_node",
        "minutes_node": "minutes_node",
        "todos_node": "todos_node",
        "controversy_node": "controversy_node",
        "plan_node": "plan_node",
        "validate_node": "validate_node",
        "execute_node": "execute_node",
    }
    if enable_react:
        confirmation_destinations["react_node"] = "react_node"
    if enable_cot:
        confirmation_destinations["cot_node"] = "cot_node"
    
    graph.add_conditional_edges(
        "confirmation_node",
        after_confirmation,
        confirmation_destinations,
    )
    
    # 检索后的路由
    retrieve_destinations = {
        "simple_qa_node": "simple_qa_node",
        "minutes_node": "minutes_node",
        "todos_node": "todos_node",
        "controversy_node": "controversy_node",
        "plan_node": "plan_node",
    }
    if enable_react:
        retrieve_destinations["react_node"] = "react_node"
    if enable_cot:
        retrieve_destinations["cot_node"] = "cot_node"
    
    graph.add_conditional_edges(
        "retrieve_node",
        route_workflow,
        retrieve_destinations,
    )
    
    # 确定性工作流直接到验证
    graph.add_edge("simple_qa_node", "validate_node")
    graph.add_edge("minutes_node", "validate_node")
    graph.add_edge("todos_node", "validate_node")
    graph.add_edge("controversy_node", "validate_node")
    
    # ReAct 和 CoT 到验证（支持回退）
    if enable_react:
        if enable_fallback and enable_cot:
            graph.add_conditional_edges(
                "react_node",
                fallback_strategy,
                {
                    "cot_node": "cot_node",
                    "simple_qa_node": "simple_qa_node",
                    "validate_node": "validate_node",
                }
            )
        else:
            graph.add_edge("react_node", "validate_node")
    
    if enable_cot:
        if enable_fallback:
            graph.add_conditional_edges(
                "cot_node",
                fallback_strategy,
                {
                    "simple_qa_node": "simple_qa_node",
                    "validate_node": "validate_node",
                }
            )
        else:
            graph.add_edge("cot_node", "validate_node")
    
    # 验证和修复循环
    graph.add_conditional_edges(
        "validate_node",
        should_repair,
        {
            "repair_node": "repair_node",
            END: END,
        },
    )
    graph.add_edge("repair_node", "validate_node")
    
    # 复杂任务流程：计划 -> 工具风险 -> 执行 -> 重新规划 -> 验证
    graph.add_edge("plan_node", "tool_risk_node")
    graph.add_conditional_edges(
        "tool_risk_node",
        after_tool_risk,
        {
            "confirmation_node": "confirmation_node",
            "execute_node": "execute_node",
        },
    )
    graph.add_edge("execute_node", "replan_node")
    graph.add_conditional_edges(
        "replan_node",
        should_replan,
        {
            "plan_node": "plan_node",
            "validate_node": "validate_node",
        }
    )

    return graph


def print_agent_architecture():
    """打印 Agent 架构信息"""
    app_logger.info("=" * 70)
    app_logger.info("📊 Agent 架构（统一版本 - 4级复杂度 + ReAct + CoT + 策略回退）")
    app_logger.info("=" * 70)
    
    app_logger.info("\n📋 PLAN 阶段 - 规划 Agent")
    app_logger.info("   能力：问题分析 | 任务拆解 | 工具选择 | 依赖分析 | 并行规划")
    app_logger.info("   输出：执行计划 | 工具调用列表")
    
    app_logger.info("\n⚡ EXECUTE 阶段 - 执行 Agent")
    app_logger.info("   能力：任务执行 | 工具调用 | 并行执行 | 上下文传递 | 依赖管理")
    app_logger.info("   工具：search_meeting | extract_todos | generate_minutes | detect_controversies | answer_question")
    
    app_logger.info("\n🔄 REPLAN 阶段 - 重新规划 Agent")
    app_logger.info("   能力：质量评估 | 重新规划 | 循环迭代 | 持续改进")
    
    app_logger.info("\n🧠 REACT 推理引擎")
    app_logger.info("   能力：思考-行动-观察循环 | 动态决策 | 工具调用")
    app_logger.info("   适用场景：复杂问题推理、多步骤任务、需要探索的场景（复杂度 >= 0.75）")
    
    app_logger.info("\n🔗 CoT 思维链推理")
    app_logger.info("   能力：详细推理链展示 | 逻辑分解 | 置信度评估")
    app_logger.info("   适用场景：需要解释推理过程、中等复杂问答（复杂度 0.5-0.75）")
    
    app_logger.info("\n🔍 RAG 检索")
    app_logger.info("   能力：文档检索 | 事实查询 | 引用生成")
    app_logger.info("   适用场景：事实型问题、需要查资料（复杂度 0.3-0.5）")
    
    app_logger.info("\n💬 Simple QA")
    app_logger.info("   能力：直接问答 | 快速响应")
    app_logger.info("   适用场景：简单问题、无需检索（复杂度 < 0.3）")
    
    app_logger.info("\n" + "=" * 70)
    app_logger.info("工作流程：")
    app_logger.info("  1. ROUTE 智能分类：复杂度评估 + 多任务判断")
    app_logger.info("  2. 判断多任务？→ PLAN 拆解 → 子任务路由")
    app_logger.info("  3. 单任务 → 按复杂度路由（S/R/C/A）")
    app_logger.info("  4. RETRIEVE （可选）检索相关文档上下文")
    app_logger.info("  5. EXECUTE 根据复杂度级别执行推理")
    app_logger.info("  6. REPLAN/回退 评估结果，必要时降级策略")
    app_logger.info("  7. VALIDATE 验证输出格式和内容")
    app_logger.info("=" * 70)
    
    app_logger.info("\n4级复杂度分类策略：")
    app_logger.info("  - S (Simple): 0.0-0.3 → Simple QA（直接答，无需检索）")
    app_logger.info("  - R (Retrieval): 0.3-0.5 → RAG（检索+直接回答）")
    app_logger.info("  - C (CoT): 0.5-0.75 → CoT + 可选检索")
    app_logger.info("  - A (Agent): 0.75-1.0 → ReAct（内含CoT+行动+观察）")
    
    app_logger.info("\n策略回退机制：")
    app_logger.info("  - ReAct 失败 → 降级到 CoT")
    app_logger.info("  - CoT 失败 → 降级到 RAG/Simple QA")