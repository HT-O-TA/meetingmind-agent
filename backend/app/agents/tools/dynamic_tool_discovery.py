"""动态工具发现与组合引擎"""
from typing import Dict, List, Any, Optional, Tuple, Callable
from enum import Enum
from datetime import datetime
from dataclasses import dataclass, field
from app.core.logger import app_logger
from app.agents.tools.registry import get_tool_registry
from app.agents.tools.tool_metadata import Tool, ToolMetadata, ToolCategory, ToolCondition, ToolCombinationRule
from app.agents.tools.selector import get_tool_selector
from app.services.llm_service import LLMService


class DiscoveryStrategy(str, Enum):
    """发现策略"""
    KEYWORD_MATCH = "keyword_match"
    SEMANTIC_SIMILARITY = "semantic_similarity"
    CONDITION_EVALUATION = "condition_evaluation"
    HYBRID = "hybrid"


@dataclass
class DiscoveryResult:
    """发现结果"""
    tool_id: str
    name: str
    description: str
    category: str
    score: float
    reason: str
    conditions_matched: int
    total_conditions: int
    compatibility_tags: List[str]
    exclusion_tags: List[str]


@dataclass
class ToolPlan:
    """工具执行计划"""
    plan_id: str
    tools: List[Dict[str, Any]]
    execution_order: str
    dependencies: List[Tuple[str, str]]
    estimated_cost: float
    estimated_time: float


