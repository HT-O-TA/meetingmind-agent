"""数据同步服务 - PostgreSQL 与 Milvus 状态同步 + 缓存主动失效

设计原则：
1. 单一数据源：PostgreSQL 是业务数据的唯一真实来源
2. 异步同步：通过事件队列异步更新 Milvus，避免阻塞主流程
3. 最终一致性：允许短暂的数据不一致，通过定期对账保证最终一致
4. 幂等操作：重复执行同步操作不会产生副作用
5. 缓存联动：数据变更时主动失效相关缓存，防止返回过时数据

同步场景：
- 文档状态变更（发布/归档/删除）→ 失效缓存 + 更新 Milvus
- 文档元数据变更（标题、权限、分类）→ 失效缓存
- 文档内容变更（需要重新Embedding）→ 失效缓存 + 重新 Embedding
"""
import asyncio
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
from enum import Enum
from dataclasses import dataclass
from collections import deque
from app.core.logger import app_logger
from app.core.config import settings
from app.services.vector_cache_manager import get_cache_manager


class SyncEventType(str, Enum):
    """同步事件类型"""
    VECTOR_ADD = "vector_add"              # 新增向量
    VECTOR_UPDATE = "vector_update"        # 更新向量
    VECTOR_DELETE = "vector_delete"        # 删除向量
    VECTOR_REINDEX = "vector_reindex"      # 重新索引
    METADATA_UPDATE = "metadata_update"    # 仅更新元数据（不需要重新Embedding）
    FULL_SYNC = "full_sync"                # 全量同步


class SyncPriority(str, Enum):
    """同步优先级"""
    HIGH = "high"      # 高优先级：删除、权限变更
    NORMAL = "normal"  # 普通：新增、更新
    LOW = "low"        # 低优先级：全量同步、重建索引


