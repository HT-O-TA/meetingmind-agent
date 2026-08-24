"""数据迁移脚本 - 将 Redis 中的长期记忆迁移到 PostgreSQL

使用方法:
    python -m app.db.migrations.migrate_memory_to_pg

功能:
    1. 从 Redis 读取所有长期记忆
    2. 转换为 PostgreSQL 格式
    3. 批量写入 PostgreSQL
    4. 验证迁移结果
"""
import asyncio
import json
import sys
from typing import List, Dict, Any
from datetime import datetime

# 添加项目根目录
sys.path.insert(0, "F:/project/meetingmind-agent/backend")

from app.core.cache import init_redis, get_redis
from app.core.logger import app_logger
from app.db.database import get_session, init_engine
from app.services.memory_store import MemoryStore
from app.core.config_center import get_config


async def migrate_memory_to_pg():
    """将 Redis 中的长期记忆迁移到 PostgreSQL"""

    print("=" * 60)
    print("开始迁移记忆数据: Redis -> PostgreSQL")
    print("=" * 60)

    # 1. 初始化 Redis 连接
    print("\n[1/5] 初始化 Redis 连接...")
    await init_redis()
    redis = get_redis()

    if not redis:
        print("❌ Redis 连接失败")
        return False
    print("✅ Redis 连接成功")

    # 2. 查找所有记忆相关的 Redis Key
    print("\n[2/5] 扫描 Redis 中的记忆数据...")
    cursor = 0
    all_keys = []
    pattern = "memory:*"

    while True:
        cursor, keys = await redis.scan(cursor, match=pattern, count=100)
        all_keys.extend(keys)
        if cursor == 0:
            break

    print(f"  找到 {len(all_keys)} 个记忆相关的 Key")

    # 3. 读取并解析 Redis 中的记忆数据
    print("\n[3/5] 读取 Redis 中的记忆数据...")
    all_memories = []

    for key in all_keys:
        try:
            key_str = key.decode() if isinstance(key, bytes) else key

            # 只迁移 long_term 类型的记忆
            if "long_term" not in key_str:
                print(f"  跳过非长期记忆 Key: {key_str}")
                continue

            # 读取数据
            raw_data = await redis.get(key)
            if not raw_data:
                continue

            # 解析 JSON 数据
            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode()

            memory_list = json.loads(raw_data) if raw_data else []

            for item in memory_list:
                if isinstance(item, dict) and item.get("type") == "long_term":
                    all_memories.append({
                        "source_key": key_str,
                        "memory_data": item
                    })

            print(f"  从 {key_str} 解析出 {len([m for m in all_memories if m['source_key'] == key_str])} 条长期记忆")

        except Exception as e:
            print(f"  ⚠️ 读取 Key {key} 失败: {e}")
            continue

    print(f"\n  总共发现 {len(all_memories)} 条长期记忆需要迁移")

    if not all_memories:
        print("  没有需要迁移的长期记忆，跳过")
        return True

    # 4. 初始化 PostgreSQL 连接并迁移数据
    print("\n[4/5] 迁移数据到 PostgreSQL...")

    # 初始化数据库引擎
    database_url = get_config("database.url", "postgresql://postgres:postgres@localhost:5432/meetingmind")
    await init_engine(database_url)

    migrated_count = 0
    failed_count = 0
    batch_size = 100

    async with get_session() as db:
        memory_store = MemoryStore(db)

        for i, record in enumerate(all_memories):
            try:
                memory_data = record["memory_data"]

                # 转换数据格式
                content = memory_data.get("content", "")
                metadata = memory_data.get("metadata", {})
                created_at_str = memory_data.get("created_at")
                session_id = record["source_key"].split(":")[1] if ":" in record["source_key"] else None

                # 解析时间
                created_at = None
                if created_at_str:
                    try:
                        created_at = datetime.fromisoformat(created_at_str)
                    except:
                        created_at = None

                # 写入 PostgreSQL
                if content:
                    # 检查是否已存在
                    from sqlalchemy import select
                    from app.models.memory import Memory

                    existing = await db.execute(
                        select(Memory).where(Memory.content == content)
                    )
                    if existing.scalar_one_or_none():
                        print(f"  跳过已存在的记忆: {content[:50]}...")
                        continue

                    # 创建新记忆
                    memory = Memory(
                        memory_id=f"mig_{datetime.now().timestamp()}_{i}",
                        session_id=session_id,
                        memory_type="long_term",
                        content=content,
                        metadata=metadata,
                        created_at=created_at or datetime.now(),
                    )
                    db.add(memory)
                    migrated_count += 1

                    # 批量提交
                    if migrated_count % batch_size == 0:
                        await db.commit()
                        print(f"  已迁移 {migrated_count} 条...")

            except Exception as e:
                print(f"  ⚠️ 迁移第 {i+1} 条记忆失败: {e}")
                failed_count += 1
                continue

        await db.commit()

    print(f"\n  ✅ 成功迁移 {migrated_count} 条长期记忆到 PostgreSQL")
    if failed_count > 0:
        print(f"  ⚠️ {failed_count} 条迁移失败")

    # 5. 验证迁移结果
    print("\n[5/5] 验证迁移结果...")

    async with get_session() as db:
        from sqlalchemy import select, func
        from app.models.memory import Memory

        # 统计 PostgreSQL 中的记忆数量
        count_result = await db.execute(
            select(func.count(Memory.id)).where(Memory.memory_type == "long_term")
        )
        pg_count = count_result.scalar() or 0

        print(f"  PostgreSQL 中的长期记忆数量: {pg_count}")

        # 查询一些示例数据
        sample_result = await db.execute(
            select(Memory).where(Memory.memory_type == "long_term").limit(5)
        )
        samples = sample_result.scalars().all()

        if samples:
            print("\n  示例数据:")
            for sample in samples:
                print(f"    - ID: {sample.memory_id}")
                print(f"      内容: {sample.content[:50]}...")
                print(f"      创建时间: {sample.created_at}")
                print()

    # 完成
    print("\n" + "=" * 60)
    print(f"✅ 迁移完成！成功迁移 {migrated_count} 条长期记忆")
    print("=" * 60)
    print("\n后续步骤:")
    print("  1. 验证新代码是否正确读取 PostgreSQL")
    print("  2. 旧 Redis 数据可以保留一段时间作为备份")
    print("  3. 确认无误后可清理 Redis 中的旧记忆数据")
    print()

    return True


