"""UnifiedMemoryService 单元测试 - Mock 隔离后端依赖

测试策略：
- 使用 unittest.mock 隔离 MemoryStore 和 LongTermMemory 后端
- 覆盖所有公共方法的正常路径、边界条件和错误处理
- 不依赖真实数据库/Redis 连接，可独立运行

覆盖范围：
1. 初始化与工厂函数
2. add_memory（含 dual_write、expires_at 自动设置、错误处理）
3. 快捷方法（add_decision / add_action_item / add_knowledge）
4. search_memories（含过滤、去重、排序、source 隔离）
5. get_memory（含 source 过滤、未找到）
6. update_memory
7. delete_memory（含部分失败）
8. purge_expired
9. generate_context_prompt（空结果、长内容截断）
10. add_meeting_memory（简化版、完整版、key_points）
11. _map_memory_type / _map_scope 映射逻辑
12. get_statistics 聚合
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from app.services.unified_memory_service import (
    UnifiedMemoryService,
    get_unified_memory,
    get_unified_memory_service,
)


# ==================== 测试用 Mock 工厂 ====================

def make_mock_pg_memory(memory_id="pg-001", content="测试内容", memory_type="knowledge",
                        importance_score=0.8, metadata=None, meeting_id=None):
    """构造模拟的 PostgreSQL 记忆对象"""
    m = MagicMock()
    m.memory_id = memory_id
    m.content = content
    m.memory_type = memory_type
    m.importance_score = importance_score
    m.memory_metadata = metadata or {}
    m.source_meeting_id = meeting_id
    m.created_at = datetime(2026, 1, 1)
    return m


def make_mock_ltm_entry(memory_id="ltm-001", content="测试内容", type_str="knowledge",
                        scope_str="team", score=0.85, meeting_id=None, entities=None):
    """构造模拟的 LongTermMemory Entry"""
    entry = MagicMock()
    entry.memory_id = memory_id
    entry.content = content
    entry.type.value = type_str
    entry.scope.value = scope_str
    entry.meeting_id = meeting_id
    entry.entities = entities or []
    entry.timestamp = datetime(2026, 1, 1)
    return entry


def create_service_with_mocks():
    """创建带 Mock 后端的 UnifiedMemoryService 实例"""
    service = UnifiedMemoryService()

    # Mock MemoryStore
    mock_store = MagicMock()
    mock_store.create_memory = AsyncMock(return_value=make_mock_pg_memory())
    mock_store.search_memories = AsyncMock(return_value=[])
    mock_store.get_memory_by_id = AsyncMock(return_value=None)
    mock_store.update_memory = AsyncMock(return_value=True)
    mock_store.delete_memory = AsyncMock(return_value=True)
    mock_store.get_memory_stats = AsyncMock(return_value={"total": 10, "avg_importance": 0.7})
    mock_store.expire_memories = AsyncMock(return_value=3)
    service._memory_store = mock_store

    # Mock LongTermMemory
    mock_ltm = MagicMock()
    mock_ltm.add_memory = AsyncMock(return_value=make_mock_ltm_entry())
    mock_ltm.search_memories = AsyncMock(return_value=[])
    mock_ltm.get_memory = MagicMock(return_value=None)
    mock_ltm.delete_memory = AsyncMock(return_value=True)
    mock_ltm.get_statistics = MagicMock(return_value={"total": 5})
    mock_ltm.purge_expired = AsyncMock(return_value=2)
    mock_ltm.generate_context_prompt = AsyncMock(return_value="")
    service._ltm = mock_ltm

    return service, mock_store, mock_ltm


# ==================== 1. 初始化与工厂函数 ====================

class TestInit:
    """测试初始化"""

    def test_init_without_db(self):
        service = UnifiedMemoryService()
        assert service._db is None
        assert service._memory_store is None
        assert service._ltm is None

    def test_init_with_db(self):
        mock_db = MagicMock()
        service = UnifiedMemoryService(db=mock_db)
        assert service._db is mock_db

    def test_lazy_loading_memory_store(self):
        service = UnifiedMemoryService()
        # 首次访问触发懒加载
        store = service.memory_store
        assert store is not None
        assert service._memory_store is store

    def test_lazy_loading_ltm(self):
        service = UnifiedMemoryService()
        ltm = service.ltm
        assert ltm is not None
        assert service._ltm is ltm

    def test_factory_get_unified_memory(self):
        service = get_unified_memory()
        assert isinstance(service, UnifiedMemoryService)

    def test_factory_get_unified_memory_service_with_db(self):
        mock_db = MagicMock()
        service = get_unified_memory_service(mock_db)
        assert isinstance(service, UnifiedMemoryService)
        assert service._db is mock_db


# ==================== 2. add_memory ====================

class TestAddMemory:
    """测试 add_memory 核心写入"""

    @pytest.mark.asyncio
    async def test_dual_write_success(self):
        """双写成功返回 success"""
        service, mock_store, mock_ltm = create_service_with_mocks()

        result = await service.add_memory(
            content="测试记忆",
            memory_type="knowledge",
            importance_score=0.8,
        )
        assert result["status"] == "success"
        assert result["pg_memory_id"] == "pg-001"
        assert result["ltm_memory_id"] == "ltm-001"
        assert result["errors"] == []
        mock_store.create_memory.assert_called_once()
        mock_ltm.add_memory.assert_called_once()

    @pytest.mark.asyncio
    async def test_dual_write_false_skips_ltm(self):
        """dual_write=False 时跳过 LongTermMemory"""
        service, mock_store, mock_ltm = create_service_with_mocks()

        result = await service.add_memory(
            content="仅PG写入",
            memory_type="knowledge",
            dual_write=False,
        )
        assert result["status"] == "success"
        assert result["pg_memory_id"] == "pg-001"
        assert result["ltm_memory_id"] is None
        mock_store.create_memory.assert_called_once()
        mock_ltm.add_memory.assert_not_called()

    @pytest.mark.asyncio
    async def test_pg_failure_partial_success(self):
        """MemoryStore 失败，LongTermMemory 成功 → partial_success"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        mock_store.create_memory = AsyncMock(side_effect=Exception("PG连接失败"))

        result = await service.add_memory(content="测试", memory_type="knowledge")
        assert result["status"] == "partial_success"
        assert result["pg_memory_id"] is None
        assert result["ltm_memory_id"] == "ltm-001"
        assert len(result["errors"]) == 1
        assert "MemoryStore" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_ltm_failure_partial_success(self):
        """LongTermMemory 失败，MemoryStore 成功 → partial_success"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        mock_ltm.add_memory = AsyncMock(side_effect=Exception("LTM写入失败"))

        result = await service.add_memory(content="测试", memory_type="knowledge")
        assert result["status"] == "partial_success"
        assert result["pg_memory_id"] == "pg-001"
        assert result["ltm_memory_id"] is None
        assert len(result["errors"]) == 1
        assert "LongTermMemory" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_both_failure_returns_failed(self):
        """两套后端都失败 → failed"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        mock_store.create_memory = AsyncMock(side_effect=Exception("PG失败"))
        mock_ltm.add_memory = AsyncMock(side_effect=Exception("LTM失败"))

        result = await service.add_memory(content="测试", memory_type="knowledge")
        assert result["status"] == "failed"
        assert result["pg_memory_id"] is None
        assert result["ltm_memory_id"] is None
        assert len(result["errors"]) == 2

    @pytest.mark.asyncio
    async def test_auto_expires_at_from_config(self):
        """未传 expires_at 时自动从配置设置"""
        service, mock_store, _ = create_service_with_mocks()

        await service.add_memory(content="测试", memory_type="knowledge")
        call_kwargs = mock_store.create_memory.call_args[1]
        assert "expires_at" in call_kwargs
        assert call_kwargs["expires_at"] is not None

    @pytest.mark.asyncio
    async def test_explicit_expires_at_preserved(self):
        """显式传入 expires_at 时不被覆盖"""
        service, mock_store, _ = create_service_with_mocks()
        custom_expiry = datetime(2099, 1, 1)

        await service.add_memory(
            content="测试",
            memory_type="knowledge",
            expires_at=custom_expiry,
        )
        call_kwargs = mock_store.create_memory.call_args[1]
        assert call_kwargs["expires_at"] == custom_expiry

    @pytest.mark.asyncio
    async def test_all_params_passed_to_store(self):
        """验证所有参数正确传递到 MemoryStore"""
        service, mock_store, _ = create_service_with_mocks()

        await service.add_memory(
            content="完整参数测试",
            memory_type="decision",
            user_id=42,
            session_id="sess-1",
            meeting_id=100,
            metadata={"key": "value"},
            importance_score=0.9,
            entities=["张三"],
            scope="team",
        )
        call_kwargs = mock_store.create_memory.call_args[1]
        assert call_kwargs["content"] == "完整参数测试"
        assert call_kwargs["memory_type"] == "decision"
        assert call_kwargs["user_id"] == 42
        assert call_kwargs["session_id"] == "sess-1"
        assert call_kwargs["source_meeting_id"] == 100
        assert call_kwargs["importance_score"] == 0.9


