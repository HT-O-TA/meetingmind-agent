"""固定长会话对照所依赖的组装器裁剪顺序；无需启动服务。"""

from app.services.context_assembler import ContextAssembler
from app.agents.memory import MemoryManager
from app.agents.state import create_initial_state
from app.services.input_preprocessor import InputPreprocessor


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


def test_task_switch_keeps_constraints_out_of_the_other_tasks_prompt():
    memory = MemoryManager()
    prepare = InputPreprocessor()
    assembler = ContextAssembler()

    def assemble(question, task_id):
        namespace = memory.resolve_task_namespace(question, task_id=task_id, meeting_id=7)
        state = create_initial_state(question, meeting_id=7)
        state.update(user_id=1, thread_id="1:session:conversation", task_id=task_id,
                     task_namespace=namespace)
        state["raw_context"] = memory.get_context_items_for_query(question, namespace=namespace)
        state["input_envelope"] = prepare.build_envelope(state)
        return namespace, assembler.assemble_state(state).text

    first = "采购设备，预算不超过8000元，禁止选择甲牌。"
    first_namespace, _ = assemble(first, "purchase")
    memory.add_exchange(first, "采购记录编号 PURCHASE-01。", namespace=first_namespace)

    other_namespace, other = assemble("安排测试，预算不超过5000元，不要调用外部API。", "test")
    assert first_namespace != other_namespace
    assert "5000" in other and "不要调用外部API" in other
    assert "8000" not in other and "甲牌" not in other and "PURCHASE-01" not in other

    _, follow_up = assemble("采购方案再说一遍", "purchase")
    assert "8000" in follow_up and "甲牌" in follow_up
