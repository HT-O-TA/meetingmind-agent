"""Pause after the child publish, before committing the parent result."""
import asyncio

from app.services.task_queue import TaskStatus, task_queue_service
from app.workers.run import main


update_status = task_queue_service.update_task_status


async def pause_before_completion(task_id, status, **kwargs):
    result = kwargs.get("result") or {}
    if status == TaskStatus.COMPLETED and result.get("vector_task_id"):
        print(f"claimed-for-crash {task_id} child={result['vector_task_id']}", flush=True)
        await asyncio.Event().wait()
    return await update_status(task_id, status, **kwargs)


task_queue_service.update_task_status = pause_before_completion
asyncio.run(main())
