"""单元测试 - Agent 行为测试"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.agents.state import (
    AgentState, TaskType, create_initial_state, Plan, TaskItem, 
    TaskContext, TaskStatus, ConfirmationStatus
)
from app.agents.nodes import AgentNodes
from app.agents.human_in_the_loop import HumanInTheLoopService, ConfirmationType


class TestAgentStateManagement:
    """测试Agent状态管理"""
    
    def test_initial_state(self):
        """测试初始状态创建"""
        state = create_initial_state("测试问题", meeting_id=1, document_ids=[1, 2])
        
        assert state["question"] == "测试问题"
        assert state["meeting_id"] == 1
        assert state["document_ids"] == [1, 2]
        assert state["current_phase"] == "plan"
        assert state["task_type"] is None
        assert state["cot_thoughts"] == []
        assert state["agents_involved"] == []
        assert state["human_confirmations"] == []
        assert state["enable_human_in_the_loop"] is False

    def test_initial_state_with_hitl(self):
        """测试启用人机协作的初始状态"""
        state = create_initial_state("测试问题", enable_human_in_the_loop=True)
        
        assert state["enable_human_in_the_loop"] is True
        assert "human_confirmations" in state

    def test_state_update(self):
        """测试状态更新"""
        state = create_initial_state("测试问题")
        state["answer"] = "这是回答"
        state["current_phase"] = "done"
        state["cot_thoughts"].append({
            "agent": "test",
            "phase": "test",
            "thought": "测试思考",
            "action": "测试动作",
            "observation": "测试观察"
        })
        
        assert state["answer"] == "这是回答"
        assert state["current_phase"] == "done"
        assert len(state["cot_thoughts"]) == 1


class TestPlanValidation:
    """测试计划验证"""
    
    def test_valid_plan_structure(self):
        """测试有效计划结构"""
        plan: Plan = {
            "analysis": "分析内容",
            "tasks": [
                {
                    "task_id": "task1",
                    "task_type": "qa",
                    "description": "回答问题",
                    "dependencies": [],
                    "status": TaskStatus.PENDING,
                    "output": None,
                    "error": None
                }
            ],
            "execution_order": ["task1"],
            "parallel_groups": []
        }
        
        assert "analysis" in plan
        assert "tasks" in plan
        assert len(plan["tasks"]) == 1
        assert plan["tasks"][0]["task_id"] == "task1"
        assert plan["tasks"][0]["task_type"] == "qa"

    def test_plan_with_multiple_tasks(self):
        """测试多任务计划"""
        plan: Plan = {
            "analysis": "复杂分析",
            "tasks": [
                {"task_id": "t1", "task_type": "retrieve", "description": "检索", "dependencies": [], "status": TaskStatus.PENDING, "output": None, "error": None},
                {"task_id": "t2", "task_type": "qa", "description": "问答", "dependencies": ["t1"], "status": TaskStatus.PENDING, "output": None, "error": None}
            ],
            "execution_order": ["t1", "t2"],
            "parallel_groups": []
        }
        
        assert len(plan["tasks"]) == 2
        assert plan["tasks"][1]["dependencies"] == ["t1"]

    def test_task_context_management(self):
        """测试任务上下文管理"""
        task_contexts: Dict[str, TaskContext] = {
            "task1": {
                "input": "输入数据",
                "output": "输出数据",
                "status": TaskStatus.COMPLETED,
                "error": None,
                "metadata": {"key": "value"}
            }
        }
        
        assert "task1" in task_contexts
        assert task_contexts["task1"]["status"] == TaskStatus.COMPLETED
        assert task_contexts["task1"]["output"] == "输出数据"


class MockLLMService:
    """Mock LLM服务"""
    def __init__(self):
        self.chat = AsyncMock(return_value="测试回答")
        self.complete = AsyncMock(return_value="测试完成")


class TestAgentNodesBasic:
    """测试Agent节点基础功能"""
    
    @pytest.mark.asyncio
    async def test_plan_agent_initial(self):
        """测试计划Agent初始状态"""
        llm_service = MockLLMService()
        nodes = AgentNodes(llm_service)
        
        assert nodes.llm_service is not None
        assert nodes.hitl_service is not None
        assert nodes.max_retries == 2

    @pytest.mark.asyncio
    async def test_format_context_empty(self):
        """测试格式化空上下文"""
        llm_service = MockLLMService()
        nodes = AgentNodes(llm_service)
        
        state = create_initial_state("测试问题")
        formatted = nodes._format_context(state)
        
        assert formatted == ""

    @pytest.mark.asyncio
    async def test_format_context_with_data(self):
        """测试格式化带来源信息的上下文"""
        llm_service = MockLLMService()
        nodes = AgentNodes(llm_service)
        
        state = create_initial_state("测试问题")
        state["context"] = [
            {"document_id": 1, "chunk_index": 0, "content": "内容1"},
            {"document_id": 2, "chunk_index": 1, "content": "内容2", "speaker_name": "张三"}
        ]
        
        formatted = nodes._format_context(state)
        
        assert "[文档1:0]" in formatted
        assert "[文档2:1]" in formatted
        assert "[张三]" in formatted
        assert "内容1" in formatted
        assert "内容2" in formatted

    def test_log_plan(self, capsys):
        """测试计划日志记录"""
        llm_service = MockLLMService()
        nodes = AgentNodes(llm_service)
        
        plan: Plan = {
            "analysis": "测试分析",
            "tasks": [
                {"task_id": "t1", "task_type": "qa", "description": "测试任务", "dependencies": [], "status": TaskStatus.PENDING, "output": None, "error": None}
            ],
            "execution_order": ["t1"],
            "parallel_groups": []
        }
        
        state = create_initial_state("测试问题")
        state["plan"] = plan
        
        nodes._log_plan(state)
        # 检查日志是否正常记录（通过capsys捕获）


class TestHumanInTheLoop:
    """测试人机协作服务"""
    
    def test_hitl_service_initialization(self):
        """测试人机协作服务初始化"""
        hitl = HumanInTheLoopService()
        
        assert hitl.default_timeout == 300
        assert hitl.pending_requests == {}
        assert hitl.request_history == []

    def test_generate_request_id(self):
        """测试请求ID生成"""
        hitl = HumanInTheLoopService()
        
        id1 = hitl._generate_request_id()
        id2 = hitl._generate_request_id()
        
        assert id1 != id2
        assert id1.startswith("confirm_")
        assert id2.startswith("confirm_")

    def test_respond_to_request(self):
        """测试响应用户请求"""
        hitl = HumanInTheLoopService()
        
        # 创建一个pending请求（通过内部方式）
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        future = loop.create_future()
        hitl.pending_requests["test_req"] = future
        
        success = hitl.respond_to_request("test_req", "approved")
        
        assert success is True
        
        # 清理事件循环
        loop.close()

    def test_respond_to_nonexistent_request(self):
        """测试响应不存在的请求"""
        hitl = HumanInTheLoopService()
        
        success = hitl.respond_to_request("nonexistent", "approved")
        
        assert success is False

    def test_get_pending_requests(self):
        """测试获取待处理请求"""
        hitl = HumanInTheLoopService()
        
        requests = hitl.get_pending_requests()
        
        assert isinstance(requests, list)

    def test_get_request_history(self):
        """测试获取请求历史"""
        hitl = HumanInTheLoopService()
        
        history = hitl.get_request_history(limit=10)
        
        assert isinstance(history, list)


class TestConfirmationTypes:
    """测试确认类型枚举"""
    
    def test_all_confirmation_types(self):
        """测试所有确认类型"""
        types = [t.value for t in ConfirmationType]
        
        assert "plan_approval" in types
        assert "task_execution" in types
        assert "tool_call" in types
        assert "result_review" in types
        assert "critical_action" in types


class TestTaskStatus:
    """测试任务状态枚举"""
    
    def test_all_task_statuses(self):
        """测试所有任务状态"""
        statuses = [s.value for s in TaskStatus]
        
        assert "pending" in statuses
        assert "ready" in statuses
        assert "in_progress" in statuses
        assert "completed" in statuses
        assert "failed" in statuses
        assert "skipped" in statuses


class TestTaskType:
    """测试任务类型枚举"""
    
    def test_all_task_types(self):
        """测试所有任务类型"""
        types = [t.value for t in TaskType]
        
        assert "qa" in types
        assert "minutes" in types
        assert "todo" in types
        assert "controversy" in types
        assert "multi" in types

    def test_task_type_equality(self):
        """测试任务类型相等性"""
        assert TaskType.QA == TaskType("qa")
        assert TaskType.MINUTES == TaskType("minutes")


class TestConfirmationStatus:
    """测试确认状态枚举"""
    
    def test_all_confirmation_statuses(self):
        """测试所有确认状态"""
        statuses = [s.value for s in ConfirmationStatus]
        
        assert "pending" in statuses
        assert "approved" in statuses
        assert "rejected" in statuses
        assert "timed_out" in statuses
        assert "skipped" in statuses
