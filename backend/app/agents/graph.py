"""LangGraph 正式图定义：Simple RAG + Tool Agent。

支持功能：
- 工具调用系统
- 复杂任务拆分
- 依赖分析
- 并行执行
- 上下文传递
- 质量评估
ReAct、CoT 和深度反思代码暂时保留为显式可选能力，默认不进入正式路径。
"""
from typing import Any
from langgraph.graph import StateGraph, START, END
from app.agents.state import AgentState, WorkflowType, ReasoningMode, ComplexityLevel
from app.agents.nodes import AgentNodes
from app.agents.tools import ToolManager
from app.agents.checkpointer import get_checkpointer
from app.services.llm_service import LLMService
from app.core.logger import app_logger


def create_agent_graph(
    llm_service: LLMService,
    tool_manager: ToolManager,
    enable_react: bool = False,
    enable_cot: bool = False,
    enable_fallback: bool = True,
    enable_reflection: bool = False,
    use_checkpointer: bool = False,
) -> Any:
    """
    创建并编译唯一 Agent 图。

    正式默认只保留 Simple RAG、确定性业务节点和 Plan-Execute Tool Agent。
    本函数是唯一图编译入口，调用方不得再次调用 ``compile()``。
    
    Args:
        llm_service: LLM 服务实例
        tool_manager: 工具管理器实例
        enable_react: 是否启用 ReAct 推理
        enable_cot: 是否启用 CoT 推理
        enable_fallback: 是否启用策略回退机制
        enable_reflection: 是否启用反思评估
        use_checkpointer: 是否使用 Checkpointer
    
    Returns:
        配置好的 StateGraph
    """
    nodes = AgentNodes(llm_service, tool_manager)

    graph = StateGraph(AgentState)

    graph.add_node("route_node", nodes.route_agent)
    graph.add_node("prompt_injection_node", nodes.prompt_injection_node)
    graph.add_node("rejection_node", nodes.rejection_node)
    graph.add_node("risk_node", nodes.risk_node)
    graph.add_node("tool_risk_node", nodes.tool_risk_node)
    graph.add_node("confirmation_node", nodes.confirmation_node)
    graph.add_node("retrieve_node", nodes.retrieve_node)
    graph.add_node("validate_node", nodes.validate_node)
    graph.add_node("repair_node", nodes.repair_node)
    
    graph.add_node("simple_qa_node", nodes.simple_qa_node)
    graph.add_node("minutes_node", nodes.minutes_node)
    graph.add_node("todos_node", nodes.todos_node)
    graph.add_node("controversy_node", nodes.controversy_node)
    graph.add_node("plan_node", nodes.plan_agent)
    graph.add_node("execute_node", nodes.execute_agent)
    graph.add_node("replan_node", nodes.replan_agent)
    
    if enable_react:
        graph.add_node("react_node", nodes.react_reasoning_node)
    if enable_cot:
        graph.add_node("cot_node", nodes.cot_reasoning_node)
    
    if enable_reflection:
        graph.add_node("reflection_node", nodes.reflection_node)

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
        reasoning_mode = state.get("reasoning_mode", ReasoningMode.DEFAULT)
        complexity_level = state.get("complexity_level")
        
        if reasoning_mode == ReasoningMode.REACT and enable_react:
            return "react_node"
        if reasoning_mode == ReasoningMode.COT and enable_cot:
            return "cot_node"
        if reasoning_mode == ReasoningMode.PLAN:
            return "plan_node"
        
        if complexity_level == ComplexityLevel.SIMPLE:
            return "simple_qa_node"
        elif complexity_level == ComplexityLevel.RETRIEVAL:
            return "simple_qa_node"
        elif complexity_level == ComplexityLevel.COT and enable_cot:
            return "cot_node"
        elif complexity_level == ComplexityLevel.AGENT and enable_react:
            return "react_node"
        
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
        reflection = state.get("reflection")
        if not reflection:
            return "validate_node"
        if reflection.get("needs_retry", False):
            return "plan_node"
        return "validate_node"

    def should_repair(state: AgentState):
        if state.get("confirmation_status") in ["required_but_disabled", "pending", "rejected"]:
            return END
        validation_errors = state.get("validation_errors") or []
        repair_count = int(state.get("repair_count", 0))
        max_repair_attempts = int(state.get("max_repair_attempts", 1))
        if validation_errors and repair_count < max_repair_attempts:
            return "repair_node"
        return END

    def fallback_strategy(state: AgentState):
        if not enable_fallback:
            return "validate_node"

        last_strategy = state.get("last_strategy")
        fallback_count = state.get("fallback_count", 0)

        # 注意：LangGraph 条件边函数中的 state 修改不会持久化，
        # fallback_count/last_strategy 的更新由各节点自身在返回时设置。
        # 这里只做只读路由判断。
        if last_strategy == "react" and enable_cot and fallback_count == 0:
            return "cot_node"

        if last_strategy == "cot" and fallback_count == 1:
            return "simple_qa_node"

        return "validate_node"
    
    def go_to_reflection(state: AgentState):
        if enable_reflection:
            return "reflection_node"
        return "validate_node"

    def should_reflect_and_regenerate(state: AgentState):
        """判断是否需要反思并重生成（LLM深度评估）"""
        if not enable_reflection:
            return "validate_node"
        
        reflection = state.get("reflection", {})
        confidence = reflection.get("confidence", 0.5)
        iterations = reflection.get("iterations", 0)
        max_iterations = 2
        
        if confidence < 0.7 and iterations < max_iterations:
            source_node = state.get("last_executed_node")
            if source_node in ["simple_qa_node", "minutes_node", "todos_node", "controversy_node"]:
                return source_node
            if source_node == "cot_node" and enable_cot:
                return "cot_node"
            if source_node == "react_node" and enable_react:
                return "react_node"
            return "simple_qa_node"
        
        return "validate_node"

    graph.add_edge(START, "route_node")
    graph.add_edge("route_node", "prompt_injection_node")

    # Prompt Injection 检测后的条件跳转
    def after_injection_check(state: AgentState):
        """注入检测后的分支：拦截则走 rejection_node，否则走 risk_node"""
        if state.get("injection_blocked", False):
            return "rejection_node"
        return "risk_node"

    graph.add_conditional_edges(
        "prompt_injection_node",
        after_injection_check,
        {
            "rejection_node": "rejection_node",
            "risk_node": "risk_node",
        },
    )

    # rejection_node 直接结束
    graph.add_edge("rejection_node", END)

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
    
    if enable_reflection:
        graph.add_edge("simple_qa_node", "reflection_node")
        graph.add_edge("minutes_node", "reflection_node")
        graph.add_edge("todos_node", "reflection_node")
        graph.add_edge("controversy_node", "reflection_node")
        
        reflection_destinations = {
            "simple_qa_node": "simple_qa_node",
            "minutes_node": "minutes_node",
            "todos_node": "todos_node",
            "controversy_node": "controversy_node",
            "cot_node": "cot_node",
            "react_node": "react_node",
            "validate_node": "validate_node",
        }
        if enable_react:
            reflection_destinations["react_node"] = "react_node"
        if enable_cot:
            reflection_destinations["cot_node"] = "cot_node"
        
        graph.add_conditional_edges(
            "reflection_node",
            should_reflect_and_regenerate,
            reflection_destinations,
        )
    else:
        graph.add_edge("simple_qa_node", "validate_node")
        graph.add_edge("minutes_node", "validate_node")
        graph.add_edge("todos_node", "validate_node")
        graph.add_edge("controversy_node", "validate_node")
    
    if enable_react:
        if enable_fallback and enable_cot:
            graph.add_conditional_edges(
                "react_node",
                fallback_strategy,
                {
                    "cot_node": "cot_node",
                    "simple_qa_node": "simple_qa_node",
                    "reflection_node": "reflection_node" if enable_reflection else "validate_node",
                    "validate_node": "validate_node",
                }
            )
        else:
            graph.add_edge("react_node", "reflection_node" if enable_reflection else "validate_node")
    
    if enable_cot:
        if enable_fallback:
            graph.add_conditional_edges(
                "cot_node",
                fallback_strategy,
                {
                    "simple_qa_node": "simple_qa_node",
                    "reflection_node": "reflection_node" if enable_reflection else "validate_node",
                    "validate_node": "validate_node",
                }
            )
        else:
            graph.add_edge("cot_node", "reflection_node" if enable_reflection else "validate_node")
    
    graph.add_conditional_edges(
        "validate_node",
        should_repair,
        {
            "repair_node": "repair_node",
            END: END,
        },
    )
    graph.add_edge("repair_node", "validate_node")
    
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
    
    def after_replan(state: AgentState):
        reflection = state.get("reflection")
        if not reflection:
            return "validate_node"

        # 统一质量门禁模式：replan/polish/validate 三选一
        if reflection.get("needs_retry", False):
            return "plan_node"
        if reflection.get("needs_polish", False) and enable_reflection:
            return "reflection_node"
        if enable_reflection and not reflection.get("evaluation_method") == "unified":
            # 非统一门禁模式：原逻辑走 reflection 做全量评估
            return "reflection_node"
        return "validate_node"
    
    graph.add_conditional_edges(
        "replan_node",
        after_replan,
        {
            "plan_node": "plan_node",
            "reflection_node": "reflection_node" if enable_reflection else "validate_node",
            "validate_node": "validate_node",
        }
    )

    if use_checkpointer:
        checkpointer = get_checkpointer()
        if checkpointer:
            app_logger.info("✅ Checkpointer 已启用")
            return graph.compile(checkpointer=checkpointer)
    
    return graph.compile()


def print_agent_architecture():
    app_logger.info("=" * 70)
    app_logger.info("📊 Agent 架构（正式主线：Simple RAG + Tool Agent）")
    app_logger.info("=" * 70)
    app_logger.info("1. ROUTE：任务类型与复杂度分类；模型不可用时规则降级")
    app_logger.info("2. SAFETY：Prompt Injection 与风险规则检查")
    app_logger.info("3a. SIMPLE：按需检索 → 问答/纪要/待办/争议 → 确定性校验")
    app_logger.info("3b. TOOL：计划 → ToolPolicy → 必要时 HITL pending → 执行 → 质量门禁")
    app_logger.info("4. HITL：批准后通过持久化快照恢复；未批准绝不执行高风险工具")
    app_logger.info("默认关闭：ReAct、CoT、深度反思、持久化 Checkpointer")
    app_logger.info("可选 Checkpointer 当前为进程内 MemorySaver，不宣称跨进程恢复")
    app_logger.info("=" * 70)
