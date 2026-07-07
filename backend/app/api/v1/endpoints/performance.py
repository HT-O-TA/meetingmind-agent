"""性能指标 API"""
from fastapi import APIRouter
from app.services.performance_metrics import (
    get_performance_matrix,
    get_latency_stats,
    get_cache_performance,
    get_cost_performance,
    get_retry_performance,
    record_performance,
    get_performance_metrics,
    generate_performance_report
)
from app.core.response import Response

router = APIRouter(tags=["性能指标"])


@router.get("/matrix", summary="获取完整性能矩阵")
async def performance_matrix():
    """
    获取完整的性能数据矩阵，包括：
    - QPS（每秒查询率）
    - 延迟统计（P50/P95/P99）
    - 缓存命中率
    - Token 成本
    - 工具调用成功率
    - Agent 成功率
    - 重试率
    - LLM 调用统计
    """
    result = await get_performance_matrix()
    return Response.ok(result)


@router.get("/latency", summary="获取延迟统计")
async def latency_stats():
    """
    获取延迟统计信息，包括：
    - P50/P95/P99 延迟
    - 平均/最小/最大延迟
    - QPS（1min/5min/15min）
    """
    result = await get_latency_stats()
    return Response.ok(result)


@router.get("/cache", summary="获取缓存性能统计")
async def cache_stats():
    """
    获取缓存性能统计，包括：
    - 总命中率
    - API 缓存命中率
    - LLM 缓存命中率
    - 命中/未命中次数
    """
    result = await get_cache_performance()
    return Response.ok(result)


@router.get("/cost", summary="获取成本统计")
async def cost_stats():
    """
    获取成本统计信息，包括：
    - Token 消耗总量
    - 平均每次请求成本
    - 总成本（美元）
    """
    result = await get_cost_performance()
    return Response.ok(result)


@router.get("/retry", summary="获取重试统计")
async def retry_stats():
    """
    获取重试统计信息，包括：
    - 总重试次数
    - 重试率
    - 成功率
    - 按组件分类的统计
    """
    result = await get_retry_performance()
    return Response.ok(result)


@router.post("/record", summary="记录性能数据")
async def record_performance_data(
    latency_ms: float = None,
    token_cost_usd: float = None
):
    """
    记录性能数据（用于插桩）
    
    - **latency_ms**: 延迟（毫秒）
    - **token_cost_usd**: Token 成本（美元）
    """
    await record_performance(
        latency_ms=latency_ms or 0.0,
        token_cost_usd=token_cost_usd or 0.0
    )
    return Response.ok({"message": "Performance data recorded"})


@router.post("/reset", summary="重置性能统计")
async def reset_performance():
    """重置所有性能统计数据"""
    pm = get_performance_metrics()
    pm.reset()
    return Response.ok({"message": "Performance metrics reset"})


@router.get("/report", summary="获取完整性能数据报告")
async def performance_report():
    """
    获取完整的性能数据报告，包括：
    
    - 系统健康状态（healthy/warning/critical）
    - 延迟统计（P50/P95/P99/avg/min/max）
    - QPS（1min/5min/15min）
    - 缓存命中率（总命中率/API缓存/LLM缓存）
    - Token 成本统计（总成本/平均成本）
    - 工具调用统计（总数/成功率/平均延迟）
    - Agent 统计（请求数/成功率/错误率/延迟/成本）
    - 重试统计（总重试次数/重试率/成功率）
    - LLM 统计（请求数/平均延迟）
    - 评估指标（任务成功率/工具成功率/路由准确率）
    - 最近追踪记录
    - 优化建议
    
    适用于生成性能测试报告和监控仪表盘。
    """
    report = await generate_performance_report()
    return Response.ok(report)