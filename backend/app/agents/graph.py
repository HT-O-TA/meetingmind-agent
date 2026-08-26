"""唯一 LangGraph 主线：安全路由、RAG、确定性抽取与受控工具执行。"""

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.nodes import AgentNodes
from app.agents.state import AgentState, ComplexityLevel, ReasoningMode, WorkflowType
from app.agents.tools import ToolManager
from app.services.llm_service import LLMService


def create_agent_graph(
    llm_service: LLMService,
    tool_manager: ToolManager,
) -> Any:
    """创建并编译唯一 Agent 图；不再保留未验证的可选图分支。"""
    nodes = AgentNodes(llm_service, tool_manager)
    graph = StateGraph(AgentState)

    graph.add_node("route_node", nodes.route_agent)
    graph.add_node("prompt_injection_node", nodes.prompt_injection_node)
    graph.add_node("rejection_node", nodes.rejection_node)
    graph.add_node("risk_node", nodes.risk_node)
    graph.add_node("confirmation_node", nodes.confirmation_node)
    graph.add_node("retrieve_node", nodes.retrieve_node)
    graph.add_node("simple_qa_node", nodes.simple_qa_node)
    graph.add_node("minutes_node", nodes.minutes_node)
    graph.add_node("todos_node", nodes.todos_node)
    graph.add_node("controversy_node", nodes.controversy_node)
    graph.add_node("plan_node", nodes.plan_agent)
    graph.add_node("tool_risk_node", nodes.tool_risk_node)
    graph.add_node("execute_node", nodes.execute_agent)
    graph.add_node("replan_node", nodes.replan_agent)
    graph.add_node("validate_node", nodes.validate_node)
    graph.add_node("repair_node", nodes.repair_node)

    def route_workflow(state: AgentState) -> str:
        workflow_type = state.get("workflow_type")
        if workflow_type == WorkflowType.MINUTES:
            return "minutes_node"
        if workflow_type == WorkflowType.TODO:
            return "todos_node"
        if workflow_type == WorkflowType.CONTROVERSY:
            return "controversy_node"
        if (
            workflow_type == WorkflowType.COMPLEX
            or state.get("reasoning_mode") == ReasoningMode.PLAN
            or state.get("complexity_level") == ComplexityLevel.AGENT
        ):
            return "plan_node"
        return "simple_qa_node"

    def should_retrieve(state: AgentState) -> str:
        if state.get("retrieval_required", True):
            return "retrieve_node"
        return route_workflow(state)

    def should_confirm(state: AgentState) -> str:
        if state.get("requires_confirmation", False):
            return "confirmation_node"
        return should_retrieve(state)

    def after_confirmation(state: AgentState) -> str:
        if state.get("confirmation_status") != "approved":
            return "validate_node"
        pending_action = state.get("pending_action") or {}
        if pending_action.get("source") == "tool":
            return "execute_node"
        return should_retrieve(state)

    def after_tool_risk(state: AgentState) -> str:
        if state.get("requires_confirmation", False):
            return "confirmation_node"
        return "execute_node"

    def after_replan(state: AgentState) -> str:
        reflection = state.get("reflection") or {}
        if reflection.get("needs_retry", False):
            return "plan_node"
        return "validate_node"

    def should_repair(state: AgentState):
        if state.get("confirmation_status") in {
            "required_but_disabled",
            "pending",
            "rejected",
        }:
            return END
        errors = state.get("validation_errors") or []
        repair_count = int(state.get("repair_count", 0))
        max_repairs = int(state.get("max_repair_attempts", 1))
        if errors and repair_count < max_repairs:
            return "repair_node"
        return END

    def after_injection_check(state: AgentState) -> str:
        return "rejection_node" if state.get("injection_blocked", False) else "risk_node"

    direct_destinations = {
        "simple_qa_node": "simple_qa_node",
        "minutes_node": "minutes_node",
        "todos_node": "todos_node",
        "controversy_node": "controversy_node",
        "plan_node": "plan_node",
    }

    graph.add_edge(START, "route_node")
    graph.add_edge("route_node", "prompt_injection_node")
    graph.add_conditional_edges(
        "prompt_injection_node",
        after_injection_check,
        {"rejection_node": "rejection_node", "risk_node": "risk_node"},
    )
    graph.add_edge("rejection_node", END)

    graph.add_conditional_edges(
        "risk_node",
        should_confirm,
        {"confirmation_node": "confirmation_node", "retrieve_node": "retrieve_node", **direct_destinations},
    )
    graph.add_conditional_edges(
        "confirmation_node",
        after_confirmation,
        {
            "retrieve_node": "retrieve_node",
            "validate_node": "validate_node",
            "execute_node": "execute_node",
            **direct_destinations,
        },
    )
    graph.add_conditional_edges("retrieve_node", route_workflow, direct_destinations)

    for node_name in (
        "simple_qa_node",
        "minutes_node",
        "todos_node",
        "controversy_node",
    ):
        graph.add_edge(node_name, "validate_node")

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
        after_replan,
        {"plan_node": "plan_node", "validate_node": "validate_node"},
    )

    graph.add_conditional_edges(
        "validate_node",
        should_repair,
        {"repair_node": "repair_node", END: END},
    )
    graph.add_edge("repair_node", "validate_node")
    return graph.compile()
