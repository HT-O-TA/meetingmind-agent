"""RabbitMQ 可靠投递、有限重试和死信拓扑。"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, Optional

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, IncomingMessage, Message
from aio_pika.abc import AbstractChannel, AbstractRobustConnection

from app.core.config import settings

logger = logging.getLogger(__name__)

MessageCallback = Callable[[Dict[str, Any]], Awaitable[Any]]
FailureCallback = Callable[[Dict[str, Any], int, str, bool], Awaitable[None]]


@dataclass
class QueueTopology:
    main: aio_pika.Queue
    retry: aio_pika.Queue
    dead: aio_pika.Queue


@dataclass
class ConsumerHandle:
    queue: aio_pika.Queue
    channel: AbstractChannel
    consumer_tag: str

    async def close(self) -> None:
        if not self.channel.is_closed:
            await self.queue.cancel(self.consumer_tag)
            await self.channel.close()


class RabbitMQManager:
    """每个实例拥有自己的 robust connection，发布默认启用 confirms。"""

    def __init__(self, url: Optional[str] = None) -> None:
        self.url = url or settings.RABBITMQ_URL
        self.connection_max_retries = settings.RABBITMQ_MAX_RETRIES
        self.connection_retry_delay = settings.RABBITMQ_RETRY_DELAY
        self.task_max_retries = settings.QUEUE_MAX_RETRIES
        self.retry_delay_seconds = settings.QUEUE_RETRY_DELAY_SECONDS
        self.task_timeout_seconds = settings.QUEUE_TASK_TIMEOUT
        self.max_queue_length = settings.QUEUE_MAX_LENGTH
        self.dlx_name = settings.QUEUE_DLX_NAME
        self._connection: Optional[AbstractRobustConnection] = None
        self._connection_lock = asyncio.Lock()
        self._publisher_lock = asyncio.Lock()
        self._topology_lock = asyncio.Lock()
        self._publisher_channel: Optional[AbstractChannel] = None
        self._declared_topologies: set[str] = set()
        self._consumer_handles: list[ConsumerHandle] = []

    @staticmethod
    def retry_queue_name(queue_name: str) -> str:
        return f"{queue_name}.retry"

    @staticmethod
    def dead_queue_name(queue_name: str) -> str:
        return f"{queue_name}.dead"

    async def connect(self) -> AbstractRobustConnection:
        async with self._connection_lock:
            if self._connection is None or self._connection.is_closed:
                logger.info("Connecting to RabbitMQ: %s", self._redacted_url())
                for attempt in range(self.connection_max_retries):
                    try:
                        self._connection = await aio_pika.connect_robust(
                            self.url,
                            timeout=settings.RABBITMQ_CONNECT_TIMEOUT_SECONDS,
                            reconnect_interval=5,
                            fail_fast=True,
                        )
                        break
                    except Exception:
                        logger.warning(
                            "RabbitMQ connection attempt %s/%s failed",
                            attempt + 1,
                            self.connection_max_retries,
                        )
                        if attempt + 1 >= self.connection_max_retries:
                            raise
                        await asyncio.sleep(self.connection_retry_delay)
                logger.info("RabbitMQ connection established")
        return self._connection

    def _redacted_url(self) -> str:
        try:
            from urllib.parse import urlsplit, urlunsplit

            parsed = urlsplit(self.url)
            hostname = parsed.hostname or ""
            port = f":{parsed.port}" if parsed.port else ""
            user = f"{parsed.username}:***@" if parsed.username else ""
            return urlunsplit((parsed.scheme, f"{user}{hostname}{port}", parsed.path, "", ""))
        except Exception:
            return "[invalid RabbitMQ URL]"

    async def get_server_properties(self) -> Dict[str, Any]:
        connection = await self.connect()
        transport = getattr(connection, "transport", None)
        protocol = getattr(transport, "connection", None)
        properties = getattr(protocol, "server_properties", {}) or {}
        return {
            "product": properties.get("product"),
            "version": properties.get("version"),
            "platform": properties.get("platform"),
        }

    async def close(self) -> None:
        handles, self._consumer_handles = self._consumer_handles, []
        for handle in handles:
            try:
                await handle.close()
            except Exception as exc:
                logger.warning("Closing RabbitMQ consumer failed: %s", exc)
        if self._publisher_channel and not self._publisher_channel.is_closed:
            await self._publisher_channel.close()
        self._publisher_channel = None
        self._declared_topologies.clear()
        async with self._connection_lock:
            if self._connection and not self._connection.is_closed:
                await self._connection.close()
            self._connection = None

    async def get_channel(self, *, publisher_confirms: bool = True) -> AbstractChannel:
        connection = await self.connect()
        return await connection.channel(
            publisher_confirms=publisher_confirms,
            on_return_raises=publisher_confirms,
        )

    async def _get_publisher_channel(self) -> AbstractChannel:
        async with self._publisher_lock:
            if self._publisher_channel is None or self._publisher_channel.is_closed:
                self._publisher_channel = await self.get_channel(publisher_confirms=True)
                self._declared_topologies.clear()
            return self._publisher_channel

    async def _ensure_topology(
        self, queue_name: str, channel: AbstractChannel
    ) -> None:
        if queue_name in self._declared_topologies:
            return
        async with self._topology_lock:
            if queue_name not in self._declared_topologies:
                await self.declare_topology(queue_name, channel=channel)
                self._declared_topologies.add(queue_name)

    async def declare_topology(
        self,
        queue_name: str,
        *,
        channel: Optional[AbstractChannel] = None,
    ) -> QueueTopology:
        """声明 main/retry/dead，所有队列持久化且主队列溢出时拒绝新发布。"""
        owns_channel = channel is None
        channel = channel or await self.get_channel()
        try:
            dlx = await channel.declare_exchange(
                self.dlx_name,
                ExchangeType.DIRECT,
                durable=True,
            )
            dead_name = self.dead_queue_name(queue_name)
            dead = await channel.declare_queue(dead_name, durable=True)
            await dead.bind(dlx, routing_key=dead_name)

            retry_name = self.retry_queue_name(queue_name)
            retry = await channel.declare_queue(
                retry_name,
                durable=True,
                arguments={
                    "x-message-ttl": int(self.retry_delay_seconds * 1000),
                    "x-dead-letter-exchange": "",
                    "x-dead-letter-routing-key": queue_name,
                },
            )

            main = await channel.declare_queue(
                queue_name,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": self.dlx_name,
                    "x-dead-letter-routing-key": dead_name,
                    "x-max-length": self.max_queue_length,
                    "x-overflow": "reject-publish",
                },
            )
            return QueueTopology(main=main, retry=retry, dead=dead)
        except Exception:
            if owns_channel and not channel.is_closed:
                await channel.close()
            raise

    def _message(
        self,
        message_body: Dict[str, Any],
        *,
        priority: int,
        headers: Optional[Dict[str, Any]],
    ) -> Message:
        task_id = str(message_body.get("task_id") or "") or None
        return Message(
            body=json.dumps(message_body, ensure_ascii=False, default=str).encode("utf-8"),
            delivery_mode=DeliveryMode.PERSISTENT,
            priority=priority,
            headers=headers or {},
            content_type="application/json",
            content_encoding="utf-8",
            message_id=task_id,
            correlation_id=task_id,
            timestamp=datetime.now(timezone.utc),
        )

    async def _confirmed_publish(
        self,
        channel: AbstractChannel,
        message: Message,
        routing_key: str,
    ) -> None:
        await asyncio.wait_for(
            channel.default_exchange.publish(
                message,
                routing_key=routing_key,
                mandatory=True,
            ),
            timeout=settings.RABBITMQ_PUBLISH_TIMEOUT_SECONDS,
        )

    async def publish_message(
        self,
        queue_name: str,
        message_body: Dict[str, Any],
        priority: int = 0,
        headers: Optional[Dict[str, Any]] = None,
    ) -> str:
        """在 publisher confirm channel 上强制路由；未路由或 broker nack 会抛错。"""
        channel = await self._get_publisher_channel()
        await self._ensure_topology(queue_name, channel)
        await self._confirmed_publish(
            channel,
            self._message(
                message_body,
                priority=priority,
                headers={"x-retry-count": 0, **(headers or {})},
            ),
            queue_name,
        )
        logger.debug("Message confirmed by RabbitMQ queue=%s task_id=%s", queue_name, message_body.get("task_id"))
        return queue_name

    async def _publish_retry(
        self,
        queue_name: str,
        message_body: Dict[str, Any],
        headers: Dict[str, Any],
    ) -> None:
        channel = await self._get_publisher_channel()
        await self._ensure_topology(queue_name, channel)
        await self._confirmed_publish(
            channel,
            self._message(message_body, priority=0, headers=headers),
            self.retry_queue_name(queue_name),
        )

    async def _publish_dead(
        self,
        queue_name: str,
        message_body: Dict[str, Any],
        headers: Dict[str, Any],
    ) -> None:
        channel = await self._get_publisher_channel()
        await self._ensure_topology(queue_name, channel)
        await self._confirmed_publish(
            channel,
            self._message(message_body, priority=0, headers=headers),
            self.dead_queue_name(queue_name),
        )

    @staticmethod
    async def _notify_failure(
        failure_callback: Optional[FailureCallback],
        body: Dict[str, Any],
        retry_count: int,
        error: str,
        dead_lettered: bool,
    ) -> None:
        """状态回写失败不能破坏已经完成的 broker 确认流程。"""
        if not failure_callback:
            return
        try:
            await failure_callback(body, retry_count, error, dead_lettered)
        except Exception:
            logger.exception(
                "Failure callback failed task_id=%s dead_lettered=%s",
                body.get("task_id"),
                dead_lettered,
            )

    async def _process_delivery(
        self,
        queue_name: str,
        message: IncomingMessage,
        callback: MessageCallback,
        failure_callback: Optional[FailureCallback],
    ) -> None:
        try:
            body = json.loads(message.body.decode("utf-8"))
            if not isinstance(body, dict) or not body.get("task_id"):
                raise ValueError("消息必须是包含 task_id 的 JSON 对象")
        except Exception as exc:
            logger.error("Malformed RabbitMQ message queue=%s: %s", queue_name, exc)
            await message.reject(requeue=False)
            return

        retry_count = int((message.headers or {}).get("x-retry-count", 0))
        try:
            await asyncio.wait_for(callback(body), timeout=self.task_timeout_seconds)
        except Exception as exc:
            error = f"{exc.__class__.__name__}: {exc}"
            if retry_count < self.task_max_retries:
                next_retry = retry_count + 1
                headers = dict(message.headers or {})
                headers.update(
                    {
                        "x-retry-count": next_retry,
                        "x-last-error": error[:500],
                    }
                )
                try:
                    await self._publish_retry(queue_name, body, headers)
                except Exception:
                    # 重试消息未获 broker confirm，保留原消息供连接恢复后再次投递。
                    await message.nack(requeue=True)
                    raise
                await message.ack()
                await self._notify_failure(
                    failure_callback, body, next_retry, error, False
                )
                logger.warning(
                    "Task scheduled for retry queue=%s task_id=%s retry=%s/%s",
                    queue_name,
                    body.get("task_id"),
                    next_retry,
                    self.task_max_retries,
                )
                return

            dead_headers = dict(message.headers or {})
            dead_headers.update(
                {
                    "x-dead-letter-reason": "retry_exhausted",
                    "x-last-error": error[:500],
                }
            )
            try:
                await self._publish_dead(queue_name, body, dead_headers)
            except Exception:
                await message.nack(requeue=True)
                raise
            await message.ack()
            await self._notify_failure(
                failure_callback, body, retry_count, error, True
            )
            logger.error(
                "Task moved to confirmed dead queue=%s task_id=%s attempts=%s",
                queue_name,
                body.get("task_id"),
                retry_count + 1,
            )
            return

        await message.ack()

    async def consume_messages(
        self,
        queue_name: str,
        callback: MessageCallback,
        prefetch_count: Optional[int] = None,
        failure_callback: Optional[FailureCallback] = None,
    ) -> ConsumerHandle:
        channel = await self.get_channel(publisher_confirms=False)
        await channel.set_qos(prefetch_count=prefetch_count or settings.QUEUE_PREFETCH_COUNT)
        topology = await self.declare_topology(queue_name, channel=channel)

        async def process(message: IncomingMessage) -> None:
            await self._process_delivery(
                queue_name,
                message,
                callback,
                failure_callback,
            )

        consumer_tag = await topology.main.consume(process, no_ack=False)
        handle = ConsumerHandle(topology.main, channel, consumer_tag)
        self._consumer_handles.append(handle)
        logger.info("Started consuming queue=%s prefetch=%s", queue_name, prefetch_count or settings.QUEUE_PREFETCH_COUNT)
        return handle

    async def delete_topology(self, queue_name: str) -> None:
        """仅供使用唯一测试队列名的集成测试清理。"""
        async with self.get_channel_context() as channel:
            for name in (
                queue_name,
                self.retry_queue_name(queue_name),
                self.dead_queue_name(queue_name),
            ):
                await channel.queue_delete(name, if_unused=False, if_empty=False)
        self._declared_topologies.discard(queue_name)

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[AbstractRobustConnection, None]:
        yield await self.connect()

    @asynccontextmanager
    async def get_channel_context(self) -> AsyncGenerator[AbstractChannel, None]:
        channel = await self.get_channel()
        try:
            yield channel
        finally:
            if not channel.is_closed:
                await channel.close()


rabbitmq_manager = RabbitMQManager()


async def get_rabbitmq() -> RabbitMQManager:
    return rabbitmq_manager


async def init_rabbitmq() -> None:
    await rabbitmq_manager.connect()


async def close_rabbitmq() -> None:
    await rabbitmq_manager.close()
