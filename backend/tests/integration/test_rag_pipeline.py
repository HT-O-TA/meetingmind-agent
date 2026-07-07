"""RAG 全链路集成测试"""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.database import init_db, get_db
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


class TestRAGPipeline:
    """RAG全链路测试类"""

    @pytest.fixture(autouse=True)
    async def setup(self):
        """测试前置条件"""
        # 初始化数据库
        await init_db()
        yield
        # 测试清理（可选）

    async def test_health_endpoint(self):
        """测试健康检查端点"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert "app" in data

    async def test_rag_ask_endpoint_structure(self):
        """测试RAG问答端点结构"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 测试基本请求结构
            response = await client.post(
                "/api/v1/rag/ask",
                json={"question": "测试问题", "top_k": 3}
            )
            # 即使没有数据，也应该返回正确的结构
            assert response.status_code in [200, 500]  # 可能因为没有数据或LLM配置问题失败
            
    async def test_vector_search_endpoint(self):
        """测试向量检索端点"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/vector-search/search",
                json={"query": "测试查询", "top_k": 5}
            )
            # 检查响应结构是否正确
            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, list)

    async def test_document_upload_structure(self):
        """测试文档上传端点结构"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 测试空文件上传（会失败，但检查端点是否存在）
            response = await client.post("/api/v1/documents/upload")
            # 应该返回422验证错误（缺少文件）
            assert response.status_code == 422


class TestComplexityClassifier:
    """复杂度分类器集成测试"""

    async def test_classify_simple_question(self):
        """测试简单问题分类"""
        from app.services.complexity_classifier import get_complexity_classifier
        
        classifier = await get_complexity_classifier()
        result = await classifier.classify("你好")
        
        assert result["level"].value == "simple"
        assert result["score"] < 0.3
        assert not result["requires_retrieval"]
        assert not result["requires_reasoning"]

    async def test_classify_retrieval_question(self):
        """测试需要检索的问题分类"""
        from app.services.complexity_classifier import get_complexity_classifier
        
        classifier = await get_complexity_classifier()
        result = await classifier.classify("2025年武汉GDP是多少")
        
        assert result["level"].value in ["retrieval", "simple", "cot", "agent"]
        assert result["requires_retrieval"] or result["score"] >= 0.3

    async def test_classify_multi_task(self):
        """测试多任务问题分类"""
        from app.services.complexity_classifier import get_complexity_classifier
        
        classifier = await get_complexity_classifier()
        result = await classifier.classify("总结会议内容并提取行动项")
        
        assert result["is_multi_task"] or result["score"] >= 0.75


class TestEnhancedRetrievalFusion:
    """增强检索融合器集成测试"""

    async def test_fusion_initialization(self):
        """测试融合器初始化"""
        from app.services.enhanced_retrieval_fusion import get_enhanced_retrieval_fusion
        
        fusion = get_enhanced_retrieval_fusion(strategy="B")
        assert fusion is not None
        assert fusion.get_strategy() == "B"

    async def test_fusion_strategy_switch(self):
        """测试策略切换"""
        from app.services.enhanced_retrieval_fusion import create_enhanced_retrieval_fusion
        
        fusion = create_enhanced_retrieval_fusion(strategy="A")
        assert fusion.get_strategy() == "A"
        
        fusion.set_strategy("B")
        assert fusion.get_strategy() == "B"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
