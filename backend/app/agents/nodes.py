"""Agent 节点定义 - 统一版本（使用 Tool Calling）

支持功能：
- 工具调用系统
- 复杂任务拆分
- 依赖分析
- 并行执行
- 上下文传递
- 质量评估
- 循环重新规划
- 可配置风险规则
- 语义风险感知
- Prompt Injection 防护
"""
import json
import re
import asyncio
from typing import Dict, List, Optional, Tuple, Any
from app.agents.state import AgentState, AgentResult, TaskType, WorkflowType, RiskLevel, AgentCard, CoTThought, Plan, TaskItem, TaskContext, TaskStatus, ComplexityLevel
from app.agents.tools import ToolExecutor, ToolExecutionResult, ToolManager
from app.agents.tools.policy import ToolPolicy
from app.agents.human_in_the_loop import get_hitl_service, ConfirmationType
from app.agents.trace_integration import AgentTraceContext
from app.services.llm_service import LLMService
from app.services.risk_rule_service import get_risk_rule_service
from app.services.semantic_risk_service import get_semantic_risk_service
from app.services.prompt_injection_guard import get_prompt_injection_guard, InjectionType
from app.services.unified_memory_service import get_unified_memory
from app.core.logger import app_logger


class AgentCards:
    """Agent 名片注册中心"""
    
    PLAN_AGENT_CARD: AgentCard = {
        "agent_id": "plan_agent",
        "name": "规划 Agent",
        "description": "分析问题，制定执行计划，决定使用哪些工具",
        "capabilities": ["问题分析", "任务拆解", "工具选择", "依赖分析", "并行规划"],
        "required_inputs": ["question", "context"],
        "outputs": ["plan", "tool_calls"],
        "dependencies": set()
    }
    
    EXECUTE_AGENT_CARD: AgentCard = {
        "agent_id": "execute_agent",
        "name": "执行 Agent",
        "description": "执行计划，调用工具",
        "capabilities": ["任务执行", "工具调用", "并行执行", "上下文传递", "依赖管理"],
        "required_inputs": ["plan", "context"],
        "outputs": ["answer", "minutes", "todos", "controversies", "tool_results"],
        "dependencies": {"plan_agent"}
    }
    
    REPLAN_AGENT_CARD: AgentCard = {
        "agent_id": "replan_agent",
        "name": "重新规划 Agent",
        "description": "评估执行结果质量，决定是否需要重新规划",
        "capabilities": ["质量评估", "缺陷检测", "改进建议", "重新规划"],
        "required_inputs": ["question", "answer", "minutes", "todos", "controversies"],
        "outputs": ["reflection"],
        "dependencies": {"execute_agent"}
    }

    @classmethod
    def get_card(cls, agent_id: str) -> Optional[AgentCard]:
        cards = {
            "plan_agent": cls.PLAN_AGENT_CARD,
            "execute_agent": cls.EXECUTE_AGENT_CARD,
            "replan_agent": cls.REPLAN_AGENT_CARD,
        }
        return cards.get(agent_id)


