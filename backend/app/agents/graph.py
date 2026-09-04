"""唯一 LangGraph 主线：安全路由、RAG、确定性抽取与受控工具执行。"""

from typing import Any, Awaitable, Callable, Optional

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from app.agents.nodes import AgentNodes
from app.agents.state import AgentState, ComplexityLevel, ReasoningMode, WorkflowType
from app.agents.tools import ToolManager
from app.services.llm_service import LLMService
from app.services.token_budget_ledger import token_budget_node_scope


def create_agent_graph(
    llm_service: LLMService,
    tool_manager: ToolManager,
    checkpointer: Optional[Any] = None,
) -> Any:
    """创建并编译唯一 Agent 图；不再保留未验证的可选图分支。"""
    nodes = AgentNodes(llm_service, tool_manager)
    graph = StateGraph(AgentState)

    def budgeted_node(
        node_name: str,
        node: Callable[[AgentState], Awaitable[Any]],
    ) -> Callable[[AgentState], Awaitable[Any]]:
        async def run(state: AgentState) -> Any:
            with token_budget_node_scope(node_name):
                return await node(state)

        return run

    async def input_gate(state: AgentState) -> Command:
        updated = await nodes.input_node(state)
        target = "rejection_node" if updated.get("input_blocked", False) else "prompt_injection_node"
        return Command(update=updated, goto=target)

    async def injection_gate(state: AgentState) -> Command:
        updated = await nodes.prompt_injection_node(state)
        target = "rejection_node" if updated.get("injection_blocked", False) else "route_node"
        return Command(update=updated, goto=target)

    graph.add_node("input_node", budgeted_node("input_node", input_gate))
    graph.add_node("route_node", budgeted_node("route_node", nodes.route_agent))
    graph.add_node(
        "prompt_injection_node",
        budgeted_node("prompt_injection_node", injection_gate),
    )
    graph.add_node("rejection_node", budgeted_node("rejection_node", nodes.rejection_node))
    graph.add_node("simple_qa_node", budgeted_node("simple_qa_node", nodes.simple_qa_node))
    graph.add_node("minutes_node", budgeted_node("minutes_node", nodes.minutes_node))
    graph.add_node("todos_node", budgeted_node("todos_node", nodes.todos_node))
    graph.add_node(
        "controversy_node",
        budgeted_node("controversy_node", nodes.controversy_node),
    )
    graph.add_node("plan_node", budgeted_node("plan_node", nodes.plan_agent))
    graph.add_node("execute_node", budgeted_node("execute_node", nodes.execute_agent))
    graph.add_node("repair_node", budgeted_node("repair_node", nodes.repair_node))

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

    def after_plan(state: AgentState) -> str:
        # 计划门禁失败时直接进入统一校验/修复出口，不能落到 execute_node
        # 再用默认计划“兜底”，否则幻觉工具可能被真正执行。
        if state.get("planning_blocked"):
            return "validate_node"
        if state.get("current_phase") == "validate" and state.get("validation_errors"):
            return "validate_node"
        return "tool_risk_node"

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
        if state.get("planning_blocked"):
            return END
        repair_count = int(state.get("repair_count", 0))
        max_repairs = int(state.get("max_repair_attempts", 1))
        if errors and repair_count < max_repairs:
            return "repair_node"
        return END

    async def risk_gate(state: AgentState) -> Command:
        updated = await nodes.risk_node(state)
        return Command(update=updated, goto=should_confirm(updated))

    async def confirmation_gate(state: AgentState) -> Command:
        updated = await nodes.confirmation_node(state)
        return Command(update=updated, goto=after_confirmation(updated))

    async def retrieve_gate(state: AgentState) -> Command:
        updated = await nodes.retrieve_node(state)
        return Command(update=updated, goto=route_workflow(updated))

    async def tool_risk_gate(state: AgentState) -> Command:
        updated = await nodes.tool_risk_node(state)
        return Command(update=updated, goto=after_tool_risk(updated))

    async def replan_gate(state: AgentState) -> Command:
        updated = await nodes.replan_agent(state)
        return Command(update=updated, goto=after_replan(updated))

    async def validate_gate(state: AgentState) -> Command:
        updated = await nodes.validate_node(state)
        return Command(update=updated, goto=should_repair(updated))

    graph.add_node("risk_node", budgeted_node("risk_node", risk_gate))
    graph.add_node(
        "confirmation_node",
        budgeted_node("confirmation_node", confirmation_gate),
    )
    graph.add_node("retrieve_node", budgeted_node("retrieve_node", retrieve_gate))
    graph.add_node("tool_risk_node", budgeted_node("tool_risk_node", tool_risk_gate))
    graph.add_node("replan_node", budgeted_node("replan_node", replan_gate))
    graph.add_node("validate_node", budgeted_node("validate_node", validate_gate))

    graph.add_edge(START, "input_node")
    graph.add_edge("route_node", "risk_node")
    graph.add_edge("rejection_node", END)

    for node_name in (
        "simple_qa_node",
        "minutes_node",
        "todos_node",
        "controversy_node",
    ):
        graph.add_edge(node_name, "validate_node")

    graph.add_conditional_edges(
        "plan_node",
        after_plan,
        {"tool_risk_node": "tool_risk_node", "validate_node": "validate_node"},
    )
    graph.add_edge("execute_node", "replan_node")
    graph.add_edge("repair_node", "validate_node")
    # Direct unit tests and one-shot callers may omit a checkpointer.  The
    # service passes the shared persistent saver in normal operation.
    if checkpointer is None:
        return graph.compile()
    return graph.compile(checkpointer=checkpointer)