async def verify_migration():
    """验证迁移结果"""
    print("\n" + "=" * 60)
    print("验证迁移结果")
    print("=" * 60)

    await init_redis()
    redis = get_redis()

    # 检查 Redis 中的旧数据
    cursor = 0
    redis_count = 0

    while True:
        cursor, keys = await redis.scan(cursor, match="memory:*long_term*", count=100)
        redis_count += len(keys)
        if cursor == 0:
            break

    print(f"\n  Redis 中的长期记忆 Key 数量: {redis_count}")

    # 检查 PostgreSQL 中的数据
    from app.db.database import get_session, init_engine
    from app.core.config_center import get_config

    database_url = get_config("database.url", "postgresql://postgres:postgres@localhost:5432/meetingmind")
    await init_engine(database_url)

    async with get_session() as db:
        from sqlalchemy import select, func
        from app.models.memory import Memory

        count_result = await db.execute(
            select(func.count(Memory.id)).where(Memory.memory_type == "long_term")
        )
        pg_count = count_result.scalar() or 0

        print(f"  PostgreSQL 中的长期记忆数量: {pg_count}")

    print("\n" + "=" * 60)
    return redis_count > 0 or pg_count > 0


async def clean_old_redis_data(dry_run: bool = True):
    """清理 Redis 中的旧记忆数据（迁移完成后）"""

    print("\n" + "=" * 60)
    print("清理 Redis 中的旧记忆数据")
    print("=" * 60)

    if dry_run:
        print("⚠️  这是 DRY RUN 模式，不会实际删除数据")
        print("   确认迁移无误后，使用 clean_old_redis_data(dry_run=False) 执行实际删除")

    await init_redis()
    redis = get_redis()

    # 找到所有长期记忆的 key
    cursor = 0
    keys_to_delete = []

    while True:
        cursor, keys = await redis.scan(cursor, match="memory:*long_term*", count=100)
        keys_to_delete.extend(keys)
        if cursor == 0:
            break

    print(f"\n  需要删除的 Key 数量: {len(keys_to_delete)}")

    if dry_run:
        for key in keys_to_delete[:5]:  # 只显示前5个
            key_str = key.decode() if isinstance(key, bytes) else key
            print(f"    - {key_str}")
        if len(keys_to_delete) > 5:
            print(f"    ... 还有 {len(keys_to_delete) - 5} 个")
    else:
        # 实际删除
        deleted_count = 0
        for key in keys_to_delete:
            await redis.delete(key)
            deleted_count += 1

        print(f"\n  ✅ 已删除 {deleted_count} 个旧记忆 Key")

    # 保留短期记忆相关的 Key
    print("\n  保留的 Key 类型 (不删除):")
    print("    - memory:*:short_term (短期记忆)")
    print("    - memory:checkpoint:* (Checkpointer)")
    print("    - memory:hot:* (热点缓存)")


# ==================== 主入口 ====================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="记忆数据迁移工具")
    parser.add_argument("--action", choices=["migrate", "verify", "clean"], default="migrate",
                        help="执行的操作: migrate(迁移), verify(验证), clean(清理)")
    parser.add_argument("--dry-run", action="store_true", help="清理时使用DRY RUN模式")

    args = parser.parse_args()

    if args.action == "migrate":
        asyncio.run(migrate_memory_to_pg())
    elif args.action == "verify":
        asyncio.run(verify_migration())
    elif args.action == "clean":
        asyncio.run(clean_old_redis_data(dry_run=args.dry_run))