# ==================== 3. 快捷方法 ====================

class TestShortcutMethods:
    """测试 add_decision / add_action_item / add_knowledge"""

    @pytest.mark.asyncio
    async def test_add_decision_params(self):
        """add_decision 正确传递 decision 类型和高重要性"""
        service, mock_store, _ = create_service_with_mocks()

        await service.add_decision(
            content="决定采用微服务架构",
            meeting_id=1,
            entities=["张三"],
        )
        call_kwargs = mock_store.create_memory.call_args[1]
        assert call_kwargs["memory_type"] == "decision"
        assert call_kwargs["importance_score"] == 0.8
        assert call_kwargs["source_meeting_id"] == 1

    @pytest.mark.asyncio
    async def test_add_action_item_params(self):
        """add_action_item 正确传递 action_item 类型"""
        service, mock_store, _ = create_service_with_mocks()

        await service.add_action_item(
            content="完成API文档",
            meeting_id=5,
            entities=["李四"],
        )
        call_kwargs = mock_store.create_memory.call_args[1]
        assert call_kwargs["memory_type"] == "action_item"
        assert call_kwargs["importance_score"] == 0.7

    @pytest.mark.asyncio
    async def test_add_knowledge_params(self):
        """add_knowledge 正确传递 knowledge 类型和最高重要性"""
        service, mock_store, _ = create_service_with_mocks()

        await service.add_knowledge(
            content="项目使用 PostgreSQL",
            entities=["架构组"],
        )
        call_kwargs = mock_store.create_memory.call_args[1]
        assert call_kwargs["memory_type"] == "knowledge"
        assert call_kwargs["importance_score"] == 0.9