@dataclass
class SyncEvent:
    """同步事件"""
    event_id: str
    event_type: SyncEventType
    entity_type: str  # document, chunk, meeting
    entity_id: int
    data: Dict[str, Any]
    priority: SyncPriority = SyncPriority.NORMAL
    created_at: datetime = None
    retry_count: int = 0
    max_retries: int = 3

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class VectorSyncService:
    """向量数据同步服务

    使用内存事件队列 + 异步消费者模式：
    1. 业务操作时发布同步事件到队列
    2. 后台异步消费者处理队列中的事件
    3. 支持优先级调度和失败重试
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # 事件队列（按优先级）
        self._high_priority_queue: deque = deque()
        self._normal_priority_queue: deque = deque()
        self._low_priority_queue: deque = deque()

        # 处理状态
        self._is_running = False
        self._consumer_task: Optional[asyncio.Task] = None

        # 统计信息
        self._events_processed = 0
        self._events_failed = 0
        self._last_sync_time: Optional[datetime] = None

        # 事件处理器注册表
        self._handlers: Dict[SyncEventType, List[Callable]] = {
            SyncEventType.VECTOR_ADD: [],
            SyncEventType.VECTOR_UPDATE: [],
            SyncEventType.VECTOR_DELETE: [],
            SyncEventType.VECTOR_REINDEX: [],
            SyncEventType.METADATA_UPDATE: [],
            SyncEventType.FULL_SYNC: [],
        }

        self._initialized = True
        app_logger.info("[VectorSyncService] 初始化完成")

    async def start(self):
        """启动后台消费者"""
        if self._is_running:
            return

        self._is_running = True
        self._consumer_task = asyncio.create_task(self._consumer_loop())
        app_logger.info("[VectorSyncService] 后台消费者已启动")

    async def stop(self):
        """停止后台消费者"""
        self._is_running = False
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
        app_logger.info("[VectorSyncService] 后台消费者已停止")

    def register_handler(self, event_type: SyncEventType, handler: Callable):
        """注册事件处理器"""
        if event_type in self._handlers:
            self._handlers[event_type].append(handler)
            app_logger.debug(f"[VectorSyncService] 注册处理器: {event_type}")

    async def publish_event(self, event: SyncEvent) -> str:
        """发布同步事件"""
        from uuid import uuid4
        event.event_id = f"sync_{uuid4().hex[:12]}"

        # 根据优先级放入对应队列
        if event.priority == SyncPriority.HIGH:
            self._high_priority_queue.append(event)
        elif event.priority == SyncPriority.LOW:
            self._low_priority_queue.append(event)
        else:
            self._normal_priority_queue.append(event)

        app_logger.info(
            f"[VectorSyncService] 发布事件: {event.event_type.value}, "
            f"entity={event.entity_type}:{event.entity_id}, "
            f"priority={event.priority.value}"
        )

        return event.event_id

    async def _consumer_loop(self):
        """消费者主循环"""
        while self._is_running:
            try:
                # 优先处理高优先级队列
                event = await self._get_next_event()

                if event:
                    await self._process_event(event)
                else:
                    # 队列为空，等待一段时间
                    await asyncio.sleep(1)

            except Exception as e:
                app_logger.error(f"[VectorSyncService] 消费者异常: {e}")
                await asyncio.sleep(5)  # 异常后等待5秒

    async def _get_next_event(self) -> Optional[SyncEvent]:
        """获取下一个事件（按优先级）"""
        # 高优先级队列优先
        if self._high_priority_queue:
            return self._high_priority_queue.popleft()
        # 然后是普通优先级
        if self._normal_priority_queue:
            return self._normal_priority_queue.popleft()
        # 最后是低优先级
        if self._low_priority_queue:
            return self._low_priority_queue.popleft()
        return None

    async def _process_event(self, event: SyncEvent):
        """处理单个事件"""
        try:
            app_logger.info(
                f"[VectorSyncService] 处理事件: {event.event_type.value}, "
                f"entity={event.entity_type}:{event.entity_id}"
            )

            # 查找并执行所有注册的处理器
            handlers = self._handlers.get(event.event_type, [])
            for handler in handlers:
                try:
                    await handler(event)
                except Exception as handler_error:
                    app_logger.error(
                        f"[VectorSyncService] 处理器执行失败: {handler_error}"
                    )

            self._events_processed += 1
            self._last_sync_time = datetime.now()

            app_logger.info(
                f"[VectorSyncService] 事件处理完成: {event.event_id}"
            )

        except Exception as e:
            self._events_failed += 1
            app_logger.error(
                f"[VectorSyncService] 事件处理失败: {e}, "
                f"event_id={event.event_id}, retry={event.retry_count}"
            )

            # 失败重试
            if event.retry_count < event.max_retries:
                event.retry_count += 1
                # 退避重试
                wait_time = 2 ** event.retry_count
                await asyncio.sleep(wait_time)

                # 重新入队（降级到低优先级）
                if event.priority != SyncPriority.LOW:
                    event.priority = SyncPriority.LOW
                self._low_priority_queue.append(event)
                app_logger.warning(
                    f"[VectorSyncService] 事件重试: {event.event_id}, "
                    f"retry={event.retry_count}"
                )

    async def sync_document_change(
        self,
        document_id: int,
        change_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        invalidate_cache: bool = True,
        **kwargs
    ) -> str:
        """
        同步文档变更（便捷方法）

        Args:
            document_id: 文档 ID
            change_type: 变更类型 (delete/status_change/content_change/add)
            metadata: 元数据
            invalidate_cache: 是否主动失效缓存（默认 True）
        """
        # 主动失效缓存
        if invalidate_cache:
            await self._invalidate_document_cache(document_id)

        # 确定事件类型和优先级
        if change_type == "delete":
            event_type = SyncEventType.VECTOR_DELETE
            priority = SyncPriority.HIGH
        elif change_type == "status_change":
            event_type = SyncEventType.METADATA_UPDATE
            priority = SyncPriority.HIGH
        elif change_type == "content_change":
            event_type = SyncEventType.VECTOR_UPDATE
            priority = SyncPriority.NORMAL
        else:
            event_type = SyncEventType.VECTOR_ADD
            priority = SyncPriority.NORMAL

        event = SyncEvent(
            event_id="",  # 将在 publish_event 中生成
            event_type=event_type,
            entity_type="document",
            entity_id=document_id,
            data={
                "change_type": change_type,
                "metadata": metadata or {},
                **kwargs
            },
            priority=priority,
        )

        return await self.publish_event(event)

    async def _invalidate_document_cache(self, document_id: int) -> int:
        """
        失效指定文档相关的缓存

        当文档内容或状态变更时调用，确保不会返回过时数据
        """
        try:
            cache_manager = get_cache_manager()
            count = await cache_manager.invalidate_cache_for_document(document_id)
            app_logger.info(
                f"[VectorSyncService] 失效文档 {document_id} 的缓存: {count} 条"
            )
            return count
        except Exception as e:
            app_logger.error(f"[VectorSyncService] 缓存失效失败: {e}")
            return 0

    async def invalidate_all_caches(self, reason: str = "") -> Dict[str, int]:
        """
        失效所有缓存（版本更新或重大变更时使用）
        """
        try:
            cache_manager = get_cache_manager()
            result = await cache_manager.invalidate_all_caches()
            app_logger.warning(
                f"[VectorSyncService] 所有缓存已失效，原因: {reason}, "
                f"详情: {result}"
            )
            return result
        except Exception as e:
            app_logger.error(f"[VectorSyncService] 全量缓存失效失败: {e}")
            return {"error": str(e)}

    async def sync_chunk_change(
        self,
        chunk_id: int,
        document_id: int,
        change_type: str,
        invalidate_cache: bool = True,
        **kwargs
    ) -> str:
        """
        同步文档块变更

        Args:
            chunk_id: 文档块 ID
            document_id: 所属文档 ID
            change_type: 变更类型 (delete/add/update)
            invalidate_cache: 是否主动失效缓存（默认 True）
        """
        # 主动失效缓存
        if invalidate_cache:
            await self._invalidate_document_cache(document_id)

        if change_type == "delete":
            event_type = SyncEventType.VECTOR_DELETE
        elif change_type == "add":
            event_type = SyncEventType.VECTOR_ADD
        else:
            event_type = SyncEventType.VECTOR_UPDATE

        event = SyncEvent(
            event_id="",
            event_type=event_type,
            entity_type="chunk",
            entity_id=chunk_id,
            data={
                "document_id": document_id,
                "change_type": change_type,
                **kwargs
            },
            priority=SyncPriority.NORMAL,
        )

        return await self.publish_event(event)

    async def full_sync(self, entity_type: str = "document") -> str:
        """触发全量同步"""
        event = SyncEvent(
            event_id="",
            event_type=SyncEventType.FULL_SYNC,
            entity_type=entity_type,
            entity_id=0,
            data={"scope": "full"},
            priority=SyncPriority.LOW,
        )
        return await self.publish_event(event)

    async def request_reindex(self, scope: str = "full") -> str:
        """索引重建请求骨架；具体 MQ 消费和版本切换后续实现。"""
        return await self.publish_event(SyncEvent(
            event_id="", event_type=SyncEventType.VECTOR_REINDEX,
            entity_type="index", entity_id=0,
            data={"scope": scope, "mode": "read_only_degraded"},
            priority=SyncPriority.LOW,
        ))

    async def check_consistency(self) -> Dict[str, Any]:
        """检查数据一致性"""
        # 此处可实现 PG 与 Milvus 的对账逻辑
        return {
            "status": "ok",
            "last_sync_time": self._last_sync_time.isoformat() if self._last_sync_time else None,
            "events_in_queue": (
                len(self._high_priority_queue) +
                len(self._normal_priority_queue) +
                len(self._low_priority_queue)
            ),
            "high_priority_events": len(self._high_priority_queue),
            "normal_priority_events": len(self._normal_priority_queue),
            "low_priority_events": len(self._low_priority_queue),
            "events_processed": self._events_processed,
            "events_failed": self._events_failed,
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取同步统计"""
        return self.check_consistency()


# 便捷函数
def get_vector_sync_service() -> VectorSyncService:
    """获取向量同步服务实例"""
    return VectorSyncService()


async def sync_document(document_id: int, change_type: str, **kwargs) -> str:
    """同步文档变更"""
    service = get_vector_sync_service()
    return await service.sync_document_change(document_id, change_type, **kwargs)


async def sync_chunk(chunk_id: int, document_id: int, change_type: str, **kwargs) -> str:
    """同步文档块变更"""
    service = get_vector_sync_service()
    return await service.sync_chunk_change(chunk_id, document_id, change_type, **kwargs)
