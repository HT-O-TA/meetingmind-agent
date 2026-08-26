from app.agents.memory import MemoryManager, ShortTermMemory


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
