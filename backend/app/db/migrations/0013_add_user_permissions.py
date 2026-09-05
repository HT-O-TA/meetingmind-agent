"""为已有数据库补齐 users.permissions 字段。

模型使用 ``create_all`` 只能创建新表，不能修改已经存在的 users 表；
因此旧环境需要显式执行这条幂等迁移。
"""

from sqlalchemy import text


async def upgrade(connection) -> None:
    await connection.execute(
        text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions TEXT"
        )
    )
    # 旧库也可能缺少 0009 引入的会议转写生命周期字段；一并幂等补齐，
    # 避免演示/启动时 ORM 查询到不存在的列。
    await connection.execute(
        text(
            "ALTER TABLE meetings ADD COLUMN IF NOT EXISTS "
            "asr_original_transcript TEXT"
        )
    )
    await connection.execute(
        text(
            "ALTER TABLE meetings ADD COLUMN IF NOT EXISTS "
            "transcript_status VARCHAR(24)"
        )
    )
    await connection.execute(
        text(
            "ALTER TABLE meetings ADD COLUMN IF NOT EXISTS "
            "transcript_revision INTEGER NOT NULL DEFAULT 0"
        )
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
    # vector_chunks 的软删除字段已进入 ORM；旧库若没有该列，首次上传
    # 文档会在 INSERT 时触发 UndefinedColumn，表现为 HTTP 500。
    await connection.execute(
        text("ALTER TABLE vector_chunks ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE")
    )
    await connection.execute(
        text("CREATE INDEX IF NOT EXISTS ix_vector_chunks_deleted_at ON vector_chunks (deleted_at)")
    )
    await connection.execute(
        text(
            "SELECT setval(pg_get_serial_sequence('documents', 'id'), "
            "COALESCE((SELECT MAX(id) FROM documents), 1), true)"
        )
    )
    # 某些旧库曾手工导入过固定 ID，导致自增序列落后于现有数据。
    # 只把序列推进到当前最大值，不改动任何业务记录。
    await connection.execute(
        text(
            "SELECT setval(pg_get_serial_sequence('meetings', 'id'), "
            "COALESCE((SELECT MAX(id) FROM meetings), 1), true)"
        )
    )


async def downgrade(connection) -> None:
    await connection.execute(
        text("ALTER TABLE users DROP COLUMN IF EXISTS permissions")
    )
