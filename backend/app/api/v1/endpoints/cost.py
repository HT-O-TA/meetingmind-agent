"""AI 成本管理 API"""
from typing import Optional
from fastapi import APIRouter, Query

from app.services.cost_manager import (
    get_cost_statistics,
    get_cost_forecast_data,
    get_model_list_data,
    get_budget_alert_data,
    select_model_for_task,
    calculate_llm_cost,
    check_token_budget,
    record_llm_cost,
    get_cost_manager
)
from app.core.response import Response

router = APIRouter(tags=["成本管理"])


@router.get("/stats", summary="获取成本统计信息")
async def cost_statistics():
    """
    获取 AI 成本统计信息，包括：
    
    - 总成本（美元）
    - 总 Token 消耗
    - 今日统计（成本、Token、请求数）
    - 按模型分类的统计
    - 按任务类型分类的统计
    - 预算使用情况
    - 缓存状态
    """
    stats = await get_cost_statistics()
    return Response.ok(stats)


@router.get("/forecast", summary="获取成本预测")
async def cost_forecast(
    requests_per_day: int = Query(100, description="每日请求数"),
    avg_tokens_per_request: int = Query(1000, description="平均每请求 Token 数")
):
    """
    获取成本预测数据
    
    - **requests_per_day**: 每日请求数
    - **avg_tokens_per_request**: 平均每请求 Token 数
    
    返回：
    - 每日预测成本
    - 每月预测成本
    - 本月剩余预测成本
    - 平均每请求成本
    """
    forecast = await get_cost_forecast_data(requests_per_day, avg_tokens_per_request)
    return Response.ok(forecast)


@router.get("/models", summary="获取模型列表")
async def model_list():
    """
    获取可用模型列表及其成本信息
    
    返回每个模型的：
    - 名称
    - Prompt 成本（每1K Token）
    - Completion 成本（每1K Token）
    - 最大 Token 数
    - 能力级别
    - 描述
    """
    models = await get_model_list_data()
    return Response.ok(models)


@router.get("/budget-alert", summary="获取预算告警")
async def budget_alert():
    """
    获取 Token 预算告警状态
    
    返回：
    - 告警级别（ok/info/warning/critical）
    - 告警信息列表
    - 每日预算使用率（%）
    - 每月预算使用率（%）
    """
    alert = await get_budget_alert_data()
    return Response.ok(alert)


@router.post("/select-model", summary="选择适合任务的模型")
async def select_model(
    task_type: str = Query(..., description="任务类型"),
    complexity: str = Query("medium", description="复杂度（simple/medium/complex）")
):
    """
    根据任务类型和复杂度选择合适的模型
    
    - **task_type**: 任务类型（summarization/analysis/qa/planning/reflection/simple）
    - **complexity**: 复杂度（simple/medium/complex）
    
    返回：
    - 推荐的模型名称
    """
    model_name = await select_model_for_task(task_type, complexity)
    return Response.ok({"model_name": model_name})


@router.post("/calculate-cost", summary="计算 LLM 调用成本")
async def calculate_cost(
    model_name: str = Query(..., description="模型名称"),
    prompt_tokens: int = Query(..., description="Prompt Token 数"),
    completion_tokens: int = Query(..., description="Completion Token 数")
):
    """
    计算指定模型的调用成本
    
    - **model_name**: 模型名称
    - **prompt_tokens**: Prompt Token 数
    - **completion_tokens**: Completion Token 数
    
    返回：
    - 成本（美元）
    """
    cost = await calculate_llm_cost(model_name, prompt_tokens, completion_tokens)
    return Response.ok({"cost_usd": round(cost, 6)})


@router.post("/check-budget", summary="检查 Token 预算")
async def check_budget(
    tokens_needed: int = Query(..., description="需要的 Token 数")
):
    """
    检查是否有足够的 Token 预算
    
    - **tokens_needed**: 需要的 Token 数
    
    返回：
    - 是否有足够预算
    - 剩余预算信息
    """
    has_budget = await check_token_budget(tokens_needed)
    stats = await get_cost_statistics()
    return Response.ok({
        "has_budget": has_budget,
        "budget": stats.get("budget", {})
    })


@router.post("/record-cost", summary="记录 LLM 调用成本")
async def record_cost(
    model_name: str = Query(..., description="模型名称"),
    prompt_tokens: int = Query(..., description="Prompt Token 数"),
    completion_tokens: int = Query(..., description="Completion Token 数"),
    task_type: str = Query("general", description="任务类型"),
    success: bool = Query(True, description="是否成功"),
    error: Optional[str] = Query(None, description="错误信息")
):
    """
    记录 LLM 调用成本
    
    - **model_name**: 模型名称
    - **prompt_tokens**: Prompt Token 数
    - **completion_tokens**: Completion Token 数
    - **task_type**: 任务类型
    - **success**: 是否成功
    - **error**: 错误信息（失败时）
    """
    await record_llm_cost(model_name, prompt_tokens, completion_tokens, task_type, success, error)
    return Response.ok({"message": "Cost recorded"})


@router.post("/clear-cache", summary="清除结果缓存")
async def clear_cache():
    """
    清除成本管理器的结果缓存
    
    返回：
    - 清除成功消息
    """
    manager = get_cost_manager()
    manager.clear_cache()
    return Response.ok({"message": "Cache cleared"})