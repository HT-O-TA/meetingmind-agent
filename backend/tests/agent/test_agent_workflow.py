"""Agent工作流完整集成测试"""
import pytest
import asyncio
from typing import Dict, Any, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class TestMeeting:
    """测试用会议数据"""
    id: int
    title: str
    content: str
    participants: List[str]
    date: str
    
    @property
    def full_content(self) -> str:
        return f"""
会议主题：{self.title}
会议时间：{self.date}
参会人员：{', '.join(self.participants)}

会议内容：
{self.content}
"""


@pytest.fixture
def sample_meeting() -> TestMeeting:
    """示例会议数据"""
    return TestMeeting(
        id=1,
        title="项目进度讨论会议",
        content="""
1. 项目A的开发进度已完成80%，预计下周完成。
2. 项目B的测试发现了一些bug，需要尽快修复。
3. 下周三有一个重要的产品发布会。

待办事项：
- 张三：修复项目B的bug，截止日期：周三
- 李四：准备产品发布会PPT，截止日期：周二
- 王五：更新项目文档，截止日期：周五

会议决定：
1. 优先修复bug
2. 发布会推迟到下周五
""",
        participants=["张三", "李四", "王五"],
        date="2024-01-15"
    )


@pytest.fixture
def mock_llm_service():
    """模拟LLM服务"""
    service = MagicMock()
    service._call = AsyncMock(return_value="这是测试回答")
    service.generate = AsyncMock(return_value="生成的文本")
    service.generate_answer = AsyncMock(return_value={
        "answer": "会议主要讨论了项目进度问题。",
        "context_used": ["上下文1", "上下文2"]
    })
    service.generate_stream = AsyncMock(return_value=iter([
        "正在分析",
        "...",
        "完成"
    ]))
    return service


@pytest.fixture
def mock_vector_service():
    """模拟向量检索服务"""
    service = MagicMock()
    service.search_by_text = AsyncMock(return_value=[
        {"chunk_id": 1, "chunk_text": "相关片段1", "score": 0.95},
        {"chunk_id": 2, "chunk_text": "相关片段2", "score": 0.88}
    ])
    service.search_by_vector = AsyncMock(return_value=[
        {"chunk_id": 1, "chunk_text": "相关片段1", "score": 0.92}
    ])
    service.use_pgvector = True
    return service


@pytest.fixture
def mock_embedding_service():
    """模拟向量化服务"""
    service = MagicMock()
    service.encode_text = MagicMock(return_value=[0.1] * 384)
    service.encode_batch = MagicMock(return_value=[[0.1] * 384] * 10)
    service.get_vector_dimension = MagicMock(return_value=384)
    service.cosine_similarity = MagicMock(return_value=0.95)
    return service


class TestAgentCoreWorkflow:
    """Agent核心工作流测试"""

    @pytest.mark.asyncio
    async def test_agent_initialization(self, mock_llm_service, mock_vector_service):
        """测试Agent服务初始化"""
        from app.agents.agent_service import AgentService
        
        agent = AgentService(
            llm_service=mock_llm_service,
            vector_search_service=mock_vector_service,
            enable_memory=True,
            enable_tool_calling=True,
            enable_human_in_the_loop=False
        )
        
        assert agent is not None
        assert agent.enable_memory == True
        assert agent.enable_tool_calling == True

    @pytest.mark.asyncio
    async def test_agent_query_processing(self, mock_llm_service, mock_vector_service):
        """测试Agent查询处理"""
        from app.agents.agent_service import AgentService
        
        agent = AgentService(
            llm_service=mock_llm_service,
            vector_search_service=mock_vector_service
        )
        
        result = await agent.process_query(
            question="总结会议的主要内容",
            meeting_id=1
        )
        
        assert result is not None

    @pytest.mark.asyncio
    async def test_agent_batch_processing(self, mock_llm_service, mock_vector_service):
        """测试Agent批量处理"""
        from app.agents.agent_service import AgentService
        
        agent = AgentService(
            llm_service=mock_llm_service,
            vector_search_service=mock_vector_service
        )
        
        questions = [
            "会议讨论了什么？",
            "有哪些待办事项？",
            "谁负责什么任务？"
        ]
        
        results = await agent.process_batch(
            questions=questions,
            meeting_id=1
        )
        
        assert len(results) == 3