# ==================== 4. search_memories ====================

class TestSearchMemories:
    """测试统一检索"""

    @pytest.mark.asyncio
    async def test_search_both_sources(self):
        """同时从两个后端检索并合并"""
        service, mock_store, mock_ltm = create_service_with_mocks()

        # 设置 Mock 返回值
        pg_mem = make_mock_pg_memory(memory_id="pg-1", content="PG结果", importance_score=0.8)
        mock_store.search_memories = AsyncMock(return_value=[pg_mem])

        ltm_entry = make_mock_ltm_entry(memory_id="ltm-1", content="LTM结果", score=0.9)
        mock_ltm.search_memories = AsyncMock(return_value=[(ltm_entry, 0.9)])

        results = await service.search_memories("测试查询")

        assert len(results) == 2
        sources = {r["source"] for r in results}
        assert sources == {"memory_store", "long_term_memory"}
        # 按分数降序
        assert results[0]["score"] >= results[1]["score"]

    @pytest.mark.asyncio
    async def test_search_semantic_only(self):
        """include_structured=False 时只查 LongTermMemory"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        mock_ltm.search_memories = AsyncMock(return_value=[])

        await service.search_memories("查询", include_structured=False)
        mock_store.search_memories.assert_not_called()
        mock_ltm.search_memories.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_structured_only(self):
        """include_semantic=False 时只查 MemoryStore"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        mock_store.search_memories = AsyncMock(return_value=[])

        await service.search_memories("查询", include_semantic=False)
        mock_ltm.search_memories.assert_not_called()
        mock_store.search_memories.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_deduplication(self):
        """相同内容的记忆去重"""
        service, mock_store, mock_ltm = create_service_with_mocks()

        same_content = "完全相同的内容用于去重测试"
        pg_mem = make_mock_pg_memory(memory_id="pg-1", content=same_content)
        ltm_entry = make_mock_ltm_entry(memory_id="ltm-1", content=same_content)

        mock_store.search_memories = AsyncMock(return_value=[pg_mem])
        mock_ltm.search_memories = AsyncMock(return_value=[(ltm_entry, 0.8)])

        results = await service.search_memories("查询")
        assert len(results) == 1  # 去重后只剩一条

    @pytest.mark.asyncio
    async def test_search_sorted_by_score(self):
        """结果按分数降序排列"""
        service, mock_store, mock_ltm = create_service_with_mocks()

        entries = [
            (make_mock_ltm_entry(memory_id=f"ltm-{i}", content=f"内容{i}"), score)
            for i, score in enumerate([0.3, 0.9, 0.5])
        ]
        mock_ltm.search_memories = AsyncMock(return_value=entries)
        mock_store.search_memories = AsyncMock(return_value=[])

        results = await service.search_memories("查询")
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_search_limit_applied(self):
        """limit 参数限制返回数量"""
        service, mock_store, mock_ltm = create_service_with_mocks()

        entries = [
            (make_mock_ltm_entry(memory_id=f"ltm-{i}", content=f"内容{i}"), 0.5)
            for i in range(20)
        ]
        mock_ltm.search_memories = AsyncMock(return_value=entries)
        mock_store.search_memories = AsyncMock(return_value=[])

        results = await service.search_memories("查询", limit=5)
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_search_empty_results(self):
        """两个后端都无结果时返回空列表"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        mock_store.search_memories = AsyncMock(return_value=[])
        mock_ltm.search_memories = AsyncMock(return_value=[])

        results = await service.search_memories("不存在的查询")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_ltm_failure_graceful(self):
        """LongTermMemory 检索失败时降级返回 PG 结果"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        mock_ltm.search_memories = AsyncMock(side_effect=Exception("LTM不可用"))
        mock_store.search_memories = AsyncMock(return_value=[
            make_mock_pg_memory(memory_id="pg-1", content="PG结果")
        ])

        results = await service.search_memories("查询")
        assert len(results) == 1
        assert results[0]["source"] == "memory_store"

    @pytest.mark.asyncio
    async def test_search_filters_passed_to_store(self):
        """过滤参数正确传递到 MemoryStore"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        mock_store.search_memories = AsyncMock(return_value=[])
        mock_ltm.search_memories = AsyncMock(return_value=[])

        await service.search_memories(
            "查询",
            user_id=10,
            session_id="sess-1",
            memory_type="decision",
            limit=5,
        )
        call_kwargs = mock_store.search_memories.call_args[1]
        assert call_kwargs["user_id"] == 10
        assert call_kwargs["session_id"] == "sess-1"
        assert call_kwargs["memory_type"] == "decision"
        assert call_kwargs["limit"] == 5


# ==================== 5. get_memory ====================

class TestGetMemory:
    """测试按 ID 获取记忆"""

    @pytest.mark.asyncio
    async def test_get_from_memory_store(self):
        """从 MemoryStore 获取"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        mock_store.get_memory_by_id = AsyncMock(return_value=make_mock_pg_memory(memory_id="pg-1"))

        result = await service.get_memory("pg-1")
        assert result is not None
        assert result["source"] == "memory_store"
        assert result["memory_id"] == "pg-1"

    @pytest.mark.asyncio
    async def test_get_from_ltm(self):
        """PG 未找到时从 LongTermMemory 获取"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        mock_store.get_memory_by_id = AsyncMock(return_value=None)
        mock_ltm.get_memory = MagicMock(return_value=make_mock_ltm_entry(memory_id="ltm-1"))

        result = await service.get_memory("ltm-1")
        assert result is not None
        assert result["source"] == "long_term_memory"

    @pytest.mark.asyncio
    async def test_get_with_source_filter(self):
        """source 过滤：只查指定后端"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        mock_store.get_memory_by_id = AsyncMock(return_value=make_mock_pg_memory())
        mock_ltm.get_memory = MagicMock(return_value=make_mock_ltm_entry())

        # 只查 memory_store
        await service.get_memory("id-1", source="memory_store")
        mock_store.get_memory_by_id.assert_called_once()
        mock_ltm.get_memory.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_not_found(self):
        """两个后端都未找到返回 None"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        mock_store.get_memory_by_id = AsyncMock(return_value=None)
        mock_ltm.get_memory = MagicMock(return_value=None)

        result = await service.get_memory("nonexistent")
        assert result is None


# ==================== 6. update_memory ====================

class TestUpdateMemory:
    """测试更新记忆"""

    @pytest.mark.asyncio
    async def test_update_success(self):
        service, mock_store, _ = create_service_with_mocks()
        mock_store.update_memory = AsyncMock(return_value=True)

        result = await service.update_memory(
            "pg-1",
            content="更新后内容",
            importance_score=0.95,
        )
        assert result["status"] == "success"
        assert result["memory_store"] == "updated"

    @pytest.mark.asyncio
    async def test_update_not_found(self):
        service, mock_store, _ = create_service_with_mocks()
        mock_store.update_memory = AsyncMock(return_value=False)

        result = await service.update_memory("nonexistent", content="新内容")
        assert result["status"] == "success"  # 操作本身成功，只是没找到
        assert any("未找到" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_update_failure(self):
        service, mock_store, _ = create_service_with_mocks()
        mock_store.update_memory = AsyncMock(side_effect=Exception("DB错误"))

        result = await service.update_memory("pg-1", content="新内容")
        assert result["status"] == "failed"


# ==================== 7. delete_memory ====================

class TestDeleteMemory:
    """测试删除/归档记忆"""

    @pytest.mark.asyncio
    async def test_delete_both_success(self):
        service, mock_store, mock_ltm = create_service_with_mocks()

        result = await service.delete_memory("pg-1")
        assert result["status"] == "success"
        assert result["memory_store"] == "archived"
        assert result["long_term_memory"] == "deleted"

    @pytest.mark.asyncio
    async def test_delete_pg_not_found(self):
        """PG 未找到但 LTM 删除成功"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        mock_store.delete_memory = AsyncMock(return_value=False)

        result = await service.delete_memory("ltm-only-id")
        assert result["status"] == "success"  # LTM 删了
        assert result["long_term_memory"] == "deleted"
        assert any("未找到" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_delete_both_not_found(self):
        """两个后端都未找到 → failed"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        mock_store.delete_memory = AsyncMock(return_value=False)
        mock_ltm.delete_memory = AsyncMock(return_value=False)

        result = await service.delete_memory("nonexistent")
        assert result["status"] == "failed"

    @pytest.mark.asyncio
    async def test_delete_ltm_error_silent(self):
        """LTM 删除出错时静默忽略（ID 可能不在 LTM 中）"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        mock_ltm.delete_memory = AsyncMock(side_effect=Exception("LTM错误"))

        result = await service.delete_memory("pg-1")
        # PG 成功了，LTM 错误被静默
        assert result["memory_store"] == "archived"
        assert "long_term_memory" not in result


# ==================== 8. purge_expired ====================

class TestPurgeExpired:
    """测试清理过期记忆"""

    @pytest.mark.asyncio
    async def test_purge_both(self):
        service, mock_store, mock_ltm = create_service_with_mocks()

        result = await service.purge_expired()
        assert result["memory_store_archived"] == 3
        assert result["ltm_cleaned"] == 2

    @pytest.mark.asyncio
    async def test_purge_pg_failure(self):
        """PG 清理失败不影响 LTM"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        mock_store.expire_memories = AsyncMock(side_effect=Exception("PG错误"))

        result = await service.purge_expired()
        assert result["ltm_cleaned"] == 2  # LTM 仍然执行

    @pytest.mark.asyncio
    async def test_purge_ltm_failure(self):
        """LTM 清理失败不影响 PG"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        mock_ltm.purge_expired = AsyncMock(side_effect=Exception("LTM错误"))

        result = await service.purge_expired()
        assert result["memory_store_archived"] == 3  # PG 仍然执行


# ==================== 9. generate_context_prompt ====================

class TestGenerateContextPrompt:
    """测试上下文提示词生成"""

    @pytest.mark.asyncio
    async def test_empty_results_returns_empty(self):
        """无搜索结果时返回空字符串"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        mock_store.search_memories = AsyncMock(return_value=[])
        mock_ltm.search_memories = AsyncMock(return_value=[])

        prompt = await service.generate_context_prompt("不存在的查询")
        assert prompt == ""

    @pytest.mark.asyncio
    async def test_prompt_contains_header(self):
        """有结果时包含标题"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        mock_store.search_memories = AsyncMock(return_value=[
            make_mock_pg_memory(content="有结果")
        ])
        mock_ltm.search_memories = AsyncMock(return_value=[])

        prompt = await service.generate_context_prompt("查询")
        assert "历史会议记忆" in prompt

    @pytest.mark.asyncio
    async def test_long_content_truncated(self):
        """超长内容被截断"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        long_content = "A" * 300
        mock_store.search_memories = AsyncMock(return_value=[
            make_mock_pg_memory(content=long_content)
        ])
        mock_ltm.search_memories = AsyncMock(return_value=[])

        prompt = await service.generate_context_prompt("查询")
        assert "..." in prompt

    @pytest.mark.asyncio
    async def test_search_failure_returns_empty(self):
        """搜索异常时返回空字符串"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        mock_store.search_memories = AsyncMock(side_effect=Exception("DB错误"))
        mock_ltm.search_memories = AsyncMock(side_effect=Exception("LTM错误"))

        prompt = await service.generate_context_prompt("查询")
        assert prompt == ""


