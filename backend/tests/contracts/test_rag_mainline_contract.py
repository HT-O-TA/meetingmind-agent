"""RAG 正式主链路的最小契约测试。

这些测试直接加载生产源码，但用轻量替身隔离数据库、Milvus、模型和 Web 框架。
因此可用标准库 ``unittest`` 运行，不要求先启动任何外部服务。
"""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


BACKEND_ROOT = Path(__file__).resolve().parents[2]
SERVICES_ROOT = BACKEND_ROOT / "app" / "services"


def _module(name: str, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _package(name: str):
    module = _module(name)
    module.__path__ = []
    return module


def _load_service(filename: str, module_name: str, stubs: dict[str, types.ModuleType]):
    """在依赖替身生效期间加载一份独立的生产服务模块。"""
    source_path = SERVICES_ROOT / filename
    spec = importlib.util.spec_from_file_location(module_name, source_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载生产源码: {source_path}")

    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


def _base_app_packages():
    return {
        "app": _package("app"),
        "app.core": _package("app.core"),
        "app.db": _package("app.db"),
        "app.models": _package("app.models"),
        "app.services": _package("app.services"),
    }


class TestRAGServiceContract(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = SimpleNamespace(
            ENABLE_KNOWLEDGE_GRAPH=False,
            ENABLE_RERANK=False,
            RERANK_TOP_N=10,
        )

        async def unused_graph_enhancement(*args, **kwargs):
            raise AssertionError("关闭知识图谱时不应执行图谱增强")

        stubs = _base_app_packages()
        stubs.update({
            "app.services.vector_search_service": _module(
                "app.services.vector_search_service", VectorSearchService=object
            ),
            "app.services.llm_service": _module(
                "app.services.llm_service", LLMService=object
            ),
            "app.services.knowledge_graph": _module(
                "app.services.knowledge_graph",
                enhance_search_results=unused_graph_enhancement,
                get_knowledge_graph_index=MagicMock(
                    side_effect=AssertionError("关闭知识图谱时不应初始化图谱")
                ),
            ),
            "app.services.enhanced_retrieval_fusion": _module(
                "app.services.enhanced_retrieval_fusion",
                get_enhanced_retrieval_fusion=MagicMock(
                    side_effect=AssertionError("关闭重排序时不应初始化 Reranker")
                ),
            ),
            "app.core.logger": _module(
                "app.core.logger", app_logger=MagicMock()
            ),
            "app.core.config": _module(
                "app.core.config", settings=self.settings
            ),
        })
        self.rag_module = _load_service(
            "rag_service.py", "rag_service_contract_target", stubs
        )

    async def test_ask_uses_the_official_retrieval_contract(self):
        class FakeVectorService:
            use_milvus = True

            def __init__(self):
                self.calls = []

            async def search_with_multi_retrieval(self, **kwargs):
                self.calls.append(kwargs)
                return [{
                    "chunk_id": 7,
                    "chunk_text": "项目将在周五上线。",
                    "score": 0.91,
                    "sources": ["bm25", "dense"],
                }]

        class FakeLLMService:
            async def generate_answer(self, **kwargs):
                raise AssertionError("use_llm=False 时不应调用 LLM")

        vector_service = FakeVectorService()
        service = self.rag_module.RAGService(vector_service, FakeLLMService())

        result = await service.ask(
            question="项目何时上线？",
            top_k=3,
            meeting_id=12,
            department="研发部",
            similarity_threshold=0.2,
            use_llm=False,
        )

        self.assertEqual(len(vector_service.calls), 1)
        self.assertEqual(vector_service.calls[0], {
            "query_text": "项目何时上线？",
            "top_k": 3,
            "meeting_id": 12,
            "department": "研发部",
            "similarity_threshold": 0.2,
            "enable_bm25": True,
            "enable_vector": True,
            "enable_rerank": False,
            "strategy": "A",
            "access_context": None,
        })
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["mode"], "milvus")
        self.assertEqual(result["retrieval_sources"], ["bm25", "dense"])
        self.assertIn("项目将在周五上线。", result["answer"])

    async def test_empty_retrieval_has_a_stable_degraded_response(self):
        class EmptyVectorService:
            use_milvus = False
            use_pgvector = False

            async def search_with_multi_retrieval(self, **kwargs):
                return []

        service = self.rag_module.RAGService(EmptyVectorService(), object())
        result = await service.ask("不存在的问题", use_llm=False)

        self.assertEqual(result["chunks"], [])
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["query_type"], "standard")
        self.assertEqual(result["mode"], "lightweight")
        self.assertIn("没有找到", result["answer"])

    async def test_reranker_receives_a_candidate_pool_larger_than_final_top_k(self):
        candidates = [
            {
                "chunk_id": index,
                "chunk_text": f"候选 {index}",
                "score": 1.0 / index,
                "sources": ["dense"],
            }
            for index in range(1, 11)
        ]

        class FakeVectorService:
            use_milvus = False
            use_pgvector = True

            def __init__(self):
                self.requested_top_k = None

            async def search_with_multi_retrieval(self, **kwargs):
                self.requested_top_k = kwargs["top_k"]
                return candidates

        class FakeFusion:
            def __init__(self):
                self.received_count = 0
                self.output_top_k = None

            async def rerank_candidates(self, query, received, top_k):
                self.received_count = len(received)
                self.output_top_k = top_k
                return received[:top_k]

        vector_service = FakeVectorService()
        fusion = FakeFusion()
        self.settings.ENABLE_RERANK = True
        self.rag_module.get_enhanced_retrieval_fusion = lambda strategy: fusion
        service = self.rag_module.RAGService(vector_service, object())

        result = await service.ask("哪个候选最相关？", top_k=3, use_llm=False)

        self.assertEqual(vector_service.requested_top_k, 10)
        self.assertEqual(fusion.received_count, 10)
        self.assertEqual(fusion.output_top_k, 3)
        self.assertEqual(result["count"], 3)


class TestRetrievalDataContract(unittest.IsolatedAsyncioTestCase):
    def test_dense_full_text_wins_when_two_retrievers_hit_the_same_chunk(self):
        settings = SimpleNamespace(
            BM25_WEIGHT=0.3,
            VECTOR_WEIGHT=0.7,
            RRF_K=60,
            RERANK_TOP_N=20,
            LOCAL_EMBEDDING_MODEL_PATH="",
        )
        stubs = _base_app_packages()
        stubs.update({
            "app.core.logger": _module(
                "app.core.logger", app_logger=MagicMock()
            ),
            "app.core.config": _module(
                "app.core.config", settings=settings
            ),
        })
        fusion_module = _load_service(
            "enhanced_retrieval_fusion.py",
            "enhanced_fusion_contract_target",
            stubs,
        )
        fusion = object.__new__(fusion_module.EnhancedMultiRetrievalFusion)

        full_text = "完整正文-" + "用于生成答案的上下文。" * 30
        result = fusion._weighted_fusion(
            bm25_results=[{
                "chunk_id": 9,
                "score": 2.0,
                "content": "BM25 展示片段……",
            }],
            dense_results=[{
                "chunk_id": 9,
                "similarity": 0.8,
                "chunk_text": full_text,
            }],
        )

        self.assertEqual(result[0]["chunk_text"], full_text)
        self.assertEqual(result[0]["content"], full_text)
        self.assertEqual(result[0]["sources"], ["bm25", "dense"])

    async def test_bm25_returns_full_chunk_text_for_rerank_and_generation(self):
        long_text = "会议正文" * 80

        class FakeRow:
            chunk_id = 3
            document_id = 4
            chunk_text = long_text
            meeting_id = 5
            department = "产品部"
            rank = 0.75

        class FakeResult:
            def __init__(self, rows=None, scalar_value=None):
                self._rows = rows or []
                self._scalar_value = scalar_value

            def scalar(self):
                return self._scalar_value

            def fetchall(self):
                return self._rows

        class FakeSession:
            def __init__(self):
                self.calls = 0

            async def execute(self, *args, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return FakeResult(scalar_value="ok")
                return FakeResult(rows=[FakeRow()])

        fake_session = FakeSession()

        class FakeSessionContext:
            async def __aenter__(self):
                return fake_session

            async def __aexit__(self, exc_type, exc, traceback):
                return False

        sqlalchemy = _package("sqlalchemy")
        sqlalchemy.text = lambda statement: statement
        stubs = _base_app_packages()
        stubs.update({
            "sqlalchemy": sqlalchemy,
            "app.db.database": _module(
                "app.db.database", async_session=lambda: FakeSessionContext()
            ),
            "app.core.logger": _module(
                "app.core.logger", app_logger=MagicMock()
            ),
            "app.core.security": _module(
                "app.core.security", AccessContext=object
            ),
        })
        bm25_module = _load_service(
            "bm25_retriever.py", "bm25_contract_target", stubs
        )

        results = await bm25_module.BM25Retriever().search("会议", top_k=1)

        self.assertEqual(results[0]["content"], long_text)
        self.assertEqual(results[0]["chunk_text"], long_text)
        self.assertGreater(len(results[0]["content"]), 200)


class TestVectorCacheContract(unittest.IsolatedAsyncioTestCase):
    async def test_successful_milvus_lookup_uses_the_cache_write_contract(self):
        cache_writes = []

        async def cache_get(*args, **kwargs):
            return None

        async def cache_set(*args, **kwargs):
            cache_writes.append((args, kwargs))

        sqlalchemy = _package("sqlalchemy")
        sqlalchemy.select = MagicMock()
        sqlalchemy.text = MagicMock()
        sqlalchemy.func = MagicMock()
        sqlalchemy.and_ = MagicMock()
        sqlalchemy.or_ = MagicMock()
        sqlalchemy.false = MagicMock()
        sqlalchemy_ext = _package("sqlalchemy.ext")
        sqlalchemy_asyncio = _module(
            "sqlalchemy.ext.asyncio",
            AsyncSession=object,
            create_async_engine=MagicMock(),
            async_sessionmaker=MagicMock(),
        )

        stubs = _base_app_packages()
        stubs.update({
            "sqlalchemy": sqlalchemy,
            "sqlalchemy.ext": sqlalchemy_ext,
            "sqlalchemy.ext.asyncio": sqlalchemy_asyncio,
            "app.models.vector": _module(
                "app.models.vector", VectorChunk=object
            ),
            "app.models.document": _module(
                "app.models.document", Document=object
            ),
            "app.core.config": _module(
                "app.core.config", settings=SimpleNamespace()
            ),
            "app.core.logger": _module(
                "app.core.logger", app_logger=MagicMock()
            ),
            "app.core.security": _module(
                "app.core.security", AccessContext=object
            ),
            "app.core.cache": _module(
                "app.core.cache", cache_get=cache_get, cache_set=cache_set
            ),
            "app.services.vector_cache_manager": _module(
                "app.services.vector_cache_manager",
                get_cached_result=cache_get,
                set_cached_result=cache_set,
            ),
        })
        vector_module = _load_service(
            "vector_search_service.py", "vector_search_contract_target", stubs
        )

        service = vector_module.VectorSearchService(db=object())
        service.use_milvus = True
        service._milvus_retrieve_ids = AsyncMock(return_value=[{
            "chunk_id": 11,
            "document_id": 2,
            "score": 0.88,
        }])
        service._fetch_chunks_from_pg = AsyncMock(return_value=[{
            "id": 11,
            "document_id": 2,
            "chunk_text": "完整正文",
            "speaker_name": "张三",
            "time_offset": 12.5,
            "metadata_json": {},
        }])
        service._search_fallback = AsyncMock(return_value=[{"fallback": True}])

        results = await service.search_by_text("项目进度", top_k=1)

        self.assertEqual(results[0]["chunk_text"], "完整正文")
        self.assertEqual(len(cache_writes), 1)
        self.assertEqual(cache_writes[0][0][0], "项目进度")
        service._search_fallback.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
