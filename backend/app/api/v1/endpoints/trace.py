"""Agent Trace API - 提供追踪数据查询接口"""
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query

from app.core.logger import app_logger
from app.agents.monitor import get_monitor
from app.core.observability import get_observability_system
from app.agents.trace_integration import get_execution_tracer

router = APIRouter(prefix="/trace", tags=["Agent Trace"])


@router.get("/spans", response_model=List[Dict[str, Any]])
async def get_spans(
    limit: int = Query(100, description="返回数量限制"),
    operation_name: Optional[str] = Query(None, description="按操作名称筛选"),
):
    """
    获取最近的追踪跨度列表
    
    Args:
        limit: 返回数量限制
        operation_name: 按操作名称筛选
        
    Returns:
        跨度列表
    """
    try:
        monitor = get_monitor()
        
        if operation_name:
            spans = monitor.get_spans_by_operation(operation_name, limit)
        else:
            spans = monitor.get_spans(limit)
        
        return spans
    except Exception as e:
        app_logger.error(f"获取跨度列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/spans/{span_id}", response_model=Optional[Dict[str, Any]])
async def get_span_by_id(span_id: str):
    """
    根据 ID 获取跨度详细信息
    
    Args:
        span_id: 跨度 ID
        
    Returns:
        跨度详细信息
    """
    try:
        monitor = get_monitor()
        span = monitor.get_span_by_id(span_id)
        
        if span:
            return span
        else:
            raise HTTPException(status_code=404, detail=f"跨度 {span_id} 未找到")
    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"获取跨度信息失败 {span_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trace-tree", response_model=List[Dict[str, Any]])
async def get_trace_tree(limit: int = Query(50, description="返回数量限制")):
    """
    获取追踪树结构（完整执行链路）
    
    返回按父级关系组织的追踪树，展示 Agent 执行的完整层级结构
    
    Args:
        limit: 返回数量限制
        
    Returns:
        追踪树列表
    """
    try:
        monitor = get_monitor()
        trace_tree = monitor.get_trace_tree(limit)
        return trace_tree
    except Exception as e:
        app_logger.error(f"获取追踪树失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics", response_model=Dict[str, Any])
async def get_metrics():
    """
    获取 Agent 监控指标
    
    Returns:
        指标统计信息
    """
    try:
        monitor = get_monitor()
        return monitor.get_all_metrics()
    except Exception as e:
        app_logger.error(f"获取指标失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/{metric_name}", response_model=Dict[str, Any])
async def get_metric(metric_name: str):
    """
    获取单个指标统计信息
    
    Args:
        metric_name: 指标名称
        
    Returns:
        指标统计信息
    """
    try:
        monitor = get_monitor()
        stats = monitor.get_metric_stats(metric_name)
        
        if stats:
            return stats
        else:
            raise HTTPException(status_code=404, detail=f"指标 {metric_name} 未找到")
    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"获取指标信息失败 {metric_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/overview", response_model=Dict[str, Any])
