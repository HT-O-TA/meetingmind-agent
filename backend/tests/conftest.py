"""pytest 配置文件"""
import fnmatch
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.llm_service import LLMService
from app.services.vector_search_service import VectorSearchService
from app.core.config import settings


@pytest.fixture(autouse=True)
def disable_rate_limits_for_offline_tests(monkeypatch):
    """普通离线测试不依赖 Redis；限流契约测试会显式重新开启。"""
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)


class InMemoryRedis:
    """覆盖 HITL 契约所需的最小异步 Redis 行为。"""

    def __init__(self):
        self.data = {}

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.data:
            return False
        self.data[key] = value
        return True

    async def get(self, key):
        return self.data.get(key)

    async def delete(self, key):
        return int(self.data.pop(key, None) is not None)

    async def eval(self, script, key_count, key, owner, *args):
        assert key_count == 1
        if await self.get(key) != owner:
            return 0
        if "EXPIRE" in script:
            return 1
        if "DEL" in script:
            return await self.delete(key)
        raise AssertionError("Unsupported Redis script")

    async def scan_iter(self, match="*", count=None):
        for key in list(self.data):
            if fnmatch.fnmatch(key, match):
                yield key


@pytest.fixture
def fake_redis():
    return InMemoryRedis()


@pytest.fixture
def mock_llm_service():
    """模拟 LLM 服务"""
    mock = AsyncMock(spec=LLMService)
    mock.chat.return_value = "测试响应"
    return mock


@pytest.fixture
def mock_vector_search_service():
    """模拟向量搜索服务"""
    mock = AsyncMock(spec=VectorSearchService)
    mock.search_by_text.return_value = [
        {"document_id": "doc1", "content": "测试内容", "speaker_name": "测试用户", "similarity": 0.9}
    ]
    mock.search_with_multi_retrieval.return_value = [
        {"document_id": "doc1", "content": "测试内容", "speaker_name": "测试用户", "similarity": 0.9}
    ]
    mock.get_document_chunks.return_value = [
        {"id": 1, "document_id": 1, "chunk_text": "测试内容"}
    ]
    return mock


@pytest.fixture
def test_data_dir():
    """测试数据目录"""
    import os
    return os.path.join(os.path.dirname(__file__), "data")