class AgentNodes:
    """统一的 Agent 节点集合（使用 Tool Calling）"""

    # 默认配置参数
    DEFAULT_CONFIG = {
        "max_react_iterations": 5,
        "max_plan_retries": 2,
        "max_context_length": 4000,
        "max_few_shot_examples": 3,
        "context_truncation_ratio": 0.8
    }

    def __init__(
        self,
        llm_service: LLMService,
        tool_manager: Optional[ToolManager] = None,
        max_retries: int = 2,
        config: Optional[Dict] = None
    ):
        self.llm_service = llm_service
        self.tool_manager = tool_manager or ToolManager(llm_service)
        self.max_retries = max_retries
        self.hitl_service = get_hitl_service()
        self.tool_policy = ToolPolicy()

        # 新增：可配置风险规则服务
        self.risk_rule_service = get_risk_rule_service()
        # 新增：语义风险感知服务（受 ENABLE_SEMANTIC_RISK_CHECK 开关控制）
        from app.core.config import settings as _cfg
        self._enable_semantic_risk = getattr(_cfg, 'ENABLE_SEMANTIC_RISK_CHECK', True)
        self.semantic_risk_service = get_semantic_risk_service()
        # 新增：Prompt Injection 防护（受 ENABLE_INJECTION_GUARD/INJECTION_GUARD_DEPTH 控制）
        self._enable_injection_guard = getattr(_cfg, 'ENABLE_INJECTION_GUARD', True)
        _guard_depth = getattr(_cfg, 'INJECTION_GUARD_DEPTH', 'light')
        self.injection_guard = get_prompt_injection_guard()
        # 根据配置项动态调整 injection_guard 行为
        self.injection_guard._enable_llm_check = self._enable_injection_guard
        self.injection_guard._llm_depth = _guard_depth

        # 合并配置
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}

    def _sanitize_state(self, state: AgentState) -> AgentState:
        """
        清理状态，防止 slice 对象等导致错误
        
        这个函数会创建一个全新的安全状态副本，避免对原对象的意外修改
        同时确保所有必要字段都有默认值
        
        Args:
            state: Agent 状态
            
        Returns:
            清理后的安全状态副本
        """
        # 创建一个新的状态字典，包含所有必要的默认值
        safe_state = {
            "question": state.get("question", ""),
            "meeting_id": state.get("meeting_id"),
            "document_ids": state.get("document_ids", []),
            "context": state.get("context", []),
            "raw_context": state.get("raw_context", []),
            "current_phase": state.get("current_phase", "plan"),
            "task_type": state.get("task_type"),
            "workflow_type": state.get("workflow_type"),
            "complexity_score": state.get("complexity_score", 0.0),
            "route_reason": state.get("route_reason", ""),
            "retrieval_required": state.get("retrieval_required", True),
            "retrieval_confidence": state.get("retrieval_confidence", 0.0),
            "citations": state.get("citations", []),
            "validation_errors": state.get("validation_errors", []),
            "policy_results": state.get("policy_results", []),
            "repair_count": state.get("repair_count", 0),
            "max_repair_attempts": state.get("max_repair_attempts", 1),
            "risk_level": state.get("risk_level"),
            "requires_confirmation": state.get("requires_confirmation", False),
            "confirmation_status": state.get("confirmation_status", "not_required"),
            "pending_action": state.get("pending_action"),
            "plan": state.get("plan"),
            "task_contexts": state.get("task_contexts", {}),
            "minutes": state.get("minutes"),
            "todos": state.get("todos"),
            "controversies": state.get("controversies"),
            "answer": state.get("answer"),
            "reflection": state.get("reflection"),
            "error": state.get("error"),
            "cot_thoughts": state.get("cot_thoughts", []),
            "agents_involved": state.get("agents_involved", []),
            "event_callback": state.get("event_callback"),
            "human_confirmations": state.get("human_confirmations", []),
            "enable_human_in_the_loop": state.get("enable_human_in_the_loop", False),
            # 路由阶段补充字段（原 _sanitize_state 遗漏，导致路由后状态丢失）
            "thread_id": state.get("thread_id"),
            "reasoning_mode": state.get("reasoning_mode"),
            "complexity_level": state.get("complexity_level"),
            "is_multi_task": state.get("is_multi_task", False),
            "last_strategy": state.get("last_strategy"),
            "fallback_count": state.get("fallback_count", 0),
            "session_context": state.get("session_context"),
            # 供 should_reflect_and_regenerate 使用的节点追踪字段
            "last_executed_node": state.get("last_executed_node"),
        }
        
        # 逐个检查并清理每个字段，防止 slice 对象
        for key, value in safe_state.items():
            if isinstance(value, slice):
                app_logger.warning(f"⚠️ 检测到 slice 对象在字段 '{key}'，已重置")
                if key in ["cot_thoughts", "agents_involved", "human_confirmations", "context", "raw_context", "validation_errors", "policy_results", "citations"]:
                    safe_state[key] = []
                elif key == "task_contexts":
                    safe_state[key] = {}
                else:
                    safe_state[key] = None
        
        # 再次确保字段类型正确
        if not isinstance(safe_state["task_contexts"], dict):
            safe_state["task_contexts"] = {}
        if not isinstance(safe_state["cot_thoughts"], list):
            safe_state["cot_thoughts"] = []
        if not isinstance(safe_state["agents_involved"], list):
            safe_state["agents_involved"] = []
        if not isinstance(safe_state["human_confirmations"], list):
            safe_state["human_confirmations"] = []
        if not isinstance(safe_state["policy_results"], list):
            safe_state["policy_results"] = []
        if not isinstance(safe_state["context"], list):
            safe_state["context"] = []
        if not isinstance(safe_state["raw_context"], list):
            safe_state["raw_context"] = []
        if not isinstance(safe_state["validation_errors"], list):
            safe_state["validation_errors"] = []
        if not isinstance(safe_state["citations"], list):
            safe_state["citations"] = []
        
        return safe_state
    
    def _add_thought(
        self,
        state: AgentState,
        agent_id: str,
        phase: str,
        thought: str,
        action: Optional[str] = None,
        observation: Optional[str] = None
    ):
        sanitized = self._sanitize_state(state)
        state.clear()
        state.update(sanitized)
        step = len(state["cot_thoughts"]) + 1
        thought_record: CoTThought = {
            "step": step,
            "agent_id": agent_id,
            "phase": phase,
            "thought": thought,
            "action": action,
            "observation": observation
        }
        state["cot_thoughts"].append(thought_record)
        app_logger.info(f"[{phase.upper()}] Step {step} - {agent_id}: {thought}")
        
        event_callback = state.get("event_callback")
        if event_callback:
            asyncio.create_task(event_callback("thought", {
                "step": step,
                "agent_id": agent_id,
                "phase": phase,
                "thought": thought,
                "action": action,
                "observation": observation
            }))

    def _format_context(self, state: AgentState) -> str:
        contexts = state.get("raw_context", [])
        if not contexts:
            contexts = state.get("context", [])
            formatted_contexts = []
            for c in contexts:
                if isinstance(c, dict):
                    document_id = c.get("document_id", 0)
                    chunk_index = c.get("chunk_index", 0)
                    content = c.get("content", "")
                    speaker = c.get("speaker_name", "")
                    if speaker:
                        formatted_contexts.append(f"[文档{document_id}:{chunk_index}] [{speaker}]: {content}")
                    else:
                        formatted_contexts.append(f"[文档{document_id}:{chunk_index}] {content}")
                else:
                    formatted_contexts.append(str(c))
            context = "\n\n".join(formatted_contexts) if formatted_contexts else ""
        else:
            context = "\n\n".join(contexts) if contexts else ""

        # P1 #4: 将 route_agent 预注入的历史会话记忆拼接到上下文头部
        session_context = (state.get("session_context") or "").strip()
        if session_context:
            context = session_context + ("\n\n" + context if context else "")

        # 应用上下文截断
        return self._truncate_context(context)
    
    def _truncate_context(self, context: str) -> str:
        """截断上下文到最大长度限制，保留开头和结尾的核心信息"""
        max_length = self.config.get("max_context_length", 4000)
        truncation_ratio = self.config.get("context_truncation_ratio", 0.8)
        
        if len(context) <= max_length:
            return context
        
        keep_length = int(max_length * truncation_ratio)
        head_length = int(keep_length * 0.3)
        tail_length = keep_length - head_length
        
        truncated = f"{context[:head_length]}...[内容截断]...{context[-tail_length:]}"
        app_logger.debug(f"[CONTEXT] 上下文长度 {len(context)} -> {len(truncated)}")
        return truncated

    def _parse_json_response(self, response: str, expected_type: str) -> Tuple[bool, Any]:
        response = response.strip()
        if "```json" in response:
            match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if match:
                response = match.group(1).strip()
        elif "```" in response:
            match = re.search(r"```\s*(.*?)\s*```", response, re.DOTALL)
            if match:
                response = match.group(1).strip()
        try:
            return True, json.loads(response)
        except json.JSONDecodeError:
            json_match = re.search(r'\[[\s\S]*\]|\{[\s\S]*\}', response)
            if json_match:
                try:
                    return True, json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
            app_logger.warning(f"[JSON解析] {expected_type} 格式解析失败")
            return False, None

    def _is_document_multi_deliverable_request(self, question: str) -> bool:
        if not self._extract_document_ids_from_question(question):
            return False
        deliverable_keywords = [
            ("总结", "主要内容", "摘要", "概括", "分析"),
            ("待办", "todo", "行动项", "任务"),
            ("纪要", "会议纪要"),
            ("争议", "争议点", "分歧"),
        ]
        matched_groups = sum(1 for group in deliverable_keywords if any(keyword in question for keyword in group))
        return matched_groups >= 3

    def _requested_outputs_for_question(self, question: str) -> List[str]:
        output_keywords = {
            "answer": ("总结", "主要内容", "摘要", "概括", "分析", "回答"),
            "todos": ("待办", "todo", "行动项", "任务"),
            "minutes": ("纪要", "会议纪要"),
            "controversies": ("争议", "争议点", "分歧"),
        }
        requested = [
            output
            for output, keywords in output_keywords.items()
            if any(keyword in question for keyword in keywords)
        ]
        return list(dict.fromkeys(requested))

    def _missing_requested_outputs(self, state: AgentState) -> List[str]:
        requested = self._requested_outputs_for_question(state.get("question", ""))
        missing = []
        for output in requested:
            value = state.get(output)
            if output in {"todos", "controversies"}:
                if not isinstance(value, list) or len(value) == 0:
                    missing.append(output)
            elif not isinstance(value, str) or not value.strip():
                missing.append(output)
        return missing

    def _build_repair_plan(
        self,
        state: AgentState,
        issues: List[Any],
        suggestions: List[Any],
        metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        missing_outputs = self._missing_requested_outputs(state)
        output_tool_map = {
            "answer": "answer_question",
            "todos": "extract_todos",
            "minutes": "generate_minutes",
            "controversies": "detect_controversies",
        }
        required_tools = [output_tool_map[output] for output in missing_outputs if output in output_tool_map]
        if self._first_document_id(state) is not None and missing_outputs:
            required_tools.insert(0, "get_document_content")

        previous_tool_calls = ((state.get("plan") or {}).get("tool_calls") or [])
        previous_tools = [
            call.get("tool_name")
            for call in previous_tool_calls
            if isinstance(call, dict) and call.get("tool_name")
        ]

        return {
            "missing_outputs": missing_outputs,
            "required_tools": list(dict.fromkeys(required_tools)),
            "avoid_tools": [],
            "context_required": bool(missing_outputs),
            "repair_strategy": "补齐缺失交付物" if missing_outputs else "根据评估意见优化计划",
            "issues": [str(issue) for issue in issues],
            "suggestions": [str(suggestion) for suggestion in suggestions],
            "previous_tools": previous_tools,
            "metrics": metrics,
        }

    def _tool_call_for_repair(self, tool_name: str, question: str, state: AgentState) -> Dict[str, Any]:
        if tool_name == "get_document_content":
            document_id = self._first_document_id(state)
            return {"tool_name": tool_name, "arguments": {"document_id": document_id} if document_id is not None else {}}
        if tool_name == "answer_question":
            return {"tool_name": tool_name, "arguments": {"question": question, "context": "{{context}}"}}
        if tool_name in {"extract_todos", "generate_minutes", "detect_controversies"}:
            return {"tool_name": tool_name, "arguments": {"context": "{{context}}"}}
        return {"tool_name": tool_name, "arguments": {}}

    def _task_for_repair_tool(self, tool_name: str, index: int) -> Optional[TaskItem]:
        task_map = {
            "get_document_content": ("repair_fetch_document", "retrieve", "重新获取文档全文", "document_content"),
            "answer_question": ("repair_answer", "qa", "补齐总结或回答", "answer"),
            "extract_todos": ("repair_todos", "todo", "补齐待办事项", "todos"),
            "generate_minutes": ("repair_minutes", "minutes", "补齐会议纪要", "minutes"),
            "detect_controversies": ("repair_controversies", "controversy", "补齐争议点", "controversies"),
        }
        if tool_name not in task_map:
            return None
        task_id, task_type, description, output_key = task_map[tool_name]
        return {
            "task_id": task_id,
            "task_type": task_type,
            "description": description,
            "priority": 100 + index,
            "status": "pending",
            "dependencies": [],
            "can_parallel_with": [],
            "input_from": None,
            "output_key": output_key,
            "tool_to_use": tool_name,
            "result": None,
            "error": None,
        }

    def _apply_repair_plan_to_plan(self, plan: Plan, repair_plan: Optional[Dict[str, Any]], state: AgentState) -> Plan:
        if not repair_plan:
            return plan

        required_tools = repair_plan.get("required_tools") or []
        if not required_tools:
            return plan

        tool_calls = list(plan.get("tool_calls") or [])
        existing_tools = {
            call.get("tool_name")
            for call in tool_calls
            if isinstance(call, dict) and call.get("tool_name")
        }
        added_tools = []
        question = state.get("question", "")
        for tool_name in required_tools:
            if tool_name not in existing_tools:
                tool_calls.append(self._tool_call_for_repair(tool_name, question, state))
                existing_tools.add(tool_name)
                added_tools.append(tool_name)

        tasks = list(plan.get("tasks") or [])
        existing_task_tools = {task.get("tool_to_use") for task in tasks if isinstance(task, dict)}
        for index, tool_name in enumerate(added_tools):
            if tool_name in existing_task_tools:
                continue
            task = self._task_for_repair_tool(tool_name, index)
            if task:
                tasks.append(task)

        execution_order = list(plan.get("execution_order") or [task.get("task_id") for task in tasks if task.get("task_id")])
        for task in tasks:
            task_id = task.get("task_id")
            if task_id and task_id not in execution_order:
                execution_order.append(task_id)

        plan["tasks"] = tasks
        plan["tool_calls"] = tool_calls
        plan["execution_order"] = execution_order
        if not plan.get("parallel_groups"):
            plan["parallel_groups"] = [[task_id for task_id in execution_order if task_id]]
        plan["repair_plan_applied"] = {
            "required_tools": required_tools,
            "added_tools": added_tools,
            "missing_outputs": repair_plan.get("missing_outputs", []),
            "strategy": repair_plan.get("repair_strategy", ""),
        }
        return plan

    def _create_document_multi_deliverable_plan(self, question: str, reflection: Optional[Dict] = None) -> Optional[Plan]:
        document_ids = self._extract_document_ids_from_question(question)
        if not document_ids:
            return None

        document_id = document_ids[0]
        
        # 基础任务列表
        tasks = [
            {
                "task_id": "fetch_document",
                "task_type": "retrieve",
                "description": f"获取 ID 为 {document_id} 的会议文档全文",
                "priority": 1,
                "status": "pending",
                "dependencies": [],
                "can_parallel_with": [],
                "input_from": None,
                "output_key": "document_content",
                "tool_to_use": "get_document_content",
                "result": None,
                "error": None,
            },
            {
                "task_id": "summarize_main_content",
                "task_type": "qa",
                "description": "总结会议主要内容并回答用户的分析需求",
                "priority": 2,
                "status": "pending",
                "dependencies": ["fetch_document"],
                "can_parallel_with": ["extract_todos", "generate_minutes", "detect_controversies"],
                "input_from": "fetch_document",
                "output_key": "answer",
                "tool_to_use": "answer_question",
                "result": None,
                "error": None,
            },
            {
                "task_id": "extract_todos",
                "task_type": "todo",
                "description": "提取会议待办事项",
                "priority": 3,
                "status": "pending",
                "dependencies": ["fetch_document"],
                "can_parallel_with": ["summarize_main_content", "generate_minutes", "detect_controversies"],
                "input_from": "fetch_document",
                "output_key": "todos",
                "tool_to_use": "extract_todos",
                "result": None,
                "error": None,
            },
            {
                "task_id": "generate_minutes",
                "task_type": "minutes",
                "description": "生成结构化会议纪要",
                "priority": 4,
                "status": "pending",
                "dependencies": ["fetch_document"],
                "can_parallel_with": ["summarize_main_content", "extract_todos", "detect_controversies"],
                "input_from": "fetch_document",
                "output_key": "minutes",
                "tool_to_use": "generate_minutes",
                "result": None,
                "error": None,
            },
            {
                "task_id": "detect_controversies",
                "task_type": "controversy",
                "description": "识别会议中的争议点和分歧",
                "priority": 5,
                "status": "pending",
                "dependencies": ["fetch_document"],
                "can_parallel_with": ["summarize_main_content", "extract_todos", "generate_minutes"],
                "input_from": "fetch_document",
                "output_key": "controversies",
                "tool_to_use": "detect_controversies",
                "result": None,
                "error": None,
            },
        ]
        
        # 工具调用列表
        tool_calls = [
            {"tool_name": "get_document_content", "arguments": {"document_id": document_id}},
            {"tool_name": "answer_question", "arguments": {"question": question, "context": "{{context}}"}},
            {"tool_name": "extract_todos", "arguments": {"context": "{{context}}"}},
            {"tool_name": "generate_minutes", "arguments": {"context": "{{context}}"}},
            {"tool_name": "detect_controversies", "arguments": {"context": "{{context}}"}},
        ]
        
        # 并行组
        parallel_groups = [
            ["fetch_document"],
            ["summarize_main_content", "extract_todos", "generate_minutes", "detect_controversies"],
        ]
        
        # 根据评估反馈调整计划
        if reflection and reflection.get("needs_retry", False):
            suggestions = reflection.get("suggestions", [])
            issues = reflection.get("issues", [])
            
            # 扩展建议识别：不仅检查suggestions，也检查issues中的关键词
            needs_summary = any(kw in s for s in suggestions for kw in ["摘要", "概括", "提炼", "总结"])
            needs_deep_analysis = any(kw in s for s in suggestions for kw in ["深入", "挖掘", "分析", "争议"]) or \
                                  any(kw in issue for issue in issues for kw in ["争议", "分析", "挖掘", "深入"])
            needs_refinement = any(kw in s for s in suggestions for kw in ["精炼", "精简", "冗余", "优化", "提炼"]) or \
                               any(kw in issue for issue in issues for kw in ["冗余", "提炼", "精炼"])
            needs_action_plan = any(kw in s for s in suggestions for kw in ["行动", "决策", "计划"]) or \
                               any(kw in issue for issue in issues for kw in ["行动", "决策", "计划"])
            
            # 1. 添加摘要提取任务
            if needs_summary:
                summary_task = {
                    "task_id": "extract_summary",
                    "task_type": "qa",
                    "description": "高度概括文档内容，生成精炼摘要（不超过150字）",
                    "priority": 1.5,
                    "status": "pending",
                    "dependencies": ["fetch_document"],
                    "can_parallel_with": [],
                    "input_from": "fetch_document",
                    "output_key": "summary",
                    "tool_to_use": "answer_question",
                    "result": None,
                    "error": None,
                }
                tasks.insert(1, summary_task)
                tool_calls.insert(1, {"tool_name": "answer_question", "arguments": {"question": "请用不超过150字高度概括以下文档的核心内容，只需列出3-5个关键点：\n\n{{context}}", "context": "{{context}}"}})
            
            # 2. 添加争议点深度分析任务
            if needs_deep_analysis:
                deep_analysis_task = {
                    "task_id": "deep_analysis",
                    "task_type": "qa",
                    "description": "深入分析文档内容，挖掘潜在问题、风险点和改进机会",
                    "priority": 5.5,
                    "status": "pending",
                    "dependencies": ["summarize_main_content", "generate_minutes"],
                    "can_parallel_with": [],
                    "input_from": "summarize_main_content",
                    "output_key": "deep_analysis",
                    "tool_to_use": "answer_question",
                    "result": None,
                    "error": None,
                }
                tasks.append(deep_analysis_task)
                tool_calls.append({"tool_name": "answer_question", "arguments": {"question": "请深入分析以下会议内容，识别潜在问题、风险点和改进机会。即使没有明显争议，也要分析需要关注的方面：\n\n{{context}}", "context": "{{context}}"}})
                parallel_groups.append(["deep_analysis"])
            
            # 3. 优化会议纪要生成（更精炼）
            if needs_refinement:
                for i, tc in enumerate(tool_calls):
                    if tc.get("tool_name") == "generate_minutes":
                        tool_calls[i] = {"tool_name": "generate_minutes", "arguments": {"question": "请生成精简的会议纪要，突出决策事项和行动项，避免与会议总结重复，控制在300字以内：\n\n{{context}}", "context": "{{context}}"}}
            
            # 4. 添加行动计划任务
            if needs_action_plan:
                action_plan_task = {
                    "task_id": "generate_action_plan",
                    "task_type": "qa",
                    "description": "根据会议内容生成明确的后续行动计划和决策事项",
                    "priority": 6,
                    "status": "pending",
                    "dependencies": ["summarize_main_content", "generate_minutes"],
                    "can_parallel_with": [],
                    "input_from": "summarize_main_content",
                    "output_key": "action_plan",
                    "tool_to_use": "answer_question",
                    "result": None,
                    "error": None,
                }
                tasks.append(action_plan_task)
                tool_calls.append({"tool_name": "answer_question", "arguments": {"question": "根据以下会议内容，列出明确的后续行动计划和具体决策事项：\n\n{{context}}", "context": "{{context}}"}})
                parallel_groups.append(["generate_action_plan"])
            
            analysis = f"调整后的计划：读取文档 {document_id}。问题：{', '.join(issues) if issues else '无'}。改进：{'、'.join(filter(None, ['摘要提取' if needs_summary else '', '深度分析' if needs_deep_analysis else '', '纪要精炼' if needs_refinement else '', '行动计划' if needs_action_plan else '']))}"
        else:
            analysis = f"确定性计划：读取文档 {document_id}，并生成总结、待办事项、会议纪要和争议点。"
        
        return {
            "analysis": analysis,
            "tasks": tasks,
            "execution_order": [t["task_id"] for t in sorted(tasks, key=lambda x: x["priority"])],
            "parallel_groups": parallel_groups,
            "tool_calls": tool_calls,
        }

    async def plan_agent(self, state: AgentState) -> AgentState:
        """规划 Agent - 支持 Tool Calling 决策"""
        async with AgentTraceContext("plan_agent", "planner") as trace:
            state = self._sanitize_state(state)
            app_logger.info("[PLAN] 开始规划阶段（Tool Calling）...")
            self._add_thought(state, "plan_agent", "plan", "开始分析问题，制定执行计划", action="问题分析")

            question = state["question"]
            context = self._format_context(state)
            tools_info = self.tool_manager.selector.format_tools_for_prompt()

            reflection = state.get("reflection")
            needs_replan = reflection and reflection.get("needs_retry", False)
            
            if needs_replan:
                retry_count = reflection.get("retry_count", 0)
                trace.update_retry(retry_count)
            
            if self._is_document_multi_deliverable_request(question):
                plan = self._create_document_multi_deliverable_plan(question, reflection)
                if plan:
                    repair_plan = reflection.get("repair_plan") if isinstance(reflection, dict) else None
                    plan = self._apply_repair_plan_to_plan(plan, repair_plan, state)
                    state["plan"] = plan
                    state["task_contexts"] = {}
                    state["current_phase"] = "execute"
                    state["task_type"] = TaskType.MULTI
                    self._log_plan(state)
                    state["agents_involved"].append("plan_agent")
                    
                    if needs_replan:
                        retry_count = reflection.get("retry_count", 0)
                        self._add_thought(
                            state,
                            "plan_agent",
                            "plan",
                            f"匹配到文档多产物请求，根据评估反馈调整计划（第{retry_count}次重试），共 {len(plan['tasks'])} 个任务",
                            observation="进入执行阶段"
                        )
                    else:
                        self._add_thought(
                            state,
                            "plan_agent",
                            "plan",
                            f"匹配到文档多产物请求，使用确定性计划，共 {len(plan['tasks'])} 个任务",
                            observation="进入执行阶段"
                        )
                    trace.update_output(f"文档多产物计划，{len(plan['tasks'])} 个任务")
                    return state
            
            if reflection and reflection.get("needs_retry", False):
                retry_count = reflection.get("retry_count", 0)
                issues = reflection.get("issues", [])
                suggestions = reflection.get("suggestions", [])
                repair_plan = reflection.get("repair_plan") or {}
                previous_score = reflection.get("overall_score", 0)
                
                self._add_thought(
                    state, "plan_agent", "plan", 
                    f"检测到需要重新规划（第{retry_count}次），上次评分: {previous_score:.2f}",
                    action="重新规划"
                )
                
                improvement_prompt = f"""
【重要：这是重新规划】
上次执行评分：{previous_score:.2f}
发现的问题：{json.dumps(issues, ensure_ascii=False) if issues else '无'}
改进建议：{json.dumps(suggestions, ensure_ascii=False) if suggestions else '无'}
结构化修复计划：{json.dumps(repair_plan, ensure_ascii=False) if repair_plan else '无'}

请根据以上问题调整执行计划，避免重复之前的错误。
如果结构化修复计划中 required_tools 不为空，必须在 tool_calls 中包含这些工具。
"""
            else:
                improvement_prompt = ""

            # Token 预算保护：评估可用 token，动态限制任务数
            from app.core.config import settings as _settings
            budget_hint = ""
            if getattr(_settings, "ENABLE_PLAN_VALIDATION", True):
                from app.services.plan_budget_guard import get_plan_budget_guard
                budget_guard = get_plan_budget_guard()
                complexity_score = state.get("complexity_score", 0.5)
                budget = budget_guard.evaluate(
                    question=question,
                    context=context[:2000] if context else "",
                    complexity_score=complexity_score,
                )
                if budget.guidance_hint:
                    budget_hint = f"\n【Token 预算提示】{budget.guidance_hint}\n最大任务数限制: {budget.recommended_max_tasks}"
                if budget.is_tight:
                    app_logger.warning(
                        f"[PLAN] Token 预算紧张: available={budget.available_output_tokens}, "
                        f"max_tasks={budget.recommended_max_tasks}"
                    )

            prompt = f"""你是一个任务规划专家，同时负责决定使用哪些工具。

{tools_info}

{improvement_prompt}
{budget_hint}

请分析以下问题，决定需要调用哪些工具来完成任务：

问题：{question}

上下文：
{context[:2000] if context else '（无上下文）'}

请按以下格式输出执行计划：
{{
    "analysis": "问题分析",
    "tasks": [
        {{
            "task_id": "task_1",
            "task_type": "qa/todo/minutes/controversy",
            "description": "任务描述",
            "priority": 1,
            "tool_to_use": "使用的工具名（可选）"
        }}
    ],
    "tool_calls": [
        {{
            "tool_name": "工具名",
            "arguments": {{"参数名": "参数值"}}
        }}
    ],
    "execution_order": ["task_1", ...],
    "parallel_groups": [["task_1", ...]]
}}"""

            messages = [
                {"role": "system", "content": "你是专业的任务规划专家，负责决定使用哪些工具。"},
                {"role": "user", "content": prompt}
            ]

            try:
                # 使用专用规划 max_tokens，避免 JSON 被截断
                _plan_max_tokens = getattr(_settings, "PLAN_LLM_MAX_TOKENS", 3000)
                # 双轴模型路由：规划阶段按复杂度选择模型（C/A → max，S/R → plus）
                from app.services.model_router import get_model_router
                _plan_model = get_model_router().select_for_planning(state.get("complexity_level"))
                response = await self.llm_service.chat(messages=messages, model=_plan_model, temperature=0.3, max_tokens=_plan_max_tokens)
                self._add_thought(state, "plan_agent", "plan", f"LLM 生成计划（模型: {_plan_model}）...", observation=response[:500])

                success, result = self._parse_json_response(response, "执行计划")
                if success and isinstance(result, dict):
                    tasks = result.get("tasks", [])
                    for task in tasks:
                        task["status"] = "pending"
                        task.setdefault("dependencies", [])
                        task.setdefault("can_parallel_with", [])
                        task.setdefault("input_from", None)
                        task.setdefault("output_key", None)
                        task.setdefault("result", None)
                        task.setdefault("error", None)

                    plan: Plan = {
                        "analysis": result.get("analysis", ""),
                        "tasks": tasks,
                        "execution_order": result.get("execution_order", []),
                        "parallel_groups": result.get("parallel_groups", [[t["task_id"] for t in tasks]]),
                        "tool_calls": result.get("tool_calls", [])
                    }

                    # Token 预算保护：校验计划完整性
                    if getattr(_settings, "ENABLE_PLAN_VALIDATION", True):
                        validation = budget_guard.validate(plan)
                        if not validation.is_valid:
                            app_logger.warning(
                                f"[PLAN] 计划校验失败: {validation.errors}"
                            )
                            # 尝试自动修复
                            for warning in validation.warnings:
                                app_logger.debug(f"[PLAN] 计划警告: {warning}")
                            if validation.errors:
                                self._add_thought(
                                    state, "plan_agent", "plan",
                                    f"计划校验发现问题: {validation.errors[:2]}",
                                    observation="尝试自动修复"
                                )
                        elif validation.warnings:
                            self._add_thought(
                                state, "plan_agent", "plan",
                                f"计划校验通过（有 {len(validation.warnings)} 个警告）",
                            )

                    repair_plan = reflection.get("repair_plan") if isinstance(reflection, dict) else None
                    plan = self._apply_repair_plan_to_plan(plan, repair_plan, state)
                    state["plan"] = plan
                    state["task_contexts"] = {}
                    state["current_phase"] = "execute"

                    if len(tasks) > 1:
                        state["task_type"] = TaskType.MULTI
                    elif tasks:
                        task_type_map = {
                            "qa": "qa", "问答": "qa",
                            "minutes": "minutes", "纪要": "minutes",
                            "todo": "todo", "待办": "todo",
                            "controversy": "controversy", "争议": "controversy",
                            "multi": "multi",
                        }
                        first_task = tasks[0].get("task_type", "qa")
                        state["task_type"] = TaskType(task_type_map.get(first_task, "qa"))

                    self._log_plan(state)
                else:
                    plan = self._create_default_plan()
                    state["plan"] = plan
                    state["task_contexts"] = {}
                    state["current_phase"] = "execute"
                    state["task_type"] = TaskType.QA

                state["agents_involved"].append("plan_agent")
                self._add_thought(state, "plan_agent", "plan", f"计划制定完成，共 {len(state['plan']['tasks'])} 个任务", observation="进入执行阶段")
                trace.update_output(f"计划制定完成，{len(state['plan']['tasks'])} 个任务")

            except Exception as e:
                app_logger.error(f"[PLAN] 规划失败: {e}")
                self._add_thought(state, "plan_agent", "plan", f"规划失败: {str(e)}", action="错误处理")
                state["error"] = str(e)
                state["current_phase"] = "execute"
                plan = self._create_default_plan()
                state["plan"] = plan
                state["task_type"] = TaskType.QA
                trace.update_error(str(e))

            return self._sanitize_state(state)

    async def route_agent(self, state: AgentState) -> AgentState:
        """意图路由节点：使用统一 IntentRouter 进行复杂度评估和任务判断。"""
        state = self._sanitize_state(state)
        question = state.get("question", "")

        # ── 规则短路通道 ──────────────────────────────────────────────
        # 问候语/寒暄等简单模式直接走 simple_qa_node，不进入分类流程，
        # 节省一次 IntentRouter / ComplexityClassifier 调用。
        if self._is_greeting(question):
            app_logger.info("[RouteAgent] 规则短路命中（问候语），跳过分类器")
            state["route_decision"] = None
            state["complexity_score"] = 0.0
            state["complexity_level"] = ComplexityLevel.SIMPLE
            state["is_multi_task"] = False
            state["workflow_type"] = WorkflowType.QA
            state["task_type"] = TaskType.QA
            state["route_reason"] = "规则短路：问候语直接走 simple_qa_node"
            state["retrieval_required"] = False
            state["route_confidence"] = 1.0
            state["route_candidates"] = []
            state["route_decision_trace"] = ["rule_short_circuit(greeting) → simple_qa_node"]
            state["retrieval_confidence"] = 1.0
            state.setdefault("citations", self._build_citations(state))
            state.setdefault("validation_errors", [])
            state.setdefault("policy_results", [])
            state["current_phase"] = "route"
            state["agents_involved"].append("route_agent")
            self._add_thought(
                state, "route_agent", "route",
                "规则短路命中（问候语），跳过分类器，直接路由到 simple_qa_node",
                action="规则短路", observation="未调用 IntentRouter 或 ComplexityClassifier"
            )
            return self._sanitize_state(state)

        # 使用统一 IntentRouter
        from app.services.intent_router import get_intent_router
        try:
            router = await get_intent_router()
            route_decision = await router.route(question, self.llm_service)
        except Exception as e:
            app_logger.warning(f"[RouteAgent] IntentRouter 异常，降级到原逻辑: {e}")
            route_decision = None

        if route_decision:
            # 新流程：使用 RouteDecision 结构化结果
            state["route_decision"] = route_decision
            state["complexity_score"] = route_decision.complexity_score
            state["complexity_level"] = route_decision.complexity_level
            state["is_multi_task"] = route_decision.is_multi_task
            state["workflow_type"] = route_decision.workflow_type
            state["task_type"] = route_decision.task_type
            state["route_reason"] = route_decision.reason
            state["retrieval_required"] = route_decision.requires_retrieval
            state["route_confidence"] = route_decision.confidence
            state["route_candidates"] = route_decision.candidates
            state["route_decision_trace"] = route_decision.decision_trace
        else:
            # 降级流程：使用原有的复杂度分类器
            from app.services.complexity_classifier import get_complexity_classifier
            classifier = await get_complexity_classifier()
            complexity_result = await classifier.classify(question)

            state["complexity_score"] = complexity_result["score"]
            state["complexity_level"] = complexity_result["level"]
            state["is_multi_task"] = complexity_result["is_multi_task"]
            state["retrieval_required"] = False if self._is_greeting(question) else complexity_result["requires_retrieval"]

            workflow_type, task_type, reason = self._classify_by_complexity(state, complexity_result)
            state["workflow_type"] = workflow_type
            state["task_type"] = task_type
            state["route_reason"] = reason

        state["retrieval_confidence"] = self._estimate_retrieval_confidence(state)
        state.setdefault("citations", self._build_citations(state))
        state.setdefault("validation_errors", [])
        state.setdefault("policy_results", [])
        state["current_phase"] = "route"
        state["agents_involved"].append("route_agent")

        # 记录路由决策链路（可观测性增强）
        trace_observation = state.get("route_decision_trace", [])
        if trace_observation:
            app_logger.debug(f"[RouteAgent] 决策链路: {' → '.join(trace_observation)}")

        candidates_info = ""
        if state.get("route_candidates"):
            top_candidates = [c["type"] for c in state["route_candidates"][:3]]
            candidates_info = f", 候选项: {', '.join(top_candidates)}"

        self._add_thought(
            state,
            "route_agent",
            "route",
            f"路由到 {state['workflow_type'].value}（复杂度: {state['complexity_level'].value}, 分数: {state['complexity_score']:.2f}, 置信度: {state.get('route_confidence', 0):.2f}{candidates_info}）",
            action="意图路由",
            observation=state.get("route_reason", ""),
        )

        # ── P1 #4: 会话记忆预注入 ──────────────────────────────────────
        if question and not self._is_greeting(question):
            try:
                unified_memory = get_unified_memory()
                memory_prompt = await unified_memory.generate_context_prompt(question)
                if memory_prompt:
                    existing = state.get("session_context") or ""
                    state["session_context"] = (existing + "\n\n" + memory_prompt).strip()
                    self._add_thought(
                        state,
                        "route_agent",
                        "route",
                        "已预注入历史会话记忆上下文",
                        observation=f"session_context_len={len(state['session_context'])}",
                    )
            except Exception as mem_exc:
                app_logger.warning(f"[Memory] route_agent 会话记忆预注入失败（不影响主流程）: {mem_exc}")

        return self._sanitize_state(state)
    
    def _detect_task_type(self, question: str) -> Tuple[Optional[WorkflowType], Optional[TaskType], Optional[str]]:
        """根据问题内容检测特定任务类型"""
        normalized = question.strip().lower()
        
        detected_types = []
        
        todo_keywords = ["待办", "待办事项", "todo", "任务", "行动项"]
        if any(kw in normalized for kw in todo_keywords):
            detected_types.append(("待办", WorkflowType.TODO, TaskType.TODO))
        
        minutes_keywords = ["纪要", "会议纪要", "会议总结", "总结会议"]
        if any(kw in normalized for kw in minutes_keywords):
            detected_types.append(("会议纪要", WorkflowType.MINUTES, TaskType.MINUTES))
        
        controversy_keywords = ["争议", "冲突", "矛盾", "分歧"]
        if any(kw in normalized for kw in controversy_keywords):
            detected_types.append(("争议点", WorkflowType.CONTROVERSY, TaskType.CONTROVERSY))
        
        if len(detected_types) > 1:
            types_str = "、".join([t[0] for t in detected_types])
            return WorkflowType.COMPLEX, TaskType.MULTI, f"检测到多任务意图：{types_str}"
        
        if detected_types:
            return detected_types[0][1], detected_types[0][2], f"检测到{detected_types[0][0]}意图"
        
        return None, None, None
    
    def _classify_by_complexity(self, state: AgentState, complexity_result: Dict) -> Tuple:
        """根据复杂度分类结果确定工作流类型"""
        level = complexity_result["level"]
        is_multi_task = complexity_result["is_multi_task"]
        question = state.get("question", "")
        
        # 问候语直接返回简单问答（优先级最高）
        if self._is_greeting(question):
            return WorkflowType.SIMPLE_QA, TaskType.QA, "问候语，直接响应"
        
        # 先检测特定任务类型
        task_workflow, task_type, reason = self._detect_task_type(question)
        if task_workflow and task_type:
            return task_workflow, task_type, reason
        
        # 如果是多任务，直接走 PLAN 模式
        if is_multi_task:
            return WorkflowType.COMPLEX, TaskType.MULTI, "检测到多任务，需要拆解执行"
        
        # 根据复杂度级别确定工作流
        from app.agents.state import ComplexityLevel
        
        if level == ComplexityLevel.SIMPLE:
            return WorkflowType.SIMPLE_QA, TaskType.QA, "简单问答，直接响应"
        elif level == ComplexityLevel.RETRIEVAL:
            return WorkflowType.SIMPLE_QA, TaskType.QA, "需要检索的事实型问题"
        elif level == ComplexityLevel.COT:
            if self._is_simple_fact_question(question):
                return WorkflowType.SIMPLE_QA, TaskType.QA, "简单事实问题，降级为检索问答"
            return WorkflowType.COMPLEX, TaskType.MULTI, "需要思维链推理"
        elif level == ComplexityLevel.AGENT:
            if self._is_simple_fact_question(question):
                return WorkflowType.SIMPLE_QA, TaskType.QA, "简单事实问题，降级为检索问答"
            return WorkflowType.COMPLEX, TaskType.MULTI, "需要ReAct代理推理"
        
        # 默认回退
        return WorkflowType.SIMPLE_QA, TaskType.QA, "默认简单问答"

    async def retrieve_node(self, state: AgentState) -> AgentState:
        """图内检索节点：由路由结果决定是否执行检索。"""
        async with AgentTraceContext("retrieve_node", "retriever") as trace:
            state = self._sanitize_state(state)
            state["current_phase"] = "retrieve"

            if not state.get("retrieval_required", True):
                self._add_thought(
                    state,
                    "retrieve_node",
                    "retrieve",
                    "当前请求不需要检索，跳过上下文召回",
                    action="跳过检索",
                )
                trace.update_output("跳过检索")
                return self._sanitize_state(state)

            vector_search_service = getattr(self.tool_manager, "vector_search_service", None)
            if not vector_search_service:
                state["validation_errors"].append("vector_search_service 不可用，无法检索上下文")
                self._add_thought(
                    state,
                    "retrieve_node",
                    "retrieve",
                    "检索服务不可用",
                    action="检索失败",
                )
                trace.update_error("检索服务不可用")
                return self._sanitize_state(state)

            self._add_thought(state, "retrieve_node", "retrieve", "开始检索相关文档", action="上下文检索")

            try:
                question = state.get("question", "")
                meeting_id = state.get("meeting_id")
                document_ids = state.get("document_ids")

                # ── Query Rewrite（HyDE + Multi-Query + Step-back）──────────────
                search_queries = [question]
                if settings.ENABLE_QUERY_REWRITE and question:
                    try:
                        from app.services.query_optimizer import get_query_optimizer
                        optimizer = get_query_optimizer()
                        expanded = await optimizer.optimize(
                            query=question,
                            enable_decompose=settings.ENABLE_MULTI_QUERY,
                            enable_hyde=settings.ENABLE_HYDE,
                            enable_expand=False,  # 同义词扩展不用于检索，避免噪音
                        )
                        # 收集扩展查询：原始 + 子查询（multi-query）+ step-back 推理结果
                        candidate_queries = {question}
                        for sq in (expanded.sub_queries or []):
                            if sq.query and sq.query.strip():
                                candidate_queries.add(sq.query.strip())
                        # HyDE：用假设文档而非原始 query 做向量检索（增强语义召回）
                        if settings.ENABLE_HYDE and expanded.hyde_result:
                            for doc in (expanded.hyde_result.hypothetical_documents or []):
                                if doc and len(doc.strip()) > 10:
                                    candidate_queries.add(doc.strip())
                        search_queries = list(candidate_queries)[:settings.QUERY_REWRITE_MAX_QUERIES]
                        self._add_thought(
                            state,
                            "retrieve_node",
                            "retrieve",
                            f"Query Rewrite 完成，生成 {len(search_queries)} 个检索查询",
                            observation=f"original={question[:30]}...",
                        )
                    except Exception as qr_exc:
                        app_logger.warning(f"[QueryRewrite] 失败，回退到原始查询: {qr_exc}")
                        search_queries = [question]

                # ── 多查询并发检索 + 去重合并 ──────────────────────────────────
                if len(search_queries) == 1:
                    chunks = await self._retrieve_context(
                        question=search_queries[0],
                        meeting_id=meeting_id,
                        document_ids=document_ids,
                        vector_search_service=vector_search_service,
                    )
                else:
                    import asyncio
                    tasks = [
                        self._retrieve_context(
                            question=q,
                            meeting_id=meeting_id,
                            document_ids=document_ids,
                            vector_search_service=vector_search_service,
                        )
                        for q in search_queries
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    # 合并去重（按 chunk_id 去重，保留最高相似度）
                    seen_ids: dict = {}
                    for result in results:
                        if isinstance(result, Exception):
                            app_logger.warning(f"[QueryRewrite] 某路检索失败: {result}")
                            continue
                        for chunk in result:
                            cid = chunk.get("chunk_id") or chunk.get("id") or id(chunk)
                            if cid not in seen_ids:
                                seen_ids[cid] = chunk
                            else:
                                # 保留相似度更高的那个
                                if chunk.get("similarity", 0) > seen_ids[cid].get("similarity", 0):
                                    seen_ids[cid] = chunk
                    # 按相似度降序，保留 top_k 个
                    merged = sorted(seen_ids.values(), key=lambda x: x.get("similarity", 0), reverse=True)
                    chunks = merged[:10]

                existing_raw_context = state.get("raw_context") or []
                state["context"] = chunks
                state["raw_context"] = existing_raw_context + self._format_chunks_to_text(chunks)
                state["retrieval_confidence"] = self._estimate_retrieval_confidence(state)
                state["citations"] = self._build_citations(state)
                self._add_thought(
                    state,
                    "retrieve_node",
                    "retrieve",
                    f"检索完成，获得 {len(chunks)} 条上下文",
                    observation=f"confidence={state['retrieval_confidence']:.2f}",
                )
                trace.update_output(f"检索完成，{len(chunks)} 条上下文")
            except Exception as exc:
                state["validation_errors"].append(f"检索失败: {exc}")
                self._add_thought(state, "retrieve_node", "retrieve", f"检索失败: {exc}", action="错误处理")
                trace.update_error(str(exc))

            # ── 注入长期记忆上下文 ──────────────────────────────────────────
            try:
                unified_memory = get_unified_memory()
                question = state.get("question", "")
                if question:
                    memory_prompt = await unified_memory.generate_context_prompt(question)
                    if memory_prompt:
                        state["raw_context"] = (state.get("raw_context") or []) + [memory_prompt]
                        self._add_thought(
                            state,
                            "retrieve_node",
                            "retrieve",
                            "已注入历史会议长期记忆上下文",
                            observation=f"memory_prompt_len={len(memory_prompt)}",
                        )
            except Exception as mem_exc:
                app_logger.warning(f"[Memory] 长期记忆注入失败（不影响主流程）: {mem_exc}")

            return self._sanitize_state(state)

    async def risk_node(self, state: AgentState) -> AgentState:
        """风险评估节点：判断是否需要人工确认。

        双轨检测：
        1. 规则检测（快速）：RiskRuleService 关键词/正则匹配
        2. 语义检测（深度）：SemanticRiskService LLM 语义理解
        """
        state = self._sanitize_state(state)
        question = state.get("question", "")
        tenant_id = state.get("tenant_id")

        # 第一层：规则检测（使用可配置风险规则）
        rule_level, rule_requires, rule_reason = self._assess_risk(state, question)

        # 第二层：语义检测（规则未命中时调用 LLM 做深度判断，受 ENABLE_SEMANTIC_RISK_CHECK 控制）
        semantic_level = None
        semantic_reason = ""
        if self._enable_semantic_risk and rule_level == RiskLevel.LOW and question and question.strip():
            try:
                semantic_result = await self.semantic_risk_service.assess_risk(
                    question=question,
                    llm_service=self.llm_service,
                )
                semantic_level = semantic_result.risk_level
                semantic_reason = semantic_result.reason

                # 如果语义检测发现更高风险，采用语义结果
                semantic_risk_map = {
                    "LOW": RiskLevel.LOW,
                    "MEDIUM": RiskLevel.MEDIUM,
                    "HIGH": RiskLevel.HIGH,
                    "CRITICAL": RiskLevel.CRITICAL,
                }
                semantic_rl = semantic_risk_map.get(semantic_level, RiskLevel.LOW)
                if semantic_rl.value != "LOW":
                    rule_level = semantic_rl
                    rule_requires = semantic_result.requires_confirmation
                    rule_reason = f"语义检测: {semantic_reason}"
                    app_logger.info(f"[RiskNode] 语义检测提升风险等级: {rule_level.value}, reason={semantic_reason}")
            except Exception as e:
                app_logger.warning(f"[RiskNode] 语义检测失败，使用规则结果: {e}")

        self._apply_risk_assessment(state, rule_level, rule_requires, rule_reason, "intent")

        state["agents_involved"].append("risk_node")
        self._add_thought(
            state,
            "risk_node",
            "risk",
            f"风险等级：{rule_level.value}",
            action="风险评估",
            observation=rule_reason,
        )
        return self._sanitize_state(state)

    async def tool_risk_node(self, state: AgentState) -> AgentState:
        """工具风险评估节点：Planner 产出工具调用后，按工具元数据做执行前门禁。"""
        state = self._sanitize_state(state)
        risk_level, requires_confirmation, reason = self._assess_tool_risk(state)
        self._apply_risk_assessment(state, risk_level, requires_confirmation, reason, "tool")
        
        app_logger.info(f"[TOOL_RISK] 风险评估完成 - risk_level={risk_level.value}, requires_confirmation={requires_confirmation}, reason={reason}")
        app_logger.info(f"[TOOL_RISK] 状态更新 - state[requires_confirmation]={state.get('requires_confirmation')}, state[confirmation_status]={state.get('confirmation_status')}")

        state["agents_involved"].append("tool_risk_node")
        self._add_thought(
            state,
            "tool_risk_node",
            "risk",
            f"工具风险等级：{risk_level.value}",
            action="工具风险评估",
            observation=reason,
        )
        return self._sanitize_state(state)

    def _apply_risk_assessment(
        self,
        state: AgentState,
        risk_level: RiskLevel,
        requires_confirmation: bool,
        reason: str,
        source: str,
    ) -> None:
        # 细粒度 HITL 控制：根据配置的最低触发风险等级决定是否真正拦截
        from app.core.config import settings as _s
        _min_level_str = getattr(_s, "HITL_MIN_RISK_LEVEL", "HIGH").upper()
        _risk_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
        _min_order = _risk_order.get(_min_level_str, 2)  # 默认 HIGH
        _current_order = _risk_order.get(risk_level.value.upper(), 0)
        # 只有当前风险等级 >= 配置的最低触发等级，才真正要求确认
        if requires_confirmation and _current_order < _min_order:
            requires_confirmation = False
            app_logger.debug(
                f"[HITL] 风险等级 {risk_level.value} 低于触发阈值 {_min_level_str}，自动放行"
            )
        state["risk_level"] = risk_level
        state["requires_confirmation"] = requires_confirmation
        state["confirmation_status"] = "required" if requires_confirmation else "not_required"
        if requires_confirmation:
            import uuid
            state["pending_action"] = {
                "request_id": str(uuid.uuid4()),
                "source": source,
                "question": state.get("question", ""),
                "workflow_type": state.get("workflow_type").value if hasattr(state.get("workflow_type"), "value") else state.get("workflow_type"),
                "task_type": state.get("task_type").value if hasattr(state.get("task_type"), "value") else state.get("task_type"),
                "risk_level": risk_level.value,
                "reason": reason,
            }
            if source == "tool":
                state["pending_action"]["tool_calls"] = (state.get("plan") or {}).get("tool_calls", [])
                for call in state["pending_action"]["tool_calls"]:
                    tool_name = call.get("tool_name") if isinstance(call, dict) else None
                    if tool_name:
                        self._record_policy_result(
                            state,
                            tool_name=tool_name,
                            code="confirmation_required",
                            allowed=False,
                            reason=reason,
                            source=source,
                        )
        else:
            state["pending_action"] = None

    def _assess_risk(self, state: AgentState, question: str) -> Tuple[RiskLevel, bool, str]:
        """评估风险等级（使用可配置风险规则）

        优先使用 RiskRuleService（数据库驱动），失败时降级到硬编码规则。
        """
        tenant_id = state.get("tenant_id")

        try:
            level_str, requires_confirmation, reason = self.risk_rule_service.evaluate_risk(
                question=question,
                tenant_id=tenant_id,
            )
            # 转换字符串等级为 RiskLevel 枚举
            level_map = {
                "LOW": RiskLevel.LOW,
                "MEDIUM": RiskLevel.MEDIUM,
                "HIGH": RiskLevel.HIGH,
                "CRITICAL": RiskLevel.CRITICAL,
            }
            risk_level = level_map.get(level_str, RiskLevel.LOW)
            return risk_level, requires_confirmation, reason
        except Exception as e:
            app_logger.warning(f"[RiskNode] RiskRuleService 异常，降级到硬编码: {e}")
            return self._assess_risk_fallback(state, question)

    def _assess_risk_fallback(self, state: AgentState, question: str) -> Tuple[RiskLevel, bool, str]:
        """硬编码兜底风险评估（数据库不可用时使用）"""
        normalized = question.lower()
        destructive_keywords = ["删除", "移除", "清空", "作废", "delete", "remove", "clear", "drop"]
        write_keywords = ["创建", "新增", "更新", "修改", "保存", "提交", "批量", "写入",
                          "create", "update", "save", "submit", "bulk", "insert"]

        if any(keyword in normalized for keyword in destructive_keywords):
            return RiskLevel.CRITICAL, True, "包含删除/清空类高风险动作（兜底规则）"
        if any(keyword in normalized for keyword in write_keywords):
            return RiskLevel.HIGH, True, "包含创建/修改/写入类动作（兜底规则）"
        if state.get("task_type") == TaskType.MULTI and state.get("workflow_type") == WorkflowType.COMPLEX:
            return RiskLevel.MEDIUM, False, "复杂分析任务，仅生成结果不写入"
        return RiskLevel.LOW, False, "只读分析或生成任务"

    def _assess_tool_risk(self, state: AgentState) -> Tuple[RiskLevel, bool, str]:
        tool_calls = (state.get("plan") or {}).get("tool_calls", [])
        if not tool_calls:
            return RiskLevel.LOW, False, "计划中没有工具调用"

        highest = RiskLevel.LOW
        requires_confirmation = False
        medium_requires_confirmation = False
        risk_reasons = []
        for call in tool_calls:
            tool_name = call.get("tool_name") if isinstance(call, dict) else None
            if not tool_name:
                continue
            tool = self._get_tool_by_name(tool_name)
            metadata = getattr(tool, "metadata", None)
            if not metadata:
                continue

            tool_risk = self._normalize_risk_level(getattr(metadata, "risk_level", RiskLevel.LOW))
            highest = self._max_risk_level(highest, tool_risk)
            if tool_risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
                requires_confirmation = True
            elif tool_risk == RiskLevel.MEDIUM:
                # MEDIUM 仅在本轮明确授权且可撤销、无外部副作用时自动放行。
                explicit = bool(state.get("explicit_write_authorization", False))
                if not explicit:
                    question = str(state.get("question", "")).lower()
                    explicit = any(word in question for word in ("创建", "新增", "保存", "更新", "修改", "写入", "create", "save", "update"))
                safe_medium = (
                    explicit
                    and bool(getattr(metadata, "reversible", True))
                    and not bool(getattr(metadata, "external_effect", False))
                    and not bool(getattr(metadata, "bulk_operation", False))
                )
                medium_requires_confirmation = medium_requires_confirmation or not safe_medium
                if not safe_medium:
                    # 当前 HITL 默认阈值为 HIGH；不满足 MEDIUM 自动放行条件时升级为 HIGH。
                    highest = self._max_risk_level(highest, RiskLevel.HIGH)
            reason = getattr(metadata, "risk_reason", "未填写风险理由")
            risk_reasons.append(f"{tool_name}:{tool_risk.value}({reason})")

        requires_confirmation = requires_confirmation or medium_requires_confirmation

        if not risk_reasons:
            return RiskLevel.LOW, False, "计划中的工具未匹配到风险元数据"
        reason = "工具风险评估：" + ", ".join(risk_reasons)
        return highest, requires_confirmation, reason

    def _get_tool_by_name(self, tool_name: str) -> Any:
        registry = getattr(self.tool_manager, "registry", None)
        if not registry:
            return None
        tool = registry.get(tool_name) if hasattr(registry, "get") else None
        if tool:
            return tool
        return registry.get_by_name(tool_name) if hasattr(registry, "get_by_name") else None

    def _normalize_risk_level(self, value: Any) -> RiskLevel:
        if isinstance(value, RiskLevel):
            return value
        if hasattr(value, "value"):
            value = value.value
        try:
            return RiskLevel(str(value).lower())
        except ValueError:
            return RiskLevel.LOW

    def _max_risk_level(self, current: RiskLevel, candidate: RiskLevel) -> RiskLevel:
        order = {
            RiskLevel.LOW: 0,
            RiskLevel.MEDIUM: 1,
            RiskLevel.HIGH: 2,
            RiskLevel.CRITICAL: 3,
        }
        return candidate if order[candidate] > order[current] else current

    async def prompt_injection_node(self, state: AgentState) -> AgentState:
        """Prompt Injection 检测节点：在 risk_node 之前检测注入攻击。

        双轨检测：
        1. 规则检测（快速）：正则+关键词匹配注入特征
        2. LLM 检测（深度）：语义理解判断是否为注入

        检测结果：
        - block: 跳转到 rejection_node
        - warning: 标记后继续
        - pass: 继续到 risk_node
        """
        state = self._sanitize_state(state)
        question = state.get("question", "")

        if not question or not question.strip():
            state["injection_check"] = {"status": "pass", "reason": "空输入"}
            state["agents_involved"].append("prompt_injection_node")
            return self._sanitize_state(state)

        # 受 ENABLE_INJECTION_GUARD 开关控制
        if not self._enable_injection_guard:
            state["injection_check"] = {"status": "pass", "reason": "注入防护已关闭（ENABLE_INJECTION_GUARD=False）"}
            state["injection_blocked"] = False
            state["agents_involved"].append("prompt_injection_node")
            app_logger.debug("[InjectionGuard] 注入防护已关闭，跳过检测")
            return self._sanitize_state(state)

        try:
            injection_result = await self.injection_guard.check(
                question=question,
                llm_service=self.llm_service,
            )

            state["injection_check"] = injection_result.to_dict()
            state["agents_involved"].append("prompt_injection_node")

            if injection_result.should_block:
                app_logger.warning(
                    f"[InjectionGuard] 检测到 Prompt Injection! "
                    f"type={injection_result.injection_type.value if injection_result.injection_type else 'unknown'}, "
                    f"confidence={injection_result.confidence:.2f}"
                )
                state["injection_blocked"] = True
                state["injection_block_reason"] = injection_result.details.get("reason", "")
                self._add_thought(
                    state,
                    "prompt_injection_node",
                    "security",
                    f"检测到注入攻击: {injection_result.injection_type.value if injection_result.injection_type else 'unknown'}",
                    action="安全拦截",
                    observation=f"置信度: {injection_result.confidence:.2f}",
                )
            elif injection_result.is_injection:
                # warning 级别，记录但不阻止
                app_logger.info(
                    f"[InjectionGuard] 可疑输入（未阻止）: "
                    f"type={injection_result.injection_type.value if injection_result.injection_type else 'unknown'}"
                )
                state["injection_blocked"] = False
                self._add_thought(
                    state,
                    "prompt_injection_node",
                    "security",
                    f"可疑输入（警告）",
                    action="安全检测",
                    observation=f"置信度: {injection_result.confidence:.2f}",
                )
            else:
                state["injection_blocked"] = False
                self._add_thought(
                    state,
                    "prompt_injection_node",
                    "security",
                    "注入检测通过",
                    action="安全检测",
                    observation="未检测到注入特征",
                )

        except Exception as e:
            app_logger.error(f"[InjectionGuard] 检测异常: {e}")
            state["injection_check"] = {"status": "error", "reason": str(e)}
            state["injection_blocked"] = False
            state["agents_involved"].append("prompt_injection_node")

        return self._sanitize_state(state)

    async def rejection_node(self, state: AgentState) -> AgentState:
        """拒绝节点：当检测到 Prompt Injection 时返回友好拒绝信息。

        注意：不暴露检测细节，避免攻击者调整策略。
        """
        state = self._sanitize_state(state)
        state["current_phase"] = "rejected"
        state["task_type"] = TaskType.SIMPLE_QA

        # 友好但坚定的拒绝信息
        rejection_messages = [
            "抱歉，我无法处理您的请求。如需帮助，请尝试重新描述您的问题。",
            "抱歉，我无法完成这个请求。如果您有其他问题，欢迎继续提问。",
            "很抱歉，当前请求无法处理。请尝试用更简单直接的方式描述您的需求。",
        ]
        # 使用固定消息，避免被识别为拦截模板
        import random
        message = random.choice(rejection_messages)

        state["answer"] = message
        state["error"] = "REJECTED_BY_SAFETY_GUARD"
        state["injection_blocked"] = True
        state["agents_involved"].append("rejection_node")

        self._add_thought(
            state,
            "rejection_node",
            "security",
            "请求被安全护栏拦截",
            action="拒绝",
            observation="检测到 Prompt Injection 攻击特征",
        )

        app_logger.warning(
            f"[RejectionNode] 请求被拦截 - "
            f"session_id={state.get('session_id')}, "
            f"reason={state.get('injection_block_reason', 'unknown')}"
        )

        return self._sanitize_state(state)

    def _record_policy_result(
        self,
        state: AgentState,
        tool_name: str,
        code: str,
        allowed: bool,
        reason: str,
        source: str = "execute",
        retry_count: int = 0,
    ) -> None:
        tool = self._get_tool_by_name(tool_name)
        metadata = getattr(tool, "metadata", None)
        risk_level = getattr(metadata, "risk_level", None) if metadata else None
        risk_value = risk_level.value if hasattr(risk_level, "value") else risk_level
        workflow_type = state.get("workflow_type")
        workflow_value = workflow_type.value if hasattr(workflow_type, "value") else workflow_type

        state.setdefault("policy_results", [])
        result = {
            "tool_name": tool_name,
            "code": code,
            "allowed": allowed,
            "reason": reason,
            "source": source,
            "risk_level": risk_value or "unknown",
            "workflow_type": workflow_value,
            "confirmation_status": state.get("confirmation_status"),
            "retry_count": retry_count,
        }
        state["policy_results"].append(result)
        app_logger.info(
            f"[ToolPolicy] {tool_name} code={code} allowed={allowed} "
            f"risk={result['risk_level']} workflow={workflow_value} confirmation={state.get('confirmation_status')}"
        )

    async def confirmation_node(self, state: AgentState) -> AgentState:
        """高风险动作确认节点。未启用 HITL 时不阻塞，只记录状态。"""
        state = self._sanitize_state(state)
        app_logger.info(f"[CONFIRMATION] 进入确认节点 - requires_confirmation={state.get('requires_confirmation')}, enable_human_in_the_loop={state.get('enable_human_in_the_loop')}")
        
        if not state.get("requires_confirmation", False):
            state["confirmation_status"] = "not_required"
            app_logger.info("[CONFIRMATION] 不需要确认，直接返回")
            return self._sanitize_state(state)

        if not state.get("enable_human_in_the_loop", False):
            state["confirmation_status"] = "required_but_disabled"
            state["validation_errors"].append("该请求需要人工确认，但当前未启用人机协作")
            self._add_thought(
                state,
                "confirmation_node",
                "confirm",
                "高风险请求需要人工确认，但人机协作未启用",
                action="确认跳过",
            )
            app_logger.info("[CONFIRMATION] 人机协作未启用，跳过确认")
            return self._sanitize_state(state)

        details = state.get("pending_action") or {}
        resume_state = self._build_resume_state(state)
        app_logger.info(f"[CONFIRMATION] 请求确认 - details={details}, event_callback={state.get('event_callback')}")
        
        # 检查 event_callback
        if state.get("event_callback") is None:
            app_logger.error("[CONFIRMATION] event_callback 为 None，无法发送确认事件！")
        
        approved = await self.hitl_service.request_confirmation(
            confirm_type=ConfirmationType.CRITICAL_ACTION,
            title="高风险操作确认",
            message=f"请求包含高风险操作：{details.get('reason', '')}\n\n用户请求：{state.get('question', '')}",
            details=details,
            resume_state=resume_state,
            event_callback=state.get("event_callback"),
        )
        state["confirmation_status"] = "approved" if approved else "rejected"
        if not approved:
            state["validation_errors"].append("高风险操作未获得人工确认")
        self._add_thought(
            state,
            "confirmation_node",
            "confirm",
            "高风险操作已确认" if approved else "高风险操作被拒绝或超时",
            action="人工确认",
        )
        app_logger.info(f"[CONFIRMATION] 确认完成 - approved={approved}")
        return self._sanitize_state(state)

    def _build_resume_state(self, state: AgentState) -> Dict[str, Any]:
        resume_state = self._sanitize_state(state).copy()
        resume_state["event_callback"] = None
        resume_state["enable_human_in_the_loop"] = False
        resume_state["confirmation_status"] = "approved"
        resume_state["requires_confirmation"] = False
        return resume_state

    def _format_chunks_to_text(self, chunks: List[Dict[str, Any]]) -> List[str]:
        texts = []
        for chunk in chunks:
            content = chunk.get("content", "")
            speaker = chunk.get("speaker_name", "")
            if speaker:
                texts.append(f"[{speaker}]: {content}")
            else:
                texts.append(content)
        return texts

    def _extract_document_ids_from_question(self, question: str) -> List[int]:
        patterns = [
            r'(?:id|ID|编号|文档id|文档ID)\s*(?:为|是|=|：|:)?\s*(\d+)',
            r'(?:文档|文件|第)\s*(\d+)\s*(?:号|个|篇)?(?:文档|文件)?',
            r'#(\d+)',
        ]
        ids = []
        for pattern in patterns:
            for match in re.finditer(pattern, question):
                ids.append(int(match.group(1)))
        return list(dict.fromkeys(ids))

    def _is_document_summary_intent(self, question: str) -> bool:
        keywords = ['主要讲', '讲了什么', '内容是什么', '内容有哪些', '说了什么',
                    '介绍了什么', '包含什么', '包含哪些', '总结', '摘要', '概述']
        return any(keyword in question for keyword in keywords)

    def _raw_results_to_search_results(self, raw_list: List[dict]) -> List[Dict[str, Any]]:
        return [
            {
                "chunk_id": item.get("chunk_id", 0),
                "document_id": item.get("document_id", 0),
                "meeting_id": item.get("meeting_id"),
                "content": item.get("content", item.get("chunk_text", "")),
                "chunk_index": item.get("chunk_index", 0),
                "similarity": item.get("similarity", item.get("score", 0.0)),
                "department": item.get("department"),
                "speaker_name": item.get("speaker_name", ""),
                "time_offset": item.get("time_offset"),
                "metadata_json": item.get("metadata_json"),
            }
            for item in raw_list
        ]

    async def _retrieve_context(
        self,
        question: str,
        meeting_id: Optional[int],
        document_ids: Optional[List[int]],
        vector_search_service,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        from app.core.config import settings

        mentioned_ids = self._extract_document_ids_from_question(question)

        if mentioned_ids and self._is_document_summary_intent(question):
            app_logger.info(f"[RETRIEVE] 检测到文档全文摘要意图，document_ids={mentioned_ids}")
            all_chunks: List[dict] = []
            for doc_id in mentioned_ids:
                chunks = await vector_search_service.get_document_chunks(doc_id)
                all_chunks.extend(chunks)
            if all_chunks:
                return self._raw_results_to_search_results(all_chunks)
            app_logger.warning(f"[RETRIEVE] 文档 {mentioned_ids} 无 chunk，回退向量检索")

        effective_doc_ids = document_ids or []
        if mentioned_ids:
            effective_doc_ids = list(dict.fromkeys(effective_doc_ids + mentioned_ids))
            top_k = max(top_k, 10)

        if settings.ENABLE_MULTI_RETRIEVAL:
            app_logger.info("[RETRIEVE] 使用多路召回模式（BM25 + 向量 + 重排序）")
            search_results = await vector_search_service.search_with_multi_retrieval(
                query_text=question,
                top_k=top_k,
                document_ids=effective_doc_ids if effective_doc_ids else None,
                meeting_id=meeting_id,
                enable_bm25=settings.ENABLE_BM25,
                enable_vector=True,
                enable_rerank=settings.ENABLE_RERANK,
            )
        else:
            search_results = await vector_search_service.search_by_text(
                query_text=question,
                top_k=top_k,
                document_ids=effective_doc_ids if effective_doc_ids else None,
                meeting_id=meeting_id,
            )

        return self._raw_results_to_search_results(search_results)

    def _classify_workflow(self, question: str) -> Tuple[WorkflowType, TaskType, float, str]:
        normalized = question.strip().lower()
        if self._is_greeting(question):
            return WorkflowType.SIMPLE_QA, TaskType.QA, 0.05, "问候语，直接响应"

        todo_keywords = ["待办", "行动项", "任务", "负责人", "截止", "todo", "action item"]
        minutes_keywords = ["纪要", "会议纪要", "总结会议", "会议总结", "摘要", "概述", "主要内容"]
        controversy_keywords = ["争议", "分歧", "冲突", "不同意见", "反对", "风险点"]
        complex_markers = ["并且", "同时", "以及", "和", "再", "然后", "分别", "综合", "分析"]

        matched = []
        if any(keyword in normalized for keyword in todo_keywords):
            matched.append((WorkflowType.TODO, TaskType.TODO, "待办提取意图"))
        if any(keyword in normalized for keyword in minutes_keywords):
            matched.append((WorkflowType.MINUTES, TaskType.MINUTES, "纪要/摘要意图"))
        if any(keyword in normalized for keyword in controversy_keywords):
            matched.append((WorkflowType.CONTROVERSY, TaskType.CONTROVERSY, "争议分析意图"))

        if len(matched) > 1:
            return WorkflowType.COMPLEX, TaskType.MULTI, 0.8, "命中多个任务意图，需要组合规划"
        if matched and any(marker in normalized for marker in complex_markers) and len(question) > 30:
            return WorkflowType.COMPLEX, TaskType.MULTI, 0.7, "包含组合连接词且问题较复杂"
        if matched:
            workflow_type, task_type, reason = matched[0]
            return workflow_type, task_type, 0.3, reason
        if len(question) > 120 and any(marker in normalized for marker in complex_markers):
            return WorkflowType.COMPLEX, TaskType.MULTI, 0.65, "长问题且包含多步骤表达"
        return WorkflowType.SIMPLE_QA, TaskType.QA, 0.2, "默认简单问答"

    def _estimate_retrieval_confidence(self, state: AgentState) -> float:
        context = state.get("context") or []
        if not context:
            return 0.0
        scores = []
        for item in context:
            if isinstance(item, dict):
                score = item.get("similarity", item.get("score"))
                if isinstance(score, (int, float)):
                    scores.append(float(score))
        if not scores:
            return 0.5
        return max(0.0, min(1.0, sum(scores) / len(scores)))

    def _build_citations(self, state: AgentState) -> List[Dict[str, Any]]:
        citations = []
        for item in (state.get("context") or [])[:5]:
            if not isinstance(item, dict):
                continue
            citations.append({
                "chunk_id": item.get("chunk_id"),
                "document_id": item.get("document_id"),
                "meeting_id": item.get("meeting_id"),
                "chunk_index": item.get("chunk_index"),
                "similarity": item.get("similarity", item.get("score")),
                "speaker_name": item.get("speaker_name"),
            })
        return citations

    def _direct_task(self, task_type: TaskType) -> TaskItem:
        return {
            "task_id": f"direct_{task_type.value}",
            "task_type": task_type.value,
            "description": "直接工作流任务",
            "priority": 1,
            "status": "pending",
            "dependencies": [],
            "can_parallel_with": [],
            "input_from": None,
            "output_key": f"{task_type.value}_result",
            "result": None,
            "error": None,
        }

    async def simple_qa_node(self, state: AgentState) -> AgentState:
        state = self._sanitize_state(state)
        state["current_phase"] = "direct_qa"
        await self._execute_qa(state, self._direct_task(TaskType.QA), self._format_context(state))
        state["agents_involved"].append("simple_qa_node")
        state["last_executed_node"] = "simple_qa_node"
        return self._sanitize_state(state)

    async def minutes_node(self, state: AgentState) -> AgentState:
        state = self._sanitize_state(state)
        state["current_phase"] = "direct_minutes"
        await self._execute_minutes(state, self._direct_task(TaskType.MINUTES), self._format_context(state))
        state["agents_involved"].append("minutes_node")
        state["last_executed_node"] = "minutes_node"
        return self._sanitize_state(state)

    async def todos_node(self, state: AgentState) -> AgentState:
        state = self._sanitize_state(state)
        state["current_phase"] = "direct_todo"
        await self._execute_todos(state, self._direct_task(TaskType.TODO), self._format_context(state))
        state["agents_involved"].append("todos_node")
        state["last_executed_node"] = "todos_node"
        return self._sanitize_state(state)

    async def controversy_node(self, state: AgentState) -> AgentState:
        state = self._sanitize_state(state)
        state["current_phase"] = "direct_controversy"
        await self._execute_controversies(state, self._direct_task(TaskType.CONTROVERSY), self._format_context(state))
        state["agents_involved"].append("controversy_node")
        state["last_executed_node"] = "controversy_node"
        return self._sanitize_state(state)

    async def validate_node(self, state: AgentState) -> AgentState:
        """确定性输出校验节点，不调用 LLM。"""
        state = self._sanitize_state(state)
        state["current_phase"] = "validate"
        existing_errors = state.get("validation_errors") or []
        validation_errors = list(existing_errors)

        task_type = state.get("task_type") or TaskType.QA
        workflow_type = state.get("workflow_type")

        if state.get("confirmation_status") in ["required_but_disabled", "rejected"]:
            pass
        elif task_type == TaskType.QA:
            validation_errors.extend(self._validate_answer(state))
        elif task_type == TaskType.MINUTES:
            validation_errors.extend(self._validate_minutes(state))
        elif task_type == TaskType.TODO:
            validation_errors.extend(self._validate_todos(state))
        elif task_type == TaskType.CONTROVERSY:
            validation_errors.extend(self._validate_controversies(state))
        elif task_type == TaskType.MULTI or workflow_type == WorkflowType.COMPLEX:
            validation_errors.extend(self._validate_complex_result(state))

        state["validation_errors"] = list(dict.fromkeys(error for error in validation_errors if error))
        state["agents_involved"].append("validate_node")
        if state["validation_errors"]:
            self._add_thought(
                state,
                "validate_node",
                "validate",
                f"校验发现 {len(state['validation_errors'])} 个问题",
                action="输出校验",
                observation="; ".join(state["validation_errors"][:3]),
            )
        else:
            self._add_thought(state, "validate_node", "validate", "输出校验通过", action="输出校验")

        # 输出侧敏感信息脱敏（第9层：输出安全校验）
        self._sanitize_output(state)

        return self._sanitize_state(state)

    async def repair_node(self, state: AgentState) -> AgentState:
        """局部修复节点：只做确定性结构修复，不重新执行完整 Agent。"""
        state = self._sanitize_state(state)
        state["current_phase"] = "repair"
        repair_count = int(state.get("repair_count", 0))
        state["repair_count"] = repair_count + 1

        task_type = state.get("task_type") or TaskType.QA
        repaired = []

        if task_type == TaskType.QA:
            if not isinstance(state.get("answer"), str) or not state.get("answer", "").strip():
                state["answer"] = "未能基于当前上下文生成有效回答，请补充更多信息或选择相关文档后重试。"
                repaired.append("补充空回答兜底提示")
        elif task_type == TaskType.TODO:
            if self._repair_todos(state):
                repaired.append("规范化待办事项结构")
        elif task_type == TaskType.CONTROVERSY:
            if self._repair_controversies(state):
                repaired.append("规范化争议点结构")
        elif task_type == TaskType.MULTI:
            if state.get("todos") is not None and self._repair_todos(state):
                repaired.append("规范化待办事项结构")
            if state.get("controversies") is not None and self._repair_controversies(state):
                repaired.append("规范化争议点结构")

        state["validation_errors"] = []
        state["agents_involved"].append("repair_node")
        self._add_thought(
            state,
            "repair_node",
            "repair",
            "完成局部修复" if repaired else "没有可自动修复的问题",
            action="局部修复",
            observation="; ".join(repaired) if repaired else None,
        )
        return self._sanitize_state(state)

    def _coerce_list_output(self, value: Any) -> Optional[List[Any]]:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            success, parsed = self._parse_json_response(value, "结构化输出")
            if success and isinstance(parsed, list):
                return parsed
        return None

    def _repair_todos(self, state: AgentState) -> bool:
        todos = self._coerce_list_output(state.get("todos"))
        if todos is None:
            return False

        normalized = []
        changed = not isinstance(state.get("todos"), list)
        for item in todos:
            if isinstance(item, str):
                normalized.append({"content": item, "assignee": "", "deadline": ""})
                changed = True
                continue
            if not isinstance(item, dict):
                changed = True
                continue
            fixed = dict(item)
            if "content" not in fixed:
                for candidate in ["task", "title", "description", "text"]:
                    if fixed.get(candidate):
                        fixed["content"] = fixed[candidate]
                        changed = True
                        break
            fixed.setdefault("content", "")
            fixed.setdefault("assignee", "")
            fixed.setdefault("deadline", "")
            normalized.append(fixed)
            changed = changed or fixed != item

        state["todos"] = normalized
        return changed

    def _repair_controversies(self, state: AgentState) -> bool:
        controversies = self._coerce_list_output(state.get("controversies"))
        if controversies is None:
            return False

        normalized = []
        changed = not isinstance(state.get("controversies"), list)
        for item in controversies:
            if isinstance(item, str):
                normalized.append({"topic": item, "description": "", "parties": []})
                changed = True
                continue
            if not isinstance(item, dict):
                changed = True
                continue
            fixed = dict(item)
            if "topic" not in fixed:
                for candidate in ["title", "issue", "content", "description"]:
                    if fixed.get(candidate):
                        fixed["topic"] = fixed[candidate]
                        changed = True
                        break
            fixed.setdefault("topic", "")
            fixed.setdefault("description", "")
            if not isinstance(fixed.get("parties"), list):
                fixed["parties"] = []
                changed = True
            normalized.append(fixed)
            changed = changed or fixed != item

        state["controversies"] = normalized
        return changed

    def _has_retrieved_context(self, state: AgentState) -> bool:
        return bool(state.get("context") or state.get("raw_context"))

    def _sanitize_output(self, state: AgentState) -> None:
        """输出侧敏感信息脱敏（第9层：输出安全校验）

        对 state["answer"] 和 state["minutes"] 调用 ContentSafetyService.check_output_text，
        将命中的敏感信息（手机号/银行卡/身份证/邮箱/密码）替换为占位符。
        脱敏结果直接写回 state，不阻断流程。
        """
        try:
            from app.services.content_safety import get_content_safety_service
            safety = get_content_safety_service()

            # 脱敏 answer
            answer = state.get("answer")
            if isinstance(answer, str) and answer.strip():
                result = safety.check_output_text(answer)
                sanitized = result.details.get("sanitized_text", answer)
                if sanitized != answer:
                    state["answer"] = sanitized

            # 脱敏 minutes
            minutes = state.get("minutes")
            if isinstance(minutes, str) and minutes.strip():
                result = safety.check_output_text(minutes)
                sanitized = result.details.get("sanitized_text", minutes)
                if sanitized != minutes:
                    state["minutes"] = sanitized

        except Exception as e:
            app_logger.debug(f"[ValidateNode] 输出脱敏失败（忽略）: {e}")

    def _validate_answer(self, state: AgentState) -> List[str]:
        errors = []
        answer = state.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            errors.append("问答结果为空")
        if state.get("retrieval_required", True) and self._has_retrieved_context(state) and not state.get("citations"):
            errors.append("问答结果缺少可追溯引用")
        return errors

    def _validate_minutes(self, state: AgentState) -> List[str]:
        errors = []
        minutes = state.get("minutes")
        if not isinstance(minutes, str) or len(minutes.strip()) < 20:
            errors.append("会议纪要为空或过短")
        return errors

    def _validate_todos(self, state: AgentState) -> List[str]:
        errors = []
        todos = state.get("todos")
        if not isinstance(todos, list):
            errors.append("待办事项结果不是列表")
            return errors
        for index, item in enumerate(todos):
            if not isinstance(item, dict):
                errors.append(f"第 {index + 1} 个待办不是对象")
                continue
            if not str(item.get("content", "")).strip():
                errors.append(f"第 {index + 1} 个待办缺少内容")
            if "assignee" in item and item.get("assignee") is not None and not isinstance(item.get("assignee"), str):
                errors.append(f"第 {index + 1} 个待办负责人格式不正确")
            if "deadline" in item and item.get("deadline") is not None and not isinstance(item.get("deadline"), str):
                errors.append(f"第 {index + 1} 个待办截止时间格式不正确")
        return errors

    def _validate_controversies(self, state: AgentState) -> List[str]:
        errors = []
        controversies = state.get("controversies")
        if not isinstance(controversies, list):
            errors.append("争议点结果不是列表")
            return errors
        for index, item in enumerate(controversies):
            if not isinstance(item, dict):
                errors.append(f"第 {index + 1} 个争议点不是对象")
                continue
            if not str(item.get("topic", "")).strip():
                errors.append(f"第 {index + 1} 个争议点缺少主题")
            if "parties" in item and item.get("parties") is not None and not isinstance(item.get("parties"), list):
                errors.append(f"第 {index + 1} 个争议点涉及方格式不正确")
        return errors

    def _validate_complex_result(self, state: AgentState) -> List[str]:
        errors = []
        if not any([state.get("answer"), state.get("minutes"), state.get("todos"), state.get("controversies")]):
            errors.append("复杂任务没有产生任何结果")
        if state.get("todos") is not None:
            errors.extend(self._validate_todos(state))
        if state.get("controversies") is not None:
            errors.extend(self._validate_controversies(state))
        return errors

    def _create_default_plan(self) -> Plan:
        return {
            "analysis": "默认计划：执行问答任务",
            "tasks": [{
                "task_id": "default_qa",
                "task_type": "qa",
                "description": "回答用户问题",
                "priority": 1,
                "status": "pending",
                "dependencies": [],
                "can_parallel_with": [],
                "input_from": None,
                "output_key": "qa_result",
                "tool_to_use": "answer_question",
                "result": None,
                "error": None
            }],
            "execution_order": ["default_qa"],
            "parallel_groups": [["default_qa"]],
            "tool_calls": [{
                "tool_name": "answer_question",
                "arguments": {"question": "{{question}}", "context": "{{context}}"}
            }]
        }

    def _log_plan(self, state: AgentState):
        plan = state.get("plan", {})
        app_logger.info("=" * 60)
        app_logger.info("📋 执行计划（支持 Tool Calling）")
        app_logger.info("=" * 60)
        app_logger.info(f"分析: {plan.get('analysis', '')}")
        app_logger.info(f"任务数: {len(plan.get('tasks', []))}")
        
        for task in plan.get("tasks", []):
            tool = task.get("tool_to_use", "无")
            app_logger.info(f"  [{task['task_id']}] {task['task_type']} - {task['description']} (工具: {tool})")
        
        tool_calls = plan.get("tool_calls", [])
        if tool_calls:
            app_logger.info(f"工具调用: {len(tool_calls)} 次")
            for tc in tool_calls:
                app_logger.info(f"  - {tc['tool_name']}: {tc.get('arguments', {})}")
        app_logger.info("=" * 60)

    async def execute_agent(self, state: AgentState) -> AgentState:
        """执行 Agent - Tool Calling"""
        async with AgentTraceContext("execute_agent", "tool") as trace:
            state = self._sanitize_state(state)
            app_logger.info("[EXECUTE] 开始执行阶段（Tool Calling）...")
            self._add_thought(state, "execute_agent", "execute", "开始执行计划，调用工具", action="工具执行")

            state["current_phase"] = "execute"
            plan = state.get("plan")
            tasks = {}  # 防止 plan is None 时 line 2175 引用 tasks 导致 NameError

            if not plan:
                state = await self._execute_default_task(state)
            else:
                tool_calls = plan.get("tool_calls", [])
                if tool_calls:
                    await self._execute_tool_calls(state, tool_calls)

                tasks = {t["task_id"]: t for t in plan.get("tasks", [])}
                parallel_groups = plan.get("parallel_groups", [])
                
                # 使用 ParallelExecutor 真正并行执行
                from app.core.config import settings
                if getattr(settings, "ENABLE_PARALLEL_EXECUTOR", True) and parallel_groups:
                    from app.services.parallel_executor import get_parallel_executor
                    executor = get_parallel_executor()
                    exec_result = await executor.execute(
                        tasks=tasks,
                        parallel_groups=parallel_groups,
                        execute_fn=self._execute_single_task,
                        state=state,
                        all_tasks=tasks,
                    )
                    self._add_thought(
                        state, "execute_agent", "execute",
                        f"并行执行完成: {exec_result.completed} 成功, {exec_result.failed} 失败, {exec_result.skipped} 跳过",
                        action="并行执行结果",
                    )
                    # 记录执行结果到 state
                    state["execution_result"] = {
                        "total": exec_result.total,
                        "completed": exec_result.completed,
                        "failed": exec_result.failed,
                        "skipped": exec_result.skipped,
                        "all_failed": exec_result.all_failed,
                        "partial_failure": exec_result.partial_failure,
                        "failure_rate": exec_result.failure_rate,
                        "failed_task_ids": exec_result.failed_task_ids,
                    }
                elif parallel_groups:
                    await self._execute_with_parallel(state, tasks, parallel_groups)
                else:
                    await self._execute_sequential(state, tasks, plan.get("execution_order", []))
            
            if not tasks and not state.get("answer"):
                if self._is_greeting(state["question"]):
                    state["answer"] = self._get_greeting_response()
                    self._add_thought(state, "execute_agent", "execute", "检测到问候语，给出友好回应", action="问候响应")

            state["agents_involved"].append("execute_agent")
            self._add_thought(state, "execute_agent", "execute", "所有任务执行完成", observation="进入反思阶段")
            state["current_phase"] = "replan"

            plan_info = plan.get("tasks", []) if plan else []
            trace.update_output(f"执行完成，{len(plan_info)} 个任务")

            # ── 写入长期记忆 ────────────────────────────────────────────
            try:
                unified_memory = get_unified_memory()
                meeting_id = state.get("meeting_id") or state.get("session_id") or state.get("thread_id")
                minutes = state.get("minutes")
                todos = state.get("todos")
                controversies = state.get("controversies")
                answer = state.get("answer")
                question = state.get("question", "")
                # 只要有实质性输出就写入记忆
                if meeting_id and (minutes or todos or controversies or answer):
                    asyncio.create_task(
                        unified_memory.add_meeting_memory(
                            meeting_id=str(meeting_id),
                            title=question[:80] if question else "未命名会议",
                            content=minutes or answer or "",
                            key_points=todos if isinstance(todos, list) else [],
                            participants=state.get("participants", []),
                            decisions=controversies if isinstance(controversies, list) else [],
                            tags=["auto"],
                        )
                    )
                    self._add_thought(
                        state,
                        "execute_agent",
                        "execute",
                        "已异步写入长期记忆",
                        observation=f"meeting_id={meeting_id}",
                    )
            except Exception as mem_exc:
                app_logger.warning(f"[Memory] 长期记忆写入失败（不影响主流程）: {mem_exc}")

            return self._sanitize_state(state)

    async def _execute_tool_calls(self, state: AgentState, tool_calls: List[Dict[str, Any]]):
        """执行工具调用 - 逐个工具确认"""
        self._add_thought(state, "execute_agent", "execute", f"开始执行 {len(tool_calls)} 个工具调用", action="工具调用")

        for tc in tool_calls:
            tool_name = tc.get("tool_name")
            arguments = tc.get("arguments", {})
            if not tool_name:
                state["validation_errors"].append("工具调用缺少 tool_name")
                continue
            tool = self._get_tool_by_name(tool_name)
            
            # 检查工具风险并逐个确认
            tool_risk = RiskLevel.LOW
            metadata = getattr(tool, "metadata", None)
            if metadata:
                tool_risk = self._normalize_risk_level(getattr(metadata, "risk_level", RiskLevel.LOW))
            
            # HIGH/CRITICAL 必须确认；MEDIUM 由 ToolPolicy 根据授权、可撤销性和外部副作用判断。
            medium_safe = False
            if tool_risk == RiskLevel.MEDIUM and metadata:
                explicit = bool(state.get("explicit_write_authorization", False))
                if not explicit:
                    question = str(state.get("question", "")).lower()
                    explicit = any(word in question for word in ("创建", "新增", "保存", "更新", "修改", "写入", "create", "save", "update"))
                medium_safe = (
                    explicit
                    and bool(getattr(metadata, "reversible", True))
                    and not bool(getattr(metadata, "external_effect", False))
                    and not bool(getattr(metadata, "bulk_operation", False))
                )
            if tool_risk in {RiskLevel.HIGH, RiskLevel.CRITICAL} or (tool_risk == RiskLevel.MEDIUM and not medium_safe):
                # 检查是否启用人机协作
                if state.get("enable_human_in_the_loop", False):
                    # 请求单个工具确认
                    approved = await self._request_tool_confirmation(state, tool_name, tool_risk)
                    if not approved:
                        app_logger.warning(f"[EXECUTE] 工具 {tool_name} 未获得确认，跳过")
                        self._add_thought(
                            state,
                            "execute_agent",
                            "execute",
                            f"工具 {tool_name} 未获得人工确认，跳过",
                            action="工具确认拒绝"
                        )
                        self._record_policy_result(
                            state, tool_name, "rejected", False, "用户拒绝确认", "execute"
                        )
                        continue
            
            # 继续工具策略校验
            policy_decision = self.tool_policy.validate_tool_call(tool, state)
            if not policy_decision.allowed:
                error_message = f"{policy_decision.code}: {policy_decision.reason}"
                state["validation_errors"].append(error_message)
                self._record_policy_result(
                    state,
                    tool_name=tool_name,
                    code=policy_decision.code,
                    allowed=False,
                    reason=policy_decision.reason,
                    retry_count=policy_decision.retry_count,
                )
                self._add_thought(
                    state,
                    "execute_agent",
                    "execute",
                    f"工具 {tool_name} 被策略拒绝",
                    action="工具策略校验",
                    observation=error_message,
                )
                continue

            # 替换变量
            arguments = self._substitute_variables(arguments, state)
            arguments = self._prepare_tool_arguments(tool_name, arguments, state)

            self._add_thought(state, "execute_agent", "execute", f"调用工具: {tool_name}", action=tool_name)
            self._record_policy_result(
                state,
                tool_name=tool_name,
                code="allowed",
                allowed=True,
                reason="工具策略校验通过",
                retry_count=policy_decision.retry_count,
            )

            # 局部重试逻辑：工具失败时最多重试 TOOL_MAX_LOCAL_RETRIES 次，避免直接升级为全量 repair
            _tool_max_retries = getattr(__import__('app.core.config', fromlist=['settings']).settings, 'TOOL_MAX_LOCAL_RETRIES', 2)
            _tool_retry_delay = getattr(__import__('app.core.config', fromlist=['settings']).settings, 'TOOL_RETRY_DELAY_SECONDS', 1)
            result: ToolExecutionResult = None  # type: ignore
            for _attempt in range(1 + _tool_max_retries):
                if _attempt > 0:
                    app_logger.warning(f"[EXECUTE] 工具 {tool_name} 第 {_attempt} 次重试...")
                    self._add_thought(
                        state, "execute_agent", "execute",
                        f"工具 {tool_name} 重试 ({_attempt}/{_tool_max_retries})",
                        action="工具重试",
                        observation=f"上次错误: {result.error if result else 'unknown'}"
                    )
                    await asyncio.sleep(_tool_retry_delay)
                result = await self.tool_manager.execute_tool(
                    tool_name,
                    arguments,
                    retry_count=policy_decision.retry_count,
                )
                if result.success:
                    break

            if result.success:
                self._add_thought(state, "execute_agent", "execute", f"工具 {tool_name} 执行成功", observation=str(result.result)[:200])

                # 存储工具结果到上下文
                state["task_contexts"][tool_name] = TaskContext(
                    task_id=tool_name,
                    data=result.result,
                    metadata={"execution_time": result.execution_time}
                )
                self._apply_tool_result_to_state(state, tool_name, result.result)
            else:
                app_logger.error(f"[EXECUTE] 工具 {tool_name} 重试 {_tool_max_retries} 次后仍失败: {result.error}")
                self._add_thought(state, "execute_agent", "execute", f"工具 {tool_name} 执行失败(已重试{_tool_max_retries}次): {result.error}", observation="错误")
                state["validation_errors"].append(f"工具 {tool_name} 执行失败: {result.error}")

    def _substitute_variables(self, arguments: Dict[str, Any], state: AgentState) -> Dict[str, Any]:
        """替换变量"""
        substituted = {}
        for key, value in arguments.items():
            if isinstance(value, str):
                if "{{question}}" in value:
                    value = value.replace("{{question}}", state.get("question", ""))
                if "{{context}}" in value:
                    value = value.replace("{{context}}", self._format_context(state))
            substituted[key] = value
        return substituted

    def _prepare_tool_arguments(self, tool_name: str, arguments: Dict[str, Any], state: AgentState) -> Dict[str, Any]:
        """将 Planner 输出的参数归一到实际工具签名。"""
        arguments = dict(arguments or {})
        context_text = self._resolve_tool_context(arguments, state)

        if tool_name in {"extract_todos", "generate_minutes", "detect_controversies"}:
            return {"context": context_text or self._format_context(state)}

        if tool_name == "answer_question":
            question = arguments.get("question") or arguments.get("query") or state.get("question", "")
            return {
                "question": str(question),
                "context": context_text or self._format_context(state),
            }

        if tool_name == "search_meeting":
            query = arguments.get("query") or arguments.get("question") or state.get("question", "")
            prepared = {"query": str(query)}
            meeting_id = arguments.get("meeting_id") or state.get("meeting_id")
            if meeting_id is not None:
                prepared["meeting_id"] = meeting_id
            prepared["top_k"] = int(arguments.get("top_k") or 5)
            return prepared

        if tool_name == "search_document":
            query = arguments.get("query") or arguments.get("question") or state.get("question", "")
            document_ids = arguments.get("document_ids") or arguments.get("document_id") or state.get("document_ids")
            prepared = {"query": str(query), "top_k": int(arguments.get("top_k") or 5)}
            normalized_ids = self._normalize_id_list(document_ids)
            if normalized_ids:
                prepared["document_ids"] = normalized_ids
            return prepared

        if tool_name == "get_document_content":
            document_id = (
                arguments.get("document_id")
                or arguments.get("documentId")
                or arguments.get("id")
                or self._first_document_id(state)
            )
            return {"document_id": int(document_id)} if document_id is not None else {}

        if tool_name == "text_processor":
            operation = arguments.get("operation") or "format"
            text = arguments.get("text") or arguments.get("content") or context_text or self._format_context(state)
            return {"operation": operation, "text": text}

        return arguments

    def _resolve_tool_context(self, arguments: Dict[str, Any], state: AgentState) -> str:
        for key in ["context", "content", "text", "input", "source_text"]:
            value = arguments.get(key)
            if value:
                return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

        input_from = arguments.get("input_from") or arguments.get("from_tool")
        if input_from and input_from in state.get("task_contexts", {}):
            data = state["task_contexts"][input_from].get("data")
            return data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)

        preferred_tools = ["get_document_content", "search_document", "search_meeting"]
        for previous_tool in preferred_tools:
            tool_context = state.get("task_contexts", {}).get(previous_tool)
            if tool_context:
                return self._tool_data_to_context(tool_context.get("data"))

        return self._format_context(state)

    def _tool_data_to_context(self, data: Any) -> str:
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            if data.get("content"):
                return str(data["content"])
            return json.dumps(data, ensure_ascii=False)
        if isinstance(data, list):
            texts = []
            for item in data:
                if isinstance(item, dict):
                    texts.append(str(item.get("content") or item.get("chunk_text") or item))
                else:
                    texts.append(str(item))
            return "\n\n".join(texts)
        return str(data) if data is not None else ""

    def _normalize_id_list(self, value: Any) -> List[int]:
        if value is None:
            return []
        if isinstance(value, list):
            return [int(item) for item in value if item is not None]
        return [int(value)]

    def _first_document_id(self, state: AgentState) -> Optional[int]:
        document_ids = state.get("document_ids") or []
        if document_ids:
            return int(document_ids[0])
        mentioned_ids = self._extract_document_ids_from_question(state.get("question", ""))
        return int(mentioned_ids[0]) if mentioned_ids else None

    def _apply_tool_result_to_state(self, state: AgentState, tool_name: str, result: Any) -> None:
        if tool_name == "get_document_content":
            content = result.get("content") if isinstance(result, dict) else None
            if content:
                state["raw_context"] = list(dict.fromkeys((state.get("raw_context") or []) + [content]))
        elif tool_name in {"search_document", "search_meeting"}:
            if isinstance(result, list):
                state["raw_context"] = list(dict.fromkeys((state.get("raw_context") or []) + self._format_chunks_to_text(result)))
        elif tool_name == "extract_todos" and isinstance(result, list):
            state["todos"] = result
        elif tool_name == "generate_minutes" and isinstance(result, str):
            state["minutes"] = result
        elif tool_name == "detect_controversies" and isinstance(result, list):
            state["controversies"] = result
        elif tool_name == "answer_question" and isinstance(result, str):
            state["answer"] = result

    async def _request_tool_confirmation(self, state: AgentState, tool_name: str, tool_risk: RiskLevel) -> bool:
        """请求单个工具确认"""
        import uuid
        
        details = {
            "request_id": str(uuid.uuid4()),
            "source": "tool",
            "question": state.get("question", ""),
            "tool_name": tool_name,
            "risk_level": tool_risk.value,
            "reason": f"工具 {tool_name} 风险等级: {tool_risk.value}，需要人工确认",
        }
        
        resume_state = self._sanitize_state(state).copy()
        resume_state["event_callback"] = None
        resume_state["enable_human_in_the_loop"] = False
        
        self._add_thought(
            state, "execute_agent", "confirm", f"等待工具 {tool_name} 人工确认...", action="工具确认"
        )
        
        approved = await self.hitl_service.request_confirmation(
            confirm_type=ConfirmationType.CRITICAL_ACTION,
            title=f"工具调用确认: {tool_name}",
            message=f"即将调用工具 {tool_name}，风险等级: {tool_risk.value}\n\n用户请求：{state.get('question', '')}",
            details=details,
            resume_state=resume_state,
            event_callback=state.get("event_callback"),
        )
        
        self._add_thought(
            state, "execute_agent", "confirm", f"工具 {tool_name} 确认结果: {'通过' if approved else '拒绝'}", action="工具确认完成"
        )
        
        return approved

    async def _execute_with_parallel(self, state: AgentState, tasks: Dict, parallel_groups: List[List[str]]):
        """按并行分组执行任务 - 确保所有任务都被执行"""
        parallel_task_ids = set()
        for group in parallel_groups:
            parallel_task_ids.update(group)
        
        sequential_tasks = [t for t in tasks.values() if t["task_id"] not in parallel_task_ids]
        
        if sequential_tasks:
            for task in sequential_tasks:
                if task.get("status") == "pending":
                    await self._execute_single_task(state, task, tasks)
        
        for group_idx, group in enumerate(parallel_groups):
            self._add_thought(state, "execute_agent", "execute", f"执行并行组 {group_idx + 1}: {group}", action="并行执行")
            ready_tasks = [t for t in group if t in tasks and tasks[t].get("status") == "pending"]
            
            if len(ready_tasks) == 1:
                await self._execute_single_task(state, tasks[ready_tasks[0]], tasks)
            elif len(ready_tasks) > 1:
                await self._execute_parallel_group(state, ready_tasks, tasks)

    async def _execute_parallel_group(self, state: AgentState, task_ids: List[str], tasks: Dict):
        self._add_thought(state, "execute_agent", "execute", f"并发执行 {len(task_ids)} 个任务", action="并发执行")

        async def execute_task_wrapper(task_id: str):
            task = tasks[task_id]
            return await self._execute_single_task(state, task, tasks)

        results = await asyncio.gather(
            *[execute_task_wrapper(tid) for tid in task_ids],
            return_exceptions=True
        )
        
        for task_id, result in zip(task_ids, results):
            if isinstance(result, Exception):
                app_logger.error(f"[EXECUTE] 任务 {task_id} 执行异常: {result}")
                tasks[task_id]["status"] = "failed"
                tasks[task_id]["error"] = str(result)

    async def _execute_sequential(self, state: AgentState, tasks: Dict, execution_order: List[str]):
        for task_id in execution_order:
            if task_id not in tasks:
                continue
            task = tasks[task_id]
            await self._execute_single_task(state, task, tasks)

    async def _execute_single_task(self, state: AgentState, task: TaskItem, all_tasks: Dict) -> AgentState:
        task_id = task["task_id"]
        task_type = task.get("task_type", "qa")
        
        task["status"] = "in_progress"
        self._add_thought(state, "execute_agent", "execute", f"执行任务: [{task_id}] {task_type}", action=task_type)

        try:
            # 检查是否有工具调用结果
            tool_context = state["task_contexts"].get(task.get("tool_to_use", ""))
            if tool_context:
                # 从 TaskContext 中获取 data
                tool_data = tool_context.get("data")
                task["result"] = tool_data
                task["status"] = "completed"
                
                task_type_lower = task_type.lower()
                tool_to_use = task.get("tool_to_use", "")
                if task_type_lower in ["qa", "问答"]:
                    # 处理工具返回的结果 - 可能是字典，需要提取 content
                    document_content = ""
                    if isinstance(tool_data, dict) and "content" in tool_data:
                        document_content = tool_data.get("content", "")
                    elif isinstance(tool_data, str):
                        document_content = tool_data
                    
                    if tool_to_use and "document" in tool_to_use:
                        # 获取了文档内容，需要基于它回答用户问题
                        if document_content:
                            # 判断是否是摘要意图
                            is_summary_intent = self._is_summary_intent(state["question"])
                            
                            if is_summary_intent:
                                self._add_thought(state, "execute_agent", "execute", "检测到摘要意图，生成文档摘要", action="生成摘要")
                                prompt = f"""请对以下文档内容进行总结，回答用户的问题。

问题：{state['question']}

文档内容：{document_content}

要求：
1. 用简洁的语言概括文档的主要内容
2. 提取核心要点和关键信息
3. 不要逐字重复文档内容
4. 保持回答的连贯性和可读性

请给出你的总结回答："""
                            else:
                                self._add_thought(state, "execute_agent", "execute", "基于获取的文档内容回答问题", action="生成回答")
                                prompt = f"""基于以下文档内容，请直接回答用户的问题。只需要给出回答，不需要重复文档原文。

问题：{state['question']}

文档内容：{document_content}

请直接给出你的回答："""
                            
                            messages = [{"role": "user", "content": prompt}]
                            # QA 兜底回答，沿用双轴路由
                            from app.services.model_router import get_model_router as _get_mr2
                            _tier_fb, _qa_fb_model = _get_mr2().select(TaskType.QA, state.get("complexity_level"))
                            final_answer = await self.llm_service.chat(messages=messages, model=_qa_fb_model, temperature=0.7)
                            state["answer"] = final_answer
                        else:
                            state["answer"] = ""
                    else:
                        # 其他情况，直接使用工具结果
                        state["answer"] = document_content if document_content else ""
                elif task_type_lower in ["minutes", "纪要"]:
                    result = task["result"]
                    state["minutes"] = result if isinstance(result, str) else ""
                elif task_type_lower in ["todo", "待办"]:
                    try:
                        result = task["result"]
                        if isinstance(result, str):
                            state["todos"] = json.loads(result)
                        elif isinstance(result, list):
                            state["todos"] = result
                        else:
                            state["todos"] = []
                    except:
                        state["todos"] = []
                elif task_type_lower in ["controversy", "争议"]:
                    try:
                        result = task["result"]
                        if isinstance(result, str):
                            state["controversies"] = json.loads(result)
                        elif isinstance(result, list):
                            state["controversies"] = result
                        else:
                            state["controversies"] = []
                    except:
                        state["controversies"] = []
                
                output_key = task.get("output_key")
                if output_key:
                    state["task_contexts"][output_key] = TaskContext(
                        task_id=task_id,
                        data=task["result"],
                        metadata={"task_type": task_type}
                    )
                
                self._add_thought(state, "execute_agent", "execute", f"任务 [{task_id}] 完成（使用工具结果）", observation=str(task["result"])[:100])
                return state

            # 否则使用默认执行
            input_context = self._get_task_input(state, task, all_tasks)

            if task_type in ["qa", "问答"]:
                result = await self._execute_qa(state, task, input_context)
            elif task_type in ["minutes", "纪要"]:
                result = await self._execute_minutes(state, task, input_context)
            elif task_type in ["todo", "待办"]:
                result = await self._execute_todos(state, task, input_context)
            elif task_type in ["controversy", "争议"]:
                result = await self._execute_controversies(state, task, input_context)
            else:
                result = await self._execute_qa(state, task, input_context)

            task["result"] = result
            task["status"] = "completed"

            output_key = task.get("output_key")
            if output_key:
                state["task_contexts"][output_key] = TaskContext(
                    task_id=task_id,
                    data=result,
                    metadata={"task_type": task_type}
                )

            self._add_thought(state, "execute_agent", "execute", f"任务 [{task_id}] 完成", observation=str(result)[:100] if result else "无输出")

        except Exception as e:
            app_logger.error(f"[EXECUTE] 任务 [{task_id}] 执行失败: {e}")
            task["status"] = "failed"
            task["error"] = str(e)
            self._add_thought(state, "execute_agent", "execute", f"任务 [{task_id}] 失败: {str(e)}", observation="错误")

        return state

    def _get_task_input(self, state: AgentState, task: TaskItem, all_tasks: Dict) -> str:
        input_from = task.get("input_from")
        if input_from and input_from in state.get("task_contexts", {}):
            context_data = state["task_contexts"][input_from]
            if isinstance(context_data.get("data"), str):
                return context_data["data"]
            return json.dumps(context_data.get("data", ""), ensure_ascii=False)
        return self._format_context(state)

    def _is_greeting(self, question: str) -> bool:
        """检测是否为问候语"""
        greetings = ["你好", "您好", "Hi", "Hello", "hi", "hello", "您好", "嗨", "哈喽", "嗨喽", "早上好", "下午好", "晚上好", "早安", "晚安", "初次见面", "很高兴认识你"]
        for greeting in greetings:
            if greeting in question.strip():
                return True
        return False
    
    def _is_simple_fact_question(self, question: str) -> bool:
        """检测是否为简单事实类问题（不需要复杂推理）"""
        simple_patterns = [
            "是什么", "什么是", "有哪些", "有多少", "谁是", "谁的", "在哪里",
            "什么时候", "几点", "多久", "讨论了什么", "内容是什么", "主题是什么",
            "介绍一下", "说明一下", "解释一下", "定义", "含义", "意思",
        ]
        normalized = question.strip().lower()
        
        for pattern in simple_patterns:
            if pattern in normalized:
                return True
        
        if len(normalized) <= 15 and "？" in normalized:
            return True
        
        return False
    
    def _is_summary_intent(self, question: str) -> bool:
        """检测是否为摘要意图"""
        summary_keywords = [
            '主要讲', '讲了什么', '内容是什么', '内容有哪些', '说了什么',
            '介绍了什么', '包含什么', '包含哪些', '总结', '摘要', '概述',
            '核心内容', '重点是什么', '要点', '主旨', '中心思想',
            '概括', '简述', '简介', '大意', '梗概'
        ]
        return any(kw in question for kw in summary_keywords)
    
    def _get_greeting_response(self) -> str:
        """生成问候语响应"""
        return "你好！我是会议智能助手，很高兴为您服务。请问我可以帮您处理什么问题？比如会议总结、待办事项提取、文档查询等。"
    
    async def _execute_qa(self, state: AgentState, task: TaskItem, context: str) -> str:
        self._add_thought(state, "execute_agent", "execute", f"[{task['task_id']}] 执行问答", action="生成回答")
        
        tool_result = state["task_contexts"].get("answer_question")
        if tool_result:
            answer_data = tool_result.get("data", "")
            state["answer"] = answer_data if isinstance(answer_data, str) else ""
            return state["answer"]
        
        # 检测并处理问候语
        if self._is_greeting(state["question"]):
            answer = self._get_greeting_response()
            state["answer"] = answer
            state["agents_involved"].append("execute_agent")
            return answer

        # 判断是否是摘要意图
        is_summary_intent = self._is_summary_intent(state["question"])
        
        if is_summary_intent and context:
            prompt = f"""请对以下内容进行总结，回答用户的问题。

问题：{state['question']}

内容：{context}

要求：
1. 用简洁的语言概括主要内容
2. 提取核心要点和关键信息
3. 不要逐字重复原文
4. 保持回答的连贯性和可读性

请给出你的总结回答："""
        else:
            prompt = f"请回答问题：{state['question']}\n\n上下文：{context}"
        
        messages = [{"role": "user", "content": prompt}]
        # 双轴模型路由：QA 任务 × 当前复杂度
        from app.services.model_router import get_model_router
        _tier, _qa_model = get_model_router().select(state.get("task_type", TaskType.QA), state.get("complexity_level"))
        answer = await self.llm_service.chat(messages=messages, model=_qa_model, temperature=0.7)
        state["answer"] = answer
        state["agents_involved"].append("execute_agent")
        return answer

    async def _execute_minutes(self, state: AgentState, task: TaskItem, context: str) -> str:
        self._add_thought(state, "execute_agent", "execute", f"[{task['task_id']}] 生成纪要", action="生成纪要")

        tool_result = state["task_contexts"].get("generate_minutes")
        if tool_result:
            state["minutes"] = tool_result.get("data", "")
            return state["minutes"]

        prompt = f"请生成会议纪要：\n{context}"
        messages = [{"role": "user", "content": prompt}]
        # 双轴模型路由：MINUTES 确定性任务，锁 plus 下限，C/A 升 max
        from app.services.model_router import get_model_router
        _tier, _minutes_model = get_model_router().select(TaskType.MINUTES, state.get("complexity_level"))
        minutes = await self.llm_service.chat(messages=messages, model=_minutes_model, temperature=0.7)
        state["minutes"] = minutes
        state["agents_involved"].append("execute_agent")
        return minutes

    async def _execute_todos(self, state: AgentState, task: TaskItem, context: str) -> str:
        self._add_thought(state, "execute_agent", "execute", f"[{task['task_id']}] 抽取待办", action="抽取待办")
        
        tool_result = state["task_contexts"].get("extract_todos")
        if tool_result:
            state["todos"] = tool_result.get("data", [])
            return json.dumps(state["todos"], ensure_ascii=False)

        prompt = f"请从以下内容中抽取待办事项：\n{context}"
        messages = [{"role": "user", "content": prompt}]

        # 双轴模型路由：TODO 确定性任务，锁 plus 下限，C/A 升 max
        from app.services.model_router import get_model_router
        _tier, _todo_model = get_model_router().select(TaskType.TODO, state.get("complexity_level"))

        for attempt in range(self.max_retries):
            try:
                response = await self.llm_service.chat(messages=messages, model=_todo_model, temperature=0.3)
                success, todos = self._parse_json_response(response, "待办事项")
                if success and isinstance(todos, list):
                    state["todos"] = todos
                    state["agents_involved"].append("execute_agent")
                    return json.dumps(todos, ensure_ascii=False)
            except Exception as e:
                app_logger.error(f"[TODO] 第 {attempt + 1} 次失败: {e}")

        state["todos"] = []
        return "[]"

    async def _execute_controversies(self, state: AgentState, task: TaskItem, context: str) -> str:
        self._add_thought(state, "execute_agent", "execute", f"[{task['task_id']}] 识别争议", action="识别争议")
        
        tool_result = state["task_contexts"].get("detect_controversies")
        if tool_result:
            state["controversies"] = tool_result.get("data", [])
            return json.dumps(state["controversies"], ensure_ascii=False)

        prompt = f"请从以下内容中识别争议点：\n{context}"
        messages = [{"role": "user", "content": prompt}]

        # 双轴模型路由：CONTROVERSY 确定性任务，锁 plus 下限，C/A 升 max
        from app.services.model_router import get_model_router
        _tier, _controversy_model = get_model_router().select(TaskType.CONTROVERSY, state.get("complexity_level"))

        for attempt in range(self.max_retries):
            try:
                response = await self.llm_service.chat(messages=messages, model=_controversy_model, temperature=0.3)
                success, controversies = self._parse_json_response(response, "争议点")
                if success and isinstance(controversies, list):
                    state["controversies"] = controversies
                    state["agents_involved"].append("execute_agent")
                    return json.dumps(controversies, ensure_ascii=False)
            except Exception as e:
                app_logger.error(f"[CONTROVERSY] 第 {attempt + 1} 次失败: {e}")

        state["controversies"] = []
        return "[]"

    async def _execute_default_task(self, state: AgentState) -> AgentState:
        task_type = state.get("task_type", TaskType.QA)
        default_plan = self._create_default_plan()
        state["plan"] = default_plan
        state["task_contexts"] = {}

        tool_calls = default_plan.get("tool_calls", [])
        if tool_calls:
            await self._execute_tool_calls(state, tool_calls)

        if task_type == TaskType.MINUTES:
            await self._execute_minutes(state, default_plan["tasks"][0], self._format_context(state))
        elif task_type == TaskType.TODO:
            await self._execute_todos(state, default_plan["tasks"][0], self._format_context(state))
        elif task_type == TaskType.CONTROVERSY:
            await self._execute_controversies(state, default_plan["tasks"][0], self._format_context(state))
        else:
            await self._execute_qa(state, default_plan["tasks"][0], self._format_context(state))

        return state

    async def replan_agent(self, state: AgentState) -> AgentState:
        """重新规划 Agent - 多维度质量评估与重新规划"""
        async with AgentTraceContext("replan_agent", "reflection") as trace:
            state = self._sanitize_state(state)
            app_logger.info("[REPLAN] 开始重新规划阶段...")
            self._add_thought(state, "replan_agent", "replan", "开始评估执行结果质量", action="质量评估")

            # 统一质量门禁：替代 replan + reflection 双重 LLM 评估
            from app.core.config import settings as _settings
            if getattr(_settings, "ENABLE_UNIFIED_QUALITY_GATE", True):
                try:
                    from app.services.quality_gate import get_quality_gate
                    quality_gate = get_quality_gate()
                    gate_result = await quality_gate.evaluate(state, self.llm_service)

                    # 将评估结果写入 state
                    reflection = state.get("reflection") or {}
                    retry_count = int(reflection.get("retry_count", 0)) if reflection else 0
                    MAX_RETRIES = getattr(_settings, "MAX_REFLECTION_ITERATIONS", 2)

                    state["reflection"] = {
                        **reflection,
                        "overall_score": gate_result.quality_score,
                        "confidence": gate_result.quality_score,
                        "issues": gate_result.issues,
                        "suggestions": gate_result.suggestions,
                        "needs_retry": gate_result.needs_replan,
                        "needs_polish": gate_result.needs_polish,
                        "polishing_prompt": gate_result.polishing_prompt,
                        "replan_prompt": gate_result.replan_prompt,
                        "retry_count": retry_count,
                        "dimensions": gate_result.dimensions,
                        "structural_errors": gate_result.structural_errors,
                        "evaluation_method": gate_result.evaluation_method,
                    }

                    emoji = "🟢" if gate_result.quality_score >= 0.7 else "🟡" if gate_result.quality_score >= 0.5 else "🔴"
                    self._add_thought(
                        state, "replan_agent", "replan",
                        f"统一质量门禁评估完成 {emoji} score={gate_result.quality_score:.2f}, "
                        f"replan={gate_result.needs_replan}, polish={gate_result.needs_polish}",
                        action="质量评估",
                        observation=f"method={gate_result.evaluation_method}, issues={len(gate_result.issues)}"
                    )
                    trace.update_output(
                        f"质量门禁: score={gate_result.quality_score:.2f}, "
                        f"replan={gate_result.needs_replan}, polish={gate_result.needs_polish}"
                    )
                    state["agents_involved"].append("replan_agent")
                    return self._sanitize_state(state)
                except Exception as e:
                    app_logger.warning(f"[REPLAN] 统一质量门禁异常，降级到原逻辑: {e}")

            # 降级路径：原有的 LLM 评估逻辑
            question = state["question"]
            answer = state.get("answer")
            if not isinstance(answer, str):
                answer = ""
            minutes = state.get("minutes")
            if not isinstance(minutes, str):
                minutes = ""
            todos = state.get("todos")
            if not isinstance(todos, list):
                todos = []
            controversies = state.get("controversies")
            if not isinstance(controversies, list):
                controversies = []
            
            reflection = state.get("reflection")
            retry_count = int(reflection.get("retry_count", 0)) if reflection else 0
            
            MAX_RETRIES = 2

            is_summary_intent = self._is_summary_intent(question)
            
            prompt = f"""请从以下5个通用维度评估 Agent 执行结果的质量：

【评估标准】
1. 任务达成度 (task_completion): 用户的问题是否被有效解决，0.0-1.0
2. 正确性 (correctness): 内容是否准确，没有错误或误导性信息，0.0-1.0
3. 流程效率 (process_efficiency): 执行过程是否高效，是否有不必要的步骤，0.0-1.0
4. 表达 (expression): 表达是否清晰、通顺、易懂，0.0-1.0
5. 风险 (risk): 是否存在潜在风险（如信息泄露、错误引导、逻辑漏洞等），0.0-1.0（注意：风险越小，分数越高）

【权重配置】
- 任务达成度: 35%
- 正确性: 25%
- 流程效率: 15%
- 表达: 15%
- 风险: 10%

【特别注意】
- 如果问题是要求"总结"、"主要讲了什么"等摘要类问题，但回答只是直接复制原文而没有进行概括提炼，任务达成度应低于0.5
- 如果回答只是原文的简单重复，没有提取核心要点，任务达成度和表达应低于0.5

【用户问题】{question}

【执行结果】
- 回答：{answer[:500] if answer else '无'}
- 纪要：{minutes[:500] if minutes else '无'}
- 待办：{len(todos)} 个
- 争议点：{len(controversies)} 个
- 当前重试次数：{retry_count}/{MAX_RETRIES}

请输出 JSON，确保所有分数都在 0.0-1.0 之间：
{{
    "overall_score": 0.7,
    "metrics": {{
        "task_completion": 0.7,
        "correctness": 0.8,
        "process_efficiency": 0.6,
        "expression": 0.8,
        "risk": 0.9
    }},
    "confidence": 0.8,
    "issues": ["具体问题列表，例如：回答只是原文复制，没有进行摘要提炼"],
    "suggestions": [
        "具体的改进建议，例如：",
        "1. 添加摘要提取任务，使用LLM对文档内容进行概括",
        "2. 在执行计划中明确要求生成摘要而非返回原文",
        "3. 使用不同的prompt引导LLM生成总结性回答"
    ],
    "needs_retry": false
}}"""

            messages = [
                {"role": "system", "content": "你是专业的质量评估专家，擅长从多个通用维度评估 AI 输出质量，并根据评估结果决定是否需要重新规划。"},
                {"role": "user", "content": prompt}
            ]

            try:
                response = await self.llm_service.chat(messages=messages, temperature=0.3)
                success, result = self._parse_json_response(response, "评估结果")

                if success and isinstance(result, dict):
                    metrics = result.get("metrics", {})
                    task_completion = float(metrics.get("task_completion", 0.5)) if isinstance(metrics.get("task_completion"), (int, float)) else 0.5
                    correctness = float(metrics.get("correctness", 0.5)) if isinstance(metrics.get("correctness"), (int, float)) else 0.5
                    process_efficiency = float(metrics.get("process_efficiency", 0.5)) if isinstance(metrics.get("process_efficiency"), (int, float)) else 0.5
                    expression = float(metrics.get("expression", 0.5)) if isinstance(metrics.get("expression"), (int, float)) else 0.5
                    risk = float(metrics.get("risk", 0.5)) if isinstance(metrics.get("risk"), (int, float)) else 0.5
                    
                    def clamp_score(score: float) -> float:
                        return max(0.0, min(1.0, score))
                    
                    task_completion = clamp_score(task_completion)
                    correctness = clamp_score(correctness)
                    process_efficiency = clamp_score(process_efficiency)
                    expression = clamp_score(expression)
                    risk = clamp_score(risk)
                    
                    weights = {
                        "task_completion": 0.35,
                        "correctness": 0.25,
                        "process_efficiency": 0.15,
                        "expression": 0.15,
                        "risk": 0.1
                    }
                    overall_score = (
                        task_completion * weights["task_completion"] +
                        correctness * weights["correctness"] +
                        process_efficiency * weights["process_efficiency"] +
                        expression * weights["expression"] +
                        risk * weights["risk"]
                    )
                    
                    issues = result.get("issues")
                    suggestions = result.get("suggestions")
                    normalized_issues = issues if (issues is not None and isinstance(issues, list)) else []
                    normalized_suggestions = suggestions if (suggestions is not None and isinstance(suggestions, list)) else []
                    confidence = clamp_score(float(result.get("confidence", 0.5)) if isinstance(result.get("confidence"), (int, float)) else 0.5)
                    repair_plan = self._build_repair_plan(state, normalized_issues, normalized_suggestions, {
                        "task_completion": task_completion,
                        "correctness": correctness,
                        "process_efficiency": process_efficiency,
                        "expression": expression,
                        "risk": risk
                    })
                    
                    needs_retry = False
                    if overall_score < 0.6 and retry_count < MAX_RETRIES:
                        needs_retry = True
                    
                    new_reflection = {
                        "overall_score": float(overall_score),
                        "quality_score": float(overall_score),
                        "metrics": {
                            "task_completion": task_completion,
                            "correctness": correctness,
                            "process_efficiency": process_efficiency,
                            "expression": expression,
                            "risk": risk
                        },
                        "confidence": confidence,
                        "issues": normalized_issues,
                        "suggestions": normalized_suggestions,
                        "repair_plan": repair_plan,
                        "needs_retry": needs_retry,
                        "retry_count": int(retry_count + 1) if needs_retry else int(retry_count)
                    }
                    state["reflection"] = new_reflection
                    
                    score = new_reflection["overall_score"]
                    emoji = "🟢" if score >= 0.8 else "🟡" if score >= 0.6 else "🔴"
                    metrics_summary = f"达成:{task_completion:.2f} 正确:{correctness:.2f} 效率:{process_efficiency:.2f} 表达:{expression:.2f} 风险:{risk:.2f}"
                    issue_summary = "；".join(str(issue) for issue in new_reflection["issues"][:3]) or "无"
                    suggestion_summary = "；".join(str(suggestion) for suggestion in new_reflection["suggestions"][:3]) or "无"
                    repair_summary = ",".join(repair_plan.get("required_tools") or []) or "无"
                    observation = f"{metrics_summary} | 问题: {len(new_reflection['issues'])} | 详情: {issue_summary} | 建议: {suggestion_summary} | 修复工具: {repair_summary}"
                    
                    if needs_retry:
                        self._add_thought(
                            state,
                            "replan_agent",
                            "replan",
                            f"综合评分: {emoji} {score:.2f} - 需要重新规划 ({retry_count + 1}/{MAX_RETRIES})",
                            observation=observation
                        )
                    else:
                        self._add_thought(
                            state,
                            "replan_agent",
                            "replan",
                            f"综合评分: {emoji} {score:.2f} - 质量合格，无需重新规划",
                            observation=observation
                        )
                    
                    trace.update_retry(new_reflection["retry_count"])
                    trace.update_output(f"评估完成，综合评分: {score:.2f}, 需要重试: {needs_retry}")
                else:
                    state["reflection"] = {
                        "overall_score": 0.5,
                        "quality_score": 0.5,
                        "metrics": {
                            "task_completion": 0.5,
                            "correctness": 0.5,
                            "process_efficiency": 0.5,
                            "expression": 0.5,
                            "risk": 0.5
                        },
                        "confidence": 0.5,
                        "issues": [],
                        "suggestions": [],
                        "needs_retry": False,
                        "retry_count": int(retry_count)
                    }
                    trace.update_output("评估解析失败，使用默认评分")

            except Exception as e:
                app_logger.error(f"[REPLAN] 重新规划失败: {e}")
                state["reflection"] = {
                    "overall_score": 0.5,
                    "quality_score": 0.5,
                    "metrics": {
                        "task_completion": 0.5,
                        "correctness": 0.5,
                        "process_efficiency": 0.5,
                        "expression": 0.5,
                        "risk": 0.5
                    },
                    "confidence": 0.5,
                    "issues": [str(e)],
                    "suggestions": [],
                    "needs_retry": False,
                    "retry_count": int(retry_count)
                }
                trace.update_error(str(e))

            state["agents_involved"].append("replan_agent")
            state["current_phase"] = "done"

            self._add_thought(state, "replan_agent", "replan", "重新规划阶段完成", observation="完成")

            return self._sanitize_state(state)
    
    async def _request_result_confirmation(self, state: AgentState) -> None:
        """请求用户确认执行结果"""
        question = state.get("question", "")
        answer = state.get("answer", "")
        minutes = state.get("minutes", "")
        todos = state.get("todos", [])
        controversies = state.get("controversies", [])
        reflection = state.get("reflection", {})
        
        score = reflection.get("overall_score", 0.5)
        score_label = "优秀" if score >= 0.8 else "良好" if score >= 0.6 else "一般"
        
        result_summary = []
        if answer:
            result_summary.append(f"回答内容：{answer[:100]}..." if len(answer) > 100 else f"回答内容：{answer}")
        if minutes:
            result_summary.append(f"纪要内容：{minutes[:100]}..." if len(minutes) > 100 else f"纪要内容：{minutes}")
        if todos:
            result_summary.append(f"待办事项：共 {len(todos)} 项")
        if controversies:
            result_summary.append(f"争议点：共 {len(controversies)} 个")
        
        details = {
            "question": question,
            "answer": answer,
            "minutes": minutes,
            "todos": todos,
            "controversies": controversies,
            "reflection": reflection
        }
        
        confirmed = await self.hitl_service.request_confirmation(
            confirm_type=ConfirmationType.RESULT_REVIEW,
            title="执行结果确认",
            message=f"Agent 已完成任务，请确认结果是否满意：\n\n质量评分：{score:.2f} ({score_label})\n\n{chr(10).join(result_summary)}",
            details=details,
            event_callback=state.get("event_callback")
        )
        
        confirmation = {
            "request_id": self.hitl_service.get_request_history(limit=1)[0]["request_id"] if self.hitl_service.get_request_history() else "",
            "type": ConfirmationType.RESULT_REVIEW.value,
            "title": "执行结果确认",
            "message": f"质量评分: {score:.2f}",
            "status": "approved" if confirmed else "rejected",
            "user_response": "approved" if confirmed else "rejected",
            "timestamp": ""
        }
        
        if "human_confirmations" not in state:
            state["human_confirmations"] = []
        state["human_confirmations"].append(confirmation)
        
        if not confirmed:
            self._add_thought(state, "replan_agent", "replan", "用户不满意执行结果", action="用户反馈")
            app_logger.warning("[REPLAN] 用户不满意执行结果")

    # ==================== ReAct 推理引擎 ====================
    
    async def react_reasoning_node(self, state: AgentState) -> AgentState:
        """ReAct 推理节点 - 实现思考-行动-观察循环"""
        state = self._sanitize_state(state)
        app_logger.info("[REACT] 开始 ReAct 推理阶段...")
        self._add_thought(state, "react_agent", "react", "开始 ReAct 思考-行动-观察循环", action="ReAct推理")
        
        state["current_phase"] = "react"
        question = state.get("question", "")
        context = self._format_context(state)
        tools_info = self.tool_manager.selector.format_tools_for_prompt()
        
        # 初始化 ReAct 历史记录
        react_history = state.get("react_history", [])
        max_iterations = self.config.get("max_react_iterations", 5)
        iteration = 0
        app_logger.info(f"[REACT] 最大迭代次数: {max_iterations}")
        
        while iteration < max_iterations:
            iteration += 1
            self._add_thought(state, "react_agent", "react", f"ReAct 迭代 {iteration}/{max_iterations}", action="迭代")
            
            # 构建历史记录字符串
            history_str = json.dumps(react_history, ensure_ascii=False) if react_history else "[]"
            
            # 获取 ReAct prompt
            from app.agents.prompts import PromptManager
            prompt_manager = PromptManager()
            prompt = prompt_manager.render_prompt(
                "react_reasoning",
                tools_info=tools_info,
                question=question,
                context=context,
                history=history_str
            )
            
            messages = [{"role": "system", "content": "你是一个推理专家，使用 ReAct 框架进行思考和行动。"}, {"role": "user", "content": prompt}]

            try:
                # ReAct 节点由路由判定为 A 复杂度，恒走 max 档位
                from app.services.model_router import get_model_router
                _react_model = get_model_router().select_for_planning(ComplexityLevel.AGENT)
                response = await self.llm_service.chat(messages=messages, model=_react_model, temperature=0.5)
                success, result = self._parse_json_response(response, "ReAct 推理")
                
                if not success or not isinstance(result, dict):
                    self._add_thought(state, "react_agent", "react", "ReAct 解析失败，退出循环", action="解析失败")
                    break
                
                thought = result.get("thought", "")
                action = result.get("action", "")
                tool_name = result.get("tool_name", "")
                arguments = result.get("arguments", {})
                confidence = result.get("confidence", 0.5)
                
                self._add_thought(state, "react_agent", "react", f"思考: {thought[:100]}...", observation=f"行动: {action}")
                
                # 记录思考
                react_step = {
                    "iteration": iteration,
                    "thought": thought,
                    "action": action,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "confidence": confidence
                }
                
                if action == "finish":
                    # 直接回答
                    self._add_thought(state, "react_agent", "react", "决定直接回答用户问题", action="完成")
                    answer_prompt = f"基于以下思考，总结回答用户问题：\n\n思考过程：{thought}\n\n问题：{question}\n\n请给出最终回答："
                    answer_messages = [{"role": "user", "content": answer_prompt}]
                    # ReAct 最终回答阶段，沿用 max 档位
                    from app.services.model_router import get_model_router as _get_mr
                    _react_final_model = _get_mr().select_for_planning(ComplexityLevel.AGENT)
                    final_answer = await self.llm_service.chat(messages=answer_messages, model=_react_final_model, temperature=0.7)
                    state["answer"] = final_answer
                    react_step["observation"] = "直接生成回答"
                    react_step["final_answer"] = final_answer[:100]
                    react_history.append(react_step)
                    break
                
                elif action == "tool_call" and tool_name:
                    # 调用工具
                    self._add_thought(state, "react_agent", "react", f"调用工具: {tool_name}", action="工具调用")
                    
                    # 替换变量
                    arguments = self._substitute_variables(arguments, state)
                    arguments = self._prepare_tool_arguments(tool_name, arguments, state)
                    
                    tool_result: ToolExecutionResult = await self.tool_manager.execute_tool(tool_name, arguments)
                    
                    if tool_result.success:
                        observation = str(tool_result.result)[:200]
                        self._add_thought(state, "react_agent", "react", f"工具执行成功: {observation}", action="工具执行成功")
                        
                        # 更新上下文
                        self._apply_tool_result_to_state(state, tool_name, tool_result.result)
                        context = self._format_context(state)
                        
                        react_step["observation"] = observation
                        react_history.append(react_step)
                    else:
                        self._add_thought(state, "react_agent", "react", f"工具执行失败: {tool_result.error}", action="工具执行失败")
                        react_step["observation"] = f"工具失败: {tool_result.error}"
                        react_history.append(react_step)
                        # 重试或退出
                        if confidence < 0.5:
                            break
                
                elif action == "retry":
                    self._add_thought(state, "react_agent", "react", "决定重试", action="重试")
                    react_step["observation"] = "重试"
                    react_history.append(react_step)
                    continue
                
                else:
                    self._add_thought(state, "react_agent", "react", f"未知行动: {action}", action="未知行动")
                    break
            
            except Exception as e:
                app_logger.error(f"[REACT] 推理失败: {e}")
                self._add_thought(state, "react_agent", "react", f"推理异常: {str(e)}", action="错误")
                break
        
        state["react_history"] = react_history
        state["agents_involved"].append("react_agent")
        state["current_phase"] = "validate"
        # 供 fallback_strategy 使用：记录当前策略，以便条件边只读路由
        state["last_strategy"] = "react"
        state["fallback_count"] = state.get("fallback_count", 0)
        # 供 should_reflect_and_regenerate 使用
        state["last_executed_node"] = "react_node"

        self._add_thought(state, "react_agent", "react", f"ReAct 推理完成，共 {iteration} 次迭代", observation="进入验证阶段")

        return self._sanitize_state(state)
    
    async def cot_reasoning_node(self, state: AgentState) -> AgentState:
        """CoT 思维链推理节点 - 引导 LLM 进行详细的链式推理"""
        state = self._sanitize_state(state)
        app_logger.info("[COT] 开始 CoT 思维链推理...")
        self._add_thought(state, "cot_agent", "cot", "开始 CoT 思维链推理", action="CoT推理")
        
        state["current_phase"] = "cot"
        question = state.get("question", "")
        context = self._format_context(state)
        
        from app.agents.prompts import PromptManager
        prompt_manager = PromptManager()
        prompt = prompt_manager.render_prompt("cot_reasoning", question=question, context=context)
        
        messages = [{"role": "system", "content": "你是一个推理专家，擅长详细展示思考过程。"}, {"role": "user", "content": prompt}]

        try:
            # CoT 节点由路由判定为 C 复杂度，恒走 max 档位
            from app.services.model_router import get_model_router
            _cot_model = get_model_router().select_for_planning(ComplexityLevel.COT)
            response = await self.llm_service.chat(messages=messages, model=_cot_model, temperature=0.5)
            success, result = self._parse_json_response(response, "CoT 推理")
            
            if success and isinstance(result, dict):
                reasoning_steps = result.get("reasoning_steps", [])
                final_answer = result.get("final_answer", "")
                confidence = result.get("confidence", 0.5)
                key_factors = result.get("key_factors", [])
                
                # 记录推理步骤到思维链
                for i, step in enumerate(reasoning_steps, 1):
                    self._add_thought(state, "cot_agent", "cot", f"推理步骤 {i}: {step[:80]}", action=f"步骤{i}")
                
                # 设置回答
                if final_answer:
                    state["answer"] = final_answer
                
                # 保存推理信息
                state["cot_reasoning"] = {
                    "reasoning_steps": reasoning_steps,
                    "final_answer": final_answer,
                    "confidence": confidence,
                    "key_factors": key_factors
                }
                
                self._add_thought(state, "cot_agent", "cot", f"CoT 推理完成，置信度: {confidence:.2f}", observation=final_answer[:100])
            else:
                # 如果解析失败，使用默认问答
                self._add_thought(state, "cot_agent", "cot", "CoT 解析失败，回退到普通问答", action="回退")
                await self._execute_qa(state, self._direct_task(TaskType.QA), context)
        
        except Exception as e:
            app_logger.error(f"[COT] 推理失败: {e}")
            self._add_thought(state, "cot_agent", "cot", f"CoT 异常: {str(e)}", action="错误")
            await self._execute_qa(state, self._direct_task(TaskType.QA), context)
        
        state["agents_involved"].append("cot_agent")
        state["current_phase"] = "validate"
        # 供 fallback_strategy 使用：记录当前策略，以便条件边只读路由
        # 若上一策略是 react（即 cot 作为 fallback 执行），则 fallback_count 递增到 1
        prev_strategy = state.get("last_strategy")
        state["last_strategy"] = "cot"
        if prev_strategy == "react":
            state["fallback_count"] = 1
        else:
            state["fallback_count"] = state.get("fallback_count", 0)
        # 供 should_reflect_and_regenerate 使用
        state["last_executed_node"] = "cot_node"

        return self._sanitize_state(state)

    async def reflection_node(self, state: AgentState) -> AgentState:
        """反思节点 - 确定性错误检查 + LLM 深度评估 + 反思记忆持久化"""
        async with AgentTraceContext("reflection_node", "reflection") as trace:
            state = self._sanitize_state(state)
            app_logger.info("[REFLECTION] 开始反思评估阶段...")
            self._add_thought(state, "reflection_node", "reflection", "开始深度质量评估", action="质量评估")
            
            question = state.get("question", "")
            answer = state.get("answer", "")
            reference_context = self._format_context(state)
            
            if not answer:
                self._add_thought(state, "reflection_node", "reflection", "没有生成回答，跳过反思", action="跳过")
                state["reflection_evaluation"] = {
                    "confidence": 0.0,
                    "needs_regeneration": False,
                    "suggestions": []
                }
                state["current_phase"] = "validate"
                return self._sanitize_state(state)

            # === 确定性错误检查（FastRetry 快速路径）===
            from app.core.config import settings as _settings
            det_result = None
            if getattr(_settings, "ENABLE_DETERMINISTIC_CHECK", True):
                try:
                    from app.services.deterministic_error_checker import get_deterministic_error_checker
                    checker = get_deterministic_error_checker()
                    det_result = checker.check(
                        answer=answer,
                        source_context=reference_context,
                        minutes=state.get("minutes", ""),
                        todos=state.get("todos", []),
                        controversies=state.get("controversies", []),
                    )

                    if det_result.has_critical_error:
                        app_logger.warning(
                            f"[REFLECTION] 确定性硬错误: types={det_result.error_types}, "
                            f"errors={det_result.errors[:2]}"
                        )
                        self._add_thought(
                            state, "reflection_node", "reflection",
                            f"确定性检查发现硬错误: {det_result.errors[:2]}",
                            action="FastRetry",
                            observation=f"error_types={det_result.error_types}"
                        )
                        # 走 FastRetry 路径：跳过 LLM 评估，直接触发重生成
                        state["reflection_evaluation"] = {
                            "confidence": 0.3,
                            "needs_regeneration": True,
                            "suggestions": det_result.errors,
                            "deterministic_errors": det_result.errors,
                            "error_types": det_result.error_types,
                            "evaluation_method": "deterministic_fast_retry",
                        }
                        state["reflection_fast_retry"] = True
                        state["agents_involved"].append("reflection_node")
                        state["current_phase"] = "validate"

                        # 异步保存反思记忆
                        await self._save_reflection_memory(state, question, 0.3, det_result.error_types, det_result.errors)

                        trace.update_output(
                            f"确定性硬错误 → FastRetry: {det_result.error_types}"
                        )
                        return self._sanitize_state(state)
                    elif det_result.has_warning:
                        self._add_thought(
                            state, "reflection_node", "reflection",
                            f"确定性检查发现软警告: {det_result.warnings[:1]}",
                            action="确定性检查",
                        )
                except Exception as e:
                    app_logger.warning(f"[REFLECTION] 确定性检查异常（不影响主流程）: {e}")

            # === LLM 深度评估 ===
            from app.agents.reflection import get_reflection_system
            
            reflection_system = get_reflection_system()
            
            try:
                result = await reflection_system.reflect_and_replan(
                    input_text=question,
                    output_text=answer,
                    context=state,
                    tools_used=state.get("tools_used", []),
                    max_iterations=self.config.get("max_reflection_iterations", 2),
                    use_llm_evaluation=True,
                    reference_context=reference_context,
                )
                
                state["reflection_evaluation"] = {
                    "confidence": result.get("confidence", 0.5),
                    "needs_regeneration": result.get("iterations", 0) > 0,
                    "suggestions": result.get("suggestions", []),
                    "evaluation": result.get("evaluation", {}),
                    "iterations": result.get("iterations", 0),
                }
                
                if result.get("output") != answer:
                    state["answer"] = result.get("output", answer)
                    self._add_thought(
                        state,
                        "reflection_node",
                        "reflection",
                        f"反思优化成功，置信度从评估值提升",
                        action="答案优化",
                        observation=f"迭代次数: {result.get('iterations', 0)}"
                    )
                
                confidence = result.get("confidence", 0.5)
                emoji = "🟢" if confidence >= 0.7 else "🟡" if confidence >= 0.5 else "🔴"
                trace.update_output(f"反思评估完成 - 置信度: {emoji} {confidence:.2f}, 迭代次数: {result.get('iterations', 0)}")

                # === 异步保存反思记忆 ===
                error_types = []
                if det_result and det_result.has_warning:
                    error_types = det_result.error_types
                await self._save_reflection_memory(
                    state, question, confidence, error_types,
                    result.get("suggestions", [])
                )
                
            except Exception as e:
                app_logger.error(f"[REFLECTION] 反思评估失败: {e}")
                state["reflection_evaluation"] = {
                    "confidence": 0.5,
                    "needs_regeneration": False,
                    "suggestions": [],
                    "error": str(e),
                }
                trace.update_error(str(e))
            
            state["agents_involved"].append("reflection_node")
            state["current_phase"] = "validate"
            
            return self._sanitize_state(state)

    async def _save_reflection_memory(
        self,
        state: AgentState,
        question: str,
        quality_score: float,
        error_types: List[str],
        suggestions: List[str],
    ) -> None:
        """异步保存反思记忆（不阻塞主流程）"""
        from app.core.config import settings as _settings
        if not getattr(_settings, "ENABLE_REFLECTION_MEMORY", True):
            return

        try:
            from app.services.reflection_memory_service import get_reflection_memory_service
            service = get_reflection_memory_service()

            reflection = state.get("reflection") or {}
            retry_count = int(reflection.get("retry_count", 0)) if reflection else 0
            final_answer = state.get("answer", "")

            if getattr(_settings, "REFLECTION_MEMORY_ASYNC", True):
                # fire-and-forget 异步写入
                import asyncio
                asyncio.create_task(
                    service.save_reflection(
                        question=question,
                        quality_score=quality_score,
                        error_types=error_types,
                        suggestions=suggestions,
                        retry_count=retry_count,
                        final_answer=final_answer,
                    )
                )
            else:
                await service.save_reflection(
                    question=question,
                    quality_score=quality_score,
                    error_types=error_types,
                    suggestions=suggestions,
                    retry_count=retry_count,
                    final_answer=final_answer,
                )
        except Exception as e:
            app_logger.debug(f"[REFLECTION] 反思记忆保存失败（不影响主流程）: {e}")
