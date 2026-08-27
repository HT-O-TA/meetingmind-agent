"""增加 ASR 证据生命周期、修订版本与片段安全字段。

冷启动由 ``Base.metadata.create_all`` 创建完整表；已有 PostgreSQL 执行：
PYTHONPATH=backend python backend/app/db/migrations/0009_harden_asr_evidence_lifecycle.py
"""

import asyncio

from sqlalchemy import text

from app.db.database import engine


async def upgrade() -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("ALTER TABLE meetings ADD COLUMN IF NOT EXISTS asr_original_transcript TEXT")
        )
        await connection.execute(
            text("ALTER TABLE meetings ADD COLUMN IF NOT EXISTS transcript_status VARCHAR(24)")
        )
        await connection.execute(
            text(
                "ALTER TABLE meetings ADD COLUMN IF NOT EXISTS "
                "transcript_revision INTEGER NOT NULL DEFAULT 0"
            )
        )
        await connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_meetings_transcript_status "
                "ON meetings (transcript_status)"
            )
        )
        await connection.execute(
            text("ALTER TABLE speech_records ADD COLUMN IF NOT EXISTS security_status VARCHAR(16)")
        )
        await connection.execute(
            text("ALTER TABLE speech_records ADD COLUMN IF NOT EXISTS security_reason VARCHAR(64)")
        )
        await connection.execute(
            text("ALTER TABLE speech_records ADD COLUMN IF NOT EXISTS content_sha256 VARCHAR(64)")
        )


if __name__ == "__main__":
    asyncio.run(upgrade())
