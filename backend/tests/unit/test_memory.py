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
