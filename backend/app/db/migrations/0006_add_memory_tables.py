"""数据库迁移脚本 - 添加记忆系统表 (memories, memory_entities, memory_entity_relations)"""
from sqlalchemy import text
from app.db.database import engine


async def upgrade():
    """升级：创建记忆系统表"""

    print("=" * 60)
    print("开始创建记忆系统表")
    print("=" * 60)

    # 1. 创建 memories 表
    try:
        async with engine.begin() as conn:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS memories (
                    id SERIAL PRIMARY KEY,
                    memory_id VARCHAR(64) UNIQUE NOT NULL,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    session_id VARCHAR(64),
                    memory_type VARCHAR(32) NOT NULL DEFAULT 'long_term',
                    memory_status VARCHAR(16) DEFAULT 'active',
                    content TEXT NOT NULL,
                    content_summary TEXT,
                    importance_score FLOAT DEFAULT 0.5,
                    relevance_score FLOAT DEFAULT 1.0,
                    confidence_score FLOAT DEFAULT 1.0,
                    metadata JSON,
                    vector_ref_id VARCHAR(64),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    expires_at TIMESTAMP WITH TIME ZONE,
                    access_count INTEGER DEFAULT 0,
                    last_accessed_at TIMESTAMP WITH TIME ZONE,
                    source_type VARCHAR(32),
                    source_id VARCHAR(64),
                    source_meeting_id INTEGER REFERENCES meetings(id) ON DELETE SET NULL
                );
            """))
        print("✅ memories 表创建成功")
    except Exception as e:
        print(f"⚠️ 创建 memories 表失败: {e}")

    # 2. 创建 memories 表的索引
    try:
        async with engine.begin() as conn:
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_memories_memory_id ON memories(memory_id);
                CREATE INDEX IF NOT EXISTS idx_memories_user_id ON memories(user_id);
                CREATE INDEX IF NOT EXISTS idx_memories_session_id ON memories(session_id);
                CREATE INDEX IF NOT EXISTS idx_memories_memory_type ON memories(memory_type);
                CREATE INDEX IF NOT EXISTS idx_memories_memory_status ON memories(memory_status);
                CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);
                CREATE INDEX IF NOT EXISTS idx_memories_expires_at ON memories(expires_at);
                CREATE INDEX IF NOT EXISTS idx_memories_source_meeting_id ON memories(source_meeting_id);
            """))
        print("✅ memories 表索引创建成功")
    except Exception as e:
        print(f"⚠️ 创建 memories 索引失败: {e}")

    # 3. 创建复合索引
    try:
        async with engine.begin() as conn:
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_memories_user_type ON memories(user_id, memory_type);
                CREATE INDEX IF NOT EXISTS ix_memories_type_status ON memories(memory_type, memory_status);
            """))
        print("✅ memories 复合索引创建成功")
    except Exception as e:
        print(f"⚠️ 创建复合索引失败: {e}")

    # 4. 创建 memory_entities 表
    try:
        async with engine.begin() as conn:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS memory_entities (
                    id SERIAL PRIMARY KEY,
                    entity_id VARCHAR(64) UNIQUE NOT NULL,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    name VARCHAR(256) NOT NULL,
                    entity_type VARCHAR(64) NOT NULL,
                    properties JSON,
                    description TEXT,
                    importance_score FLOAT DEFAULT 0.5,
                    access_count INTEGER DEFAULT 0,
                    last_accessed_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            """))
        print("✅ memory_entities 表创建成功")
    except Exception as e:
        print(f"⚠️ 创建 memory_entities 表失败: {e}")

    # 5. 创建 memory_entities 表的索引
    try:
        async with engine.begin() as conn:
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_entities_entity_id ON memory_entities(entity_id);
                CREATE INDEX IF NOT EXISTS idx_entities_user_id ON memory_entities(user_id);
                CREATE INDEX IF NOT EXISTS idx_entities_name ON memory_entities(name);
                CREATE INDEX IF NOT EXISTS idx_entities_entity_type ON memory_entities(entity_type);
            """))
        print("✅ memory_entities 表索引创建成功")
    except Exception as e:
        print(f"⚠️ 创建 memory_entities 索引失败: {e}")

    # 6. 创建 memory_entity_relations 表
    try:
        async with engine.begin() as conn:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS memory_entity_relations (
                    id SERIAL PRIMARY KEY,
                    source_entity_id VARCHAR(64) REFERENCES memory_entities(entity_id) ON DELETE CASCADE NOT NULL,
                    target_entity_id VARCHAR(64) REFERENCES memory_entities(entity_id) ON DELETE CASCADE NOT NULL,
                    relation_type VARCHAR(64) NOT NULL,
                    description TEXT,
                    confidence_score FLOAT DEFAULT 1.0,
                    source_memory_id VARCHAR(64),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            """))
        print("✅ memory_entity_relations 表创建成功")
    except Exception as e:
        print(f"⚠️ 创建 memory_entity_relations 表失败: {e}")

    # 7. 创建 memory_entity_relations 表的索引
    try:
        async with engine.begin() as conn:
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_relations_source ON memory_entity_relations(source_entity_id);
                CREATE INDEX IF NOT EXISTS idx_relations_target ON memory_entity_relations(target_entity_id);
                CREATE INDEX IF NOT EXISTS idx_relations_type ON memory_entity_relations(relation_type);
            """))
        print("✅ memory_entity_relations 表索引创建成功")
    except Exception as e:
        print(f"⚠️ 创建 memory_entity_relations 索引失败: {e}")

    print("\n" + "=" * 60)
    print("✅ 记忆系统表创建完成")
    print("=" * 60)


async def downgrade():
    """降级：删除记忆系统表"""

    print("开始删除记忆系统表...")

    # 1. 删除 memory_entity_relations 表
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS memory_entity_relations CASCADE;"))
        print("✅ memory_entity_relations 表已删除")
    except Exception as e:
        print(f"⚠️ 删除 memory_entity_relations 表失败: {e}")

    # 2. 删除 memory_entities 表
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS memory_entities CASCADE;"))
        print("✅ memory_entities 表已删除")
    except Exception as e:
        print(f"⚠️ 删除 memory_entities 表失败: {e}")

    # 3. 删除 memories 表
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS memories CASCADE;"))
        print("✅ memories 表已删除")
    except Exception as e:
        print(f"⚠️ 删除 memories 表失败: {e}")

    print("✅ 记忆系统表删除完成")


if __name__ == "__main__":
    import asyncio
    asyncio.run(upgrade())
