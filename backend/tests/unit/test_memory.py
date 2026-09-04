from datetime import datetime, timedelta, timezone

from app.agents.memory import MemoryManager, SessionMemoryStore, ShortTermMemory
from app.agents.session_context import SessionContext


def test_short_term_memory_keeps_bounded_window():
    memory = ShortTermMemory(max_raw_turns=2)
    memory.add_turn("q1", "a1")
    memory.add_turn("q2", "a2")
    memory.add_turn("q3", "a3")

    assert [turn["question"] for turn in memory.raw_turns] == ["q2", "q3"]


def test_memory_manager_formats_recent_context():
    memory = MemoryManager(max_short_term_turns=3)
    memory.add_exchange("第一问", "第一答")
    memory.add_exchange("第二问", "第二答")

    assert memory.get_context_for_query("继续", n_recent=1) == "问: 第二问\n答: 第二答"


def test_memory_manager_returns_independent_turns_most_recent_first():
    memory = MemoryManager(max_short_term_turns=3)
    memory.add_exchange("第一问", "第一答")
    memory.add_exchange("第二问", "第二答")

    items = memory.get_context_items_for_query("继续", n_recent=2)

    assert "第二问" in items[0]
    assert "第一问" in items[1]


def test_memory_manager_clear_removes_session_context():
    memory = MemoryManager()
    memory.add_exchange("问题", "答案")
    memory.clear_all()

    assert memory.get_context_for_query("问题") == ""


def test_session_memory_store_is_bounded_and_lru():
    store = SessionMemoryStore(max_sessions=2, max_raw_turns=2)
    first = store.get("user-1:session:conversation")
    second = store.get("user-2:session:conversation")
    assert store.get("user-1:session:conversation") is first

    store.get("user-3:session:conversation")
    assert len(store) == 2
    assert store.get("user-2:session:conversation") is not second


def test_thread_id_and_memory_are_isolated_by_user():
    context_a = SessionContext(user_id=1, session_id="same", conversation_id="same")
    context_b = SessionContext(user_id=2, session_id="same", conversation_id="same")
    store = SessionMemoryStore()

    store.get(context_a.thread_id).add_exchange("A 的问题", "A 的答案")

    assert context_a.thread_id == "1:same:same"
    assert context_b.thread_id == "2:same:same"
    assert store.get(context_b.thread_id).get_context_for_query("继续") == ""


def test_memory_write_gate_skips_empty_answer_and_limits_context_size():
    memory = MemoryManager(max_short_term_turns=3)

    assert memory.add_exchange("问题", "") is False
    assert memory.add_exchange("问题", "答案" * 2000) is True
    assert len(memory.short_term.raw_turns[0]["answer"]) <= 3000
    assert all("tool_log" not in item for item in memory.records[0].metadata or {})


def test_memory_namespace_keeps_new_task_from_old_task_context():
    memory = MemoryManager(max_short_term_turns=5)
    memory.add_exchange("订机票", "靠窗", namespace="flight")
    memory.add_exchange("写代码", "使用 Python", namespace="coding")

    assert "靠窗" not in memory.get_context_for_query("代码", namespace="coding")
    assert "使用 Python" in memory.get_context_for_query("代码", namespace="coding")


def test_fact_write_marks_old_value_superseded_and_search_uses_recency_confidence():
    memory = MemoryManager()
    old = memory.add_fact(namespace="task-a", key="目的地", value="北京", confidence=0.9)
    new = memory.add_fact(namespace="task-a", key="目的地", value="上海", confidence=0.95)

    assert old is not None and new is not None
    assert old.status == "superseded"
    assert new.supersedes == old.record_id
    assert [item.value for item in memory.search_records("目的地", namespace="task-a")] == ["上海"]


def test_memory_forget_removes_expired_and_superseded_records():
    memory = MemoryManager()
    old = memory.add_fact(namespace="task-a", key="临时", value="旧", valid_until="2020-01-01T00:00:00+00:00")
    assert old is not None
    removed = memory.forget(now=datetime.now(timezone.utc))

    assert removed == 1
    assert memory.records == []


def test_explicit_task_id_produces_stable_isolated_namespace():
    memory = MemoryManager()
    first = memory.resolve_task_namespace("继续", task_id="travel-2026", meeting_id=3)
    second = memory.resolve_task_namespace("换个说法", task_id="travel-2026", meeting_id=3)
    other = memory.resolve_task_namespace("继续", task_id="coding-2026", meeting_id=3)

    assert first == second
    assert first != other
