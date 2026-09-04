from __future__ import annotations

from pathlib import Path

import pytest
from langgraph.graph import END, START, StateGraph
from typing import TypedDict

from app.agents.checkpoint import (
    PersistentCheckpointSaver,
    checkpoint_state_scope,
)
from app.agents.agent_service import AgentService
from app.agents.session_context import SessionContext
from app.agents.human_in_the_loop import HumanInTheLoopService, ConfirmationType


def test_checkpoint_scope_keeps_task_contract_and_redacts_runtime_context():
    callback = lambda *_args: None
    values = {
        "question": "整理会议结论",
        "input_envelope": {"schema_version": "input.v1"},
        "task_anchor": {"schema_version": "task-anchor.v1"},
        "pending_action": {"source": "tool"},
        "task_namespace": "task-a",
        "task_contexts": {
            "search": {
                "status": "succeeded",
                "data": {"content": "x" * 6000, "tool_log": "private"},
            }
        },
        "context": [{"content": "不应持久化的证据正文"}],
        "raw_context": ["不应持久化的会话正文"],
        "cot_thoughts": [{"thought": "private"}],
        "session_context": "private formatted context",
        "event_callback": callback,
        "unknown_runtime_value": object(),
    }

    scoped = checkpoint_state_scope(values)

    assert scoped["question"] == values["question"]
    assert scoped["input_envelope"] == values["input_envelope"]
    assert scoped["task_anchor"] == values["task_anchor"]
    assert scoped["pending_action"] == values["pending_action"]
    assert scoped["task_namespace"] == "task-a"
    assert scoped["task_contexts"]["search"]["data"]["content"]["_truncated"] is True
    assert "tool_log" not in scoped["task_contexts"]["search"]["data"]
    assert scoped["context"] == []
    assert scoped["raw_context"] == []
    assert scoped["cot_thoughts"] == []
    assert scoped["session_context"] is None
    assert scoped["event_callback"] is None
    assert "unknown_runtime_value" not in scoped


def test_persistent_saver_round_trips_and_enforces_thread_owner(tmp_path: Path):
    state_type = TypedDict("CheckpointState", {"question": str})
    builder = StateGraph(state_type)
    builder.add_node("increment", lambda state: {"question": state["question"] + "!"})
    builder.add_edge(START, "increment")
    builder.add_edge("increment", END)

    checkpoint_path = tmp_path / "checkpoints.pkl"
    saver = PersistentCheckpointSaver(checkpoint_path)
    graph = builder.compile(checkpointer=saver)
    config = {
        "configurable": {
            "thread_id": "7:sess:conv",
            "user_id": 7,
        }
    }

    assert graph.invoke({"question": "go"}, config)["question"] == "go!"
    assert checkpoint_path.exists()

    restored = PersistentCheckpointSaver(checkpoint_path)
    checkpoint = restored.get_tuple(config)
    assert checkpoint is not None
    assert checkpoint.checkpoint["channel_values"]["question"] == "go!"

    with pytest.raises(PermissionError):
        restored.get_tuple(
            {"configurable": {"thread_id": "7:sess:conv", "user_id": 8}}
        )


def test_session_context_exposes_durable_thread_and_run_semantics():
    context = SessionContext(user_id=11, session_id="sess", conversation_id="conv")

    config = context.get_config(run_id="run-1")

    assert config["thread_id"] == "11:sess:conv"
    assert config["configurable"]["thread_id"] == "11:sess:conv"
    assert config["configurable"]["run_id"] == "run-1"
    assert config["configurable"]["checkpoint_ns"] == "run-1"


def test_resume_falls_back_to_checkpoint_and_reconstructs_approval_binding():
    class FakeSaver:
        def __init__(self):
            self.deleted = None

        def get_tuple(self, config):
            assert config["configurable"]["thread_id"] == "7:sess:conv"
            assert config["configurable"]["checkpoint_ns"] == "run-1"
            return type("Checkpoint", (), {
                "checkpoint": {"channel_values": {
                    "user_id": 7,
                    "thread_id": "7:sess:conv",
                    "agent_run_id": "run-1",
                    "pending_action": {
                        "source": "tool",
                        "tool_name": "send_notification",
                        "tool_call_index": 0,
                        "idempotency_key": "idem-1",
                    },
                }}
            })()

        def delete_namespace(self, thread_id, checkpoint_ns):
            self.deleted = (thread_id, checkpoint_ns)

    service = AgentService.__new__(AgentService)
    service.checkpointer = FakeSaver()
    request = {"details": {"thread_id": "7:sess:conv", "agent_run_id": "run-1"}}

    state = service._load_checkpoint_resume_state(request, user_id=7)

    assert state["approved_tool_call"] == {
        "tool_name": "send_notification",
        "idempotency_key": "idem-1",
    }
    assert state["resume_from_tool_index"] == 0
    assert state["confirmation_status"] == "pending"
    service._cleanup_checkpoint(state)
    assert service.checkpointer.deleted == ("7:sess:conv", "run-1")


@pytest.mark.asyncio
async def test_hitl_claim_lease_allows_single_runner_and_retry(fake_redis):
    service = HumanInTheLoopService()
    service.redis = fake_redis
    request_id = await service.request_confirmation(
        ConfirmationType.TOOL_CALL,
        "确认",
        "请确认",
        details={"user_id": 7},
    )

    claimed = await service.claim_request(request_id, expected_user_id=7, lease_seconds=30)
    assert claimed and claimed["run_status"] == "running"
    assert await service.claim_request(request_id, expected_user_id=7, lease_seconds=30) is None
    assert await service.finish_claim(request_id, claimed["claim_token"], success=False, error="crash")
    # 失败状态可以在下一次恢复中重新 claim，而不会丢失确认请求。
    claimed_again = await service.claim_request(request_id, expected_user_id=7, lease_seconds=30)
    assert claimed_again and claimed_again["attempt_count"] == 2
