"""独立 Worker 进程入口，与 FastAPI Web 进程解耦。"""
import asyncio
import signal

from app.core.logger import app_logger
from app.core.cache_init import close_redis, init_redis
from app.core.rabbitmq import rabbitmq_manager
from app.core.config import settings
from app.workers.document_worker import start_workers


async def initialize_worker_dependencies() -> None:
    """初始化任务状态存储；队列 Worker 不允许在无 Redis 时降级运行。"""
    if not await init_redis():
        raise RuntimeError("Worker startup failed: Redis is unavailable")


async def main() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    outbox_task = None
    try:
        await initialize_worker_dependencies()
        handles = await start_workers()
        if settings.MEMORY_INDEX_WORKER_ENABLED:
            from app.workers.memory_index_worker import publish_outbox_loop
            outbox_task = asyncio.create_task(publish_outbox_loop(stop_event))
        app_logger.info(f"Worker process ready, consumers={len(handles)}")
        await stop_event.wait()
    finally:
        if outbox_task is not None:
            outbox_task.cancel()
            await asyncio.gather(outbox_task, return_exceptions=True)
        await rabbitmq_manager.close()
        await close_redis()
        app_logger.info("Worker process stopped")


if __name__ == "__main__":
    asyncio.run(main())
