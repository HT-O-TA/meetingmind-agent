"""多Agent架构 - Planner → Retriever → Summarizer → Todo → Reviewer"""
import asyncio
import json
import re
from typing import Dict, List, Any, Optional, Callable
from enum import Enum
from datetime import datetime
from dataclasses import dataclass, field
from collections import deque
from app.core.logger import app_logger
from app.agents.state import TaskType, WorkflowType, ReasoningMode, AgentState, create_initial_state
from app.agents.prompt_market import get_prompt_market
from app.services.unified_memory_service import get_unified_memory
from app.services.knowledge_graph import enhance_search_results
from app.services.vector_search_service import get_vector_search_service


class AgentRole(str, Enum):
    """Agent角色"""
    PLANNER = "planner"
    RETRIEVER = "retriever"
    SUMMARIZER = "summarizer"
    TODO_EXTRACTOR = "todo_extractor"
    REVIEWER = "reviewer"
    COORDINATOR = "coordinator"


class MessageType(str, Enum):
    """消息类型"""
    TASK = "task"
    RESULT = "result"
    STATUS = "status"
    ERROR = "error"
    CONTINUE = "continue"
    STOP = "stop"


@dataclass
class AgentMessage:
    """Agent间消息"""
    message_id: str
    sender: AgentRole
    receiver: AgentRole
    message_type: MessageType
    content: Any
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "sender": self.sender.value,
            "receiver": self.receiver.value,
            "message_type": self.message_type.value,
            "content": self.content,
            "context": self.context,
            "timestamp": self.timestamp,
        }


@dataclass
class AgentTask:
    """Agent任务"""
    task_id: str
    type: str
    description: str
    input_data: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    status: str = "pending"
    result: Optional[Any] = None
    error: Optional[str] = None


class BaseAgent:
    """基础Agent类"""
    
    def __init__(self, role: AgentRole):
        self.role = role
        self._prompt_market = get_prompt_market()
        self._memory = get_unified_memory()
        self._message_queue = deque()
        self._is_running = False

    async def start(self):
        """启动Agent"""
        self._is_running = True
        app_logger.info(f"[Agent] 启动 {self.role.value} Agent")

    async def stop(self):
        """停止Agent"""
        self._is_running = False
        app_logger.info(f"[Agent] 停止 {self.role.value} Agent")

    def send_message(self, message: AgentMessage):
        """发送消息"""
        self._message_queue.append(message)
        app_logger.debug(f"[Agent] {self.role.value} 发送消息到 {message.receiver.value}")

    async def receive_message(self) -> Optional[AgentMessage]:
        """接收消息"""
        if self._message_queue:
            return self._message_queue.popleft()
        await asyncio.sleep(0.1)
        return None

    async def process(self, task: AgentTask) -> AgentTask:
        """处理任务（子类实现）"""
        raise NotImplementedError


class PlannerAgent(BaseAgent):
    """规划Agent - 分析需求并制定执行计划"""
    
    def __init__(self):
        super().__init__(AgentRole.PLANNER)

    async def process(self, task: AgentTask) -> AgentTask:
        """分析问题并制定执行计划"""
        app_logger.info(f"[Planner] 开始规划: {task.description}")
        
        question = task.input_data.get("question", "")
        meeting_id = task.input_data.get("meeting_id")
        document_ids = task.input_data.get("document_ids", [])

        context_prompt = await self._memory.generate_context_prompt(question)
        
        template = self._prompt_market.get_template("meeting_plan_v1")
        if template:
            plan_prompt = self._prompt_market.render_template(
                "meeting_plan_v1",
                meeting_topic=question,
                duration=60,
                participants=""
            )
        else:
            plan_prompt = f"请分析以下问题并制定执行计划：\n\n问题：{question}\n\n历史参考：\n{context_prompt}"

        plan = {
            "analysis": f"分析问题：{question}",
            "tasks": [
                {
                    "task_id": "retrieve",
                    "type": "retrieve",
                    "description": "检索相关文档和历史会议",
                    "input": {"question": question, "meeting_id": meeting_id, "document_ids": document_ids}
                },
                {
                    "task_id": "summarize",
                    "type": "summarize",
                    "description": "生成会议纪要",
                    "input": {"question": question},
                    "depends_on": ["retrieve"]
                },
                {
                    "task_id": "extract_todos",
                    "type": "extract_todos",
                    "description": "提取待办事项",
                    "input": {"question": question},
                    "depends_on": ["summarize"]
                },
                {
                    "task_id": "review",
                    "type": "review",
                    "description": "审查结果质量",
                    "input": {},
                    "depends_on": ["extract_todos"]
                }
            ],
            "execution_order": ["retrieve", "summarize", "extract_todos", "review"],
            "context_prompt": context_prompt
        }

        task.result = plan
        task.status = "completed"
        app_logger.info(f"[Planner] 规划完成，生成 {len(plan['tasks'])} 个任务")
        
        return task