# ==================== 10. add_meeting_memory ====================

class TestAddMeetingMemory:
    """测试会议记忆添加（兼容方法）"""

    @pytest.mark.asyncio
    async def test_simple_version(self):
        """简化版参数"""
        service, mock_store, _ = create_service_with_mocks()

        result = await service.add_meeting_memory(
            meeting_id="100",
            title="周会",
            content="讨论了项目进度",
            session_id="sess-1",
        )
        assert result["success"] is True
        assert result["meeting_id"] == "100"
        # 验证写入了一次 meeting_summary
        call_kwargs = mock_store.create_memory.call_args[1]
        assert call_kwargs["memory_type"] == "meeting_summary"
        assert call_kwargs["source_meeting_id"] == 100

    @pytest.mark.asyncio
    async def test_full_version_with_all_fields(self):
        """完整版参数（决策 + 行动项 + 争议）"""
        service, mock_store, _ = create_service_with_mocks()

        result = await service.add_meeting_memory(
            meeting_id="200",
            topic="产品评审",
            date="2026-01-01",
            participants=["张三", "李四"],
            summary="评审通过",
            decisions=["采用方案A"],
            action_items=["完成原型"],
            controversies=["时间紧张"],
        )
        assert result["success"] is True
        # summary(1) + decision(1) + action_item(1) + controversy(1) = 4次写入
        assert mock_store.create_memory.call_count == 4

    @pytest.mark.asyncio
    async def test_full_version_no_decisions(self):
        """完整版但无决策和行动项"""
        service, mock_store, _ = create_service_with_mocks()

        result = await service.add_meeting_memory(
            meeting_id="300",
            topic="简短会议",
            date="2026-01-01",
            participants=[],
            summary="简短讨论",
            decisions=[],
            action_items=[],
            controversies=[],
        )
        assert result["success"] is True
        assert mock_store.create_memory.call_count == 1  # 只有 summary

    @pytest.mark.asyncio
    async def test_key_points_as_action_items(self):
        """key_points 被作为 action_item 写入"""
        service, mock_store, _ = create_service_with_mocks()

        result = await service.add_meeting_memory(
            meeting_id="400",
            title="会议",
            content="内容",
            key_points=["要点1", "要点2"],
        )
        assert result["success"] is True
        # content(1) + key_points(2) = 3次
        assert mock_store.create_memory.call_count == 3

    @pytest.mark.asyncio
    async def test_non_numeric_meeting_id(self):
        """非数字 meeting_id 安全处理"""
        service, mock_store, _ = create_service_with_mocks()

        result = await service.add_meeting_memory(
            meeting_id="meeting-abc",
            title="测试",
            content="内容",
        )
        assert result["success"] is True
        call_kwargs = mock_store.create_memory.call_args[1]
        assert call_kwargs["source_meeting_id"] is None


