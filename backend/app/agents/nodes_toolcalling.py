"""Agent 节点定义 - Tool Calling 版本"""
import json
import re
from typing import Dict, List, Optional, Tuple, Any
from app.agents.state import AgentState, AgentResult, TaskType, AgentCard, CoTThought, Plan, TaskItem, TaskContext, TaskStatus
from app.agents.tools import ToolExecutor, ToolExecutionResult, ToolManager
from app.services.llm_service import LLMService
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
        "capabilities": ["任务执行", "工具调用", "上下文传递", "依赖管理"],
        "required_inputs": ["plan", "context"],
        "outputs": ["answer", "minutes", "todos", "controversies", "tool_results"],
        "dependencies": {"plan_agent"}
    }
    
    REFLECT_AGENT_CARD: AgentCard = {
        "agent_id": "reflect_agent",
        "name": "反思 Agent",
        "description": "评估执行结果质量",
        "capabilities": ["质量评估", "缺陷检测", "改进建议"],
        "required_inputs": ["question", "answer", "minutes", "todos", "controversies"],
        "outputs": ["reflection"],
        "dependencies": {"execute_agent"}
    }

    @classmethod
    def get_card(cls, agent_id: str) -> Optional[AgentCard]:
        cards = {
            "plan_agent": cls.PLAN_AGENT_CARD,
            "execute_agent": cls.EXECUTE_AGENT_CARD,
            "reflect_agent": cls.REFLECT_AGENT_CARD,
        }
        return cards.get(agent_id)


