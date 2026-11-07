"""固定长会话对照所依赖的组装器裁剪顺序；无需启动服务。"""

from app.services.context_assembler import ContextAssembler


def test_context_budget_keeps_tool_evidence_then_retrieval_then_relevant_memory():
    assembler = ContextAssembler(max_items=3)
    result = assembler.assemble_state(
        {
            "question": "档案搬迁的安排是什么？",
            "task_contexts": {
                "get_document_content": {"data": {"content": "工具读到的原始纪要"}}
            },
            "context": [{"document_id": 1, "content": "当前检索证据", "similarity": 0.9}],
            # MemoryManager 的 raw_context 按从新到旧提供。
            "raw_context": ["最新轮：讨论周报", "较旧轮：先征集负责人", "最旧轮：档案搬迁安排在周五"],
        },
        max_chars=1000,
    )

    assert [item["content_ref"] for item in result.manifest["included"]] == [
        "tool:get_document_content:0",
        "retrieval:document:1:chunk:0",
        "session_context:2",
    ]
    assert [
        (item["content_ref"], item["reason"]) for item in result.manifest["dropped"]
    ] == [
        ("session_context:0", "item_count_limit"),
        ("session_context:1", "item_count_limit"),
    ]
    assert "档案搬迁安排在周五" in result.text
    assert "先征集负责人" not in result.text
