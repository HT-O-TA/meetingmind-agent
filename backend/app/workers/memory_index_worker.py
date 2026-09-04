"""长期记忆索引消费者。

消费者只定义同步边界，不把 Milvus/Neo4j 客户端硬编码进主链。生产启动时注入
实现了 ``upsert``/``delete`` 的投影器即可；投影失败会交给 RabbitMQ 重试和死信。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from app.core.config import settings
from app.core.rabbitmq import rabbitmq_manager
from app.services.memory_repository import MemoryRepository

logger = logging.getLogger(__name__)


class MemoryIndexProjector:
    def __init__(self, *, milvus: Optional[Any] = None, neo4j: Optional[Any] = None):
        self.milvus = milvus
        self.neo4j = neo4j

    async def __call__(self, body: dict) -> dict:
        operation = body.get("operation", "upsert")
        if operation == "delete":
            method = "delete"
        else:
            method = "upsert"
        payload = body.get("payload") or body
        if self.milvus is None and self.neo4j is None:
            raise RuntimeError("未配置 Milvus 或 Neo4j 记忆索引投影器，拒绝确认消息")
        for sink in (self.milvus, self.neo4j):
            if sink is not None:
                handler = getattr(sink, method, None)
                if handler is None:
                    raise RuntimeError(f"记忆索引投影器缺少 {method} 方法")
                result = handler(payload)
                if hasattr(result, "__await__"):
                    await result
        return {"event_id": body.get("event_id"), "operation": operation, "projected": True}


async def start_memory_index_worker(
    *,
    projector: Optional[MemoryIndexProjector] = None,
    failure_callback=None,
):
    """启动 RabbitMQ 消费者；未配置投影器时仍可用于链路演练。"""

    return await rabbitmq_manager.consume_messages(
        settings.QUEUE_MEMORY_INDEX,
        projector or MemoryIndexProjector(),
        failure_callback=failure_callback,
    )


async def publish_outbox_loop(stop_event: asyncio.Event) -> None:
    """后台投递 PG outbox；数据库不可用时保留事件，下一轮继续。"""

    repository = MemoryRepository()
    while not stop_event.is_set():
        try:
            await repository.publish_pending_events()
        except Exception as exc:
            # 不在这里吞掉事件；下一轮会继续尝试，运维可从日志/指标发现异常。
            logger.warning("长期记忆 outbox 发布失败，将在下一轮重试: %s", exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(0.2, settings.MEMORY_OUTBOX_PUBLISH_INTERVAL_SECONDS))
        except asyncio.TimeoutError:
            continue


__all__ = ["MemoryIndexProjector", "start_memory_index_worker", "publish_outbox_loop"]
