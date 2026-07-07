"""Agent通信与任务分发系统 - 支持多Agent协作"""
import asyncio
import json
from typing import Dict, List, Any, Optional, Callable
from enum import Enum
from datetime import datetime
from dataclasses import dataclass, asdict
from app.core.logger import app_logger


class MessageType(str, Enum):
    """消息类型枚举"""
    TASK_ASSIGN = "task_assign"
    TASK_RESULT = "task_result"
    TASK_CANCEL = "task_cancel"
    TASK_STATUS = "task_status"
    AGENT_REQUEST = "agent_request"
    AGENT_RESPONSE = "agent_response"
    BROADCAST = "broadcast"
    ERROR = "error"


class TaskPriority(str, Enum):
    """任务优先级"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentMessage:
    """Agent消息结构"""
    sender_id: str
    receiver_id: str
    message_type: MessageType
    content: Dict[str, Any]
    message_id: str = ""
    timestamp: datetime = None
    reply_to: Optional[str] = None
    
    def __post_init__(self):
        if not self.message_id:
            self.message_id = f"msg_{int(datetime.now().timestamp() * 1000)}_{id(self)}"
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class Task:
    """任务结构"""
    task_id: str
    description: str
    priority: TaskPriority
    name: str = ""
    task_type: str = "general"
    status: TaskStatus = TaskStatus.PENDING
    assignee_id: Optional[str] = None
    assigned_agent: Optional[str] = None
    creator_id: Optional[str] = None
    input_data: Dict[str, Any] = None
    output_data: Dict[str, Any] = None
    error_info: Optional[str] = None
    created_at: datetime = None
    updated_at: datetime = None
    deadline: Optional[datetime] = None
    dependencies: List[str] = None
    
    def __post_init__(self):
        if isinstance(self.priority, str):
            self.priority = TaskPriority(self.priority)
        if isinstance(self.status, str):
            self.status = TaskStatus(self.status)
        if self.assignee_id is None and self.assigned_agent is not None:
            self.assignee_id = self.assigned_agent
        if not self.name:
            self.name = self.description
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()
        if self.dependencies is None:
            self.dependencies = []


class MessageBus:
    """消息总线 - 负责Agent间通信"""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._message_history: List[AgentMessage] = []
        self._lock = asyncio.Lock()
    
    def subscribe(self, agent_id: str, handler: Callable):
        """订阅消息"""
        if agent_id not in self._subscribers:
            self._subscribers[agent_id] = []
        self._subscribers[agent_id].append(handler)
        app_logger.debug(f"[MessageBus] Agent {agent_id} 订阅消息")
    
    def unsubscribe(self, agent_id: str, handler: Callable):
        """取消订阅"""
        if agent_id in self._subscribers:
            self._subscribers[agent_id].remove(handler)
            app_logger.debug(f"[MessageBus] Agent {agent_id} 取消订阅")
    
    async def send(self, message: AgentMessage):
        """发送消息"""
        async with self._lock:
            self._message_history.append(message)
            
            # 发送给指定接收者
            if message.receiver_id in self._subscribers:
                for handler in self._subscribers[message.receiver_id]:
                    try:
                        await handler(message)
                    except Exception as e:
                        app_logger.error(f"[MessageBus] 消息处理失败: {e}")
            
            # 如果是广播，发送给所有订阅者
            if message.message_type == MessageType.BROADCAST:
                for agent_id, handlers in self._subscribers.items():
                    if agent_id != message.sender_id:
                        for handler in handlers:
                            try:
                                await handler(message)
                            except Exception as e:
                                app_logger.error(f"[MessageBus] 广播消息处理失败: {e}")
    
    async def broadcast(self, sender_id, content: Optional[Dict[str, Any]] = None):
        """广播消息"""
        if isinstance(sender_id, AgentMessage):
            message = sender_id
            message.message_type = MessageType.BROADCAST
            message.receiver_id = "*"
        else:
            message = AgentMessage(
                message_id=self._generate_message_id(),
                sender_id=sender_id,
                receiver_id="*",
                message_type=MessageType.BROADCAST,
                content=content or {}
            )
        await self.send(message)
    
    def _generate_message_id(self) -> str:
        """生成唯一消息ID"""
        return f"msg_{id(self)}_{int(datetime.now().timestamp())}"
    
    def get_message_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取消息历史"""
        history = []
        for msg in self._message_history[-limit:]:
            data = asdict(msg)
            data["timestamp"] = msg.timestamp.isoformat()
            history.append(data)
        return history
    
    def clear_history(self):
        """清空消息历史"""
        self._message_history.clear()