# ==================== 11. 映射函数 ====================

class TestMappingFunctions:
    """测试 _map_memory_type 和 _map_scope"""

    def test_map_memory_type_known(self):
        service = UnifiedMemoryService()
        from app.services.long_term_memory import MemoryType

        assert service._map_memory_type("decision") == MemoryType.DECISION
        assert service._map_memory_type("action_item") == MemoryType.ACTION_ITEM
        assert service._map_memory_type("knowledge") == MemoryType.KNOWLEDGE
        assert service._map_memory_type("controversy") == MemoryType.CONTROVERSY
        assert service._map_memory_type("meeting_summary") == MemoryType.MEETING_SUMMARY

    def test_map_memory_type_unknown_defaults_knowledge(self):
        service = UnifiedMemoryService()
        from app.services.long_term_memory import MemoryType

        result = service._map_memory_type("unknown_type")
        assert result == MemoryType.KNOWLEDGE

    def test_map_scope_known(self):
        service = UnifiedMemoryService()
        from app.services.long_term_memory import MemoryScope

        assert service._map_scope("team") == MemoryScope.TEAM
        assert service._map_scope("department") == MemoryScope.DEPARTMENT
        assert service._map_scope("organization") == MemoryScope.ORGANIZATION
        assert service._map_scope("project") == MemoryScope.PROJECT

    def test_map_scope_unknown_defaults_team(self):
        service = UnifiedMemoryService()
        from app.services.long_term_memory import MemoryScope

        result = service._map_scope("unknown_scope")
        assert result == MemoryScope.TEAM


