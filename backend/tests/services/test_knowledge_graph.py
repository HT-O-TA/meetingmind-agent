"""知识图谱服务测试"""
import pytest
from app.services.knowledge_graph import (
    get_knowledge_graph_index,
    build_graph_from_chunks,
    enhance_search_results,
    get_entity_subgraph
)


class TestKnowledgeGraph:
    """知识图谱测试类"""

    @pytest.mark.asyncio
    async def test_build_graph_from_chunks(self):
        """测试从 chunks 构建图谱"""
        chunks = [
            {"id": "chunk1", "content": "张三和李四讨论了项目计划"},
            {"id": "chunk2", "content": "王五负责技术架构"}
        ]
        result = await build_graph_from_chunks(chunks)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_enhance_search_results(self):
        """测试增强搜索结果"""
        vector_results = [
            {"document_id": "doc1", "content": "测试内容"}
        ]
        result = await enhance_search_results("测试查询", vector_results, depth=2)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_entity_subgraph(self):
        """测试获取实体子图"""
        result = await get_entity_subgraph("张三", depth=2)
        assert isinstance(result, dict)

    def test_get_knowledge_graph_index(self):
        """测试获取图谱索引"""
        index = get_knowledge_graph_index()
        assert index is not None
        assert hasattr(index, 'search_with_graph')
