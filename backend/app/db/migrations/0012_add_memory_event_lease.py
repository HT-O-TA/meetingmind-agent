"""为 outbox 发布事件增加崩溃后可回收的租约字段。"""

import asyncio

from sqlalchemy import text

from app.db.database import engine


async def upgrade() -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("ALTER TABLE memory_index_events ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMP NULL")
        )


if __name__ == "__main__":
    asyncio.run(upgrade())
