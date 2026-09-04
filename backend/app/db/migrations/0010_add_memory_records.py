"""创建长期事实记忆主库和索引同步 outbox。

已有环境可执行：
``PYTHONPATH=backend python backend/app/db/migrations/0010_add_memory_records.py``
"""

import asyncio

from app.db.database import engine
from app.models.memory import MemoryIndexEventModel, MemoryRecordModel


async def upgrade() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(MemoryRecordModel.__table__.create, checkfirst=True)
        await connection.run_sync(MemoryIndexEventModel.__table__.create, checkfirst=True)


if __name__ == "__main__":
    asyncio.run(upgrade())
