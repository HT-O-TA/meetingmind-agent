"""创建阶段 2 工具执行审计表。

应用启动时 ``create_all`` 会覆盖冷启动；此脚本用于已有数据库显式升级：
PYTHONPATH=backend python backend/app/db/migrations/0007_add_tool_execution_audits.py
"""
import asyncio

from app.db.database import engine
from app.models.tool_execution import ToolExecutionAudit


async def upgrade() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(ToolExecutionAudit.__table__.create, checkfirst=True)


if __name__ == "__main__":
    asyncio.run(upgrade())