# ==================== 12. get_statistics ====================

class TestStatistics:
    """测试统计信息聚合"""

    @pytest.mark.asyncio
    async def test_statistics_aggregation(self):
        service, mock_store, mock_ltm = create_service_with_mocks()

        stats = await service.get_statistics()
        assert "memory_store" in stats
        assert "long_term_memory" in stats
        assert stats["memory_store"]["total_memories"] == 10
        assert stats["memory_store"]["avg_importance"] == 0.7

    @pytest.mark.asyncio
    async def test_statistics_pg_failure(self):
        """PG 统计失败不影响 LTM 统计"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        mock_store.get_memory_stats = AsyncMock(side_effect=Exception("PG错误"))

        stats = await service.get_statistics()
        assert stats["memory_store"] == {}
        assert stats["long_term_memory"] == {"total": 5}

    @pytest.mark.asyncio
    async def test_statistics_ltm_failure(self):
        """LTM 统计失败不影响 PG 统计"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        mock_ltm.get_statistics = MagicMock(side_effect=Exception("LTM错误"))

        stats = await service.get_statistics()
        assert stats["memory_store"]["total_memories"] == 10
        assert stats["long_term_memory"] == {}


# ==================== 13. find_relevant_memories ====================

class TestFindRelevantMemories:
    """测试兼容方法 find_relevant_memories"""

    @pytest.mark.asyncio
    async def test_delegates_to_search(self):
        """find_relevant_memories 委托给 search_memories"""
        service, mock_store, mock_ltm = create_service_with_mocks()
        mock_store.search_memories = AsyncMock(return_value=[])
        mock_ltm.search_memories = AsyncMock(return_value=[])

        results = await service.find_relevant_memories("查询", limit=3)
        assert isinstance(results, list)
        # 验证 limit 被传递（limit 是关键字参数）
        ltm_call_kwargs = mock_ltm.search_memories.call_args[1]
        assert ltm_call_kwargs["limit"] == 3
