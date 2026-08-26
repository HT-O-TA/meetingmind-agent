"""企业工作流引擎 - 支持会议→审批→任务→提醒→跟踪全流程"""
import asyncio
import json
from typing import Dict, List, Any, Optional, Callable, Tuple
from enum import Enum
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import deque
from app.core.logger import app_logger
from app.agents.human_in_the_loop import get_hitl_service, ConfirmationType, ConfirmationStatus
from app.agents.prompt_market import get_prompt_market, TemplateCategory
from app.agents.tools.enterprise_tools import (
    get_feishu_client, get_jira_client, get_email_client, execute_feishu_tool, execute_jira_tool, execute_email_tool
)


class WorkflowStatus(str, Enum):
    """工作流状态"""
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStepType(str, Enum):
    """工作流步骤类型"""
    MEETING_SUMMARY = "meeting_summary"
    APPROVAL = "approval"
    TASK_CREATION = "task_creation"
    NOTIFICATION = "notification"
    FOLLOW_UP = "follow_up"
    STATUS_UPDATE = "status_update"


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    """任务优先级"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class WorkflowTask:
    """工作流任务"""
    task_id: str
    title: str
    description: str
    assignee: str
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    due_date: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    external_id: Optional[str] = None
    external_system: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "assignee": self.assignee,
            "priority": self.priority.value,
            "status": self.status.value,
            "due_date": self.due_date,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "external_id": self.external_id,
            "external_system": self.external_system,
        }


@dataclass
class WorkflowStep:
    """工作流步骤"""
    step_id: str
    type: WorkflowStepType
    title: str
    status: WorkflowStatus = WorkflowStatus.CREATED
    assignee: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "type": self.type.value,
            "title": self.title,
            "status": self.status.value,
            "assignee": self.assignee,
            "data": self.data,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


@dataclass
class WorkflowInstance:
    """工作流实例"""
    workflow_id: str
    name: str
    type: str
    status: WorkflowStatus = WorkflowStatus.CREATED
    steps: List[WorkflowStep] = field(default_factory=list)
    tasks: List[WorkflowTask] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    creator: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "type": self.type,
            "status": self.status.value,
            "steps": [step.to_dict() for step in self.steps],
            "tasks": [task.to_dict() for task in self.tasks],
            "context": self.context,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "creator": self.creator,
        }


class ApprovalRequest:
    """审批请求"""
    def __init__(
        self,
        approval_id: str,
        workflow_id: str,
        step_id: str,
        title: str,
        description: str,
        approver: str,
        details: Dict[str, Any] = None
    ):
        self.approval_id = approval_id
        self.workflow_id = workflow_id
        self.step_id = step_id
        self.title = title
        self.description = description
        self.approver = approver
        self.details = details or {}
        self.status = ConfirmationStatus.PENDING
        self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
        self.comments: List[Dict[str, Any]] = []
        self.history: List[Dict[str, Any]] = []
        self.level = 1
        self.total_levels = 1

    def add_comment(self, comment: str, user: str):
        """添加审批意见"""
        self.comments.append({
            "comment": comment,
            "user": user,
            "timestamp": datetime.now().isoformat()
        })
        self.updated_at = datetime.now().isoformat()

    def add_history(self, action: str, user: str, details: Dict[str, Any] = None):
        """添加审批历史记录"""
        self.history.append({
            "action": action,
            "user": user,
            "timestamp": datetime.now().isoformat(),
            "details": details or {}
        })
        self.updated_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "workflow_id": self.workflow_id,
            "step_id": self.step_id,
            "title": self.title,
            "description": self.description,
            "approver": self.approver,
            "details": self.details,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "comments": self.comments,
            "history": self.history,
            "level": self.level,
            "total_levels": self.total_levels,
        }


class WorkflowEngine:
    """工作流引擎"""

    def __init__(self):
        self._workflows: Dict[str, WorkflowInstance] = {}
        self._tasks: Dict[str, WorkflowTask] = {}
        self._approvals: Dict[str, ApprovalRequest] = {}
        self._follow_up_queue: deque = deque()
        self._next_workflow_id = 0
        self._next_task_id = 0
        self._next_step_id = 0
        self._hitl_service = get_hitl_service()
        self._prompt_market = get_prompt_market()
        self._workflow_templates: Dict[str, Dict[str, Any]] = {}
        self._load_default_templates()

    def _load_default_templates(self):
        """加载默认工作流模板"""
        self._workflow_templates = {
            "meeting_to_task": {
                "name": "会议转任务",
                "description": "会议纪要生成→审批→任务创建→通知→跟进",
                "steps": [
                    {"type": "meeting_summary", "title": "生成会议纪要"},
                    {"type": "approval", "title": "Leader审批"},
                    {"type": "task_creation", "title": "创建任务"},
                    {"type": "notification", "title": "发送通知"},
                    {"type": "follow_up", "title": "设置跟进提醒"},
                ],
                "approval_levels": 1,
            },
            "meeting_to_task_multi_level": {
                "name": "会议转任务（多级审批）",
                "description": "会议纪要生成→部门审批→总监审批→任务创建→通知→跟进",
                "steps": [
                    {"type": "meeting_summary", "title": "生成会议纪要"},
                    {"type": "approval", "title": "部门审批"},
                    {"type": "approval", "title": "总监审批"},
                    {"type": "task_creation", "title": "创建任务"},
                    {"type": "notification", "title": "发送通知"},
                    {"type": "follow_up", "title": "设置跟进提醒"},
                ],
                "approval_levels": 2,
            },
            "simple_task": {
                "name": "简单任务",
                "description": "直接创建任务→通知→跟进",
                "steps": [
                    {"type": "task_creation", "title": "创建任务"},
                    {"type": "notification", "title": "发送通知"},
                    {"type": "follow_up", "title": "设置跟进提醒"},
                ],
                "approval_levels": 0,
            },
        }

    def _generate_workflow_id(self) -> str:
        self._next_workflow_id += 1
        return f"wf_{self._next_workflow_id}_{int(datetime.now().timestamp())}"

    def _generate_task_id(self) -> str:
        self._next_task_id += 1
        return f"task_{self._next_task_id}_{int(datetime.now().timestamp())}"

    def _generate_step_id(self) -> str:
        self._next_step_id += 1
        return f"step_{self._next_step_id}"

    def create_workflow(
        self,
        name: str,
        type: str,
        context: Optional[Dict[str, Any]] = None,
        creator: Optional[str] = None
    ) -> WorkflowInstance:
        """创建工作流实例"""
        workflow_id = self._generate_workflow_id()
        instance = WorkflowInstance(
            workflow_id=workflow_id,
            name=name,
            type=type,
            context=context or {},
            creator=creator
        )
        self._workflows[workflow_id] = instance
        app_logger.info(f"[Workflow] 创建工作流: {workflow_id} - {name}")
        return instance

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowInstance]:
        """获取工作流实例"""
        return self._workflows.get(workflow_id)

    def get_all_workflows(self) -> List[WorkflowInstance]:
        """获取所有工作流"""
        return list(self._workflows.values())

    def get_workflows_by_status(self, status: WorkflowStatus) -> List[WorkflowInstance]:
        """按状态获取工作流"""
        return [w for w in self._workflows.values() if w.status == status]

    async def start_workflow(self, workflow_id: str) -> bool:
        """启动工作流"""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return False

        if workflow.status != WorkflowStatus.CREATED:
            app_logger.warning(f"[Workflow] 工作流状态不允许启动: {workflow_id}")
            return False

        workflow.status = WorkflowStatus.IN_PROGRESS
        workflow.started_at = datetime.now().isoformat()
        workflow.updated_at = datetime.now().isoformat()

        app_logger.info(f"[Workflow] 启动工作流: {workflow_id}")

        await self._execute_next_step(workflow)
        return True

    async def _execute_next_step(self, workflow: WorkflowInstance):
        """执行下一步"""
        current_step_index = len(workflow.steps)

        if workflow.type == "meeting_to_task":
            step_map = [
                (WorkflowStepType.MEETING_SUMMARY, "生成会议纪要"),
                (WorkflowStepType.APPROVAL, "Leader审批"),
                (WorkflowStepType.TASK_CREATION, "创建任务"),
                (WorkflowStepType.NOTIFICATION, "发送通知"),
                (WorkflowStepType.FOLLOW_UP, "设置跟进提醒"),
            ]

            if current_step_index >= len(step_map):
                workflow.status = WorkflowStatus.COMPLETED
                workflow.completed_at = datetime.now().isoformat()
                app_logger.info(f"[Workflow] 工作流完成: {workflow.workflow_id}")
                return

            step_type, step_title = step_map[current_step_index]
            step = WorkflowStep(
                step_id=self._generate_step_id(),
                type=step_type,
                title=step_title,
                status=WorkflowStatus.IN_PROGRESS
            )
            workflow.steps.append(step)

            if step_type == WorkflowStepType.MEETING_SUMMARY:
                await self._execute_meeting_summary(workflow, step)
            elif step_type == WorkflowStepType.APPROVAL:
                await self._execute_approval(workflow, step)
            elif step_type == WorkflowStepType.TASK_CREATION:
                await self._execute_task_creation(workflow, step)
            elif step_type == WorkflowStepType.NOTIFICATION:
                await self._execute_notification(workflow, step)
            elif step_type == WorkflowStepType.FOLLOW_UP:
                await self._execute_follow_up(workflow, step)

    async def _execute_meeting_summary(self, workflow: WorkflowInstance, step: WorkflowStep):
        """执行会议纪要生成"""
        app_logger.info(f"[Workflow] 执行会议纪要生成: {step.step_id}")

        meeting_content = workflow.context.get("meeting_content", "")
        meeting_topic = workflow.context.get("meeting_topic", "未命名会议")
        participants = workflow.context.get("participants", [])

        template = self._prompt_market.get_template("meeting_summary_v1")
        if template:
            summary = self._prompt_market.render_template(
                "meeting_summary_v1",
                meeting_topic=meeting_topic,
                meeting_time=datetime.now().isoformat(),
                participants=", ".join(participants),
                meeting_content=meeting_content,
                max_length=1000
            )
        else:
            summary = f"会议纪要：{meeting_topic}\n\n{meeting_content}"

        step.data["summary"] = summary
        step.data["meeting_topic"] = meeting_topic
        step.status = WorkflowStatus.COMPLETED
        step.completed_at = datetime.now().isoformat()
        workflow.context["meeting_summary"] = summary
        workflow.updated_at = datetime.now().isoformat()

        app_logger.info(f"[Workflow] 会议纪要生成完成: {step.step_id}")
        await self._execute_next_step(workflow)

    async def _execute_approval(self, workflow: WorkflowInstance, step: WorkflowStep):
        """执行审批步骤"""
        app_logger.info(f"[Workflow] 执行审批步骤: {step.step_id}")

        leader = workflow.context.get("leader", "leader@example.com")
        summary = workflow.context.get("meeting_summary", "")
        meeting_topic = workflow.context.get("meeting_topic", "未命名会议")

        step.data["approval_type"] = "meeting_summary"
        step.data["approver"] = leader
        workflow.updated_at = datetime.now().isoformat()

        approval_id = f"approval_{step.step_id}"
        approval_request = ApprovalRequest(
            approval_id=approval_id,
            workflow_id=workflow.workflow_id,
            step_id=step.step_id,
            title=f"会议纪要审批: {meeting_topic}",
            description="请审批以下会议纪要内容",
            approver=leader,
            details={"summary": summary, "meeting_topic": meeting_topic}
        )
        self._approvals[approval_id] = approval_request

        if workflow.context.get("auto_approve", False):
            step.status = WorkflowStatus.APPROVED
            approval_request.status = ConfirmationStatus.APPROVED
            workflow.context["approval_result"] = "approved"
            app_logger.info(f"[Workflow] 自动审批通过: {step.step_id}")
            approval_request.updated_at = datetime.now().isoformat()
            await self._execute_next_step(workflow)
            return

        step.status = WorkflowStatus.PENDING_APPROVAL
        workflow.status = WorkflowStatus.PENDING_APPROVAL

        try:
            request_id = await self._hitl_service.request_confirmation(
                confirm_type=ConfirmationType.PLAN_APPROVAL,
                title=f"会议纪要审批: {meeting_topic}",
                message="请审批以下会议纪要内容",
                details={"summary": summary},
                timeout_seconds=300
            )

            approval_request.status = ConfirmationStatus.PENDING
            workflow.context["approval_result"] = "pending"
            workflow.context["confirmation_request_id"] = request_id
            app_logger.info(f"[Workflow] 审批请求已挂起: {step.step_id}, request_id={request_id}")

        except Exception as e:
            step.status = WorkflowStatus.FAILED
            approval_request.status = ConfirmationStatus.TIMED_OUT
            workflow.status = WorkflowStatus.FAILED
            app_logger.error(f"[Workflow] 审批步骤失败: {e}")

        approval_request.updated_at = datetime.now().isoformat()

    async def _execute_task_creation(self, workflow: WorkflowInstance, step: WorkflowStep):
        """执行任务创建"""
        app_logger.info(f"[Workflow] 执行任务创建: {step.step_id}")

        action_items = workflow.context.get("action_items", [])
        if not action_items:
            template = self._prompt_market.get_template("action_item_v1")
            if template:
                meeting_content = workflow.context.get("meeting_content", "")
                action_items_str = self._prompt_market.render_template(
                    "action_item_v1",
                    meeting_content=meeting_content
                )
                action_items = [{"title": action_items_str, "assignee": "待定", "description": action_items_str}]

        created_tasks = []
        for idx, item in enumerate(action_items):
            task = WorkflowTask(
                task_id=self._generate_task_id(),
                title=item.get("title", f"任务{idx+1}"),
                description=item.get("description", ""),
                assignee=item.get("assignee", "待定"),
                priority=TaskPriority(item.get("priority", "medium")),
                due_date=item.get("due_date")
            )

            try:
                external_id = await self._create_external_task(task)
                if external_id:
                    task.external_id = external_id
                    task.external_system = "jira"
                    app_logger.info(f"[Workflow] 外部任务创建成功: {external_id}")
            except Exception as e:
                app_logger.warning(f"[Workflow] 外部任务创建失败: {e}")

            self._tasks[task.task_id] = task
            workflow.tasks.append(task)
            created_tasks.append(task.to_dict())

        step.data["tasks"] = created_tasks
        step.status = WorkflowStatus.COMPLETED
        step.completed_at = datetime.now().isoformat()
        workflow.context["created_tasks"] = created_tasks
        workflow.updated_at = datetime.now().isoformat()

        app_logger.info(f"[Workflow] 任务创建完成，共创建 {len(created_tasks)} 个任务")
        await self._execute_next_step(workflow)

    async def _create_external_task(self, task: WorkflowTask) -> Optional[str]:
        """创建外部任务（Jira等）"""
        from app.core.config import settings
        if not settings.JIRA_MCP_ENABLED:
            return None

        result = await execute_jira_tool("jira_create_issue", {
            "project_key": "PROJ",
            "issue_type": "Task",
            "summary": task.title,
            "description": task.description,
            "assignee": task.assignee
        })

        if result.get("success"):
            return result.get("issue_key")
        return None

    async def _execute_notification(self, workflow: WorkflowInstance, step: WorkflowStep):
        """执行通知步骤"""
        app_logger.info(f"[Workflow] 执行通知步骤: {step.step_id}")

        meeting_topic = workflow.context.get("meeting_topic", "未命名会议")
        summary = workflow.context.get("meeting_summary", "")
        tasks = workflow.tasks

        notification_results = []

        for task in tasks:
            if task.assignee and "@" in task.assignee:
                email_result = await execute_email_tool("send_email", {
                    "to": [task.assignee],
                    "subject": f"【会议任务】{meeting_topic} - {task.title}",
                    "body": f"您好，会议 '{meeting_topic}' 已为您创建任务：\n\n任务：{task.title}\n描述：{task.description}\n截止日期：{task.due_date or '未指定'}\n\n请及时处理。",
                    "cc": []
                })
                notification_results.append({
                    "assignee": task.assignee,
                    "task_title": task.title,
                    "email_sent": email_result.get("success", False)
                })

        step.data["notifications"] = notification_results
        step.status = WorkflowStatus.COMPLETED
        step.completed_at = datetime.now().isoformat()
        workflow.context["notifications"] = notification_results
        workflow.updated_at = datetime.now().isoformat()

        app_logger.info(f"[Workflow] 通知发送完成，共发送 {len(notification_results)} 封邮件")
        await self._execute_next_step(workflow)

    async def _execute_follow_up(self, workflow: WorkflowInstance, step: WorkflowStep):
        """执行跟进提醒设置"""
        app_logger.info(f"[Workflow] 执行跟进提醒设置: {step.step_id}")

        follow_up_tasks = []
        for task in workflow.tasks:
            if task.due_date:
                due_date = datetime.fromisoformat(task.due_date)
                reminder_date = due_date - timedelta(days=2)
                if reminder_date > datetime.now():
                    self._follow_up_queue.append({
                        "task_id": task.task_id,
                        "workflow_id": workflow.workflow_id,
                        "reminder_time": reminder_date.isoformat(),
                        "assignee": task.assignee,
                        "task_title": task.title,
                        "due_date": task.due_date
                    })

        step.data["follow_up_count"] = len(follow_up_tasks)
        step.data["follow_up_tasks"] = follow_up_tasks
        step.status = WorkflowStatus.COMPLETED
        step.completed_at = datetime.now().isoformat()
        workflow.context["follow_up_count"] = len(follow_up_tasks)
        workflow.updated_at = datetime.now().isoformat()

        app_logger.info(f"[Workflow] 跟进提醒设置完成，共设置 {len(follow_up_tasks)} 个提醒")

    async def process_follow_up(self):
        """处理跟进提醒队列"""
        now = datetime.now().isoformat()
        while self._follow_up_queue and self._follow_up_queue[0]["reminder_time"] <= now:
            item = self._follow_up_queue.popleft()
            app_logger.info(f"[Workflow] 发送跟进提醒: {item['task_title']}")

            await execute_email_tool("send_email", {
                "to": [item["assignee"]] if item["assignee"] and "@" in item["assignee"] else [],
                "subject": f"【任务跟进提醒】{item['task_title']}",
                "body": f"您好，您有一个任务即将到期：\n\n任务：{item['task_title']}\n截止日期：{item['due_date']}\n\n请及时推进工作进度。",
                "cc": []
            })

    def update_task_status(self, task_id: str, status: TaskStatus) -> bool:
        """更新任务状态"""
        task = self._tasks.get(task_id)
        if not task:
            return False

        task.status = status
        task.updated_at = datetime.now().isoformat()

        for workflow in self._workflows.values():
            for t in workflow.tasks:
                if t.task_id == task_id:
                    t.status = status
                    t.updated_at = task.updated_at
                    workflow.updated_at = datetime.now().isoformat()
                    break

        app_logger.info(f"[Workflow] 更新任务状态: {task_id} -> {status.value}")
        return True

    def get_task(self, task_id: str) -> Optional[WorkflowTask]:
        """获取任务"""
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> List[WorkflowTask]:
        """获取所有任务"""
        return list(self._tasks.values())

    def get_tasks_by_status(self, status: TaskStatus) -> List[WorkflowTask]:
        """按状态获取任务"""
        return [t for t in self._tasks.values() if t.status == status]

    def get_pending_approvals(self) -> List[ApprovalRequest]:
        """获取待审批请求"""
        return [a for a in self._approvals.values() if a.status == ConfirmationStatus.PENDING]

    def get_approval(self, approval_id: str) -> Optional[ApprovalRequest]:
        """获取审批请求"""
        return self._approvals.get(approval_id)

    def get_workflow_templates(self) -> Dict[str, Any]:
        """获取所有工作流模板"""
        return self._workflow_templates

    def get_workflow_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """获取工作流模板"""
        return self._workflow_templates.get(template_id)

    def create_approval_flow(
        self,
        title: str,
        description: str,
        approvers: List[str],
        details: Dict[str, Any] = None,
        creator: Optional[str] = None
    ) -> ApprovalRequest:
        """创建审批流程"""
        workflow_id = self._generate_workflow_id()
        step_id = self._generate_step_id()
        approval_id = f"approval_{workflow_id}"

        approval = ApprovalRequest(
            approval_id=approval_id,
            workflow_id=workflow_id,
            step_id=step_id,
            title=title,
            description=description,
            approver=approvers[0] if approvers else "",
            details=details or {}
        )
        approval.level = 1
        approval.total_levels = len(approvers)
        approval.add_history("created", creator or "system")

        self._approvals[approval_id] = approval
        app_logger.info(f"[Workflow] 创建审批流程: {approval_id} - {title}")

        return approval

    async def approve_approval(self, approval_id: str, user: str, comment: str = "") -> bool:
        """审批通过"""
        approval = self._approvals.get(approval_id)
        if not approval or approval.status != ConfirmationStatus.PENDING:
            return False

        approval.status = ConfirmationStatus.APPROVED
        if comment:
            approval.add_comment(comment, user)
        approval.add_history("approved", user)
        approval.updated_at = datetime.now().isoformat()

        app_logger.info(f"[Workflow] 审批通过: {approval_id}")
        return True

    async def reject_approval(self, approval_id: str, user: str, comment: str = "") -> bool:
        """拒绝审批"""
        approval = self._approvals.get(approval_id)
        if not approval or approval.status != ConfirmationStatus.PENDING:
            return False

        approval.status = ConfirmationStatus.REJECTED
        if comment:
            approval.add_comment(comment, user)
        approval.add_history("rejected", user)
        approval.updated_at = datetime.now().isoformat()

        app_logger.info(f"[Workflow] 拒绝审批: {approval_id}")
        return True

    async def delegate_approval(self, approval_id: str, new_approver: str, user: str) -> bool:
        """转派审批"""
        approval = self._approvals.get(approval_id)
        if not approval or approval.status != ConfirmationStatus.PENDING:
            return False

        old_approver = approval.approver
        approval.approver = new_approver
        approval.add_history("delegated", user, {"from": old_approver, "to": new_approver})
        approval.updated_at = datetime.now().isoformat()

        app_logger.info(f"[Workflow] 审批转派: {approval_id} from {old_approver} to {new_approver}")
        return True

    async def sync_task_to_external(self, task_id: str, system: str = "feishu") -> Optional[str]:
        """同步任务到外部系统"""
        task = self._tasks.get(task_id)
        if not task:
            return None

        try:
            if system == "feishu":
                result = await execute_feishu_tool("feishu_create_task", {
                    "title": task.title,
                    "description": task.description,
                    "assignee": task.assignee,
                    "due_date": task.due_date,
                    "priority": task.priority.value
                })
            elif system == "jira":
                result = await execute_jira_tool("jira_create_issue", {
                    "project_key": "PROJ",
                    "issue_type": "Task",
                    "summary": task.title,
                    "description": task.description,
                    "assignee": task.assignee
                })
            elif system == "notion":
                result = await execute_feishu_tool("notion_create_page", {
                    "title": task.title,
                    "content": task.description,
                    "assignee": task.assignee
                })
            else:
                return None

            if result.get("success"):
                task.external_id = result.get("id") or result.get("issue_key")
                task.external_system = system
                task.updated_at = datetime.now().isoformat()
                app_logger.info(f"[Workflow] 任务同步成功: {task_id} -> {system}")
                return task.external_id
        except Exception as e:
            app_logger.error(f"[Workflow] 任务同步失败: {task_id} -> {system}: {e}")

        return None

    def get_tasks_by_assignee(self, assignee: str) -> List[WorkflowTask]:
        """按负责人获取任务"""
        return [t for t in self._tasks.values() if t.assignee == assignee]

    def get_overdue_tasks(self) -> List[WorkflowTask]:
        """获取逾期任务"""
        now = datetime.now()
        overdue = []
        for task in self._tasks.values():
            if task.due_date and task.status != TaskStatus.COMPLETED:
                try:
                    due_date = datetime.fromisoformat(task.due_date)
                    if due_date < now:
                        overdue.append(task)
                except (ValueError, TypeError):
                    pass
        return overdue

    def get_task_statistics(self) -> Dict[str, Any]:
        """获取任务统计"""
        total = len(self._tasks)
        pending = len([t for t in self._tasks.values() if t.status == TaskStatus.PENDING])
        in_progress = len([t for t in self._tasks.values() if t.status == TaskStatus.IN_PROGRESS])
        completed = len([t for t in self._tasks.values() if t.status == TaskStatus.COMPLETED])
        blocked = len([t for t in self._tasks.values() if t.status == TaskStatus.BLOCKED])
        overdue = len(self.get_overdue_tasks())

        return {
            "total": total,
            "pending": pending,
            "in_progress": in_progress,
            "completed": completed,
            "blocked": blocked,
            "overdue": overdue,
            "completion_rate": completed / total if total > 0 else 0,
        }

    def get_workflow_statistics(self) -> Dict[str, Any]:
        """获取工作流统计"""
        total = len(self._workflows)
        in_progress = len([w for w in self._workflows.values() if w.status == WorkflowStatus.IN_PROGRESS])
        pending_approval = len([w for w in self._workflows.values() if w.status == WorkflowStatus.PENDING_APPROVAL])
        completed = len([w for w in self._workflows.values() if w.status == WorkflowStatus.COMPLETED])
        rejected = len([w for w in self._workflows.values() if w.status == WorkflowStatus.REJECTED])

        return {
            "total": total,
            "in_progress": in_progress,
            "pending_approval": pending_approval,
            "completed": completed,
            "rejected": rejected,
            "completion_rate": completed / total if total > 0 else 0,
        }

    async def approve_workflow(self, workflow_id: str, step_id: str) -> bool:
        """审批工作流步骤"""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return False

        for step in workflow.steps:
            if step.step_id == step_id and step.status == WorkflowStatus.PENDING_APPROVAL:
                step.status = WorkflowStatus.APPROVED
                step.completed_at = datetime.now().isoformat()
                workflow.status = WorkflowStatus.IN_PROGRESS
                workflow.updated_at = datetime.now().isoformat()

                app_logger.info(f"[Workflow] 手动审批通过: {workflow_id} - {step_id}")
                await self._execute_next_step(workflow)
                return True

        return False

    async def reject_workflow(self, workflow_id: str, step_id: str) -> bool:
        """拒绝工作流步骤"""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return False

        for step in workflow.steps:
            if step.step_id == step_id and step.status == WorkflowStatus.PENDING_APPROVAL:
                step.status = WorkflowStatus.REJECTED
                step.completed_at = datetime.now().isoformat()
                workflow.status = WorkflowStatus.REJECTED
                workflow.completed_at = datetime.now().isoformat()
                workflow.updated_at = datetime.now().isoformat()

                app_logger.info(f"[Workflow] 手动审批拒绝: {workflow_id} - {step_id}")
                return True

        return False


_workflow_engine: Optional[WorkflowEngine] = None


def get_workflow_engine() -> WorkflowEngine:
    """获取工作流引擎实例"""
    global _workflow_engine
    if _workflow_engine is None:
        _workflow_engine = WorkflowEngine()
    return _workflow_engine
