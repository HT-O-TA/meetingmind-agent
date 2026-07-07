"""动态工具发现与组合API端点"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from app.agents.tools.dynamic_tool_discovery import get_dynamic_tool_discovery, get_tool_combination_engine, DiscoveryStrategy
from app.agents.tools.manager import ToolManager
from app.services.llm_service import LLMService

router = APIRouter(prefix="/dynamic-tool", tags=["动态工具"])


@router.get("/discover", response_model=Dict[str, Any])
async def discover_tools(
    query: str,
    strategy: str = "hybrid",
    max_tools: int = 10,
    min_score: float = 0.3,
):
    """
    动态发现工具
    
    Args:
        query: 用户查询
        strategy: 发现策略 (keyword_match, semantic_similarity, condition_evaluation, hybrid)
        max_tools: 最大返回工具数
        min_score: 最低匹配分数
    """
    try:
        discovery = get_dynamic_tool_discovery()
        results = await discovery.discover_tools(
            query=query,
            strategy=DiscoveryStrategy(strategy.lower()),
            max_tools=max_tools,
            min_score=min_score,
        )
        
        return {
            "success": True,
            "data": [r.__dict__ for r in results],
            "count": len(results),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/plan", response_model=Dict[str, Any])
async def generate_tool_plan(
    query: str,
):
    """
    生成工具组合计划
    
    Args:
        query: 用户查询
    """
    try:
        engine = get_tool_combination_engine()
        plan = await engine.generate_combination_plan(query)
        
        return {
            "success": True,
            "data": plan.__dict__,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execute-plan", response_model=Dict[str, Any])
async def execute_tool_plan(
    plan: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
):
    """
    执行工具组合计划
    
    Args:
        plan: 工具计划
        params: 工具参数
    """
    try:
        engine = get_tool_combination_engine()
        
        from app.agents.tools.dynamic_tool_discovery import ToolPlan
        tool_plan = ToolPlan(
            plan_id=plan["plan_id"],
            tools=plan["tools"],
            execution_order=plan.get("execution_order", "sequential"),
            dependencies=plan.get("dependencies", []),
            estimated_cost=plan.get("estimated_cost", 0.0),
            estimated_time=plan.get("estimated_time", 0.0),
        )
        
        result = await engine.execute_combination(tool_plan, params or {}, {})
        
        return {
            "success": True,
            "data": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rules", response_model=Dict[str, Any])
async def get_combination_rules():
    """获取工具组合规则"""
    try:
        engine = get_tool_combination_engine()
        rules = engine.get_combination_rules()
        
        return {
            "success": True,
            "data": [r.__dict__ for r in rules],
            "count": len(rules),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add-rule", response_model=Dict[str, Any])
async def add_combination_rule(
    rule_id: str,
    tool_ids: List[str],
    execution_order: str = "sequential",
    condition: Optional[str] = None,
    description: str = "",
    priority: int = 0,
):
    """
    添加工具组合规则
    
    Args:
        rule_id: 规则ID
        tool_ids: 工具ID列表
        execution_order: 执行顺序 (sequential, parallel)
        condition: 触发条件
        description: 规则描述
        priority: 优先级
    """
    try:
        from app.agents.tools.tool_metadata import ToolCombinationRule
        
        engine = get_tool_combination_engine()
        rule = ToolCombinationRule(
            rule_id=rule_id,
            tool_ids=tool_ids,
            execution_order=execution_order,
            condition=condition,
            description=description,
            priority=priority,
        )
        
        engine.add_combination_rule(rule)
        
        return {
            "success": True,
            "message": f"组合规则 {rule_id} 添加成功",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", response_model=Dict[str, Any])
async def get_discovery_history(limit: int = 20):
    """获取工具发现历史"""
    try:
        discovery = get_dynamic_tool_discovery()
        history = discovery.get_discovery_history(limit)
        
        return {
            "success": True,
            "data": history,
            "count": len(history),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patterns", response_model=Dict[str, Any])
async def get_usage_patterns():
    """获取工具使用模式"""
    try:
        discovery = get_dynamic_tool_discovery()
        patterns = discovery.get_usage_patterns()
        
        return {
            "success": True,
            "data": patterns,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))