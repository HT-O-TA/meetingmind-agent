"""并行执行失败阈值的停止契约。"""

import pytest

from app.services.parallel_executor import ParallelExecutor


def _tasks():
    return {
        "first_ok": {"task_id": "first_ok", "status": "pending"},
        "first_failed": {"task_id": "first_failed", "status": "pending"},
        "later": {"task_id": "later", "status": "pending"},
    }


async def _execute_task(_state, task, _all_tasks):
    task["status"] = "failed" if task["task_id"] == "first_failed" else "completed"


@pytest.mark.asyncio
async def test_failure_threshold_stops_later_waves_and_marks_them_skipped():
    tasks = _tasks()
    executor = ParallelExecutor(max_workers=2, failure_threshold=0.3)

    result = await executor.execute(
        tasks,
        [["first_ok", "first_failed"], ["later"]],
        _execute_task,
        state={},
        all_tasks=tasks,
    )

    assert tasks["later"]["status"] == "skipped"
    assert tasks["later"]["error"] == "execution_stopped_failure_threshold"
    assert result.completed == 1
    assert result.failed == 1
    assert result.skipped == 1
    assert result.stopped_by_failure_threshold is True


@pytest.mark.asyncio
async def test_failure_rate_below_threshold_continues_later_waves():
    tasks = _tasks()
    executor = ParallelExecutor(max_workers=2, failure_threshold=0.75)

    result = await executor.execute(
        tasks,
        [["first_ok", "first_failed"], ["later"]],
        _execute_task,
        state={},
        all_tasks=tasks,
    )

    assert tasks["later"]["status"] == "completed"
    assert result.completed == 2
    assert result.failed == 1
    assert result.skipped == 0
    assert result.stopped_by_failure_threshold is False


def test_global_executor_uses_configured_failure_threshold(monkeypatch):
    from app.core.config import settings
    from app.services import parallel_executor as executor_module

    monkeypatch.setattr(settings, "PARALLEL_FAILURE_THRESHOLD", 0.75, raising=False)
    monkeypatch.setattr(executor_module, "_executor_instance", None)

    executor = executor_module.get_parallel_executor()

    assert executor._failure_threshold == 0.75
