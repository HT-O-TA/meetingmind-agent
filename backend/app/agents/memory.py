"""有界会话记忆。

仅保存当前进程内、当前 session 最近若干轮对话，用于连续追问。
不承担长期知识库、跨用户画像、反思样本库或检查点持久化职责。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List


@dataclass
class ConversationTurn:
    question: str
    answer: str
    timestamp: str


class ShortTermMemory:
    """固定窗口的会话记录，超出上限后丢弃最早内容。"""

    def __init__(self, max_raw_turns: int = 10):
        self.max_raw_turns = max(1, max_raw_turns)
        self.raw_turns: List[Dict[str, Any]] = []

    def add_turn(self, question: str, answer: str, **_: Any) -> None:
        turn = ConversationTurn(
            question=question.strip(),
            answer=answer.strip(),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self.raw_turns.append(asdict(turn))
        del self.raw_turns[:-self.max_raw_turns]

    def get_recent_turns(self, limit: int = 3) -> List[Dict[str, Any]]:
        return self.raw_turns[-max(0, limit):]

    def get_summary(self) -> Dict[str, int]:
        return {"raw_turns": len(self.raw_turns), "max_turns": self.max_raw_turns}

    def clear(self) -> None:
        self.raw_turns.clear()


class MemoryManager:
    """按 session 使用的轻量短期记忆适配器。"""

    def __init__(self, max_short_term_turns: int = 10):
        self.short_term = ShortTermMemory(max_raw_turns=max_short_term_turns)

    def add_conversation(self, question: str, answer: str, **kwargs: Any) -> None:
        self.short_term.add_turn(question, answer, **kwargs)

    def add_exchange(self, question: str, answer: str) -> None:
        self.add_conversation(question, answer)

    def get_context_for_query(self, _query: str, n_recent: int = 3) -> str:
        turns = self.short_term.get_recent_turns(n_recent)
        return "\n".join(
            line
            for turn in turns
            for line in (f"问: {turn['question']}", f"答: {turn['answer']}")
        )

    def get_memory_stats(self) -> Dict[str, Any]:
        return {"short_term": self.short_term.get_summary()}

    def clear_all(self) -> None:
        self.short_term.clear()
