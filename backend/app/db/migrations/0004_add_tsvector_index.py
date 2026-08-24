"""数据库迁移脚本 - 添加 tsvector 全文索引"""
from sqlalchemy import text
from app.db.database import engine


async def check_ts_config():
    """检测可用的分词配置（使用独立连接）"""
    async with engine.connect() as conn:
        try:
            await conn.execute(text("SELECT to_tsvector('chinese', '测试');"))
            return 'chinese'
        except:
            return 'simple'


async def upgrade():
    """升级：添加 tsvector 字段和 GIN 索引"""

    # 1. 检测分词配置
    ts_config = await check_ts_config()
    if ts_config == 'chinese':
        print("✅ 检测到中文分词配置 'chinese'")
    else:
        print("⚠️ 未检测到中文分词配置，使用 'simple' 配置（建议安装 zhparser 扩展）")

    # 2. 添加 tsvector 字段（独立事务）
    try:
        async with engine.begin() as conn:
            await conn.execute(text("""
                ALTER TABLE vector_chunks
                ADD COLUMN IF NOT EXISTS tsv_content tsvector;
            """))
        print("✅ tsvector 字段添加成功")
    except Exception as e:
        print(f"⚠️ 添加 tsvector 字段失败（可能已存在）: {e}")

    # 3. 创建 GIN 索引（独立事务）
    try:
        async with engine.begin() as conn:
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_vector_chunks_tsv
                ON vector_chunks USING GIN(tsv_content);
            """))
        print("✅ GIN 索引创建成功")
    except Exception as e:
        print(f"⚠️ 创建 GIN 索引失败（可能已存在）: {e}")

    # 4. 更新已有数据的 tsvector（独立事务）
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f"""
                UPDATE vector_chunks
                SET tsv_content = to_tsvector('{ts_config}', chunk_text)
                WHERE tsv_content IS NULL;
            """))
        print("✅ 更新已有数据的 tsvector 完成")
    except Exception as e:
        print(f"⚠️ 更新 tsvector 失败: {e}")

    # 5. 创建触发器函数（独立事务）
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f"""
                CREATE OR REPLACE FUNCTION update_tsv_content()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.tsv_content = to_tsvector('{ts_config}', NEW.chunk_text);
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """))
        print("✅ 触发器函数创建成功")
    except Exception as e:
        print(f"⚠️ 创建触发器函数失败: {e}")

    # 6. 添加触发器（独立事务）
    try:
        async with engine.begin() as conn:
            await conn.execute(text("""
                DROP TRIGGER IF EXISTS trigger_tsv_update ON vector_chunks;
            """))
            await conn.execute(text("""
                CREATE TRIGGER trigger_tsv_update
                BEFORE INSERT OR UPDATE ON vector_chunks
                FOR EACH ROW EXECUTE FUNCTION update_tsv_content();
            """))
        print("✅ 触发器添加成功")
    except Exception as e:
        print(f"⚠️ 添加触发器失败: {e}")

    print("\n✅ 数据库迁移完成：tsvector 字段和 GIN 索引已添加")


async def downgrade():
    """降级：移除 tsvector 字段和 GIN 索引"""
    # 1. 移除触发器
    try:
        async with engine.begin() as conn:
            await conn.execute(text("""
                DROP TRIGGER IF EXISTS trigger_tsv_update ON vector_chunks;
            """))
        print("✅ 触发器移除成功")
    except Exception as e:
        print(f"⚠️ 移除触发器失败: {e}")

    # 2. 移除函数
    try:
        async with engine.begin() as conn:
            await conn.execute(text("""
                DROP FUNCTION IF EXISTS update_tsv_content();
            """))
        print("✅ 函数移除成功")
    except Exception as e:
        print(f"⚠️ 移除函数失败: {e}")

    # 3. 移除索引
    try:
        async with engine.begin() as conn:
            await conn.execute(text("""
                DROP INDEX IF EXISTS idx_vector_chunks_tsv;
            """))
        print("✅ 索引移除成功")
    except Exception as e:
        print(f"⚠️ 移除索引失败: {e}")

    # 4. 移除字段
    try:
        async with engine.begin() as conn:
            await conn.execute(text("""
                ALTER TABLE vector_chunks DROP COLUMN IF EXISTS tsv_content;
            """))
        print("✅ 字段移除成功")
    except Exception as e:
        print(f"⚠️ 移除字段失败: {e}")

    print("\n✅ 数据库降级完成：tsvector 字段和 GIN 索引已移除")


if __name__ == "__main__":
    import asyncio
    asyncio.run(upgrade())
