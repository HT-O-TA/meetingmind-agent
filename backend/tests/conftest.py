"""pytest 配置文件"""
import fnmatch
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.llm_service import LLMService
from app.services.vector_search_service import VectorSearchService


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
    return mock


@pytest.fixture
def test_data_dir():
    """测试数据目录"""
    import os
    return os.path.join(os.path.dirname(__file__), "data")
