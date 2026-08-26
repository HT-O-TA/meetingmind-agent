"""LangGraph Checkpointer 配置。

当前只提供与锁定版本兼容的进程内 MemorySaver。持久化 Redis/PostgreSQL
Checkpointer 必须在阶段 3 以恢复、并发和过期测试重新接入，不能继续沿用旧 API。
"""

from typing import Optional

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver


_checkpointer: Optional[BaseCheckpointSaver] = None


def get_checkpointer() -> BaseCheckpointSaver:
    """返回进程级 Checkpointer；仅在调用方显式启用时参与图编译。"""
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = MemorySaver()
    return _checkpointer


def reset_checkpointer() -> None:
    """清空进程级实例，供隔离测试使用。"""
    global _checkpointer
    _checkpointer = None
