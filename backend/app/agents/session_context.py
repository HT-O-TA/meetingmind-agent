"""会话上下文管理 - 统一四层 ID 体系

ID 分层设计：
  层级1: user_id         用户身份（JWT Token）
  层级2: session_id      浏览器会话（前端生成，uuid4）
  层级3: thread_id       Agent 对话线程（user_id:session_id:conversation_id）
  层级4: meeting_id      业务域（数据库主键）
  任务级: task_id         用户显式指定的任务标识（可选）
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
    通过 thread_id = f"{user_id}:{session_id}:{conversation_id}" 确保跨用户状态隔离。
    """

    user_id: Optional[int] = None
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    meeting_id: Optional[int] = None
    task_id: Optional[str] = None
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
        格式: user_id:session_id:conversation_id
        确保不同用户与不同对话同时隔离
        """
        owner = str(self.user_id) if self.user_id is not None else "anonymous"
        return f"{owner}:{self.session_id}:{self.conversation_id}"

    @staticmethod
    def parse_thread_id(thread_id: str) -> tuple:
        """解析 thread_id 为 (session_id, conversation_id)，并兼容旧两段格式。"""
        if not thread_id:
            return ("default", "default")
        parts = thread_id.split(":")
        if len(parts) >= 3:
            return (parts[-2], parts[-1])
        if len(parts) == 2:
            return (parts[0], parts[1])
        return (thread_id, "default")

    def to_hitl_key(self) -> str:
        """生成人机协作 Key"""
        return f"hitl:thread:{self.thread_id}"

    def get_config(self, run_id: Optional[str] = None) -> dict:
        """转换为 LangGraph config 格式。

        ``thread_id`` is the durable conversation key and must live inside
        ``configurable`` for LangGraph checkpointers.  The top-level copy is
        retained for older callers.  ``run_id`` identifies one execution and
        must not be used as the thread key.
        """
        return {
            "thread_id": self.thread_id,
            "configurable": {
                "thread_id": self.thread_id,
                "run_id": run_id,
                # A new run gets its own namespace so a fresh user query does
                # not accidentally inherit the previous run's task state.
                "checkpoint_ns": run_id or "",
                "user_id": self.user_id,
                "session_id": self.session_id,
                "conversation_id": self.conversation_id,
                "meeting_id": self.meeting_id,
                "task_id": self.task_id,
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
            "task_id": self.task_id,
        }

    @classmethod
    def from_config(cls, config: dict) -> "SessionContext":
        """从 LangGraph config 重建 SessionContext"""
        configurable = config.get("configurable", {})
        thread_id = config.get("thread_id") or configurable.get("thread_id", "")

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
            task_id=configurable.get("task_id"),
            access_scope=configurable.get("access_scope"),
        )
