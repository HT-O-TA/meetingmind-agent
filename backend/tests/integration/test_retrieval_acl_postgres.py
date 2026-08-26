"""真实 PostgreSQL 上验证文档 ACL 与软删除一致性。

默认核心测试不收集本文件；运行命令见阶段 1 文档。
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.core.security import AccessContext
from app.models.document import Document
from app.models.user import User
from app.models.vector import VectorChunk
from app.services.vector_search_service import VectorSearchService


@pytest.mark.asyncio
async def test_postgres_acl_and_soft_delete_are_authoritative():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        try:
            suffix = uuid4().hex
            owner = User(
                username=f"acl_owner_{suffix}",
                email=f"acl_owner_{suffix}@example.com",
                hashed_password="not-used",
                department="研发部",
                role="user",
            )
            outsider = User(
                username=f"acl_outsider_{suffix}",
                email=f"acl_outsider_{suffix}@example.com",
                hashed_password="not-used",
                department="市场部",
                role="user",
            )
            session.add_all([owner, outsider])
            await session.flush()

            documents = [
                Document(
                    uploader_id=owner.id,
                    filename=f"own-{suffix}.txt",
                    original_filename="own.txt",
                    file_path=f"/tmp/own-{suffix}.txt",
                    department="研发部",
                    is_public=False,
                ),
                Document(
                    uploader_id=outsider.id,
                    filename=f"public-{suffix}.txt",
                    original_filename="public.txt",
                    file_path=f"/tmp/public-{suffix}.txt",
                    department="市场部",
                    is_public=True,
                ),
                Document(
                    uploader_id=outsider.id,
                    filename=f"deleted-{suffix}.txt",
                    original_filename="deleted.txt",
                    file_path=f"/tmp/deleted-{suffix}.txt",
                    department="市场部",
                    is_public=True,
                    deleted_at=datetime.now(timezone.utc),
                ),
            ]
            session.add_all(documents)
            await session.flush()
            chunks = [
                VectorChunk(document_id=document.id, chunk_text=f"chunk-{index}", chunk_index=0)
                for index, document in enumerate(documents, 1)
            ]
            session.add_all(chunks)
            await session.flush()

            service = VectorSearchService(session)
            candidate_ids = [chunk.id for chunk in chunks]
            owner_results = await service._fetch_chunks_from_pg(
                candidate_ids,
                access_context=AccessContext(user_id=owner.id, department="研发部"),
            )
            outsider_results = await service._fetch_chunks_from_pg(
                candidate_ids,
                access_context=AccessContext(user_id=outsider.id, department="市场部"),
            )
            denied_results = await service._fetch_chunks_from_pg(
                candidate_ids,
                access_context=AccessContext(
                    user_id=outsider.id,
                    department="市场部",
                    document_scope=[],
                ),
            )

            assert {item["id"] for item in owner_results} == {chunks[0].id, chunks[1].id}
            assert {item["id"] for item in outsider_results} == {chunks[1].id}
            assert denied_results == []
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()
