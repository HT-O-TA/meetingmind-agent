import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as connection:
        await connection.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions TEXT")
        )
        await connection.execute(
            text("ALTER TABLE meetings ADD COLUMN IF NOT EXISTS asr_original_transcript TEXT")
        )
        await connection.execute(
            text("ALTER TABLE meetings ADD COLUMN IF NOT EXISTS transcript_status VARCHAR(24)")
        )
        await connection.execute(
            text("ALTER TABLE meetings ADD COLUMN IF NOT EXISTS transcript_revision INTEGER NOT NULL DEFAULT 0")
        )
        await connection.execute(
            text("ALTER TABLE meetings ADD COLUMN IF NOT EXISTS transcript_metadata JSON")
        )
        await connection.execute(
            text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE")
        )
        await connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_documents_deleted_at ON documents (deleted_at)")
        )
        await connection.execute(
            text("ALTER TABLE vector_chunks ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE")
        )
        await connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_vector_chunks_deleted_at ON vector_chunks (deleted_at)")
        )
        await connection.execute(
            text("SELECT setval(pg_get_serial_sequence('documents', 'id'), COALESCE((SELECT MAX(id) FROM documents), 1), true)")
        )
        await connection.execute(
            text("SELECT setval(pg_get_serial_sequence('meetings', 'id'), COALESCE((SELECT MAX(id) FROM meetings), 1), true)")
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
