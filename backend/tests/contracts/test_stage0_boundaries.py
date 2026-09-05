"""阶段 0 的主链路与生产暴露边界契约。"""

from __future__ import annotations

import ast
from contextlib import nullcontext
import importlib.util
import sys
import types
import unittest
from enum import Enum
from pathlib import Path
from unittest.mock import MagicMock, patch


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _module(name: str, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _package(name: str):
    module = _module(name)
    module.__path__ = []
    return module


def _load_file(relative_path: str, module_name: str, stubs=None):
    source_path = BACKEND_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, source_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载生产源码: {source_path}")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs or {}):
        spec.loader.exec_module(module)
    return module


class TestRouterPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = _load_file(
            "app/api/v1/router_policy.py", "router_policy_contract_target"
        )

    def test_production_exposes_only_formal_business_routers(self):
        names = {
            name for name, _, _ in self.policy.enabled_router_specs("production")
        }
        self.assertEqual(names, {
            "users", "meetings", "documents", "todos", "rag", "agents",
            "feedback", "tasks",
        })
        self.assertTrue(names.isdisjoint(self.policy.REMOVED_ROUTERS))

    def test_internal_routers_are_development_or_test_only(self):
        production = {
            name for name, _, _ in self.policy.enabled_router_specs("production")
        }
        development = {
            name for name, _, _ in self.policy.enabled_router_specs("development")
        }
        internal = {name for name, _, _ in self.policy.INTERNAL_ROUTERS}
        self.assertTrue(internal.isdisjoint(production))
        self.assertTrue(internal.issubset(development))

    def test_removed_routers_cannot_be_enabled_by_configuration(self):
        exposed = {
            name for name, _, _ in self.policy.enabled_router_specs("development")
        }
        self.assertTrue(exposed.isdisjoint(self.policy.REMOVED_ROUTERS))


class TestAgentGraphContract(unittest.TestCase):
    def _load_graph_module(self):
        class WorkflowType(str, Enum):
            MINUTES = "minutes"
            TODO = "todo"
            CONTROVERSY = "controversy"
            COMPLEX = "complex"

        class ReasoningMode(str, Enum):
            DEFAULT = "default"
            REACT = "react"
            COT = "cot"
            PLAN = "plan"

        class ComplexityLevel(str, Enum):
            SIMPLE = "simple"
            RETRIEVAL = "retrieval"
            COT = "cot"
            AGENT = "agent"

        class FakeNodes:
            def __init__(self, *args, **kwargs):
                pass

            def __getattr__(self, name):
                return lambda state=None: state

        class FakeCompiledGraph:
            def __init__(self, builder):
                self.builder = builder

        class FakeCommand:
            def __init__(self, update=None, goto=None):
                self.update = update
                self.goto = goto

        class FakeStateGraph:
            last_instance = None

            def __init__(self, state_type):
                self.state_type = state_type
                self.nodes = {}
                self.compile_count = 0
                FakeStateGraph.last_instance = self

            def add_node(self, name, callback):
                self.nodes[name] = callback

            def add_edge(self, *args, **kwargs):
                pass

            def add_conditional_edges(self, *args, **kwargs):
                pass

            def compile(self, **kwargs):
                self.compile_count += 1
                return FakeCompiledGraph(self)

        stubs = {
            "langgraph": _package("langgraph"),
            "langgraph.graph": _module(
                "langgraph.graph",
                StateGraph=FakeStateGraph,
                START="__start__",
                END="__end__",
            ),
            "langgraph.types": _module("langgraph.types", Command=FakeCommand),
            "app": _package("app"),
            "app.agents": _package("app.agents"),
            "app.services": _package("app.services"),
            "app.core": _package("app.core"),
            "app.agents.state": _module(
                "app.agents.state",
                AgentState=dict,
                WorkflowType=WorkflowType,
                ReasoningMode=ReasoningMode,
                ComplexityLevel=ComplexityLevel,
            ),
            "app.agents.nodes": _module(
                "app.agents.nodes", AgentNodes=FakeNodes
            ),
            "app.agents.tools": _module(
                "app.agents.tools", ToolManager=object
            ),
            "app.services.llm_service": _module(
                "app.services.llm_service", LLMService=object
            ),
            # graph.py 在每个节点外包裹 Token 预算上下文；这里用空上下文，
            # 只测试图的节点和编译边界，不把可选运行依赖带进契约测试。
            "app.services.token_budget_ledger": _module(
                "app.services.token_budget_ledger",
                token_budget_node_scope=lambda _name: nullcontext(),
            ),
            "app.core.logger": _module(
                "app.core.logger", app_logger=MagicMock()
            ),
        }
        module = _load_file(
            "app/agents/graph.py", "agent_graph_contract_target", stubs
        )
        return module, FakeStateGraph

    def test_default_graph_is_simple_rag_plus_tool_agent_and_compiles_once(self):
        graph_module, fake_graph_type = self._load_graph_module()
        compiled = graph_module.create_agent_graph(object(), object())
        builder = compiled.builder

        self.assertEqual(builder.compile_count, 1)
        self.assertTrue({
            "input_node", "route_node", "retrieve_node", "simple_qa_node",
            "plan_node", "tool_risk_node", "execute_node", "validate_node",
        }.issubset(builder.nodes))
        self.assertTrue({
            "react_node", "cot_node", "reflection_node",
        }.isdisjoint(builder.nodes))
        self.assertIs(builder, fake_graph_type.last_instance)

    def test_agent_service_does_not_compile_an_already_compiled_graph(self):
        source = (BACKEND_ROOT / "app/agents/agent_service.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("self.graph.compile(", source)
        self.assertIn("self.app = self.graph", source)


class TestRemovedCapabilities(unittest.TestCase):
    def test_removed_capabilities_are_not_kept_as_dead_flags(self):
        source_path = BACKEND_ROOT / "app/core/config.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        settings_class = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "Settings"
        )
        defaults = {
            node.target.id: ast.literal_eval(node.value)
            for node in settings_class.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
            and isinstance(node.value, ast.Constant)
        }
        removed_names = {
            "ENABLE_QUERY_REWRITE",
            "ENABLE_HYDE",
            "ENABLE_MULTI_QUERY",
            "ENABLE_STEP_BACK",
            "ENABLE_MULTIMODAL",
            "ENABLE_REFLECTION_MEMORY",
            "ENABLE_KNOWLEDGE_GRAPH",
            "ENABLE_NEO4J_PERSISTENCE",
            "ENABLE_MCP_SERVER",
            "ENABLE_SPARSE_RETRIEVAL",
        }
        self.assertTrue(removed_names.isdisjoint(defaults))
        self.assertNotIn("ENABLE_AGENT_WORKER", defaults)


if __name__ == "__main__":
    unittest.main()