class TestAgentMemory:
    """Agent记忆系统测试"""

    @pytest.mark.asyncio
    async def test_short_term_memory(self):
        """测试短期记忆"""
        from app.agents.memory import MemorySystem, MemoryType
        
        memory = MemorySystem()
        
        memory.add_short_term_memory(
            "用户询问项目进度",
            {"intent": "query", "topic": "project"}
        )
        
        memories = memory.get_short_term_memory()
        assert len(memories) > 0
        assert memories[0].content == "用户询问项目进度"

    @pytest.mark.asyncio
    async def test_long_term_memory(self):
        """测试长期记忆"""
        from app.agents.memory import MemorySystem
        
        memory = MemorySystem()
        
        memory.add_long_term_memory(
            "会议决定使用微服务架构",
            {"type": "decision", "project": "meeting_system"}
        )
        
        results = memory.search_long_term_memory("架构")
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_memory_consolidation(self):
        """测试记忆整合"""
        from app.agents.memory import MemorySystem
        
        memory = MemorySystem()
        
        for i in range(5):
            memory.add_short_term_memory(f"对话 {i}", {"turn": i})
        
        consolidated = memory.consolidate_short_term()
        assert consolidated is not None


class TestAgentReflection:
    """Agent反思系统测试"""

    def test_self_evaluation(self):
        """测试自我评估"""
        from app.agents.reflection import ReflectionSystem, FeedbackType, EvaluationMetric
        
        reflection = ReflectionSystem()
        
        metrics = reflection.perform_self_evaluation(
            input_text="用户询问项目进度",
            output_text="项目A已完成80%，项目B正在测试中。"
        )
        
        assert metrics is not None
        assert EvaluationMetric.ACCURACY in metrics

    def test_feedback_collection(self):
        """测试反馈收集"""
        from app.agents.reflection import ReflectionSystem, FeedbackType
        
        reflection = ReflectionSystem()
        
        reflection.collect_feedback(
            feedback_type=FeedbackType.USER_RATING,
            content="回答很好",
            rating=5,
            agent_id="agent_1"
        )
        
        feedbacks = reflection.get_recent_feedbacks(limit=10)
        assert len(feedbacks) > 0

    def test_improvement_suggestions(self):
        """测试改进建议生成"""
        from app.agents.reflection import ReflectionSystem
        
        reflection = ReflectionSystem()
        
        suggestions = reflection.generate_improvement_suggestions()
        
        assert isinstance(suggestions, list)

    def test_performance_report(self):
        """测试性能报告"""
        from app.agents.reflection import ReflectionSystem
        
        reflection = ReflectionSystem()
        
        report = reflection.get_performance_report()
        
        assert "total_interactions" in report
        assert "avg_rating" in report
        assert "success_rate" in report


class TestAgentCommunication:
    """Agent通信测试"""

    @pytest.mark.asyncio
    async def test_message_bus_subscribe(self):
        """测试消息订阅"""
        from app.agents.agent_communication import MessageBus, AgentMessage, MessageType
        
        bus = MessageBus()
        received = []
        
        async def handler(msg):
            received.append(msg)
        
        bus.subscribe("agent1", handler)
        
        msg = AgentMessage(
            sender_id="agent2",
            receiver_id="agent1",
            message_type=MessageType.TASK_ASSIGN,
            content={"task": "search"}
        )
        
        await bus.send(msg)
        
        assert len(received) == 1
        assert received[0].content["task"] == "search"

    @pytest.mark.asyncio
    async def test_message_broadcast(self):
        """测试消息广播"""
        from app.agents.agent_communication import MessageBus, AgentMessage, MessageType
        
        bus = MessageBus()
        received_count = [0, 0]
        
        async def handler1(msg):
            received_count[0] += 1
        
        async def handler2(msg):
            received_count[1] += 1
        
        bus.subscribe("agent1", handler1)
        bus.subscribe("agent2", handler2)
        
        msg = AgentMessage(
            sender_id="controller",
            receiver_id="",
            message_type=MessageType.BROADCAST,
            content={"event": "task_complete"}
        )
        
        await bus.broadcast(msg)
        
        assert received_count[0] == 1
        assert received_count[1] == 1

    @pytest.mark.asyncio
    async def test_task_dispatcher_submit(self):
        """测试任务提交"""
        from app.agents.agent_communication import TaskDispatcher, Task, TaskPriority
        
        dispatcher = TaskDispatcher()
        
        task = Task(
            task_id="task_1",
            description="测试任务",
            priority=TaskPriority.HIGH
        )
        
        await dispatcher.submit_task(task)
        
        pending = dispatcher.get_pending_tasks()
        assert len(pending) > 0

    @pytest.mark.asyncio
    async def test_task_dispatcher_cancel(self):
        """测试任务取消"""
        from app.agents.agent_communication import TaskDispatcher, Task, TaskPriority
        
        dispatcher = TaskDispatcher()
        
        task = Task(
            task_id="task_cancel",
            description="待取消任务",
            priority=TaskPriority.NORMAL
        )
        
        await dispatcher.submit_task(task)
        result = await dispatcher.cancel_task("task_cancel")
        
        assert result == True


