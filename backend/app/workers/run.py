"""独立 Worker 进程入口，与 FastAPI Web 进程解耦。"""
import asyncio
import signal

from app.core.config import settings
from app.core.logger import app_logger
from app.core.rabbitmq import rabbitmq_manager
from app.services.agent_worker import start_agent_worker
from app.workers.document_worker import start_workers


async def main() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    handles = await start_workers()
    if settings.ENABLE_AGENT_WORKER:
        handles.append(await start_agent_worker())
    app_logger.info(f"Worker process ready, consumers={len(handles)}")

    try:
        await stop_event.wait()
    finally:
        await rabbitmq_manager.close()
        app_logger.info("Worker process stopped")


if __name__ == "__main__":
    asyncio.run(main())
