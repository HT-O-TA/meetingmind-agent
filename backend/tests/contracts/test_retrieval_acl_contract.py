"""检索 ACL、软删除与缓存隔离的离线契约测试。"""
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.core.security import AccessContext
from app.models.vector import VectorChunk
from app.services.vector_cache_manager import MultiLevelCacheManager
from app.services.vector_search_service import VectorSearchService


def test_access_context_normalizes_untrusted_permission_ids():
    user = SimpleNamespace(
        id="7",
        department="研发部",
        role="user",
        permissions='{"meeting_ids": [1, "2", "bad"], "document_scope": []}',
    )

    context = AccessContext.from_user(user)

    assert context.user_id == 7
    assert context.meeting_ids == [1, 2]
    assert context.document_scope == []
    assert context.to_milvus_expr() == "meeting_id in [1, 2] and document_id in [-1]"
    assert "department_id" not in context.to_milvus_expr()


def test_postgres_rehydration_query_is_live_and_acl_filtered():
    service = VectorSearchService(db=None)
    context = AccessContext(
        user_id=7,
        department="研发部",
        document_scope=[3, 4],
        meeting_ids=[9],
    )

    query = service._apply_live_document_filters(select(VectorChunk), context)
    sql = str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    assert "JOIN documents" in sql
    assert "vector_chunks.deleted_at IS NULL" in sql
    assert "documents.deleted_at IS NULL" in sql
    assert "documents.is_public IS true" in sql
    assert "documents.uploader_id = 7" in sql
    assert "documents.department = '研发部'" in sql
    assert "vector_chunks.document_id IN (3, 4)" in sql
    assert "vector_chunks.meeting_id IN (9)" in sql


def test_pgvector_acl_sql_is_parameterized():
    context = AccessContext(
        user_id=7,
        department="研发部' OR TRUE --",
        document_scope=[3],
        meeting_ids=[9],
    )

    clause, params = VectorSearchService._build_acl_sql(context)

    assert "研发部" not in clause
    assert ":acl_department" in clause
    assert params["acl_department"] == "研发部' OR TRUE --"
    assert params["acl_document_id_0"] == 3
    assert params["acl_meeting_id_0"] == 9


@pytest.mark.asyncio
async def test_retrieval_cache_is_isolated_by_acl_scope():
    manager = MultiLevelCacheManager()
    query = "项目状态"
    team_a = {"acl": {"user_id": 1, "department": "A"}}
    team_b = {"acl": {"user_id": 2, "department": "B"}}

    await manager.cache_result(
        query,
        [{"chunk_id": 10, "document_id": 1, "score": 0.9}],
        top_k=5,
        filters=team_a,
    )

    assert await manager.get_cached_result(query, top_k=5, filters=team_b) is None
    cached = await manager.get_cached_result(query, top_k=5, filters=team_a)
    assert cached == [{"chunk_id": 10, "document_id": 1, "score": 0.9}]