class RetrieverAgent(BaseAgent):
    """检索Agent - 获取相关文档和历史信息"""
    
    def __init__(self):
        super().__init__(AgentRole.RETRIEVER)

    async def _get_vector_search(self):
        return await get_vector_search_service()

    async def process(self, task: AgentTask) -> AgentTask:
        """检索相关文档"""
        app_logger.info(f"[Retriever] 开始检索: {task.description}")
        
        question = task.input_data.get("question", "")
        
        vector_results = []
        try:
            vs = await self._get_vector_search()
            vector_results = await vs.search_by_text(question, top_k=5)
        except Exception as e:
            app_logger.warning(f"[Retriever] 向量检索失败: {e}")

        enhanced_results = await enhance_search_results(question, vector_results, depth=2)

        historical_memories = await self._memory.find_relevant_memories(question)

        task.result = {
            "vector_results": vector_results,
            "enhanced_results": enhanced_results,
            "historical_memories": historical_memories,
            "context": [r.get("content", "") for r in vector_results]
        }
        task.status = "completed"
        app_logger.info(f"[Retriever] 检索完成，找到 {len(enhanced_results)} 条结果")
        
        return task


class SummarizerAgent(BaseAgent):
    """总结Agent - 生成会议纪要"""
    
    def __init__(self):
        super().__init__(AgentRole.SUMMARIZER)

    async def process(self, task: AgentTask) -> AgentTask:
        """生成会议纪要"""
        app_logger.info(f"[Summarizer] 开始总结: {task.description}")
        
        question = task.input_data.get("question", "")
        context = task.input_data.get("context", "")
        context_prompt = task.input_data.get("context_prompt", "")

        template = self._prompt_market.get_template("meeting_summary_v1")
        if template:
            summary = self._prompt_market.render_template(
                "meeting_summary_v1",
                meeting_topic=question,
                meeting_time=datetime.now().isoformat(),
                participants="",
                meeting_content=context,
                max_length=1000
            )
        else:
            summary = f"会议纪要：{question}\n\n{context}"

        if context_prompt:
            summary = f"{context_prompt}\n\n{summary}"

        task.result = {
            "summary": summary,
            "meeting_topic": question
        }
        task.status = "completed"
        app_logger.info(f"[Summarizer] 总结完成")
        
        return task


