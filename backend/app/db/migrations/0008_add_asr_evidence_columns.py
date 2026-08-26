"""为已有 PostgreSQL 数据库增加阶段 4 ASR 证据字段。

冷启动由 ``Base.metadata.create_all`` 创建完整表；已有库执行：
PYTHONPATH=backend python backend/app/db/migrations/0008_add_asr_evidence_columns.py
"""
import asyncio

from sqlalchemy import text

from app.db.database import engine


async def upgrade() -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("ALTER TABLE meetings ADD COLUMN IF NOT EXISTS transcript_metadata JSON")
        )
        await connection.execute(
            text("ALTER TABLE speech_records ADD COLUMN IF NOT EXISTS source_type VARCHAR(16)")
        )
        await connection.execute(
            text("ALTER TABLE speech_records ADD COLUMN IF NOT EXISTS source_task_id VARCHAR(64)")
        )
        await connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_speech_records_source_task_id "
                "ON speech_records (source_task_id)"
            )
        )


if __name__ == "__main__":
    asyncio.run(upgrade())
