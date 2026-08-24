"""RabbitMQ 连接管理模块"""
import asyncio
import logging
from typing import Optional, AsyncGenerator
from contextlib import asynccontextmanager
import aio_pika
from aio_pika import Connection, Channel, Message, DeliveryMode
from aio_pika.abc import AbstractRobustConnection
from app.core.config import settings

logger = logging.getLogger(__name__)

# 全局连接实例
_connection: Optional[AbstractRobustConnection] = None
_connection_lock = asyncio.Lock()


class RabbitMQManager:
    """RabbitMQ 连接管理器"""
    
    def __init__(self):
        self.url = settings.RABBITMQ_URL
        self.pool_size = settings.RABBITMQ_POOL_SIZE
        self.max_retries = settings.RABBITMQ_MAX_RETRIES
        self.retry_delay = settings.RABBITMQ_RETRY_DELAY
    
    async def connect(self) -> AbstractRobustConnection:
        """建立 RabbitMQ 连接"""
        global _connection
        
        async with _connection_lock:
            if _connection is None or _connection.is_closed:
                logger.info(f"Connecting to RabbitMQ: {self.url}")
                for attempt in range(self.max_retries):
                    try:
                        _connection = await aio_pika.connect_robust(
                            self.url,
                            timeout=30,
                            reconnect_interval=5,
                            fail_fast=False
                        )
                        logger.info("RabbitMQ connection established")
                        break
                    except Exception as e:
                        logger.warning(f"RabbitMQ connection attempt {attempt + 1} failed: {e}")
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(self.retry_delay)
                        else:
                            raise
        
        return _connection
    
    async def close(self):
        """关闭 RabbitMQ 连接"""
        global _connection
        
        async with _connection_lock:
            if _connection and not _connection.is_closed:
                await _connection.close()
                _connection = None
                logger.info("RabbitMQ connection closed")
    
    async def get_channel(self) -> Channel:
        """获取一个 channel"""
        connection = await self.connect()
        return await connection.channel()
    
    async def declare_queue(self, queue_name: str, durable: bool = True) -> aio_pika.Queue:
        """声明一个队列"""
        channel = await self.get_channel()
        return await channel.declare_queue(
            queue_name,
            durable=durable,
            arguments={
                'x-message-ttl': settings.QUEUE_TASK_TIMEOUT * 1000,  # 消息过期时间
                'x-max-length': 10000,  # 队列最大消息数
            }
        )
    
    async def publish_message(
        self,
        queue_name: str,
        message_body: dict,
        priority: int = 0,
        headers: Optional[dict] = None
    ) -> str:
        """发布消息到队列"""
        channel = await self.get_channel()
        
        # 确保队列存在
        queue = await self.declare_queue(queue_name)
        
        # 创建消息
        import json as _json
        message = Message(
            body=_json.dumps(message_body).encode(),
            delivery_mode=DeliveryMode.PERSISTENT,
            priority=priority,
            headers=headers or {},
            content_type='application/json'
        )
        
        # 发布消息
        await channel.default_exchange.publish(
            message,
            routing_key=queue_name
        )
        
        logger.info(f"Message published to queue '{queue_name}'")
        return queue_name
    
    async def consume_messages(
        self,
        queue_name: str,
        callback,
        prefetch_count: int = None
    ) -> aio_pika.Queue:
        """消费队列中的消息"""
        channel = await self.get_channel()
        
        # 设置 QoS
        await channel.set_qos(prefetch_count or settings.QUEUE_PREFETCH_COUNT)
        
        # 确保队列存在
        queue = await self.declare_queue(queue_name)
        
        # 开始消费
        await queue.consume(callback)
        
        logger.info(f"Started consuming from queue '{queue_name}'")
        return queue
    
    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[AbstractRobustConnection, None]:
        """上下文管理器：获取连接"""
        connection = await self.connect()
        try:
            yield connection
        finally:
            pass  # 连接由管理器统一管理，不在这里关闭
    
    @asynccontextmanager
    async def get_channel_context(self) -> AsyncGenerator[Channel, None]:
        """上下文管理器：获取 channel"""
        channel = await self.get_channel()
        try:
            yield channel
        finally:
            await channel.close()


# 全局单例
rabbitmq_manager = RabbitMQManager()


# 便捷函数
async def get_rabbitmq() -> RabbitMQManager:
    """获取 RabbitMQ 管理器实例"""
    return rabbitmq_manager


async def init_rabbitmq():
    """初始化 RabbitMQ 连接"""
    try:
        await rabbitmq_manager.connect()
        logger.info("RabbitMQ initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize RabbitMQ: {e}")
        raise


async def close_rabbitmq():
    """关闭 RabbitMQ 连接"""
    await rabbitmq_manager.close()
    logger.info("RabbitMQ closed")
