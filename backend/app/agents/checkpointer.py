"""LangGraph Checkpointer 配置 - 支持 Redis 和 PostgreSQL 持久化"""
import json
from typing import Optional, Dict, Any, Tuple
from langgraph.checkpoint.base import BaseCheckpoint, CheckpointTuple
from langgraph.checkpoint.redis import RedisSaver
from app.core.config import settings
from app.core.cache_init import get_redis
from app.core.logger import app_logger


class RedisCheckpointer(RedisSaver):
    """基于Redis的Checkpointer"""

    def __init__(self):
        redis = get_redis()
        super().__init__(redis)


class AsyncCheckpointerAdapter:
    """异步Checkpointer适配器"""

    def __init__(self, checkpointer: Optional[BaseCheckpoint] = None):
        self._checkpointer = checkpointer or self._create_default_checkpointer()

    def _create_default_checkpointer(self) -> BaseCheckpoint:
        """创建默认的Checkpointer"""
        try:
            return RedisCheckpointer()
        except Exception as e:
            app_logger.warning(f"Redis Checkpointer 创建失败: {e}")
            return None

    @property
    def checkpointer(self) -> Optional[BaseCheckpoint]:
        """获取Checkpointer实例"""
        return self._checkpointer

    def save(self, thread_id: str, checkpoint: Dict[str, Any]) -> None:
        """保存检查点"""
        if self._checkpointer:
            try:
                self._checkpointer.put(thread_id, checkpoint)
                app_logger.debug(f"Checkpoint saved for thread: {thread_id}")
            except Exception as e:
                app_logger.error(f"Checkpoint save failed: {e}")

    def load(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """加载检查点"""
        if self._checkpointer:
            try:
                checkpoint_tuple = self._checkpointer.get(thread_id)
                if checkpoint_tuple:
                    return {
                        "values": checkpoint_tuple.values,
                        "next": checkpoint_tuple.next,
                        "metadata": checkpoint_tuple.metadata
                    }
            except Exception as e:
                app_logger.error(f"Checkpoint load failed: {e}")
        return None

    def exists(self, thread_id: str) -> bool:
        """检查检查点是否存在"""
        if self._checkpointer:
            try:
                return self._checkpointer.get(thread_id) is not None
            except Exception:
                return False
        return False


async_checkpointer = AsyncCheckpointerAdapter()


def get_checkpointer() -> Optional[BaseCheckpoint]:
    """获取Checkpointer实例"""
    return async_checkpointer.checkpointer
