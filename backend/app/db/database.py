"""
数据库模块 - PostgreSQL 异步连接池管理

配置说明：
- 使用 SQLAlchemy 2.0 异步引擎 (create_async_engine)
- 连接池参数：pool_size=10, max_overflow=20
- pool_pre_ping=True：每次从池中获取连接前先测试连接是否有效
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from app.core.config import settings


# ============================================================================
# 数据库引擎配置 (create_async_engine)
# ============================================================================
# 参数说明：
#   - DATABASE_URL: PostgreSQL 连接字符串，格式如：
#     postgresql+asyncpg://user:password@host:port/database
#
#   - echo=False: 强制关闭 SQL 日志输出，避免打印敏感数据和大量日志
#     注意：即使 settings.DEBUG=True 也不会输出 SQL
#
#   - future=True: 启用 SQLAlchemy 2.0 特性，使用新的查询编译机制
#
#   - pool_size=10: 保持 10 个空闲连接在池中，减少连接创建开销
#     适用于中等并发场景，如需更高并发可调大此值
#
#   - max_overflow=20: 允许最多额外创建 20 个临时连接（超过 pool_size）
#     总最大连接数 = pool_size + max_overflow = 30
#
#   - pool_pre_ping=True: 每次获取连接前执行 SELECT 1 测试连接
#     防止使用已断开的死连接，提高连接可靠性
# ============================================================================
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # 强制关闭，不受 DEBUG 设置影响
    future=True,  # 启用 SQLAlchemy 2.0
    pool_size=10,  # 空闲连接池大小
    max_overflow=20,  # 最大临时连接数（突发时可用）
    pool_pre_ping=True,  # 连接可用性检测
)


# ============================================================================
# 异步会话工厂 (async_sessionmaker)
# ============================================================================
# 参数说明：
#   - engine: 绑定数据库引擎
#
#   - class_=AsyncSession: 使用异步会话类（与同步 Session 区分）
#
#   - expire_on_commit=False: 事务提交后不自动过期对象
#     允许在提交后仍访问对象的属性（如延迟加载字段）
#
#   - autocommit=False: 禁用自动提交，需手动 session.commit()
#     这是最佳实践，确保显式控制事务
#
#   - autoflush=False: 禁用自动刷新（将待处理变更写入数据库）
#     结合 with_for_update() 等语句时更安全，避免意外提交
# ============================================================================
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,  # 异步会话
    expire_on_commit=False,  # 提交后保留对象可访问性
    autocommit=False,  # 手动提交（推荐）
    autoflush=False,  # 手动刷新（推荐）
)


class Base(DeclarativeBase):
    pass


# ============================================================================
# 数据库会话依赖注入 (get_db)
# ============================================================================
# FastAPI 依赖注入函数，用于 API 路由中获取数据库会话
#
# 使用方式：
#   @router.get("/items")
#   async def get_items(db: AsyncSession = Depends(get_db)):
#       ...
#
# 事务管理：
#   - 正常流程：自动提交 (commit) 变更
#   - 异常流程：自动回滚 (rollback) 变更
#   - 最终：确保关闭连接，归还到连接池
# ============================================================================
async def get_db():
    """
    数据库会话依赖注入
    
    每次请求创建一个新会话，请求结束后自动关闭。
    支持事务自动回滚，确保数据一致性。
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session  # 返回会话给路由处理
        except Exception:
            await session.rollback()  # 异常时回滚事务
            raise
        finally:
            await session.close()  # 确保关闭连接


# ============================================================================
# 数据库初始化 (init_db)
# ============================================================================
# 创建所有表结构（仅在数据库首次创建时使用）
# 使用 engine.begin() 开启事务上下文
# ============================================================================
async def init_db():
    """创建 ORM 表，并确保无需手工迁移即可使用基础全文索引。"""
    import app.models  # noqa: F401 - 注册所有 ORM metadata

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_vector_chunks_fts_simple
            ON vector_chunks USING GIN (
                to_tsvector('simple', COALESCE(chunk_text, ''))
            )
        """))