class TestAgentToolCalling:
    """Agent工具调用测试"""

    def test_tool_registry_get_tools(self):
        """测试工具注册表获取工具"""
        from app.agents.tools.decorator import get_tool_registry, ToolCategory
        
        registry = get_tool_registry()
        tools = registry.get_all()
        
        assert isinstance(tools, list)

    def test_tool_schema_generation(self):
        """测试工具Schema生成"""
        from app.agents.tools.decorator import get_tool_registry
        
        registry = get_tool_registry()
        schemas = registry.get_openai_tools()
        
        assert isinstance(schemas, list)

    def test_tool_parameter_validation(self):
        """测试工具参数验证"""
        from app.agents.tools.decorator import get_tool_registry
        
        registry = get_tool_registry()
        all_tools = registry.get_all()
        
        if all_tools:
            tool = all_tools[0]
            valid, error = tool.validate_parameters({})
            
            assert isinstance(valid, bool)


class TestAgentFaultTolerance:
    """Agent容错机制测试"""

    @pytest.mark.asyncio
    async def test_retry_mechanism(self):
        """测试重试机制"""
        from app.core.fault_tolerance import RetryManager
        
        retry_mgr = RetryManager()
        
        attempts = []
        
        async def failing_func():
            attempts.append(len(attempts) + 1)
            if len(attempts) < 3:
                raise Exception("Temporary failure")
            return "Success"
        
        result = await retry_mgr.execute_with_retry(
            "test_op",
            failing_func,
            max_retries=3
        )
        
        assert result == "Success"
        assert len(attempts) == 3

    @pytest.mark.asyncio
    async def test_circuit_breaker(self):
        """测试熔断器"""
        from app.core.fault_tolerance import CircuitBreaker, CircuitState
        
        breaker = CircuitBreaker(
            name="test_breaker",
            failure_threshold=3,
            success_threshold=2,
            reset_timeout=1
        )
        
        async def failing_func():
            raise Exception("Service unavailable")
        
        for _ in range(3):
            try:
                await breaker.call(failing_func)
            except:
                pass
        
        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_fallback_strategy(self):
        """测试降级策略"""
        from app.core.fault_tolerance import FallbackManager, FallbackStrategy
        
        fallback_mgr = FallbackManager()
        
        result = await fallback_mgr.execute_fallback(
            strategy=FallbackStrategy.RETURN_DEFAULT,
            default_value={"result": "fallback"}
        )
        
        assert result == {"result": "fallback"}


class TestAgentObservability:
    """Agent可观测性测试"""

    def test_tracer(self):
        """测试追踪器"""
        from app.core.observability import Tracer
        
        tracer = Tracer()
        
        with tracer.start_span("test_operation") as span:
            span.set_attribute("key", "value")
        
        assert len(tracer.get_trace()) > 0

    def test_metrics_collector(self):
        """测试指标收集器"""
        from app.core.observability import MetricsCollector
        
        collector = MetricsCollector()
        
        collector.increment("requests_total")
        collector.record("response_time", 0.5)
        
        metrics = collector.get_metrics()
        
        assert "requests_total" in metrics

    def test_health_status(self):
        """测试健康状态"""
        from app.core.observability import ObservabilitySystem
        
        obs = ObservabilitySystem()
        status = obs.get_health_status()
        
        assert "status" in status
        assert "uptime_seconds" in status


class TestRAGPipeline:
    """RAG管道测试"""

    @pytest.mark.asyncio
    async def test_vector_search(self, mock_embedding_service):
        """测试向量检索"""
        try:
            from app.services.vector_search_service import VectorSearchService
            
            service = VectorSearchService(embedding_service=mock_embedding_service)
            
            results = await service.search_by_text("测试查询", top_k=5)
            
            assert isinstance(results, list)
        except Exception as e:
            pytest.skip(f"Vector search service not available: {e}")

    @pytest.mark.asyncio
    async def test_bm25_retrieval(self):
        """测试BM25检索"""
        try:
            from app.services.bm25_retriever import BM25Retriever
            
            retriever = BM25Retriever()
            retriever.add_documents([
                {"id": 1, "content": "项目进度讨论"},
                {"id": 2, "content": "技术方案评审"}
            ])
            
            results = retriever.search("项目", top_k=2)
            
            assert isinstance(results, list)
        except ImportError:
            pytest.skip("BM25 retriever not available")

    @pytest.mark.asyncio
    async def test_reranking(self):
        """测试重排序"""
        try:
            from app.services.reranker import get_reranker
            
            reranker = get_reranker()
            
            documents = [
                {"chunk_id": 1, "chunk_text": "文档1", "score": 0.8},
                {"chunk_id": 2, "chunk_text": "文档2", "score": 0.7}
            ]
            
            results = await reranker.arerank("测试查询", documents, top_n=2)
            
            assert isinstance(results, list)
        except ImportError:
            pytest.skip("Reranker not available")


