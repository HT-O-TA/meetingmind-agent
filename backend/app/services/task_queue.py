"""任务队列服务 - 文档异步处理"""
import json
import uuid
import logging
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
import asyncio

from app.core.rabbitmq import rabbitmq_manager
from app.core.config import settings
from app.core.cache_init import get_redis

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"           # 待处理
    PROCESSING = "processing"     # 处理中
    COMPLETED = "completed"       # 已完成
    FAILED = "failed"            # 失败
    CANCELLED = "cancelled"      # 已取消


class TaskType(str, Enum):
    """任务类型枚举"""
    DOCUMENT_PROCESS = "document_process"     # 文档处理
    VECTOR_EMBED = "vector_embed"            # 向量化
    KNOWLEDGE_GRAPH = "knowledge_graph"       # 知识图谱构建


@dataclass
class TaskInfo:
    """任务信息"""
    task_id: str
    task_type: str
    status: str
    progress: int = 0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    metadata: Optional[Dict[str, Any]] = None


class TaskQueueService:
    """任务队列服务"""
    
    def __init__(self):
        self.redis = None  # 延迟初始化
    
    async def _get_redis(self):
        """获取 Redis 客户端"""
        if self.redis is None:
            self.redis = get_redis()
        return self.redis
    
    def _get_task_key(self, task_id: str) -> str:
        """获取任务存储的 Redis key"""
        return f"task:{task_id}"
    
    def _get_task_queue(self, task_type: str) -> str:
        """获取任务队列名称"""
        queue_map = {
            TaskType.DOCUMENT_PROCESS: settings.QUEUE_DOCUMENT_PROCESS,
            TaskType.VECTOR_EMBED: settings.QUEUE_VECTOR_EMBED,
            TaskType.KNOWLEDGE_GRAPH: settings.QUEUE_KNOWLEDGE_GRAPH,
        }
        return queue_map.get(task_type, settings.QUEUE_DOCUMENT_PROCESS)
    
    async def create_task(
        self,
        task_type: TaskType,
        payload: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> TaskInfo:
        """创建新任务"""
        task_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        task_info = TaskInfo(
            task_id=task_id,
            task_type=task_type.value,
            status=TaskStatus.PENDING.value,
            progress=0,
            created_at=now,
            updated_at=now,
            metadata=metadata or {}
        )
        
        # 存储任务信息到 Redis
        redis = await self._get_redis()
        task_key = self._get_task_key(task_id)
        await redis.set(
            task_key,
            json.dumps(asdict(task_info)),
            ex=settings.QUEUE_TASK_TIMEOUT  # 任务过期时间
        )
        
        # 发布任务到消息队列
        message = {
            "task_id": task_id,
            "task_type": task_type.value,
            "payload": payload,
            "metadata": metadata or {},
            "created_at": now
        }
        
        queue_name = self._get_task_queue(task_type)
        await rabbitmq_manager.publish_message(
            queue_name=queue_name,
            message_body=message,
            priority=0,
            headers={"task_id": task_id}
        )
        
        logger.info(f"Task created: {task_id}, type: {task_type.value}")
        return task_info
    
    async def get_task_status(self, task_id: str) -> Optional[TaskInfo]:
        """获取任务状态"""
        redis = await self._get_redis()
        task_key = self._get_task_key(task_id)
        
        task_data = await redis.get(task_key)
        if task_data:
            return TaskInfo(**json.loads(task_data))
        return None
    
    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        progress: int = None,
        result: Dict[str, Any] = None,
        error: str = None
    ) -> Optional[TaskInfo]:
        """更新任务状态"""
        redis = await self._get_redis()
        task_key = self._get_task_key(task_id)
        
        task_data = await redis.get(task_key)
        if not task_data:
            logger.warning(f"Task not found: {task_id}")
            return None
        
        task_info = TaskInfo(**json.loads(task_data))
        
        # 更新字段
        task_info.status = status.value
        task_info.updated_at = datetime.now().isoformat()
        
        if progress is not None:
            task_info.progress = progress
        if result is not None:
            task_info.result = result
        if error is not None:
            task_info.error = error
        
        # 保存更新
        await redis.set(
            task_key,
            json.dumps(asdict(task_info)),
            ex=settings.QUEUE_TASK_TIMEOUT
        )
        
        logger.info(f"Task updated: {task_id}, status: {status.value}, progress: {task_info.progress}%")
        return task_info
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        task_info = await self.update_task_status(
            task_id,
            TaskStatus.CANCELLED
        )
        return task_info is not None
    
    async def list_tasks(
        self,
        task_type: Optional[TaskType] = None,
        status: Optional[TaskStatus] = None,
        limit: int = 100
    ) -> List[TaskInfo]:
        """列出任务"""
        redis = await self._get_redis()
        
        # 扫描所有任务 key
        pattern = "task:*"
        tasks = []
        
        async for key in redis.scan_iter(match=pattern, count=limit):
            task_data = await redis.get(key)
            if task_data:
                task_info = TaskInfo(**json.loads(task_data))
                
                # 过滤条件
                if task_type and task_info.task_type != task_type.value:
                    continue
                if status and task_info.status != status.value:
                    continue
                
                tasks.append(task_info)
        
        # 按创建时间排序
        tasks.sort(key=lambda x: x.created_at, reverse=True)
        return tasks[:limit]
    
    async def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        redis = await self._get_redis()
        task_key = self._get_task_key(task_id)
        result = await redis.delete(task_key)
        return result > 0


# 全局单例
task_queue_service = TaskQueueService()


# 便捷函数
async def create_document_process_task(
    document_id: int,
    file_path: str,
    user_id: int = None,
    metadata: Dict[str, Any] = None
) -> TaskInfo:
    """创建文档处理任务"""
    payload = {
        "document_id": document_id,
        "file_path": file_path,
        "user_id": user_id
    }
    return await task_queue_service.create_task(
        TaskType.DOCUMENT_PROCESS,
        payload,
        metadata
    )


async def create_vector_embed_task(
    document_id: int,
    chunk_ids: List[int],
    metadata: Dict[str, Any] = None
) -> TaskInfo:
    """创建向量化任务"""
    payload = {
        "document_id": document_id,
        "chunk_ids": chunk_ids
    }
    return await task_queue_service.create_task(
        TaskType.VECTOR_EMBED,
        payload,
        metadata
    )


async def create_knowledge_graph_task(
    document_id: int,
    chunk_ids: List[int],
    metadata: Dict[str, Any] = None
) -> TaskInfo:
    """创建知识图谱构建任务"""
    payload = {
        "document_id": document_id,
        "chunk_ids": chunk_ids
    }
    return await task_queue_service.create_task(
        TaskType.KNOWLEDGE_GRAPH,
        payload,
        metadata
    )
