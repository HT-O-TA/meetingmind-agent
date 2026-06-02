"""Agent 节点定义 - 支持复杂任务拆分（依赖分析 + 上下文传递 + 并行执行）"""
import json
import re
import asyncio
from typing import Dict, List, Optional, Tuple, Any, Set
from app.agents.state import AgentState, TaskType, AgentCard, CoTThought, Plan, TaskItem, TaskContext, TaskStatus, HumanConfirmation, ConfirmationStatus
from app.agents.human_in_the_loop import get_hitl_service, ConfirmationType
from app.services.llm_service import LLMService
from app.core.logger import app_logger


class AgentCards:
    """Agent 名片注册中心"""
    
    PLAN_AGENT_CARD: AgentCard = {
        "agent_id": "plan_agent",
        "name": "规划 Agent",
        "description": "分析问题，制定复杂任务计划（支持依赖分析、并行分组）",
        "capabilities": ["问题分析", "任务拆解", "依赖分析", "并行规划"],
        "required_inputs": ["question", "context"],
        "outputs": ["plan"],
        "dependencies": set()
    }
    
    EXECUTE_AGENT_CARD: AgentCard = {
        "agent_id": "execute_agent",
        "name": "执行 Agent",
        "description": "执行任务计划，支持并行执行和上下文传递",
        "capabilities": ["任务执行", "并行处理", "上下文传递", "依赖管理"],
        "required_inputs": ["plan", "context"],
        "outputs": ["answer", "minutes", "todos", "controversies"],
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


class AgentNodes:
    """Agent 节点集合 - 复杂任务拆分"""

    def __init__(self, llm_service: LLMService, vector_search_service=None):
        self.llm_service = llm_service
        self.vector_search_service = vector_search_service
        self.max_retries = 2
        self.hitl_service = get_hitl_service()

    def _add_thought(self, state: AgentState, agent_id: str, phase: str, thought: str, action: Optional[str] = None, observation: Optional[str] = None):
        # 步骤号从 state 推导，避免实例变量在并发时产生竞争
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
        
        # 触发事件回调
        event_callback = state.get("event_callback")
        if event_callback:
            import asyncio
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
            # 保留来源信息的格式化
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
            return "\n\n".join(formatted_contexts) if formatted_contexts else ""
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

    # =========================================================================
    # Plan Agent - 复杂任务拆分（集成模板库 + 规划验证）
    # =========================================================================
    async def plan_agent(self, state: AgentState) -> AgentState:
        """规划 Agent - 支持模板匹配 + LLM规划 + 计划验证"""
        app_logger.info("[PLAN] 开始规划阶段（模板匹配 + 智能拆分）...")
        self._add_thought(state, "plan_agent", "plan", "开始分析问题，制定任务计划", action="问题分析")

        question = state["question"]
        context = self._format_context(state)

        try:
            # 1. 尝试使用模板库匹配
            from app.agents.task_templates import get_task_template_library
            template_library = get_task_template_library()
            
            matched_template = template_library.find_best_match(question)
            
            if matched_template:
                app_logger.info(f"[PLAN] 匹配到模板: {matched_template.name}")
                self._add_thought(state, "plan_agent", "plan", f"匹配到任务模板: {matched_template.name}", 
                                action="模板匹配")
                
                # 使用模板生成计划
                tasks = matched_template.generate_tasks(context={"question": question})
                plan: Plan = {
                    "analysis": f"根据{matched_template.name}模板生成计划：{matched_template.description}",
                    "tasks": tasks,
                    "execution_order": [t["task_id"] for t in tasks],
                    "parallel_groups": self._generate_parallel_groups_from_tasks(tasks),
                    "template_id": matched_template.template_id,
                }
                
                # 验证计划
                is_valid, issues = self._validate_plan(plan)
                if not is_valid:
                    app_logger.warning(f"[PLAN] 模板计划验证失败，尝试LLM规划")
                    self._add_thought(state, "plan_agent", "plan", "模板计划验证失败，切换到LLM规划", action="回退")
                    plan = None
                else:
                    state["plan"] = plan
                    state["task_contexts"] = {}
                    state["current_phase"] = "execute"
                    
                    # 确定任务类型
                    if len(tasks) > 1:
                        state["task_type"] = TaskType.MULTI
                    else:
                        state["task_type"] = TaskType.QA
                    
                    self._log_plan(state)
                    state["agents_involved"].append("plan_agent")
                    self._add_thought(state, "plan_agent", "plan", f"计划制定完成，共 {len(tasks)} 个任务（来自模板）", 
                                    observation="进入执行阶段")
                    
                    # 人机协作：请求用户确认计划
                    if state.get("enable_human_in_the_loop", False):
                        await self._request_plan_confirmation(state)
                    
                    return state
            
            # 2. 如果没有匹配的模板，使用LLM生成计划
            plan = await self._generate_llm_plan(question, context)
            
            if plan:
                # 验证并修复计划
                is_valid, issues = self._validate_plan(plan)
                if not is_valid:
                    app_logger.warning(f"[PLAN] LLM计划验证失败，尝试自动修复")
                    plan = self._fix_plan(plan)
                
                state["plan"] = plan
                state["task_contexts"] = {}
                
                # 确定任务类型
                tasks = plan.get("tasks", [])
                if len(tasks) > 1:
                    state["task_type"] = TaskType.MULTI
                elif tasks:
                    task_type_map = {
                        "retrieve": "retrieve", "检索": "retrieve",
                        "qa": "qa", "问答": "qa",
                        "minutes": "minutes", "纪要": "minutes",
                        "todo": "todo", "待办": "todo",
                        "controversy": "controversy", "争议": "controversy",
                        "combine": "combine", "整合": "combine",
                        "multi": "multi",
                    }
                    first_task = tasks[0].get("task_type", "qa")
                    state["task_type"] = TaskType(task_type_map.get(first_task, "qa"))
                
                self._log_plan(state)
                
                # 人机协作：请求用户确认计划
                if state.get("enable_human_in_the_loop", False):
                    await self._request_plan_confirmation(state)
                
                state["current_phase"] = "execute"
            else:
                # 计划生成失败，使用默认计划
                plan = self._create_default_plan()
                state["plan"] = plan
                state["task_contexts"] = {}
                state["current_phase"] = "execute"
                state["task_type"] = TaskType.QA

            state["agents_involved"].append("plan_agent")
            self._add_thought(state, "plan_agent", "plan", f"计划制定完成，共 {len(state['plan']['tasks'])} 个任务", 
                            observation="进入执行阶段")

        except Exception as e:
            app_logger.error(f"[PLAN] 规划失败: {e}")
            self._add_thought(state, "plan_agent", "plan", f"规划失败: {str(e)}", action="错误处理")
            state["error"] = str(e)
            state["current_phase"] = "execute"
            # 使用默认计划
            plan = self._create_default_plan()
            state["plan"] = plan
            state["task_type"] = TaskType.QA

        return state
    
    async def _generate_llm_plan(self, question: str, context: str) -> Optional[Plan]:
        """使用LLM生成执行计划"""
        prompt = f"""你是一个专业的任务规划专家。请分析以下问题并制定详细的执行计划。

【重要】你的规划需要支持：
1. 依赖分析：识别任务间的依赖关系
2. 并行规划：识别可以同时执行的任务
3. 上下文传递：一个任务的输出可能作为另一个任务的输入

请按照以下步骤分析：

步骤 1：理解问题
- 用户的核心需求是什么？
- 需要完成哪些类型的任务？

步骤 2：任务拆解
- 将问题拆解为具体的可执行任务
- 每个任务需要有明确的目标

步骤 3：依赖分析
- 哪些任务有先后顺序依赖？
- 哪些任务可以并行执行？

步骤 4：上下文传递规划
- 哪些任务需要依赖其他任务的输出？
- 如何组织任务间的数据流？

用户问题：{question}

会议上下文：
{context[:2000] if context else '（无上下文）'}

请输出你的完整分析过程，然后用 JSON 格式输出执行计划：
{{
    "analysis": "问题分析和规划思路",
    "tasks": [
        {{
            "task_id": "task_1",
            "task_type": "retrieve/qa/minutes/todo/controversy/combine",
            "description": "任务描述",
            "priority": 1,
            "status": "pending",
            "dependencies": [],  // 依赖的任务ID列表
            "can_parallel_with": ["task_2"],  // 可以并行执行的任务ID
            "input_from": null,  // 从哪个任务获取输入，null表示使用原始上下文
            "output_key": "retrieved_context"  // 输出数据的键名
        }}
    ],
    "execution_order": ["task_1", "task_2", ...],
    "parallel_groups": [["task_1", "task_2"], ["task_3"]]  // 可并行执行的任务分组
}}"""

        messages = [
            {"role": "system", "content": "你是专业的任务规划专家，支持依赖分析、并行规划和上下文传递。"},
            {"role": "user", "content": prompt}
        ]

        try:
            response = await self.llm_service.chat(messages=messages, temperature=0.3)
            self._add_thought(self._get_state_for_logging(), "plan_agent", "plan", "LLM 生成计划...")

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

                return {
                    "analysis": result.get("analysis", ""),
                    "tasks": tasks,
                    "execution_order": result.get("execution_order", []),
                    "parallel_groups": result.get("parallel_groups", [])
                }
        except Exception as e:
            app_logger.error(f"[PLAN] LLM规划失败: {e}")
        
        return None
    
    def _validate_plan(self, plan: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]]]:
        """验证执行计划"""
        from app.agents.plan_validator import get_plan_validator
        validator = get_plan_validator()
        
        is_valid, issues = validator.validate(plan, {"has_context": True})
        
        # 记录验证问题
        for issue in issues:
            if issue.severity == "error":
                app_logger.error(f"[PLAN] 验证错误: {issue.message}")
            elif issue.severity == "warning":
                app_logger.warning(f"[PLAN] 验证警告: {issue.message}")
        
        return is_valid, [vars(i) for i in issues]
    
    def _fix_plan(self, plan: Dict[str, Any]) -> Plan:
        """自动修复计划问题"""
        from app.agents.plan_validator import get_plan_validator
        validator = get_plan_validator()
        
        fixed_plan = validator.fix_common_issues(plan)
        app_logger.info("[PLAN] 计划已自动修复")
        
        return fixed_plan
    
    async def _request_plan_confirmation(self, state: AgentState) -> None:
        """请求用户确认执行计划"""
        plan = state.get("plan", {})
        tasks = plan.get("tasks", [])
        
        task_list = "\n".join([f"- [{t['task_id']}] {t['task_type']}: {t['description']}" for t in tasks])
        
        details = {
            "plan_analysis": plan.get("analysis", ""),
            "tasks": tasks,
            "execution_order": plan.get("execution_order", []),
            "parallel_groups": plan.get("parallel_groups", []),
            "question": state.get("question", "")
        }
        
        confirmed = await self.hitl_service.request_confirmation(
            confirm_type=ConfirmationType.PLAN_APPROVAL,
            title="执行计划确认",
            message=f"Agent 已制定执行计划，请确认是否执行：\n\n{task_list}",
            details=details,
            event_callback=state.get("event_callback")
        )
        
        # 记录确认结果到状态
        confirmation: HumanConfirmation = {
            "request_id": self.hitl_service.get_request_history(limit=1)[0]["request_id"] if self.hitl_service.get_request_history() else "",
            "type": ConfirmationType.PLAN_APPROVAL.value,
            "title": "执行计划确认",
            "message": f"计划包含 {len(tasks)} 个任务",
            "status": ConfirmationStatus.APPROVED if confirmed else ConfirmationStatus.REJECTED,
            "user_response": "approved" if confirmed else "rejected",
            "timestamp": ""
        }
        
        if "human_confirmations" not in state:
            state["human_confirmations"] = []
        state["human_confirmations"].append(confirmation)
        
        if not confirmed:
            self._add_thought(state, "plan_agent", "plan", "用户拒绝执行计划", action="用户取消")
            app_logger.warning("[PLAN] 用户拒绝执行计划")
    
    def _generate_parallel_groups_from_tasks(self, tasks: List[Dict[str, Any]]) -> List[List[str]]:
        """从任务列表生成并行分组"""
        if not tasks:
            return []
        
        groups = []
        processed = set()
        
        # 首先添加没有依赖的任务
        no_dep_tasks = [
            task.get("task_id") 
            for task in tasks 
            if not task.get("dependencies") or task.get("dependencies") == [None]
        ]
        
        if no_dep_tasks:
            groups.append(no_dep_tasks)
            processed.update(no_dep_tasks)
        
        # 然后添加可以并行的任务
        for task in tasks:
            task_id = task.get("task_id")
            if task_id in processed:
                continue
            
            can_parallel = task.get("can_parallel_with", [])
            if can_parallel:
                parallel_group = [task_id]
                for dep_id in can_parallel:
                    if dep_id not in processed:
                        parallel_group.append(dep_id)
                        processed.add(dep_id)
                
                if len(parallel_group) > 1:
                    groups.append(parallel_group)
                processed.add(task_id)
        
        # 最后添加剩下的任务
        remaining = [task.get("task_id") for task in tasks if task.get("task_id") not in processed]
        for task_id in remaining:
            groups.append([task_id])
        
        return groups
    
    def _get_state_for_logging(self) -> AgentState:
        """获取用于记录日志的state（避免传递self.state的问题）"""
        return {}

    def _create_default_plan(self) -> Plan:
        """创建默认计划"""
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
                "result": None,
                "error": None
            }],
            "execution_order": ["default_qa"],
            "parallel_groups": [["default_qa"]]
        }

    def _log_plan(self, state: AgentState):
        """打印计划详情"""
        plan = state.get("plan", {})
        app_logger.info("=" * 60)
        app_logger.info("📋 执行计划")
        app_logger.info("=" * 60)
        app_logger.info(f"分析: {plan.get('analysis', '')}")
        app_logger.info(f"任务数: {len(plan.get('tasks', []))}")
        
        for task in plan.get("tasks", []):
            deps = ", ".join(task.get("dependencies", []) or [])
            parallel = ", ".join(task.get("can_parallel_with", []) or [])
            app_logger.info(f"  [{task['task_id']}] {task['task_type']} - {task['description']}")
            if deps:
                app_logger.info(f"      依赖: {deps}")
            if parallel:
                app_logger.info(f"      可并行: {parallel}")
        
        groups = plan.get("parallel_groups", [])
        if groups:
            app_logger.info(f"并行分组: {groups}")
        app_logger.info("=" * 60)

    # =========================================================================
    # Execute Agent - 支持并行执行和上下文传递
    # =========================================================================
    async def execute_agent(self, state: AgentState) -> AgentState:
        """执行 Agent - 支持并行执行和上下文传递"""
        app_logger.info("[EXECUTE] 开始执行阶段（复杂任务）...")
        self._add_thought(state, "execute_agent", "execute", "开始执行计划", action="任务执行")

        state["current_phase"] = "execute"
        plan = state.get("plan")

        if not plan:
            app_logger.warning("[EXECUTE] 无执行计划，使用默认执行")
            state = await self._execute_default_task(state)
        else:
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

    async def _execute_with_parallel(self, state: AgentState, tasks: Dict, parallel_groups: List[List[str]]):
        """按并行分组执行任务 - 确保所有任务都被执行"""
        # 收集所有在并行分组中的任务ID
        parallel_task_ids = set()
        for group in parallel_groups:
            parallel_task_ids.update(group)
        
        # 找出不在并行分组中的任务（需要顺序执行的任务）
        sequential_tasks = [t for t in tasks.values() if t["task_id"] not in parallel_task_ids]
        
        # 先执行所有不在并行分组中的任务（按依赖顺序）
        if sequential_tasks:
            self._add_thought(state, "execute_agent", "execute", f"开始顺序执行前置任务: {[t['task_id'] for t in sequential_tasks]}", action="顺序执行")
            for task in sequential_tasks:
                if task.get("status") == "pending":
                    await self._execute_single_task(state, task, tasks)
            self._add_thought(state, "execute_agent", "execute", "顺序任务执行完成", observation=f"完成 {len(sequential_tasks)} 个任务")
        
        # 然后执行并行分组中的任务
        for group_idx, group in enumerate(parallel_groups):
            group_name = f"Group-{group_idx + 1}"
            self._add_thought(state, "execute_agent", "execute", f"开始执行并行组 {group_name}: {group}", action="并行执行")

            ready_tasks = [t for t in group if t in tasks and tasks[t].get("status") == "pending"]
            
            if len(ready_tasks) == 1:
                await self._execute_single_task(state, tasks[ready_tasks[0]], tasks)
            elif len(ready_tasks) > 1:
                await self._execute_parallel_group(state, ready_tasks, tasks)
            
            self._add_thought(state, "execute_agent", "execute", f"并行组 {group_name} 执行完成", observation=f"完成 {len(ready_tasks)} 个任务")

    async def _execute_parallel_group(self, state: AgentState, task_ids: List[str], tasks: Dict):
        """并行执行一组任务 - 各任务结果写入独立的 task_contexts，避免共享字段竞争"""
        self._add_thought(state, "execute_agent", "execute", f"并发执行 {len(task_ids)} 个任务: {task_ids}", action="并发执行")

        async def execute_task_wrapper(task_id: str):
            task = tasks[task_id]
            task_type = task.get("task_type", "qa")
            task["status"] = "in_progress"
            try:
                input_context = self._get_task_input(state, task, tasks)
                if task_type in ["retrieve", "检索"]:
                    result = await self._execute_retrieve(state, task, input_context)
                elif task_type in ["qa", "问答"]:
                    result = await self._execute_qa_isolated(state, task, input_context)
                elif task_type in ["minutes", "纪要"]:
                    result = await self._execute_minutes_isolated(state, task, input_context)
                elif task_type in ["todo", "待办"]:
                    result = await self._execute_todos_isolated(state, task, input_context)
                elif task_type in ["controversy", "争议"]:
                    result = await self._execute_controversies_isolated(state, task, input_context)
                else:
                    result = await self._execute_qa_isolated(state, task, input_context)
                task["result"] = result
                task["status"] = "completed"
                output_key = task.get("output_key") or task_id
                state["task_contexts"][output_key] = TaskContext(
                    task_id=task_id,
                    data=result,
                    metadata={"task_type": task_type}
                )
            except Exception as e:
                app_logger.error(f"[EXECUTE] 任务 {task_id} 执行异常: {e}")
                task["status"] = "failed"
                task["error"] = str(e)

        await asyncio.gather(*[execute_task_wrapper(tid) for tid in task_ids], return_exceptions=False)

        # 并行完成后，将各任务结果合并到 state 顶层字段
        for task_id in task_ids:
            task = tasks.get(task_id, {})
            task_type = task.get("task_type", "")
            result = task.get("result")
            if result is None:
                continue
            if task_type in ["qa", "问答"] and not state.get("answer"):
                state["answer"] = result
            elif task_type in ["combine", "整合"] and not state.get("answer"):
                state["answer"] = result
            elif task_type in ["minutes", "纪要"] and not state.get("minutes"):
                state["minutes"] = result
            elif task_type in ["todo", "待办"] and not state.get("todos"):
                try:
                    import json as _json
                    state["todos"] = _json.loads(result) if isinstance(result, str) else result
                except Exception:
                    pass
            elif task_type in ["controversy", "争议"] and not state.get("controversies"):
                try:
                    import json as _json
                    state["controversies"] = _json.loads(result) if isinstance(result, str) else result
                except Exception:
                    pass

    async def _execute_sequential(self, state: AgentState, tasks: Dict, execution_order: List[str]):
        """顺序执行任务"""
        for task_id in execution_order:
            if task_id not in tasks:
                continue
            task = tasks[task_id]
            await self._execute_single_task(state, task, tasks)

    async def _execute_single_task(self, state: AgentState, task: TaskItem, all_tasks: Dict) -> AgentState:
        """执行单个任务"""
        task_id = task["task_id"]
        task_type = task.get("task_type", "qa")
        
        task["status"] = "in_progress"
        self._add_thought(state, "execute_agent", "execute", f"执行任务: [{task_id}] {task_type}", action=task_type)

        try:
            input_context = self._get_task_input(state, task, all_tasks)

            if task_type in ["retrieve", "检索"]:
                result = await self._execute_retrieve(state, task, input_context)
            elif task_type in ["qa", "问答"]:
                result = await self._execute_qa(state, task, input_context)
            elif task_type in ["minutes", "纪要"]:
                result = await self._execute_minutes(state, task, input_context)
            elif task_type in ["todo", "待办"]:
                result = await self._execute_todos(state, task, input_context)
            elif task_type in ["controversy", "争议"]:
                result = await self._execute_controversies(state, task, input_context)
            elif task_type in ["combine", "整合"]:
                result = await self._execute_combine(state, task)
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
        """获取任务的输入上下文（支持上下文传递）"""
        input_from = task.get("input_from")
        
        if input_from and input_from in state.get("task_contexts", {}):
            context_data = state["task_contexts"][input_from]
            self._add_thought(state, "execute_agent", "execute", f"从 [{input_from}] 获取输入", observation="上下文传递")
            if isinstance(context_data.get("data"), str):
                return context_data["data"]
            return json.dumps(context_data.get("data", ""), ensure_ascii=False)
        
        return self._format_context(state)

    async def _execute_retrieve(self, state: AgentState, task: TaskItem, context: str) -> str:
        """执行检索任务"""
        self._add_thought(state, "execute_agent", "execute", f"[{task['task_id']}] 执行检索任务", action="检索")
        
        # 首先检查 state 中是否已有上下文
        if state.get("raw_context") or state.get("context"):
            ctx_count = len(state.get("raw_context", [])) or len(state.get("context", []))
            return f"已检索相关上下文，共 {ctx_count} 个相关片段"
        
        # 尝试从任务描述中提取文档ID
        task_desc = task.get("description", "")
        doc_ids = []
        
        # 从 state 中获取 document_ids
        doc_ids_from_state = state.get("document_ids", [])
        if doc_ids_from_state:
            doc_ids.extend(doc_ids_from_state)
        
        # 从任务描述中匹配文档ID
        import re
        id_matches = re.findall(r"(?:文档|document|id).*?(\d+)", task_desc, re.IGNORECASE)
        doc_ids.extend([int(id) for id in id_matches if id.isdigit()])
        
        # 去重
        doc_ids = list(set(doc_ids))
        
        if doc_ids and self.vector_search_service:
            all_chunks = []
            for doc_id in doc_ids:
                try:
                    chunks = await self.vector_search_service.get_document_chunks(doc_id)
                    all_chunks.extend(chunks)
                except Exception as e:
                    app_logger.warning(f"获取文档 {doc_id} 内容失败: {e}")
            
            if all_chunks:
                chunk_texts = [chunk.get("chunk_text", "") for chunk in all_chunks]
                self._add_thought(state, "execute_agent", "execute", f"获取到 {len(all_chunks)} 个文档片段")
                return "\n\n".join(chunk_texts)
        
        # 如果没有找到文档ID，就用原来的上下文
        return self._format_context(state)

    async def _execute_qa(self, state: AgentState, task: TaskItem, context: str) -> str:
        """执行问答任务"""
        self._add_thought(state, "qa_sub_agent", "execute", f"[{task['task_id']}] 执行问答", action="生成回答")

        prompt = f"""请按照思考步骤回答问题：

思考步骤：
1. 理解用户的问题
2. 从上下文中寻找相关信息
3. 组织语言给出回答，并在回答中标注引用来源

【重要】引用来源标注规则：
- 每个事实性陈述都必须标注引用来源
- 引用格式为：[文档ID:chunk_index]
- 如果引用了多个来源，用逗号分隔：[文档1:0, 文档2:3]
- 来源信息已在上下文中标注，例如：[文档1:0] 这是内容...

问题：{state['question']}

上下文：
{context}

请输出你的思考过程，然后给出最终回答。回答中必须包含来源引用标注。"""

        messages = [
            {"role": "system", "content": "你是专业的问答助手，必须在回答中标注引用来源。"},
            {"role": "user", "content": prompt}
        ]

        answer = await self.llm_service.chat(messages=messages, temperature=0.7)
        state["answer"] = answer
        state["agents_involved"].append("qa_sub_agent")
        return answer

    async def _execute_minutes(self, state: AgentState, task: TaskItem, context: str) -> str:
        """执行纪要生成任务"""
        self._add_thought(state, "minutes_sub_agent", "execute", f"[{task['task_id']}] 生成纪要", action="生成纪要")

        prompt = f"""请生成会议纪要：

会议内容：
{context}

请输出结构化的会议纪要。"""

        messages = [
            {"role": "system", "content": "你是专业的会议纪要生成助手。"},
            {"role": "user", "content": prompt}
        ]

        minutes = await self.llm_service.chat(messages=messages, temperature=0.7)
        state["minutes"] = minutes
        state["agents_involved"].append("minutes_sub_agent")
        return minutes

    async def _execute_todos(self, state: AgentState, task: TaskItem, context: str) -> str:
        """执行待办抽取任务"""
        self._add_thought(state, "todo_sub_agent", "execute", f"[{task['task_id']}] 抽取待办", action="抽取待办")

        prompt = f"""请从会议内容中抽取待办事项：

会议内容：
{context}

请输出JSON格式的待办事项列表。"""

        messages = [
            {"role": "system", "content": "你是专业的待办抽取助手，只输出JSON格式。"},
            {"role": "user", "content": prompt}
        ]

        for attempt in range(self.max_retries + 1):
            try:
                response = await self.llm_service.chat(messages=messages, temperature=0.3)
                success, todos = self._parse_json_response(response, "待办事项")

                if success and isinstance(todos, list):
                    state["todos"] = todos
                    state["agents_involved"].append("todo_sub_agent")
                    self._add_thought(state, "todo_sub_agent", "execute", f"抽取到 {len(todos)} 个待办", observation=str(len(todos)))
                    return json.dumps(todos, ensure_ascii=False)

                if attempt < self.max_retries:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": "请只输出JSON数组格式。"})

            except Exception as e:
                app_logger.error(f"[TODO] 第 {attempt + 1} 次失败: {e}")

        state["todos"] = []
        return "[]"

    async def _execute_controversies(self, state: AgentState, task: TaskItem, context: str) -> str:
        """执行争议点识别任务"""
        self._add_thought(state, "controversy_sub_agent", "execute", f"[{task['task_id']}] 识别争议", action="识别争议")

        prompt = f"""请从会议内容中识别争议点：

会议内容：
{context}

请输出JSON格式的争议点列表。"""

        messages = [
            {"role": "system", "content": "你是专业的争议点识别助手，只输出JSON格式。"},
            {"role": "user", "content": prompt}
        ]

        for attempt in range(self.max_retries + 1):
            try:
                response = await self.llm_service.chat(messages=messages, temperature=0.3)
                success, controversies = self._parse_json_response(response, "争议点")

                if success and isinstance(controversies, list):
                    state["controversies"] = controversies
                    state["agents_involved"].append("controversy_sub_agent")
                    self._add_thought(state, "controversy_sub_agent", "execute", f"识别到 {len(controversies)} 个争议点", observation=str(len(controversies)))
                    return json.dumps(controversies, ensure_ascii=False)

                if attempt < self.max_retries:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": "请只输出JSON数组格式。"})

            except Exception as e:
                app_logger.error(f"[CONTROVERSY] 第 {attempt + 1} 次失败: {e}")

        state["controversies"] = []
        return "[]"

    async def _execute_combine(self, state: AgentState, task: TaskItem) -> str:
        """执行整合任务"""
        self._add_thought(state, "execute_agent", "execute", f"[{task['task_id']}] 整合结果", action="整合")

        contexts = state.get("task_contexts", {})
        combine_prompt = f"""请整合以下任务结果，生成统一的输出：

任务结果：
{json.dumps(contexts, ensure_ascii=False, indent=2)}

用户问题：{state['question']}

请输出整合后的结果。"""

        messages = [
            {"role": "system", "content": "你是专业的整合助手。"},
            {"role": "user", "content": combine_prompt}
        ]

        combined = await self.llm_service.chat(messages=messages, temperature=0.7)
        self._add_thought(state, "execute_agent", "execute", "结果整合完成", observation=f"整合了 {len(contexts)} 个任务的输出")
        return combined

    # 隔离版本：并行执行时只返回结果，不直接写 state 顶层字段
    async def _execute_qa_isolated(self, state: AgentState, task: TaskItem, context: str) -> str:
        prompt = f"""请按照思考步骤回答问题：

思考步骤：
1. 理解用户的问题
2. 从上下文中寻找相关信息
3. 组织语言给出回答，并在回答中标注引用来源

【重要】引用来源标注规则：
- 每个事实性陈述都必须标注引用来源
- 引用格式为：[文档ID:chunk_index]
- 如果引用了多个来源，用逗号分隔：[文档1:0, 文档2:3]

问题：{state['question']}

上下文：
{context}

请给出回答，回答中必须包含来源引用标注。"""
        messages = [{"role": "system", "content": "你是专业的问答助手，必须在回答中标注引用来源。"}, {"role": "user", "content": prompt}]
        return await self.llm_service.chat(messages=messages, temperature=0.7)

    async def _execute_minutes_isolated(self, state: AgentState, task: TaskItem, context: str) -> str:
        prompt = f"请生成会议纪要：\n\n会议内容：\n{context}\n\n请输出结构化的会议纪要。"
        messages = [{"role": "system", "content": "你是专业的会议纪要生成助手。"}, {"role": "user", "content": prompt}]
        return await self.llm_service.chat(messages=messages, temperature=0.7)

    async def _execute_todos_isolated(self, state: AgentState, task: TaskItem, context: str) -> str:
        prompt = f"请从会议内容中抽取待办事项：\n\n会议内容：\n{context}\n\n请输出JSON格式的待办事项列表。"
        messages = [{"role": "system", "content": "你是专业的待办抽取助手，只输出JSON格式。"}, {"role": "user", "content": prompt}]
        for attempt in range(self.max_retries + 1):
            try:
                response = await self.llm_service.chat(messages=messages, temperature=0.3)
                success, todos = self._parse_json_response(response, "待办事项")
                if success and isinstance(todos, list):
                    return json.dumps(todos, ensure_ascii=False)
                if attempt < self.max_retries:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": "请只输出JSON数组格式。"})
            except Exception as e:
                app_logger.error(f"[TODO-ISO] 第 {attempt + 1} 次失败: {e}")
        return "[]"

    async def _execute_controversies_isolated(self, state: AgentState, task: TaskItem, context: str) -> str:
        prompt = f"请从会议内容中识别争议点：\n\n会议内容：\n{context}\n\n请输出JSON格式的争议点列表。"
        messages = [{"role": "system", "content": "你是专业的争议点识别助手，只输出JSON格式。"}, {"role": "user", "content": prompt}]
        for attempt in range(self.max_retries + 1):
            try:
                response = await self.llm_service.chat(messages=messages, temperature=0.3)
                success, controversies = self._parse_json_response(response, "争议点")
                if success and isinstance(controversies, list):
                    return json.dumps(controversies, ensure_ascii=False)
                if attempt < self.max_retries:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": "请只输出JSON数组格式。"})
            except Exception as e:
                app_logger.error(f"[CONTROVERSY-ISO] 第 {attempt + 1} 次失败: {e}")
        return "[]"

    async def _execute_default_task(self, state: AgentState) -> AgentState:
        task_type = state.get("task_type", TaskType.QA)
        
        default_plan = self._create_default_plan()
        state["plan"] = default_plan
        state["task_contexts"] = {}
        
        if task_type == TaskType.MINUTES:
            await self._execute_minutes(state, default_plan["tasks"][0], self._format_context(state))
        elif task_type == TaskType.TODO:
            await self._execute_todos(state, default_plan["tasks"][0], self._format_context(state))
        elif task_type == TaskType.CONTROVERSY:
            await self._execute_controversies(state, default_plan["tasks"][0], self._format_context(state))
        else:
            await self._execute_qa(state, default_plan["tasks"][0], self._format_context(state))
        
        return state

    # =========================================================================
    # Reflect Agent
    # =========================================================================
    async def reflect_agent(self, state: AgentState) -> AgentState:
        """反思 Agent - 评估执行结果质量"""
        app_logger.info("[REFLECT] 开始反思阶段...")
        self._add_thought(state, "reflect_agent", "reflect", "开始评估执行结果质量", action="质量评估")

        question = state["question"]
        answer = state.get("answer") or ""
        minutes = state.get("minutes") or ""
        todos = state.get("todos") or []
        controversies = state.get("controversies") or []

        prompt = f"""你是质量评估专家。请评估 Agent 执行结果的质量：

用户问题：{question}

执行结果：
- 回答：{answer[:500] if answer else '无'}
- 纪要：{minutes[:500] if minutes else '无'}
- 待办：{len(todos)} 个
- 争议点：{len(controversies)} 个

请评估：
1. 完整性：结果是否回答了用户的问题？
2. 准确性：结果是否与上下文一致？
3. 质量评分：给出 0-1 的质量分数

输出 JSON：
{{
    "quality_score": 0.8,
    "issues": ["问题列表"],
    "suggestions": ["改进建议"],
    "needs_retry": false,
    "retry_count": 0
}}"""

        messages = [
            {"role": "system", "content": "你是专业的质量评估专家。"},
            {"role": "user", "content": prompt}
        ]

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
                    "retry_count": result.get("retry_count", 0) or 0
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
        
        # 人机协作：请求用户确认结果
        if state.get("enable_human_in_the_loop", False):
            await self._request_result_confirmation(state)
        
        self._add_thought(state, "reflect_agent", "reflect", "反思阶段完成", observation="完成")

        return state
    
    async def _request_result_confirmation(self, state: AgentState) -> None:
        """请求用户确认执行结果"""
        question = state.get("question", "")
        answer = state.get("answer", "")
        minutes = state.get("minutes", "")
        todos = state.get("todos", [])
        controversies = state.get("controversies", [])
        reflection = state.get("reflection", {})
        
        score = reflection.get("quality_score", 0.5)
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
        
        confirmation: HumanConfirmation = {
            "request_id": self.hitl_service.get_request_history(limit=1)[0]["request_id"] if self.hitl_service.get_request_history() else "",
            "type": ConfirmationType.RESULT_REVIEW.value,
            "title": "执行结果确认",
            "message": f"质量评分: {score:.2f}",
            "status": ConfirmationStatus.APPROVED if confirmed else ConfirmationStatus.REJECTED,
            "user_response": "approved" if confirmed else "rejected",
            "timestamp": ""
        }
        
        if "human_confirmations" not in state:
            state["human_confirmations"] = []
        state["human_confirmations"].append(confirmation)
        
        if not confirmed:
            self._add_thought(state, "reflect_agent", "reflect", "用户不满意执行结果", action="用户反馈")
            app_logger.warning("[REFLECT] 用户不满意执行结果")