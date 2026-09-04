"""为长期事实增加可并存冲突组字段。"""

import asyncio

from sqlalchemy import text

from app.db.database import engine


async def upgrade() -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("ALTER TABLE memory_records ADD COLUMN IF NOT EXISTS conflict_group_id VARCHAR(64)")
        )
        await connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_memory_records_conflict_group "
                "ON memory_records (conflict_group_id)"
            )
        )


if __name__ == "__main__":
    asyncio.run(upgrade())
