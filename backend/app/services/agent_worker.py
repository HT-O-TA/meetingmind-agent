"""Agent执行消费者 - 异步处理Agent任务"""
import json
import logging
from typing import Dict, Any
from app.core.rabbitmq import rabbitmq_manager
from app.core.config import settings
from app.core.logger import app_logger
from app.services.task_queue import task_queue_service, TaskStatus, TaskType
from app.agents.graph import create_agent_graph
from app.services.llm_service import LLMService
from app.agents.tools import ToolManager


logger = logging.getLogger(__name__)


async def agent_execute_consumer(message_body: Dict[str, Any]):
    """
    Agent执行任务消费者

    Args:
        message_body: 消息体，包含task_id和payload
    """
    task_id = message_body.get("task_id")
    payload = message_body.get("payload", {})

    try:
        await task_queue_service.update_task_status(
            task_id, TaskStatus.PROCESSING, progress=10
        )

        question = payload.get("question", "")
        document_ids = payload.get("document_ids", [])
        meeting_id = payload.get("meeting_id")
        thread_id = payload.get("thread_id", task_id)

        llm_service = LLMService()
        tool_manager = ToolManager(llm_service)

        await task_queue_service.update_task_status(
            task_id, TaskStatus.PROCESSING, progress=20
        )

        graph = create_agent_graph(
            llm_service=llm_service,
            tool_manager=tool_manager,
            enable_react=True,
            enable_cot=True,
            enable_fallback=True,
            enable_reflection=True,
            use_checkpointer=True,
        )

        await task_queue_service.update_task_status(
            task_id, TaskStatus.PROCESSING, progress=30
        )

        initial_state = {
            "question": question,
            "meeting_id": meeting_id,
            "document_ids": document_ids,
            "thread_id": thread_id,
            "context": [],
            "raw_context": [],
            "current_phase": "plan",
            "task_type": None,
            "workflow_type": None,
            "reasoning_mode": None,
            "complexity_score": 0.0,
            "complexity_level": None,
            "is_multi_task": False,
            "route_reason": "",
            "retrieval_required": True,
            "retrieval_confidence": 0.0,
            "citations": [],
            "validation_errors": [],
            "policy_results": [],
            "repair_count": 0,
            "max_repair_attempts": 1,
            "risk_level": "low",
            "requires_confirmation": False,
            "confirmation_status": "not_required",
            "pending_action": None,
            "plan": None,
            "task_contexts": {},
            "minutes": None,
            "todos": None,
            "controversies": None,
            "answer": None,
            "reflection": None,
            "error": None,
            "cot_thoughts": [],
            "agents_involved": [],
            "last_strategy": None,
            "fallback_count": 0,
            "event_callback": None,
            "human_confirmations": [],
            "enable_human_in_the_loop": False,
            "session_context": None,
        }

        await task_queue_service.update_task_status(
            task_id, TaskStatus.PROCESSING, progress=40
        )

        result = await graph.ainvoke(initial_state, config={"configurable": {"thread_id": thread_id}})

        await task_queue_service.update_task_status(
            task_id, TaskStatus.PROCESSING, progress=90
        )

        response_data = {
            "answer": result.get("answer", ""),
            "minutes": result.get("minutes"),
            "todos": result.get("todos"),
            "controversies": result.get("controversies"),
            "citations": result.get("citations", []),
            "reflection": result.get("reflection"),
        }

        await task_queue_service.update_task_status(
            task_id, TaskStatus.COMPLETED, progress=100, result=response_data
        )

        logger.info(f"Agent task completed: {task_id}")

    except Exception as e:
        logger.error(f"Agent task failed: {task_id}, error: {str(e)}", exc_info=True)
        await task_queue_service.update_task_status(
            task_id, TaskStatus.FAILED, error=str(e)
        )


async def start_agent_worker():
    """启动Agent执行消费者"""
    try:
        await rabbitmq_manager.register_consumer(
            queue_name=settings.QUEUE_AGENT_EXECUTE,
            callback=agent_execute_consumer,
            prefetch_count=settings.QUEUE_PREFETCH_COUNT,
        )
        app_logger.info(f"✅ Agent执行消费者已启动，队列: {settings.QUEUE_AGENT_EXECUTE}")
    except Exception as e:
        app_logger.error(f"❌ Agent执行消费者启动失败: {e}")


async def create_agent_task(
    question: str,
    document_ids: list = None,
    meeting_id: int = None,
    metadata: dict = None,
) -> dict:
    """
    创建Agent异步执行任务

    Args:
        question: 用户问题
        document_ids: 相关文档ID列表
        meeting_id: 会议ID
        metadata: 元数据

    Returns:
        任务信息
    """
    payload = {
        "question": question,
        "document_ids": document_ids or [],
        "meeting_id": meeting_id,
        "metadata": metadata or {},
    }

    task_info = await task_queue_service.create_task(
        TaskType.AGENT_EXECUTE,
        payload,
        metadata=metadata,
    )

    return {
        "task_id": task_info.task_id,
        "status": task_info.status,
        "created_at": task_info.created_at,
    }