class ToolCallingNodes:
    """支持 Tool Calling 的 Agent 节点"""

    def __init__(
        self,
        llm_service: LLMService,
        tool_manager: ToolManager,
        max_retries: int = 2
    ):
        self.llm_service = llm_service
        self.tool_manager = tool_manager
        self.max_retries = max_retries

    def _add_thought(
        self,
        state: AgentState,
        agent_id: str,
        phase: str,
        thought: str,
        action: Optional[str] = None,
        observation: Optional[str] = None
    ):
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

    def _format_context(self, state: AgentState) -> str:
        contexts = state.get("raw_context", [])
        if not contexts:
            contexts = state.get("context", [])
            contexts = [c.get("content", "") if isinstance(c, dict) else str(c) for c in contexts]
        return "\n\n".join(contexts) if contexts else ""

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

    async def plan_agent(self, state: AgentState) -> AgentState:
        """规划 Agent - 支持 Tool Calling 决策"""
        app_logger.info("[PLAN] 开始规划阶段（Tool Calling）...")
        self._add_thought(state, "plan_agent", "plan", "开始分析问题，制定执行计划", action="问题分析")

        question = state["question"]
        context = self._format_context(state)
        tools_info = self.tool_manager.selector.format_tools_for_prompt()

        prompt = f"""你是一个任务规划专家，同时负责决定使用哪些工具。

{tools_info}

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
    "execution_order": ["task_1", ...]
}}"""

        messages = [
            {"role": "system", "content": "你是专业的任务规划专家，负责决定使用哪些工具。"},
            {"role": "user", "content": prompt}
        ]

        try:
            response = await self.llm_service.chat(messages=messages, temperature=0.3)
            self._add_thought(state, "plan_agent", "plan", f"LLM 生成计划...", observation=response[:500])

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

        except Exception as e:
            app_logger.error(f"[PLAN] 规划失败: {e}")
            self._add_thought(state, "plan_agent", "plan", f"规划失败: {str(e)}", action="错误处理")
            state["error"] = str(e)
            state["current_phase"] = "execute"

        return state

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
        app_logger.info("[EXECUTE] 开始执行阶段（Tool Calling）...")
        self._add_thought(state, "execute_agent", "execute", "开始执行计划，调用工具", action="工具执行")

        state["current_phase"] = "execute"
        plan = state.get("plan")

        if not plan:
            state = await self._execute_default_task(state)
        else:
            # 执行工具调用
            tool_calls = plan.get("tool_calls", [])
            if tool_calls:
                await self._execute_tool_calls(state, tool_calls)

            # 执行任务
            tasks = {t["task_id"]: t for t in plan.get("tasks", [])}
            parallel_groups = plan.get("parallel_groups", [])
            
            if parallel_groups:
                await self._execute_with_parallel(state, tasks, parallel_groups)
            else:
                await self._execute_sequential(state, tasks, plan.get("execution_order", []))

        state["agents_involved"].append("execute_agent")
        self._add_thought(state, "execute_agent", "execute", "所有任务执行完成", observation="进入反思阶段")
        state["current_phase"] = "reflect"

        return state

    async def _execute_tool_calls(self, state: AgentState, tool_calls: List[Dict[str, Any]]):
        """执行工具调用"""
        self._add_thought(state, "execute_agent", "execute", f"开始执行 {len(tool_calls)} 个工具调用", action="工具调用")

        for tc in tool_calls:
            tool_name = tc.get("tool_name")
            arguments = tc.get("arguments", {})

            # 替换变量
            arguments = self._substitute_variables(arguments, state)

            self._add_thought(state, "execute_agent", "execute", f"调用工具: {tool_name}", action=tool_name)

            result: ToolExecutionResult = await self.tool_manager.executor.execute(tool_name, arguments)

            if result.success:
                self._add_thought(state, "execute_agent", "execute", f"工具 {tool_name} 执行成功", observation=str(result.result)[:200])
                
                # 存储工具结果到上下文
                state["task_contexts"][tool_name] = TaskContext(
                    task_id=tool_name,
                    data=result.result,
                    metadata={"execution_time": result.execution_time}
                )
            else:
                self._add_thought(state, "execute_agent", "execute", f"工具 {tool_name} 执行失败: {result.error}", observation="错误")

    def _substitute_variables(self, arguments: Dict[str, Any], state: AgentState) -> Dict[str, Any]:
        """替换变量"""
        substituted = {}
        for key, value in arguments.items():
            if isinstance(value, str):
                # 替换 {{question}}
                if "{{question}}" in value:
                    value = value.replace("{{question}}", state.get("question", ""))
                # 替换 {{context}}
                if "{{context}}" in value:
                    value = value.replace("{{context}}", self._format_context(state))
            substituted[key] = value
        return substituted

    async def _execute_with_parallel(self, state: AgentState, tasks: Dict, parallel_groups: List[List[str]]):
        """按并行分组执行任务 - 确保所有任务都被执行"""
        # 收集所有在并行分组中的任务ID
        parallel_task_ids = set()
        for group in parallel_groups:
            parallel_task_ids.update(group)
        
        # 找出不在并行分组中的任务（需要顺序执行的任务）
        sequential_tasks = [t for t in tasks.values() if t["task_id"] not in parallel_task_ids]
        
        # 先执行所有不在并行分组中的任务
        if sequential_tasks:
            for task in sequential_tasks:
                if task.get("status") == "pending":
                    await self._execute_single_task(state, task, tasks)
        
        # 然后执行并行分组中的任务
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
            tool_result = state["task_contexts"].get(task.get("tool_to_use", ""))
            if tool_result:
                task["result"] = tool_result.get("data")
                task["status"] = "completed"
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

    async def _execute_qa(self, state: AgentState, task: TaskItem, context: str) -> str:
        self._add_thought(state, "execute_agent", "execute", f"[{task['task_id']}] 执行问答", action="生成回答")
        
        # 使用工具调用结果
        tool_result = state["task_contexts"].get("answer_question")
        if tool_result:
            state["answer"] = tool_result.get("data", "")
            return state["answer"]

        prompt = f"请回答问题：{state['question']}\n\n上下文：{context}"
        messages = [{"role": "user", "content": prompt}]
        answer = await self.llm_service.chat(messages=messages, temperature=0.7)
        state["answer"] = answer
        state["agents_involved"].append("execute_agent")
        return answer

    async def _execute_minutes(self, state: AgentState, task: TaskItem, context: str) -> str:
        self._add_thought(state, "execute_agent", "execute", f"[{task['task_id']}] 生成纪要", action="生成纪要")
        
        # 使用工具调用结果
        tool_result = state["task_contexts"].get("generate_minutes")
        if tool_result:
            state["minutes"] = tool_result.get("data", "")
            return state["minutes"]

        prompt = f"请生成会议纪要：\n{context}"
        messages = [{"role": "user", "content": prompt}]
        minutes = await self.llm_service.chat(messages=messages, temperature=0.7)
        state["minutes"] = minutes
        state["agents_involved"].append("execute_agent")
        return minutes

    async def _execute_todos(self, state: AgentState, task: TaskItem, context: str) -> str:
        self._add_thought(state, "execute_agent", "execute", f"[{task['task_id']}] 抽取待办", action="抽取待办")
        
        # 使用工具调用结果
        tool_result = state["task_contexts"].get("extract_todos")
        if tool_result:
            state["todos"] = tool_result.get("data", [])
            return json.dumps(state["todos"], ensure_ascii=False)

        prompt = f"请从以下内容中抽取待办事项：\n{context}"
        messages = [{"role": "user", "content": prompt}]
        
        for attempt in range(self.max_retries):
            try:
                response = await self.llm_service.chat(messages=messages, temperature=0.3)
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
        
        # 使用工具调用结果
        tool_result = state["task_contexts"].get("detect_controversies")
        if tool_result:
            state["controversies"] = tool_result.get("data", [])
            return json.dumps(state["controversies"], ensure_ascii=False)

        prompt = f"请从以下内容中识别争议点：\n{context}"
        messages = [{"role": "user", "content": prompt}]
        
        for attempt in range(self.max_retries):
            try:
                response = await self.llm_service.chat(messages=messages, temperature=0.3)
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

        # 执行工具调用
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

    async def reflect_agent(self, state: AgentState) -> AgentState:
        """反思 Agent"""
        app_logger.info("[REFLECT] 开始反思阶段...")
        self._add_thought(state, "reflect_agent", "reflect", "开始评估执行结果质量", action="质量评估")

        question = state["question"]
        answer = state.get("answer") or ""
        minutes = state.get("minutes") or ""
        todos = state.get("todos") or []
        controversies = state.get("controversies") or []

        prompt = f"""请评估 Agent 执行结果的质量：

用户问题：{question}

执行结果：
- 回答：{answer[:500] if answer else '无'}
- 纪要：{minutes[:500] if minutes else '无'}
- 待办：{len(todos)} 个
- 争议点：{len(controversies)} 个

请输出 JSON：
{{
    "quality_score": 0.8,
    "issues": ["问题列表"],
    "suggestions": ["改进建议"],
    "needs_retry": false
}}"""

        messages = [{"role": "user", "content": prompt}]

        try:
            response = await self.llm_service.chat(messages=messages, temperature=0.3)
            success, result = self._parse_json_response(response, "反思结果")

            if success and isinstance(result, dict):
                issues = result.get("issues")
                suggestions = result.get("suggestions")
                reflection = {
                    "quality_score": result.get("quality_score", 0.5) or 0.5,
                    "issues": issues if issues is not None else [],
                    "suggestions": suggestions if suggestions is not None else [],
                    "needs_retry": result.get("needs_retry", False) or False,
                    "retry_count": 0
                }
                state["reflection"] = reflection
                
                score = reflection["quality_score"]
                emoji = "🟢" if score >= 0.8 else "🟡" if score >= 0.6 else "🔴"
                self._add_thought(state, "reflect_agent", "reflect", f"质量评分: {emoji} {score:.2f}", observation=f"问题: {len(reflection['issues'])}")
            else:
                state["reflection"] = {"quality_score": 0.5, "issues": [], "suggestions": [], "needs_retry": False, "retry_count": 0}

        except Exception as e:
            app_logger.error(f"[REFLECT] 反思失败: {e}")
            state["reflection"] = {"quality_score": 0.5, "issues": [str(e)], "suggestions": [], "needs_retry": False, "retry_count": 0}

        state["agents_involved"].append("reflect_agent")
        state["current_phase"] = "done"
        self._add_thought(state, "reflect_agent", "reflect", "反思阶段完成", observation="完成")

        return state