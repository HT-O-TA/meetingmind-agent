"""有界会话记忆。

仅保存当前进程内、当前 session 最近若干轮对话，用于连续追问。
不承担长期知识库、跨用户画像、反思样本库或检查点持久化职责。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from collections import OrderedDict
import hashlib
import math
import re
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_memory_text(value: Any, max_chars: int) -> str:
    """写入前做轻量清洗，避免把控制字符、整段日志和超长正文带入记忆。"""
    text = str(value or "").replace("\x00", "")
    text = re.sub(r"[\u0001-\u0008\u000b\u000c\u000e-\u001f]", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:max_chars]


@dataclass
class MemoryRecord:
    """可审计的记忆条目；事实、决定和反思不能混成一种文本。"""

    record_id: str
    namespace: str
    kind: str
    text: str
    created_at: str
    source: str = "user"
    key: Optional[str] = None
    value: Optional[str] = None
    confidence: float = 0.5
    importance: float = 0.5
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    supersedes: Optional[str] = None
    status: str = "active"
    metadata: Optional[Dict[str, Any]] = None


class MemoryWriteGate:
    """确定性写入门禁：只接收有边界的最终结果，不接收 CoT/工具原始日志。"""

    MAX_QUESTION_CHARS = 1200
    MAX_ANSWER_CHARS = 3000
    ALLOWED_KINDS = {"conversation", "fact", "decision"}
    BLOCKED_FIELDS = {"cot", "chain_of_thought", "tool_log", "raw_tool_output", "prompt"}

    @classmethod
    def conversation(cls, question: Any, answer: Any) -> Optional[Dict[str, str]]:
        q = _clean_memory_text(question, cls.MAX_QUESTION_CHARS)
        a = _clean_memory_text(answer, cls.MAX_ANSWER_CHARS)
        if not q or not a:
            return None
        return {"question": q, "answer": a}

    @classmethod
    def metadata(cls, metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(metadata, dict):
            return {}
        return {
            str(key): value
            for key, value in metadata.items()
            if str(key).lower() not in cls.BLOCKED_FIELDS
            and isinstance(value, (str, int, float, bool, type(None)))
        }


@dataclass
class ConversationTurn:
    question: str
    answer: str
    timestamp: str
    namespace: str = "default"


class ShortTermMemory:
    """固定窗口的会话记录，超出上限后丢弃最早内容。"""

    def __init__(self, max_raw_turns: int = 10):
        self.max_raw_turns = max(1, max_raw_turns)
        self.raw_turns: List[Dict[str, Any]] = []

    def add_turn(self, question: str, answer: str, *, namespace: str = "default", **_: Any) -> bool:
        prepared = MemoryWriteGate.conversation(question, answer)
        if prepared is None:
            return False
        turn = ConversationTurn(
            question=prepared["question"],
            answer=prepared["answer"],
            timestamp=_now_iso(),
            namespace=str(namespace or "default"),
        )
        self.raw_turns.append(asdict(turn))
        del self.raw_turns[:-self.max_raw_turns]
        return True

    def get_recent_turns(self, limit: int = 3, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        turns = self.raw_turns
        if namespace:
            turns = [turn for turn in turns if turn.get("namespace", "default") == namespace]
        return turns[-max(0, limit):]

    def get_summary(self) -> Dict[str, int]:
        return {"raw_turns": len(self.raw_turns), "max_turns": self.max_raw_turns}

    def clear(self) -> None:
        self.raw_turns.clear()


class MemoryManager:
    """按 session 使用的轻量短期记忆适配器。"""

    def __init__(self, max_short_term_turns: int = 10):
        self.short_term = ShortTermMemory(max_raw_turns=max_short_term_turns)
        self.active_namespace = "default"
        self.records: List[MemoryRecord] = []

    @staticmethod
    def _is_follow_up(question: str) -> bool:
        text = _clean_memory_text(question, 200)
        return len(text) <= 18 or bool(re.match(r"^(那|然后|接着|继续|它|这个|刚才|上面|所以|还有|另外)", text))

    def resolve_task_namespace(
        self,
        question: str,
        *,
        task_id: Optional[str] = None,
        meeting_id: Optional[int] = None,
        document_ids: Optional[List[int]] = None,
    ) -> str:
        """为当前问题选择任务空间；短追问沿用当前空间，明显新问题开启新空间。"""
        if task_id:
            basis = f"explicit:{_clean_memory_text(task_id, 128)}|meeting:{meeting_id}|docs:{sorted(document_ids or [])}"
            return "task_" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
        if self.active_namespace != "default" and self._is_follow_up(question):
            return self.active_namespace
        basis = f"{_clean_memory_text(question, 1200).casefold()}|meeting:{meeting_id}|docs:{sorted(document_ids or [])}"
        return "task_" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]

    def set_active_namespace(self, namespace: str) -> None:
        self.active_namespace = str(namespace or "default")

    def add_conversation(self, question: str, answer: str, **kwargs: Any) -> bool:
        namespace = str(kwargs.pop("namespace", self.active_namespace) or "default")
        accepted = self.short_term.add_turn(question, answer, namespace=namespace, **kwargs)
        if accepted:
            prepared = MemoryWriteGate.conversation(question, answer)
            assert prepared is not None
            self.records.append(
                MemoryRecord(
                    record_id=f"conversation_{hashlib.sha256((namespace + prepared['question'] + prepared['answer']).encode('utf-8')).hexdigest()[:16]}",
                    namespace=namespace,
                    kind="conversation",
                    text=f"问: {prepared['question']} 答: {prepared['answer']}",
                    created_at=_now_iso(),
                    source="user",
                    importance=0.4,
                    metadata={"write_policy": "conversation_final_only"},
                )
            )
            self.records = self.records[-max(20, self.short_term.max_raw_turns * 2):]
        return accepted

    def add_exchange(self, question: str, answer: str, **kwargs: Any) -> bool:
        return self.add_conversation(question, answer, **kwargs)

    def get_context_for_query(self, _query: str, n_recent: int = 3, namespace: Optional[str] = None) -> str:
        turns = self.short_term.get_recent_turns(n_recent, namespace=namespace)
        return "\n".join(
            line
            for turn in turns
            for line in (f"问: {turn['question']}", f"答: {turn['answer']}")
        )

    def get_context_items_for_query(self, _query: str, n_recent: int = 3, namespace: Optional[str] = None) -> List[str]:
        """按最近优先返回独立轮次，便于组装器逐项预算和丢弃旧内容。"""
        turns = reversed(self.short_term.get_recent_turns(n_recent, namespace=namespace))
        return [
            f"【会话轮次】\n问: {turn['question']}\n答: {turn['answer']}"
            for turn in turns
        ]

    def add_fact(
        self,
        *,
        namespace: str,
        key: str,
        value: str,
        source: str = "user",
        confidence: float = 0.8,
        importance: float = 0.7,
        valid_until: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[MemoryRecord]:
        """写入结构化事实；同一 key 的新事实会标记旧事实为 superseded。"""
        clean_key = _clean_memory_text(key, 120)
        clean_value = _clean_memory_text(value, 800)
        if not clean_key or not clean_value:
            return None
        if not (0.0 <= confidence <= 1.0 and 0.0 <= importance <= 1.0):
            raise ValueError("confidence/importance 必须位于 [0,1]")
        previous = next(
            (
                item
                for item in reversed(self.records)
                if item.namespace == namespace and item.kind == "fact" and item.key == clean_key and item.status == "active"
            ),
            None,
        )
        if previous and previous.value == clean_value:
            return previous
        if previous:
            previous.status = "superseded"
            previous.valid_until = _now_iso()
        record = MemoryRecord(
            record_id=f"fact_{hashlib.sha256(f'{namespace}:{clean_key}:{clean_value}:{_now_iso()}'.encode('utf-8')).hexdigest()[:16]}",
            namespace=namespace,
            kind="fact",
            text=f"{clean_key}: {clean_value}",
            created_at=_now_iso(),
            source=source,
            key=clean_key,
            value=clean_value,
            confidence=confidence,
            importance=importance,
            valid_from=_now_iso(),
            valid_until=valid_until,
            supersedes=previous.record_id if previous else None,
            metadata=MemoryWriteGate.metadata(metadata),
        )
        self.records.append(record)
        return record

    def search_records(
        self,
        query: str,
        *,
        namespace: Optional[str] = None,
        limit: int = 5,
        now: Optional[datetime] = None,
    ) -> List[MemoryRecord]:
        """轻量混合检索：词面命中 + 可选 dense_score + 时间衰减 + 置信度。"""
        query_terms = set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", _clean_memory_text(query, 500).casefold()))
        current = now or datetime.now(timezone.utc)
        ranked: list[tuple[float, MemoryRecord]] = []
        for record in self.records:
            if record.status != "active" or (namespace and record.namespace != namespace):
                continue
            if record.valid_until:
                try:
                    if datetime.fromisoformat(record.valid_until) <= current:
                        continue
                except ValueError:
                    pass
            text_terms = set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", record.text.casefold()))
            lexical = len(query_terms & text_terms) / max(len(query_terms), 1)
            dense = float((record.metadata or {}).get("dense_score", 0.0) or 0.0)
            try:
                created = datetime.fromisoformat(record.created_at)
                age_days = max(0.0, (current - created).total_seconds() / 86400)
            except (TypeError, ValueError):
                age_days = 0.0
            recency = math.exp(-age_days / 30.0)
            score = 0.55 * lexical + 0.2 * dense + 0.15 * recency + 0.1 * record.confidence
            if query_terms and lexical == 0 and dense == 0:
                continue
            ranked.append((score, record))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [record for _, record in ranked[: max(1, limit)]]

    def forget(self, *, max_age_days: int = 30, now: Optional[datetime] = None) -> int:
        """基础主动遗忘：过期条目和低重要性旧会话从进程内记录移除。"""
        current = now or datetime.now(timezone.utc)
        kept: list[MemoryRecord] = []
        removed = 0
        for record in self.records:
            try:
                age_days = max(0.0, (current - datetime.fromisoformat(record.created_at)).total_seconds() / 86400)
            except (TypeError, ValueError):
                age_days = 0.0
            expired = bool(record.valid_until and record.valid_until <= current.isoformat())
            stale_low_value = record.kind == "conversation" and age_days > max_age_days and record.importance < 0.6
            if expired or stale_low_value or record.status == "superseded":
                removed += 1
            else:
                kept.append(record)
        self.records = kept
        return removed

    def get_memory_stats(self) -> Dict[str, Any]:
        return {
            "short_term": self.short_term.get_summary(),
            "records": len(self.records),
            "active_namespace": self.active_namespace,
        }

    def clear_all(self) -> None:
        self.short_term.clear()
        self.records.clear()
        self.active_namespace = "default"


class SessionMemoryStore:
    """有界的 LRU 会话容器。

    每个对话内部只保留固定轮数，同时限制进程内会话总数，
    避免不断提交新 session_id 造成无界内存增长。
    """

    def __init__(self, max_sessions: int = 1000, max_raw_turns: int = 10):
        self.max_sessions = max(1, max_sessions)
        self.max_raw_turns = max(1, max_raw_turns)
        self._items: "OrderedDict[str, MemoryManager]" = OrderedDict()

    def get(self, key: str) -> MemoryManager:
        memory = self._items.pop(key, None)
        if memory is None:
            memory = MemoryManager(self.max_raw_turns)
        self._items[key] = memory
        while len(self._items) > self.max_sessions:
            self._items.popitem(last=False)
        return memory

    def __len__(self) -> int:
        return len(self._items)
