"""单元测试 - 记忆模块"""
import pytest
from datetime import datetime
from app.agents.memory import ShortTermMemory, LongTermMemory, MemoryCompressor, MemoryManager


class TestShortTermMemory:
    def test_add_turn(self):
        mem = ShortTermMemory()
        turn = mem.add_turn("问题1", "回答1")
        assert turn["question"] == "问题1"
        assert turn["answer"] == "回答1"
        assert len(mem.raw_turns) == 1

    def test_max_raw_turns_overflow(self):
        mem = ShortTermMemory(max_raw_turns=3)
        for i in range(5):
            mem.add_turn(f"问题{i}", f"回答{i}")
        mem.mark_for_compression()
        assert len(mem.raw_turns) == 3
        assert len(mem.pending_for_compression) == 2

    def test_get_recent_turns(self):
        mem = ShortTermMemory()
        for i in range(5):
            mem.add_turn(f"q{i}", f"a{i}")
        recent = mem.get_recent_turns(3)
        assert len(recent) == 3
        assert recent[-1]["question"] == "q4"

    def test_get_context_empty(self):
        mem = ShortTermMemory()
        ctx = mem.get_context()
        assert ctx == ""

    def test_get_context_with_turns(self):
        mem = ShortTermMemory()
        mem.add_turn("你好", "你好！")
        ctx = mem.get_context()
        assert "你好" in ctx

    def test_compress_clears_pending(self):
        mem = ShortTermMemory(max_raw_turns=2)
        for i in range(4):
            mem.add_turn(f"q{i}", f"a{i}")
        mem.mark_for_compression()
        summary = {
            "turn_id": 99,
            "summary": "摘要",
            "key_points": [],
            "original_turn_ids": [1, 2],
            "timestamp": datetime.now().isoformat(),
            "task_type": "qa"
        }
        mem.compress(summary)
        assert len(mem.pending_for_compression) == 0
        assert len(mem.summarized_turns) == 1


class TestLongTermMemory:
    def test_add_memory(self):
        mem = LongTermMemory()
        item = mem.add_memory("test", "测试内容", importance=0.8)
        assert item["content"] == "测试内容"
        assert item["importance"] == 0.8
        assert len(mem.items) == 1

    def test_prune_keeps_high_importance(self):
        mem = LongTermMemory(max_items=4)
        for i in range(6):
            mem.add_memory("test", f"内容{i}", importance=i * 0.1)
        # 手动触发剪枝
        mem._prune_low_importance()
        # 高重要性的应该被保留
        importances = [item["importance"] for item in mem.items]
        assert max(importances) >= 0.4

    def test_search_by_content(self):
        mem = LongTermMemory()
        mem.add_memory("decision", "会议决策：采购新设备")
        mem.add_memory("schedule", "会议时间：下午3点")
        results = mem.search_by_content("采购")
        assert len(results) == 1
        assert "采购" in results[0]["content"]

    def test_add_key_fact(self):
        mem = LongTermMemory()
        fact = mem.add_key_fact("项目截止日期是12月31日", "deadline", extracted_from=1)
        assert fact["content"] == "项目截止日期是12月31日"
        assert fact["category"] == "deadline"
        assert len(mem.key_facts) == 1


class TestMemoryCompressor:
    @pytest.mark.asyncio
    async def test_compress_empty_turns(self):
        compressor = MemoryCompressor()
        result = await compressor.compress_turns([])
        assert result["summary"] == "无对话记录"
        assert result["turn_id"] == 0

    @pytest.mark.asyncio
    async def test_simple_compress(self):
        compressor = MemoryCompressor(llm_service=None)
        turns = [
            {
                "turn_id": 1,
                "question": "项目进展如何？",
                "answer": "进展顺利，已完成70%",
                "plan": None,
                "reflection": None,
                "timestamp": datetime.now().isoformat(),
                "task_type": "qa",
                "success": True
            }
        ]
        result = await compressor.compress_turns(turns)
        assert result["turn_id"] == 1
        assert result["task_type"] == "qa"
        assert isinstance(result["key_points"], list)


class TestMemoryManager:
    def test_init(self):
        mgr = MemoryManager(max_short_term_turns=10, max_long_term_items=100)
        assert mgr.short_term.max_raw_turns == 5
        assert mgr.long_term.max_items == 100

    def test_add_conversation_and_stats(self):
        mgr = MemoryManager()
        mgr.add_conversation("问题", "回答")
        stats = mgr.get_memory_stats()
        assert stats["short_term"]["raw_turns"] == 1

    def test_clear_all(self):
        mgr = MemoryManager()
        mgr.add_conversation("问题", "回答")
        mgr.clear_all()
        stats = mgr.get_memory_stats()
        assert stats["short_term"]["raw_turns"] == 0

    def test_get_context_for_query(self):
        mgr = MemoryManager()
        mgr.add_conversation("上次会议讨论了什么？", "讨论了Q4预算")
        ctx = mgr.get_context_for_query("预算")
        assert isinstance(ctx, str)

    def test_save_and_load_checkpoint(self):
        mgr = MemoryManager()
        mgr.add_conversation("问题", "回答")
        cp = mgr.save_checkpoint("sess1")
        assert cp["session_id"] == "sess1"
        assert "short_term" in cp

        mgr2 = MemoryManager()
        mgr2.load_checkpoint(cp)
        assert len(mgr2.short_term.raw_turns) == 1
