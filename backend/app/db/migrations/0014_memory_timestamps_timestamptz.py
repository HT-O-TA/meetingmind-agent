"""将记忆和 outbox 的时间列统一为 PostgreSQL TIMESTAMPTZ。

旧数据按既有约定解释为 UTC，再转换为带时区时间。
"""

from sqlalchemy import text

from app.db.database import engine


TABLE_COLUMNS = {
    "memory_records": ("valid_from", "valid_until", "created_at", "deleted_at"),
    "memory_index_events": ("available_at", "claimed_at", "created_at", "processed_at"),
}


async def upgrade() -> None:
    async with engine.begin() as connection:
        for table, columns in TABLE_COLUMNS.items():
            for column in columns:
                await connection.execute(
                    text(
                        f"ALTER TABLE {table} ALTER COLUMN {column} "
                        "TYPE TIMESTAMPTZ USING "
                        f"({column} AT TIME ZONE 'UTC')"
                    )
                )


if __name__ == "__main__":
    import asyncio

    asyncio.run(upgrade())
