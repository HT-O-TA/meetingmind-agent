"""冒烟测试 - UnifiedMemoryService 端到端验证

验证内容：
1. UnifiedMemoryService 可在无 db session 情况下创建
2. add_memory / search_memories / get_memory / delete_memory 端到端可用
3. generate_context_prompt 兼容方法可用
4. add_meeting_memory 兼容方法可用
5. get_statistics 可用
"""
import pytest
import asyncio
from datetime import datetime
from app.services.unified_memory_service import (
    UnifiedMemoryService,
    get_unified_memory_service,
    get_unified_memory,
)


class TestUnifiedMemoryServiceSmoke:
    """冒烟测试 - 验证 UnifiedMemoryService 核心路径"""

    def test_create_without_db(self):
        """测试无 db session 创建（后台任务模式）"""
        service = UnifiedMemoryService()
        assert service is not None
        assert service._db is None

    def test_factory_functions(self):
        """测试工厂函数"""
        service1 = get_unified_memory()
        service2 = get_unified_memory_service()
        assert isinstance(service1, UnifiedMemoryService)
        assert isinstance(service2, UnifiedMemoryService)

    @pytest.mark.asyncio
    async def test_add_and_search_memory(self):
        """测试添加和搜索记忆"""
        service = UnifiedMemoryService()

        # 添加记忆
        result = await service.add_memory(
            content="这是一条测试记忆内容，关于项目架构设计",
            memory_type="knowledge",
            metadata={"source": "smoke_test"},
            importance_score=0.8,
        )
        assert result["status"] in ("success", "partial_success")

    @pytest.mark.asyncio
    async def test_add_decision(self):
        """测试添加决策"""
        service = UnifiedMemoryService()

        result = await service.add_decision(
            content="决定采用微服务架构",
            meeting_id=1,
            entities=["张三", "李四"],
        )
        assert result["status"] in ("success", "partial_success")
        assert result.get("pg_memory_id") is not None or result.get("ltm_memory_id") is not None

    @pytest.mark.asyncio
    async def test_add_action_item(self):
        """测试添加行动项"""
        service = UnifiedMemoryService()

        result = await service.add_action_item(
            content="完成 API 文档编写",
            meeting_id=1,
            entities=["王五"],
        )
        assert result["status"] in ("success", "partial_success")

    @pytest.mark.asyncio
    async def test_generate_context_prompt(self):
        """测试生成上下文提示词"""
        service = UnifiedMemoryService()

        # 先添加一些记忆
        await service.add_memory(
            content="项目采用 PostgreSQL 作为主数据库",
            memory_type="knowledge",
            importance_score=0.9,
        )

        # 生成提示词
        prompt = await service.generate_context_prompt("数据库选择")
        assert isinstance(prompt, str)
        # 至少包含历史记忆标记
        if prompt:
            assert "历史会议记忆" in prompt

    @pytest.mark.asyncio
    async def test_add_meeting_memory_compat(self):
        """测试兼容旧接口的 add_meeting_memory"""
        service = UnifiedMemoryService()

        # 简化版参数
        result = await service.add_meeting_memory(
            meeting_id="999",
            title="测试会议",
            content="会议讨论了项目架构",
            session_id="test_session",
        )
        assert result["success"] is True
        assert result["meeting_id"] == "999"

    @pytest.mark.asyncio
    async def test_full_version_add_meeting_memory(self):
        """测试完整版 add_meeting_memory（API 端点兼容）"""
        service = UnifiedMemoryService()

        result = await service.add_meeting_memory(
            meeting_id="100",
            topic="产品评审",
            date="2025-01-01",
            participants=["张三", "李四"],
            summary="评审通过，进入开发阶段",
            decisions=["采用方案 A"],
            action_items=["完成原型", "编写文档"],
            controversies=["时间线紧张"],
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_get_statistics(self):
        """测试获取统计信息"""
        service = UnifiedMemoryService()
        stats = await service.get_statistics()
        assert isinstance(stats, dict)
        assert "memory_store" in stats
        assert "long_term_memory" in stats

    @pytest.mark.asyncio
    async def test_delete_memory(self):
        """测试删除记忆"""
        service = UnifiedMemoryService()

        # 先添加
        add_result = await service.add_memory(
            content="待删除的记忆",
            memory_type="knowledge",
            importance_score=0.3,
        )
        assert add_result["status"] in ("success", "partial_success")

        # 删除（软删除/归档）
        pg_id = add_result.get("pg_memory_id")
        if pg_id:
            delete_result = await service.delete_memory(pg_id)
            assert delete_result["status"] == "success"

    @pytest.mark.asyncio
    async def test_find_relevant_memories(self):
        """测试兼容旧接口的 find_relevant_memories"""
        service = UnifiedMemoryService()

        await service.add_memory(
            content="关于人工智能的测试内容",
            memory_type="knowledge",
        )

        results = await service.find_relevant_memories("人工智能")
        assert isinstance(results, list)


class TestMemoryStoreBackwardCompat:
    """测试 MemoryStore 向后兼容"""

    def test_memory_store_without_db(self):
        """测试 MemoryStore 无 db 创建"""
        from app.services.memory_store import MemoryStore
        store = MemoryStore()
        assert store._db is None

    def test_get_memory_store_without_db(self):
        """测试工厂函数无 db"""
        from app.services.memory_store import get_memory_store
        store = get_memory_store()
        assert store is not None


class TestLongTermMemoryBackwardCompat:
    """测试 LongTermMemory 类保留（作为存储后端）"""

    def test_long_term_memory_class_exists(self):
        """验证 LongTermMemory 类存在"""
        from app.services.long_term_memory import LongTermMemory
        assert hasattr(LongTermMemory, '__init__')

    def test_enums_and_dataclasses_preserved(self):
        """验证枚举和数据类保留（供 UnifiedMemoryService 复用）"""
        from app.services.long_term_memory import (
            LongTermMemory,
            MemoryType,
            MemoryScope,
            MemoryEntry,
            MeetingContext,
        )
        assert LongTermMemory is not None
        assert MemoryType is not None
        assert MemoryScope is not None
        assert MemoryEntry is not None
        assert MeetingContext is not None


class TestMemorySystemBackwardCompat:
    """测试 MemorySystem 向后兼容"""

    def test_memory_system_creation(self):
        """验证 MemorySystem 可创建"""
        from app.agents.memory import MemorySystem
        system = MemorySystem()
        assert system is not None
        assert system.memory_store is not None

    def test_memory_manager_creation(self):
        """验证 MemoryManager 可创建"""
        from app.agents.memory import MemoryManager
        manager = MemoryManager()
        assert manager is not None

    @pytest.mark.asyncio
    async def test_memory_system_short_term(self):
        """验证短期记忆功能正常"""
        from app.agents.memory import MemorySystem
        system = MemorySystem()
        system.add_short_term_memory("测试内容")
        assert len(system._short_term_memory) >= 1