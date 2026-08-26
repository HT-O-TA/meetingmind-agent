"""会话上下文管理 - 统一四层 ID 体系

ID 分层设计：
  层级1: user_id         用户身份（JWT Token）
  层级2: session_id      浏览器会话（前端生成，uuid4）
  层级3: thread_id       Agent 对话线程（session_id:conversation_id）
  层级4: meeting_id      业务域（数据库主键）
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import uuid
import re


def generate_session_id() -> str:
    """生成 session_id"""
    return f"sess_{uuid.uuid4().hex[:12]}"


def generate_conversation_id() -> str:
    """生成 conversation_id"""
    return f"conv_{uuid.uuid4().hex[:8]}"


@dataclass
class SessionContext:
    """统一的会话上下文管理

    封装四层 ID，确保会话隔离和业务过滤的正确性。
    通过 thread_id = f"{session_id}:{conversation_id}" 确保 LangGraph 状态唯一。
    """

    user_id: Optional[int] = None
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    meeting_id: Optional[int] = None
    access_scope: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if not self.session_id:
            self.session_id = generate_session_id()
        if not self.conversation_id:
            self.conversation_id = generate_conversation_id()

    @property
    def thread_id(self) -> str:
        """
        生成 LangGraph thread_id
        格式: session_id:conversation_id
        确保同一浏览器标签页的不同对话隔离
        """
        return f"{self.session_id}:{self.conversation_id}"

    @staticmethod
    def parse_thread_id(thread_id: str) -> tuple:
        """解析 thread_id 为 (session_id, conversation_id)"""
        if not thread_id:
            return ("default", "default")
        if ":" in thread_id:
            parts = thread_id.split(":", 1)
            return (parts[0], parts[1])
        return (thread_id, "default")

    def to_redis_key(self) -> str:
        """生成 Redis 缓存 Key（会话级）"""
        base = f"session:{self.session_id}"
        if self.meeting_id:
            base += f":meeting:{self.meeting_id}"
        return base

    def to_checkpointer_key(self) -> str:
        """生成 Checkpointer Key"""
        return f"checkpoint:{self.thread_id}"

    def to_memory_key(self) -> str:
        """生成记忆系统 Key"""
        return f"memory:{self.session_id}"

    def to_short_term_key(self) -> str:
        """生成短期记忆 Key"""
        return f"memory:{self.session_id}:short_term"

    def to_long_term_key(self) -> str:
        """生成长期记忆 Key（按会议）"""
        if self.meeting_id:
            return f"memory:{self.session_id}:meeting:{self.meeting_id}:long_term"
        return f"memory:{self.session_id}:long_term"

    def to_hitl_key(self) -> str:
        """生成人机协作 Key"""
        return f"hitl:thread:{self.thread_id}"

    def get_config(self) -> dict:
        """转换为 LangGraph config 格式"""
        return {
            "thread_id": self.thread_id,
            "configurable": {
                "user_id": self.user_id,
                "session_id": self.session_id,
                "conversation_id": self.conversation_id,
                "meeting_id": self.meeting_id,
                "access_scope": self.access_scope,
            }
        }

    def to_dict(self) -> dict:
        """转换为字典（用于 API 响应）"""
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "conversation_id": self.conversation_id,
            "thread_id": self.thread_id,
            "meeting_id": self.meeting_id,
        }

    @classmethod
    def from_config(cls, config: dict) -> "SessionContext":
        """从 LangGraph config 重建 SessionContext"""
        configurable = config.get("configurable", {})
        thread_id = config.get("thread_id", "")

        session_id = configurable.get("session_id")
        conversation_id = configurable.get("conversation_id")

        if not session_id or not conversation_id:
            parsed_session, parsed_conv = cls.parse_thread_id(thread_id)
            session_id = session_id or parsed_session
            conversation_id = conversation_id or parsed_conv

        return cls(
            user_id=configurable.get("user_id"),
            session_id=session_id,
            conversation_id=conversation_id,
            meeting_id=configurable.get("meeting_id"),
            access_scope=configurable.get("access_scope"),
        )
