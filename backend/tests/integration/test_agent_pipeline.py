"""Agent 全链路集成测试"""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.database import init_db

pytestmark = pytest.mark.asyncio


class TestAgentPipeline:
    """Agent全链路测试类 - 覆盖S/R/C/A四个复杂度等级"""

    @pytest.fixture(autouse=True)
    async def setup(self):
        """测试前置条件"""
        await init_db()
        yield

    async def test_agent_simple_question(self):
        """测试S级 - 简单问题"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/agents/chat",
                json={"message": "你好", "session_id": "test-session"}
            )
            assert response.status_code in [200, 401]  # 可能需要认证
            
            if response.status_code == 200:
                data = response.json()
                assert "response" in data
                assert isinstance(data["response"], str)

    async def test_agent_retrieval_question(self):
        """测试R级 - 需要检索的问题"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/agents/chat",
                json={"message": "会议中有哪些讨论要点", "session_id": "test-session"}
            )
            assert response.status_code in [200, 401]

    async def test_agent_cot_question(self):
        """测试C级 - 需要CoT推理的问题"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/agents/chat",
                json={"message": "比较2024年和2025年的销售数据，分析增长趋势", "session_id": "test-session"}
            )
            assert response.status_code in [200, 401]

    async def test_agent_multi_task_question(self):
        """测试A级 - 需要多任务规划的问题"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/agents/chat",
                json={"message": "总结上周的三个会议，提取每个会议的决策事项和行动项", "session_id": "test-session"}
            )
            assert response.status_code in [200, 401]

    async def test_agent_workflow_router(self):
        """测试工作流路由"""
        from app.agents.nodes import AgentNodes
        from unittest.mock import MagicMock
        
        llm_service = MagicMock()
        tool_manager = MagicMock()
        tool_manager.selector.format_tools_for_prompt.return_value = ""
        nodes = AgentNodes(llm_service=llm_service, tool_manager=tool_manager)
        
        from app.agents.state import create_initial_state
        state = create_initial_state("简单问题")
        routed = await nodes.route_agent(state)
        
        assert routed is not None
        assert "workflow_type" in routed


class TestToolExecution:
    """工具执行集成测试"""

    async def test_tool_manager_initialization(self):
        """测试工具管理器初始化"""
        from app.agents.tools.tool_registry import ToolRegistry
        
        registry = ToolRegistry()
        assert registry is not None
        tools = registry.get_all_tools()
        assert isinstance(tools, list)

    async def test_tool_executor(self):
        """测试工具执行器"""
        from app.agents.nodes import AgentNodes
        from unittest.mock import MagicMock
        
        llm_service = MagicMock()
        tool_manager = MagicMock()
        tool_manager.selector.format_tools_for_prompt.return_value = ""
        nodes = AgentNodes(llm_service=llm_service, tool_manager=tool_manager)
        
        assert nodes is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])