async def get_observability_overview():
    """
    获取可观测性概览信息
    
    Returns:
        概览信息（追踪、指标、日志）
    """
    try:
        obs_system = get_observability_system()
        return obs_system.get_overview()
    except Exception as e:
        app_logger.error(f"获取概览信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=Dict[str, Any])
async def get_health_status():
    """
    获取健康状态
    
    Returns:
        健康状态信息
    """
    try:
        obs_system = get_observability_system()
        return obs_system.get_health_status()
    except Exception as e:
        app_logger.error(f"获取健康状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monitor-status", response_model=Dict[str, Any])
async def get_monitor_status():
    """
    获取监控器状态
    
    Returns:
        监控器状态信息
    """
    try:
        monitor = get_monitor()
        return monitor.get_monitor_status()
    except Exception as e:
        app_logger.error(f"获取监控器状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recent-traces", response_model=List[Dict[str, Any]])
async def get_recent_traces(limit: int = Query(10, description="返回数量限制")):
    """
    获取最近的追踪记录
    
    Args:
        limit: 返回数量限制
        
    Returns:
        追踪记录列表
    """
    try:
        obs_system = get_observability_system()
        tracer = obs_system.get_tracer()
        traces = tracer.get_recent_traces(limit)
        
        return [
            {
                "trace_id": trace.trace_id,
                "status": trace.status.value,
                "duration_ms": trace.duration_ms,
                "start_time": trace.start_time.isoformat(),
                "end_time": trace.end_time.isoformat() if trace.end_time else None,
                "span_count": len(trace.spans),
                "metadata": trace.metadata,
            }
            for trace in traces
        ]
    except Exception as e:
        app_logger.error(f"获取追踪记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recent-traces/{trace_id}", response_model=Dict[str, Any])
async def get_trace_detail(trace_id: str):
    """
    获取单个追踪记录的详细信息
    
    Args:
        trace_id: 追踪 ID
        
    Returns:
        追踪详细信息
    """
    try:
        obs_system = get_observability_system()
        tracer = obs_system.get_tracer()
        trace = tracer.get_trace(trace_id)
        
        if trace:
            return {
                "trace_id": trace.trace_id,
                "status": trace.status.value,
                "duration_ms": trace.duration_ms,
                "start_time": trace.start_time.isoformat(),
                "end_time": trace.end_time.isoformat() if trace.end_time else None,
                "metadata": trace.metadata,
                "spans": [
                    {
                        "span_id": span.span_id,
                        "parent_span_id": span.parent_span_id,
                        "name": span.name,
                        "status": span.status.value,
                        "duration_ms": span.duration_ms,
                        "start_time": span.start_time.isoformat(),
                        "end_time": span.end_time.isoformat() if span.end_time else None,
                        "attributes": span.attributes,
                        "events": span.events,
                    }
                    for span in trace.spans
                ],
            }
        else:
            raise HTTPException(status_code=404, detail=f"追踪 {trace_id} 未找到")
    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"获取追踪详情失败 {trace_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics-summary", response_model=Dict[str, Any])
async def get_metrics_summary():
    """
    获取指标摘要（内部指标）
    
    Returns:
        指标摘要信息
    """
    try:
        obs_system = get_observability_system()
        metrics = obs_system.get_metrics_collector()
        return metrics.get_metric_summary()
    except Exception as e:
        app_logger.error(f"获取指标摘要失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timeline", response_model=Dict[str, Any])
async def get_agent_timeline(trace_id: Optional[str] = Query(None, description="追踪 ID")):
    """
    获取 Agent Timeline 数据
    
    展示 Question → Planner → Retriever → Tool → Reflection → LLM → Answer 的完整执行时间线
    
    Args:
        trace_id: 追踪 ID（可选，默认获取最近一次）
        
    Returns:
        Timeline 数据，包含每一步的耗时、Token、成本等信息
    """
    try:
        tracer = get_execution_tracer()
        timeline = tracer.get_timeline(trace_id)
        return timeline
    except Exception as e:
        app_logger.error(f"获取 Timeline 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/execution-steps", response_model=List[Dict[str, Any]])
async def get_recent_execution_traces(limit: int = Query(10, description="返回数量限制")):
    """
    获取最近的执行链路追踪记录
    
    Returns:
        执行链路列表，包含每一步的详细信息
    """
    try:
        tracer = get_execution_tracer()
        traces = tracer.get_recent_traces(limit)
        return traces
    except Exception as e:
        app_logger.error(f"获取执行链路失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/execution-steps/{trace_id}", response_model=Dict[str, Any])
async def get_execution_trace_detail(trace_id: str):
    """
    获取单个执行链路的详细信息
    
    Args:
        trace_id: 追踪 ID
        
    Returns:
        执行链路详细信息，包含完整的步骤树和摘要统计
    """
    try:
        tracer = get_execution_tracer()
        trace = tracer.get_trace(trace_id)
        
        if trace:
            return trace
        else:
            raise HTTPException(status_code=404, detail=f"执行链路 {trace_id} 未找到")
    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"获取执行链路详情失败 {trace_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))