class TodoExtractorAgent(BaseAgent):
    """待办提取Agent - 从会议中提取待办事项"""
    
    def __init__(self):
        super().__init__(AgentRole.TODO_EXTRACTOR)

    async def process(self, task: AgentTask) -> AgentTask:
        """提取待办事项"""
        app_logger.info(f"[TodoExtractor] 开始提取待办: {task.description}")
        
        question = task.input_data.get("question", "")
        summary = task.input_data.get("summary", "")
        content = summary or question

        template = self._prompt_market.get_template("action_item_v1")
        if template:
            todos_text = self._prompt_market.render_template(
                "action_item_v1",
                meeting_content=content
            )
        else:
            todos_text = content

        todos = await self._parse_todos_from_content(content)

        task.result = {
            "todos": todos,
            "todos_text": todos_text
        }
        task.status = "completed"
        app_logger.info(f"[TodoExtractor] 待办提取完成，共 {len(todos)} 条")
        
        return task

    async def _parse_todos_from_content(self, content: str) -> List[Dict[str, Any]]:
        """从内容中解析待办事项"""
        if not content:
            return []
        
        todos = []
        import re
        
        patterns = [
            r'待办[：:]\s*(.*?)(?=\n|$)',
            r'行动项[：:]\s*(.*?)(?=\n|$)',
            r'任务[：:]\s*(.*?)(?=\n|$)',
            r'- (.*?负责.*?)\n',
            r'负责(.*?)\n',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, content, re.DOTALL)
            for match in matches:
                match = match.strip()
                if match and len(match) > 2:
                    assignee = self._extract_assignee(match)
                    todos.append({
                        "content": match,
                        "assignee": assignee,
                        "deadline": None
                    })
        
        unique_todos = []
        seen = set()
        for todo in todos:
            key = todo["content"]
            if key not in seen:
                seen.add(key)
                unique_todos.append(todo)
        
        return unique_todos[:10]

    def _extract_assignee(self, text: str) -> Optional[str]:
        """从文本中提取负责人"""
        patterns = [
            r'(负责|分配给|交给)\s*(\w+)',
            r'(\w+)\s*负责',
            r'(\w+)\s*的任务',
            r'(\w+)\s*做',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(2) if len(match.groups()) > 1 else match.group(1)
        return None


class ReviewerAgent(BaseAgent):
    """审查Agent - 审查结果质量"""
    
    def __init__(self):
        super().__init__(AgentRole.REVIEWER)

    async def process(self, task: AgentTask) -> AgentTask:
        """审查结果质量"""
        app_logger.info(f"[Reviewer] 开始审查: {task.description}")
        
        summary = task.input_data.get("summary", "")
        todos = task.input_data.get("todos", [])

        issues = []
        suggestions = []
        overall_score = 0.85

        if len(summary) < 50:
            issues.append("会议纪要内容过短")
            suggestions.append("建议增加更多细节")
            overall_score -= 0.1

        if not todos:
            issues.append("未提取待办事项")
            suggestions.append("建议从会议内容中提取待办")
            overall_score -= 0.15

        task.result = {
            "overall_score": max(0, overall_score),
            "issues": issues,
            "suggestions": suggestions,
            "needs_retry": len(issues) > 1,
            "review_details": {
                "summary_length": len(summary),
                "todos_count": len(todos),
                "completeness": "complete" if len(todos) >= 1 else "partial"
            }
        }
        task.status = "completed"
        app_logger.info(f"[Reviewer] 审查完成，评分: {overall_score}")
        
        return task


class CoordinatorAgent(BaseAgent):
    """协调Agent - 任务分发与结果汇总"""
    
    def __init__(self):
        super().__init__(AgentRole.COORDINATOR)
        self._agents: Dict[AgentRole, BaseAgent] = {}
        self._task_results: Dict[str, Any] = {}

    def register_agent(self, agent: BaseAgent):
        """注册Agent"""
        self._agents[agent.role] = agent
        app_logger.info(f"[Coordinator] 注册Agent: {agent.role.value}")

    async def start_all(self):
        """启动所有Agent"""
        await asyncio.gather(*[agent.start() for agent in self._agents.values()])

    async def stop_all(self):
        """停止所有Agent"""
        await asyncio.gather(*[agent.stop() for agent in self._agents.values()])

    async def run_workflow(self, question: str, meeting_id: Optional[str] = None, document_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        """运行多Agent工作流"""
        app_logger.info(f"[Coordinator] 开始多Agent工作流: {question}")
        
        self._task_results.clear()

        planner = self._agents.get(AgentRole.PLANNER)
        if not planner:
            return {"error": "Planner Agent 未注册"}

        plan_task = AgentTask(
            task_id="plan",
            type="plan",
            description=f"规划任务: {question}",
            input_data={"question": question, "meeting_id": meeting_id, "document_ids": document_ids}
        )
        plan_result = await planner.process(plan_task)
        plan = plan_result.result

        self._task_results["plan"] = plan

        for step_id in plan.get("execution_order", []):
            step_def = next((t for t in plan.get("tasks", []) if t["task_id"] == step_id), None)
            if not step_def:
                continue

            dependencies = step_def.get("depends_on", [])
            for dep in dependencies:
                if dep not in self._task_results:
                    app_logger.warning(f"[Coordinator] 依赖任务 {dep} 未完成，跳过 {step_id}")
                    continue

            input_data = step_def.get("input", {}).copy()
            for dep in dependencies:
                if dep in self._task_results:
                    input_data[dep + "_result"] = self._task_results[dep]

            if step_id == "retrieve":
                retriever = self._agents.get(AgentRole.RETRIEVER)
                if retriever:
                    task = AgentTask(task_id=step_id, type=step_def["type"], description=step_def["description"], input_data=input_data)
                    result = await retriever.process(task)
                    self._task_results[step_id] = result.result
                    input_data["context"] = result.result.get("context", "")
                    input_data["context_prompt"] = plan.get("context_prompt", "")

            elif step_id == "summarize":
                summarizer = self._agents.get(AgentRole.SUMMARIZER)
                if summarizer:
                    task = AgentTask(task_id=step_id, type=step_def["type"], description=step_def["description"], input_data=input_data)
                    result = await summarizer.process(task)
                    self._task_results[step_id] = result.result
                    input_data["summary"] = result.result.get("summary", "")

            elif step_id == "extract_todos":
                todo_extractor = self._agents.get(AgentRole.TODO_EXTRACTOR)
                if todo_extractor:
                    task = AgentTask(task_id=step_id, type=step_def["type"], description=step_def["description"], input_data=input_data)
                    result = await todo_extractor.process(task)
                    self._task_results[step_id] = result.result
                    input_data["todos"] = result.result.get("todos", [])

            elif step_id == "review":
                reviewer = self._agents.get(AgentRole.REVIEWER)
                if reviewer:
                    task = AgentTask(task_id=step_id, type=step_def["type"], description=step_def["description"], input_data=input_data)
                    result = await reviewer.process(task)
                    self._task_results[step_id] = result.result

        final_result = {
            "success": True,
            "question": question,
            "plan": self._task_results.get("plan"),
            "summary": self._task_results.get("summarize", {}).get("summary"),
            "todos": self._task_results.get("extract_todos", {}).get("todos"),
            "review": self._task_results.get("review"),
            "retrieval": self._task_results.get("retrieve"),
            "agents_involved": list(self._agents.keys()),
            "completed_steps": list(self._task_results.keys())
        }

        app_logger.info(f"[Coordinator] 多Agent工作流完成")
        return final_result


def create_multi_agent_system() -> CoordinatorAgent:
    """创建多Agent系统"""
    coordinator = CoordinatorAgent()
    
    coordinator.register_agent(PlannerAgent())
    coordinator.register_agent(RetrieverAgent())
    coordinator.register_agent(SummarizerAgent())
    coordinator.register_agent(TodoExtractorAgent())
    coordinator.register_agent(ReviewerAgent())
    
    return coordinator