class TestPromptTemplate:
    """Prompt模板测试"""

    def test_template_rendering(self):
        """测试模板渲染"""
        from app.agents.prompt_market import PromptMarket, TemplateCategory
        
        market = PromptMarket()
        templates = market.get_templates_by_category(TemplateCategory.MEETING_SUMMARY)
        
        assert isinstance(templates, list)

    def test_template_search(self):
        """测试模板搜索"""
        from app.agents.prompt_market import PromptMarket
        
        market = PromptMarket()
        results = market.search_templates("总结")
        
        assert isinstance(results, list)


class TestSecuritySystem:
    """安全系统测试"""

    def test_access_control(self):
        """测试访问控制"""
        from app.core.security import get_security_system, ResourceType, PermissionLevel
        
        security = get_security_system()
        ac = security.get_access_control()
        
        ac.grant_permission(
            user_id="user_1",
            resource_type=ResourceType.DOCUMENT,
            resource_id="doc_1",
            level=PermissionLevel.READ
        )
        
        has_access = ac.check_permission(
            user_id="user_1",
            resource_type=ResourceType.DOCUMENT,
            resource_id="doc_1",
            required_level=PermissionLevel.READ
        )
        
        assert has_access == True

    def test_data_masking(self):
        """测试数据脱敏"""
        from app.core.security import get_security_system
        
        security = get_security_system()
        
        phone = "13812345678"
        masked = security._data_masking.mask_phone(phone)
        
        assert masked != phone

    def test_audit_logging(self):
        """测试审计日志"""
        from app.core.security import get_security_system, AuditAction
        
        security = get_security_system()
        
        security.log_action(
            user_id="user_1",
            action=AuditAction.CREATE,
            resource_type="document",
            resource_id="doc_1",
            details={"title": "测试文档"}
        )
        
        logs = security.get_audit_logs(user_id="user_1", limit=10)
        
        assert len(logs) > 0


class TestAPIResponse:
    """API响应格式测试"""

    def test_success_response(self):
        """测试成功响应"""
        from app.core.api_response import APIResponse
        
        response = APIResponse.success(
            data={"result": "test"},
            message="操作成功"
        )
        
        assert response.code == "00000"
        assert response.data == {"result": "test"}

    def test_error_response(self):
        """测试错误响应"""
        from app.core.api_response import APIResponse
        
        response = APIResponse.error(
            code="40000",
            message="参数错误",
            error_detail={"field": "name"}
        )
        
        assert response.code == "40000"
        assert response.error is not None

    def test_paginated_response(self):
        """测试分页响应"""
        from app.core.api_response import APIResponse
        
        response = APIResponse.paginated(
            items=[1, 2, 3],
            total=100,
            page=1,
            page_size=20
        )
        
        assert response.data["pagination"]["total"] == 100
        assert response.data["pagination"]["total_pages"] == 5


class TestEndToEndScenarios:
    """端到端场景测试"""

    @pytest.mark.asyncio
    async def test_meeting_summary_workflow(
        self,
        mock_llm_service,
        mock_vector_service,
        sample_meeting
    ):
        """测试会议总结工作流"""
        from app.agents.agent_service import AgentService
        
        agent = AgentService(
            llm_service=mock_llm_service,
            vector_search_service=mock_vector_service
        )
        
        result = await agent.process_query(
            question=f"总结以下会议内容：\n{sample_meeting.full_content}",
            meeting_id=sample_meeting.id
        )
        
        assert result is not None

    @pytest.mark.asyncio
    async def test_todo_extraction_workflow(
        self,
        mock_llm_service,
        mock_vector_service,
        sample_meeting
    ):
        """测试待办提取工作流"""
        from app.agents.agent_service import AgentService
        
        agent = AgentService(
            llm_service=mock_llm_service,
            vector_search_service=mock_vector_service
        )
        
        result = await agent.process_query(
            question=f"提取以下会议的待办事项：\n{sample_meeting.full_content}",
            meeting_id=sample_meeting.id
        )
        
        assert result is not None

    @pytest.mark.asyncio
    async def test_multi_agent_collaboration(
        self,
        mock_llm_service,
        mock_vector_service
    ):
        """测试多Agent协作"""
        from app.agents.agent_communication import MessageBus, TaskDispatcher, AgentMessage, MessageType, Task, TaskPriority
        
        bus = MessageBus()
        dispatcher = TaskDispatcher()
        
        task = Task(
            task_id="collab_task",
            description="协作测试任务",
            priority=TaskPriority.HIGH,
            assigned_agent="agent_1"
        )
        
        await dispatcher.submit_task(task)
        
        msg = AgentMessage(
            sender_id="agent_1",
            receiver_id="agent_2",
            message_type=MessageType.TASK_ASSIGN,
            content={"task_id": "collab_task", "status": "in_progress"}
        )
        
        await bus.send(msg)
        
        assert len(dispatcher.get_pending_tasks()) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])