class DynamicToolDiscovery:
    """动态工具发现机制"""
    
    def __init__(self, llm_service: Optional[LLMService] = None):
        self.registry = get_tool_registry()
        self.selector = get_tool_selector()
        self.llm_service = llm_service
        self._discovery_history: List[Dict[str, Any]] = []
        self._usage_patterns: Dict[str, List[str]] = {}
    
    async def discover_tools(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        strategy: DiscoveryStrategy = DiscoveryStrategy.HYBRID,
        max_tools: int = 10,
        min_score: float = 0.3,
    ) -> List[DiscoveryResult]:
        """
        动态发现匹配的工具
        
        Args:
            query: 用户查询
            context: 上下文信息
            strategy: 发现策略
            max_tools: 最大返回工具数
            min_score: 最低匹配分数
            
        Returns:
            发现结果列表
        """
        context = context or {}
        context["query"] = query
        
        if strategy == DiscoveryStrategy.KEYWORD_MATCH:
            results = self._discover_by_keywords(query, context)
        elif strategy == DiscoveryStrategy.SEMANTIC_SIMILARITY:
            results = await self._discover_by_semantic(query, context)
        elif strategy == DiscoveryStrategy.CONDITION_EVALUATION:
            results = self._discover_by_conditions(query, context)
        else:
            results = self._discover_hybrid(query, context)
        
        results = [r for r in results if r.score >= min_score]
        results.sort(key=lambda x: x.score, reverse=True)
        
        self._record_discovery(query, results)
        
        return results[:max_tools]
    
    def _discover_by_keywords(self, query: str, context: Dict[str, Any]) -> List[DiscoveryResult]:
        """基于关键词匹配发现工具"""
        suggestions = self.selector.get_tool_suggestions(query, limit=20)
        results = []
        
        for suggestion in suggestions:
            tool = self.registry.get(suggestion["tool_id"])
            if tool:
                results.append(DiscoveryResult(
                    tool_id=suggestion["tool_id"],
                    name=suggestion["name"],
                    description=suggestion["description"],
                    category=suggestion["category"],
                    score=suggestion["score"],
                    reason="关键词匹配",
                    conditions_matched=0,
                    total_conditions=0,
                    compatibility_tags=tool.metadata.compatibility_tags,
                    exclusion_tags=tool.metadata.exclusion_tags,
                ))
        
        return results
    
    async def _discover_by_semantic(self, query: str, context: Dict[str, Any]) -> List[DiscoveryResult]:
        """基于语义相似度发现工具"""
        results = []
        
        if self.llm_service:
            try:
                all_tools = self.registry.get_all()
                tool_descriptions = []
                
                for tool in all_tools:
                    if tool.metadata.status.value == "active":
                        tool_descriptions.append({
                            "tool_id": tool.metadata.tool_id,
                            "name": tool.metadata.name,
                            "description": tool.metadata.description,
                            "category": tool.metadata.category.value,
                        })
                
                prompt = f"""你是一个工具选择专家。请根据以下用户查询，从可用工具中选择最合适的工具，并给出匹配分数（0-1）。

用户查询：{query}

可用工具：{json.dumps(tool_descriptions, ensure_ascii=False)}

请返回JSON格式：
[
  {{"tool_id": "工具ID", "score": 匹配分数, "reason": "匹配原因"}}
]
"""
                response = await self.llm_service.generate_response(prompt)
                import json
                try:
                    llm_results = json.loads(response)
                    for r in llm_results:
                        tool = self.registry.get(r["tool_id"])
                        if tool:
                            results.append(DiscoveryResult(
                                tool_id=r["tool_id"],
                                name=tool.metadata.name,
                                description=tool.metadata.description,
                                category=tool.metadata.category.value,
                                score=r["score"],
                                reason=r.get("reason", "语义匹配"),
                                conditions_matched=0,
                                total_conditions=0,
                                compatibility_tags=tool.metadata.compatibility_tags,
                                exclusion_tags=tool.metadata.exclusion_tags,
                            ))
                except json.JSONDecodeError:
                    app_logger.warning("LLM返回的工具选择结果格式错误")
            except Exception as e:
                app_logger.warning(f"语义发现失败: {e}")
        
        if not results:
            results = self._discover_by_keywords(query, context)
        
        return results
    
    def _discover_by_conditions(self, query: str, context: Dict[str, Any]) -> List[DiscoveryResult]:
        """基于条件评估发现工具"""
        results = []
        
        for tool in self.registry.get_all():
            if tool.metadata.status.value != "active":
                continue
            
            condition_score = tool.metadata.evaluate_conditions(context)
            
            if condition_score > 0:
                matched_count = sum(1 for c in tool.metadata.conditions if c.evaluate(context))
                total_count = len(tool.metadata.conditions)
                
                results.append(DiscoveryResult(
                    tool_id=tool.metadata.tool_id,
                    name=tool.metadata.name,
                    description=tool.metadata.description,
                    category=tool.metadata.category.value,
                    score=condition_score,
                    reason=f"条件匹配 {matched_count}/{total_count}",
                    conditions_matched=matched_count,
                    total_conditions=total_count,
                    compatibility_tags=tool.metadata.compatibility_tags,
                    exclusion_tags=tool.metadata.exclusion_tags,
                ))
        
        return results
    
    def _discover_hybrid(self, query: str, context: Dict[str, Any]) -> List[DiscoveryResult]:
        """混合策略发现工具"""
        keyword_results = self._discover_by_keywords(query, context)
        condition_results = self._discover_by_conditions(query, context)
        
        combined: Dict[str, DiscoveryResult] = {}
        
        for result in keyword_results:
            combined[result.tool_id] = result
            combined[result.tool_id].score *= 0.5
        
        for result in condition_results:
            if result.tool_id in combined:
                combined[result.tool_id].score += result.score * 0.5
                combined[result.tool_id].conditions_matched = result.conditions_matched
                combined[result.tool_id].total_conditions = result.total_conditions
            else:
                result.score *= 0.5
                combined[result.tool_id] = result
        
        return list(combined.values())
    
    def _record_discovery(self, query: str, results: List[DiscoveryResult]):
        """记录发现历史"""
        record = {
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "discovered_tool_ids": [r.tool_id for r in results],
            "scores": {r.tool_id: r.score for r in results},
        }
        self._discovery_history.append(record)
        
        for result in results:
            if result.tool_id not in self._usage_patterns:
                self._usage_patterns[result.tool_id] = []
            self._usage_patterns[result.tool_id].append(query)
    
    def get_discovery_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取发现历史"""
        return self._discovery_history[-limit:]
    
    def get_usage_patterns(self) -> Dict[str, List[str]]:
        """获取使用模式"""
        return self._usage_patterns
    
    async def suggest_tool_combination(self, query: str, context: Optional[Dict[str, Any]] = None) -> ToolPlan:
        """建议工具组合"""
        discovered = await self.discover_tools(query, context, max_tools=10)
        
        compatible_tools = []
        selected_tool_ids = set()
        
        for tool in discovered:
            if not tool.exclusion_tags:
                compatible = True
                for existing in compatible_tools:
                    if set(tool.exclusion_tags) & set(existing["exclusion_tags"]):
                        compatible = False
                        break
                if compatible:
                    compatible_tools.append({
                        "tool_id": tool.tool_id,
                        "name": tool.name,
                        "description": tool.description,
                        "score": tool.score,
                        "compatibility_tags": tool.compatibility_tags,
                        "exclusion_tags": tool.exclusion_tags,
                    })
                    selected_tool_ids.add(tool.tool_id)
        
        tools_info = []
        dependencies = []
        estimated_cost = 0.0
        estimated_time = 0.0
        
        for tool_info in compatible_tools[:5]:
            tool = self.registry.get(tool_info["tool_id"])
            if tool:
                tools_info.append({
                    "tool_id": tool.metadata.tool_id,
                    "name": tool.metadata.name,
                    "description": tool.metadata.description,
                    "category": tool.metadata.category.value,
                    "parameters": [p.name for p in tool.metadata.parameters],
                    "cost": tool.metadata.cost,
                    "timeout": tool.metadata.timeout,
                })
                estimated_cost += tool.metadata.cost
                estimated_time += tool.metadata.avg_execution_time or tool.metadata.timeout
                
                for dep_tool_id in tool.metadata.dependencies:
                    if dep_tool_id in selected_tool_ids:
                        dependencies.append((dep_tool_id, tool.metadata.tool_id))
        
        execution_order = "sequential" if dependencies else "parallel"
        
        return ToolPlan(
            plan_id=f"plan_{int(datetime.now().timestamp())}",
            tools=tools_info,
            execution_order=execution_order,
            dependencies=dependencies,
            estimated_cost=estimated_cost,
            estimated_time=estimated_time,
        )


class ToolCombinationEngine:
    """工具组合引擎"""
    
    def __init__(self, llm_service: Optional[LLMService] = None):
        self.registry = get_tool_registry()
        self.llm_service = llm_service
        self._combination_rules: List[ToolCombinationRule] = []
        self._init_default_rules()
    
    def _init_default_rules(self):
        """初始化默认组合规则"""
        default_rules = [
            ToolCombinationRule(
                rule_id="rule_meeting_analysis",
                tool_ids=["search_meeting", "extract_todos", "extract_controversies", "generate_minutes"],
                execution_order="sequential",
                condition="会议分析",
                description="完整的会议分析流程",
                priority=10,
            ),
            ToolCombinationRule(
                rule_id="rule_doc_analysis",
                tool_ids=["search_document", "extract_key_points"],
                execution_order="sequential",
                condition="文档分析",
                description="文档分析流程",
                priority=8,
            ),
            ToolCombinationRule(
                rule_id="rule_knowledge_search",
                tool_ids=["knowledge_base_search", "search_meeting"],
                execution_order="parallel",
                condition="知识搜索",
                description="并行搜索知识库和会议记录",
                priority=7,
            ),
        ]
        
        self._combination_rules.extend(default_rules)
    
    def add_combination_rule(self, rule: ToolCombinationRule):
        """添加组合规则"""
        self._combination_rules.append(rule)
        app_logger.info(f"[ToolCombination] 添加组合规则: {rule.rule_id}")
    
    def match_combinations(self, query: str, context: Optional[Dict[str, Any]] = None) -> List[ToolCombinationRule]:
        """匹配适用的组合规则"""
        matched = []
        
        for rule in self._combination_rules:
            if rule.condition and rule.condition.lower() in query.lower():
                matched.append(rule)
        
        matched.sort(key=lambda x: x.priority, reverse=True)
        
        return matched
    
    async def generate_combination_plan(self, query: str, context: Optional[Dict[str, Any]] = None) -> ToolPlan:
        """生成工具组合计划"""
        matched_rules = self.match_combinations(query, context)
        
        if matched_rules:
            rule = matched_rules[0]
            tools_info = []
            dependencies = []
            estimated_cost = 0.0
            estimated_time = 0.0
            
            for tool_id in rule.tool_ids:
                tool = self.registry.get(tool_id)
                if tool and tool.metadata.status.value == "active":
                    tools_info.append({
                        "tool_id": tool.metadata.tool_id,
                        "name": tool.metadata.name,
                        "description": tool.metadata.description,
                        "category": tool.metadata.category.value,
                        "parameters": [p.name for p in tool.metadata.parameters],
                        "cost": tool.metadata.cost,
                        "timeout": tool.metadata.timeout,
                    })
                    estimated_cost += tool.metadata.cost
                    estimated_time += tool.metadata.avg_execution_time or tool.metadata.timeout
            
            return ToolPlan(
                plan_id=f"plan_{int(datetime.now().timestamp())}",
                tools=tools_info,
                execution_order=rule.execution_order,
                dependencies=dependencies,
                estimated_cost=estimated_cost,
                estimated_time=estimated_time,
            )
        
        discovery = DynamicToolDiscovery(self.llm_service)
        return await discovery.suggest_tool_combination(query, context)
    
    async def execute_combination(self, plan: ToolPlan, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """执行工具组合"""
        results = {}
        context = context or {}
        
        if plan.execution_order == "parallel":
            import asyncio
            
            async def execute_tool(tool_info):
                tool = self.registry.get(tool_info["tool_id"])
                if tool:
                    tool_params = params.get(tool_info["tool_id"], {})
                    tool_params.update(context.get("common_params", {}))
                    result = await tool.execute(tool_params, context)
                    return tool_info["tool_id"], result
            
            tasks = [execute_tool(t) for t in plan.tools]
            executed_results = await asyncio.gather(*tasks)
            
            for tool_id, result in executed_results:
                results[tool_id] = result.to_dict() if hasattr(result, "to_dict") else result
        
        else:
            for tool_info in plan.tools:
                tool = self.registry.get(tool_info["tool_id"])
                if tool:
                    tool_params = params.get(tool_info["tool_id"], {})
                    tool_params.update(context.get("common_params", {}))
                    
                    for dep_id, _ in plan.dependencies:
                        if dep_id in results:
                            dep_result = results[dep_id]
                            if "result" in dep_result:
                                tool_params["previous_result"] = dep_result["result"]
                    
                    result = await tool.execute(tool_params, context)
                    results[tool_info["tool_id"]] = result.to_dict() if hasattr(result, "to_dict") else result
        
        return {
            "plan_id": plan.plan_id,
            "execution_order": plan.execution_order,
            "results": results,
            "total_tools": len(plan.tools),
            "successful_tools": sum(1 for r in results.values() if r.get("success")),
        }
    
    def get_combination_rules(self) -> List[ToolCombinationRule]:
        """获取所有组合规则"""
        return self._combination_rules


# 全局实例
_dynamic_discovery: Optional[DynamicToolDiscovery] = None
_combination_engine: Optional[ToolCombinationEngine] = None


def get_dynamic_tool_discovery(llm_service: Optional[LLMService] = None) -> DynamicToolDiscovery:
    """获取动态工具发现实例"""
    global _dynamic_discovery
    if _dynamic_discovery is None:
        _dynamic_discovery = DynamicToolDiscovery(llm_service)
    return _dynamic_discovery


def get_tool_combination_engine(llm_service: Optional[LLMService] = None) -> ToolCombinationEngine:
    """获取工具组合引擎实例"""
    global _combination_engine
    if _combination_engine is None:
        _combination_engine = ToolCombinationEngine(llm_service)
    return _combination_engine