class TaskDispatcher:
    """任务分发器 - 负责任务分配和调度"""
    
    def __init__(self, message_bus: Optional[MessageBus] = None):
        self.message_bus = message_bus or MessageBus()
        self._tasks: Dict[str, Task] = {}
        self._agent_capabilities: Dict[str, List[str]] = {}  # agent_id -> [capabilities]
        self._task_queue: List[Task] = []
        self._lock = asyncio.Lock()
    
    def register_agent(self, agent_id: str, capabilities: List[str]):
        """注册Agent及其能力"""
        self._agent_capabilities[agent_id] = capabilities
        app_logger.info(f"[TaskDispatcher] Agent {agent_id} 注册，能力: {capabilities}")
    
    def unregister_agent(self, agent_id: str):
        """注销Agent"""
        if agent_id in self._agent_capabilities:
            del self._agent_capabilities[agent_id]
            app_logger.info(f"[TaskDispatcher] Agent {agent_id} 注销")
    
    def create_task(
        self,
        name: str,
        description: str,
        task_type: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        input_data: Optional[Dict[str, Any]] = None,
        creator_id: Optional[str] = None,
        deadline: Optional[datetime] = None,
        dependencies: Optional[List[str]] = None
    ) -> Task:
        """创建任务"""
        task = Task(
            task_id=f"task_{int(datetime.now().timestamp())}_{id(self)}",
            name=name,
            description=description,
            task_type=task_type,
            priority=priority,
            status=TaskStatus.PENDING,
            input_data=input_data or {},
            creator_id=creator_id,
            deadline=deadline,
            dependencies=dependencies or []
        )
        
        self._tasks[task.task_id] = task
        self._task_queue.append(task)
        
        app_logger.info(f"[TaskDispatcher] 创建任务: {task.task_id} - {name}")
        return task
    
    async def dispatch_task(self, task_id: str) -> bool:
        """分发任务"""
        async with self._lock:
            if task_id not in self._tasks:
                app_logger.warning(f"[TaskDispatcher] 任务不存在: {task_id}")
                return False
            
            task = self._tasks[task_id]
            if task.status != TaskStatus.PENDING:
                app_logger.warning(f"[TaskDispatcher] 任务状态不允许分发: {task.status}")
                return False
            
            # 查找合适的Agent
            agent_id = await self._find_best_agent(task)
            
            if agent_id:
                # 分配任务
                task.status = TaskStatus.ASSIGNED
                task.assignee_id = agent_id
                task.updated_at = datetime.now()
                
                # 从队列移除
                if task in self._task_queue:
                    self._task_queue.remove(task)
                
                # 发送任务分配消息
                message = AgentMessage(
                    message_id=f"task_{task_id}",
                    sender_id="dispatcher",
                    receiver_id=agent_id,
                    message_type=MessageType.TASK_ASSIGN,
                    content={
                        "task_id": task.task_id,
                        "name": task.name,
                        "description": task.description,
                        "task_type": task.task_type,
                        "priority": task.priority.value,
                        "input_data": task.input_data,
                        "deadline": task.deadline.isoformat() if task.deadline else None
                    }
                )
                
                await self.message_bus.send(message)
                app_logger.info(f"[TaskDispatcher] 任务 {task_id} 分配给 Agent {agent_id}")
                return True
            else:
                app_logger.warning(f"[TaskDispatcher] 找不到合适的Agent处理任务: {task_id}")
                return False
    
    async def _find_best_agent(self, task: Task) -> Optional[str]:
        """查找最适合处理任务的Agent"""
        # 优先按能力匹配
        candidates = []
        for agent_id, capabilities in self._agent_capabilities.items():
            if task.task_type in capabilities:
                candidates.append(agent_id)
        
        if candidates:
            # 简单策略：选择第一个可用的Agent
            # 可扩展为更复杂的负载均衡策略
            return candidates[0]
        
        # 如果没有精确匹配，选择具有"general"能力的Agent
        for agent_id, capabilities in self._agent_capabilities.items():
            if "general" in capabilities:
                return agent_id
        
        return None
    
    async def update_task_status(self, task_id: str, status: TaskStatus, output_data: Optional[Dict[str, Any]] = None, error_info: Optional[str] = None):
        """更新任务状态"""
        async with self._lock:
            if task_id not in self._tasks:
                return False
            
            task = self._tasks[task_id]
            task.status = status
            task.updated_at = datetime.now()
            
            if output_data:
                task.output_data = output_data
            
            if error_info:
                task.error_info = error_info
            
            app_logger.info(f"[TaskDispatcher] 任务 {task_id} 状态更新: {status}")
            return True
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        return self._tasks.get(task_id)

    async def submit_task(self, task: Task) -> bool:
        """兼容旧接口：提交已构造的任务并尝试分发。"""
        self._tasks[task.task_id] = task
        if task.status == TaskStatus.PENDING and task not in self._task_queue:
            self._task_queue.append(task)
        return await self.dispatch_task(task.task_id)

    async def cancel_task(self, task_id: str) -> bool:
        """兼容旧接口：取消任务。"""
        task = self._tasks.get(task_id)
        if not task:
            return False
        task.status = TaskStatus.CANCELLED
        task.updated_at = datetime.now()
        if task in self._task_queue:
            self._task_queue.remove(task)
        return True
    
    def get_tasks_by_status(self, status: TaskStatus) -> List[Task]:
        """按状态获取任务"""
        return [task for task in self._tasks.values() if task.status == status]
    
    def get_pending_tasks(self) -> List[Task]:
        """获取待处理任务"""
        return self.get_tasks_by_status(TaskStatus.PENDING)
    
    def get_tasks_by_agent(self, agent_id: str) -> List[Task]:
        """获取Agent的任务"""
        return [task for task in self._tasks.values() if task.assignee_id == agent_id]
    
    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """获取所有任务"""
        result = []
        for task in self._tasks.values():
            data = asdict(task)
            data["created_at"] = task.created_at.isoformat()
            data["updated_at"] = task.updated_at.isoformat()
            data["deadline"] = task.deadline.isoformat() if task.deadline else None
            result.append(data)
        return result


# 全局实例
message_bus = MessageBus()
task_dispatcher = TaskDispatcher(message_bus)


def get_message_bus() -> MessageBus:
    """获取消息总线实例"""
    return message_bus


def get_task_dispatcher() -> TaskDispatcher:
    """获取任务分发器实例"""
    return task_dispatcher
