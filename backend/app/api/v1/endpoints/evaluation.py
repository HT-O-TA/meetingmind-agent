"""RAG 和 Agent 评估 API"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.services.rag_evaluation_service import RAGEvaluationService
from app.services.vector_search_service import VectorSearchService
from app.services.rag_regression import run_regression_test, establish_baseline, run_single_test
from app.services.ragas_evaluator import (
    get_evaluation_statistics, 
    get_agent_evaluation_statistics, 
    evaluate_agent_response,
    get_agent_benchmark,
    BenchmarkTask,
    evaluate_batch_agent
)
from app.services.agent_benchmark import (
    run_agent_benchmark,
    run_single_agent_test,
    get_benchmark_categories,
    get_difficulty_levels
)
from app.agents.monitor import get_monitor
from app.core.response import Response
try:
    from tests.rag.rag_eval_dataset import get_eval_dataset
except ImportError:
    try:
        from tests.rag_eval_dataset import get_eval_dataset
    except ImportError:
        from app.tests.data.rag_eval_dataset import get_eval_dataset

router = APIRouter(tags=["评估"])


async def get_evaluation_service(db: AsyncSession = Depends(get_db)) -> RAGEvaluationService:
    """获取 RAG 评估服务实例"""
    vector_service = VectorSearchService(db)
    await vector_service.check_pgvector_support()
    return RAGEvaluationService(vector_service=vector_service)


@router.get("/dataset", summary="获取评估数据集")
async def get_evaluation_dataset():
    """获取内置的 RAG 评估测试数据集"""
    dataset = get_eval_dataset()
    return Response.ok(dataset)


@router.post("/evaluate", summary="评估单个问题")
async def evaluate_single_question(
    question: str,
    expected_answer: str,
    relevant_doc_ids: list = [],
    top_k: int = 5,
    skip_llm: bool = False,
    service: RAGEvaluationService = Depends(get_evaluation_service),
):
    """
    评估单个问题的检索和回答质量

    - **question**: 用户问题
    - **expected_answer**: 期望的正确回答
    - **relevant_doc_ids**: 相关文档ID列表（可选）
    - **top_k**: 检索返回数量（默认5）
    - **skip_llm**: 是否跳过LLM生成，只计算检索指标（默认False）
    """
    result = await service.evaluate_single_question(
        question=question,
        expected_answer=expected_answer,
        relevant_doc_ids=relevant_doc_ids,
        top_k=top_k,
        skip_llm=skip_llm,
    )
    return Response.ok(result)


@router.post("/evaluate/{question_id}", summary="根据ID评估问题")
async def evaluate_by_id(
    question_id: str,
    top_k: int = 5,
    skip_llm: bool = False,
    service: RAGEvaluationService = Depends(get_evaluation_service),
):
    """
    根据问题ID评估单个问题（从内置数据集获取）

    - **question_id**: 问题ID（如 q1, q2）
    - **top_k**: 检索返回数量（默认5）
    - **skip_llm**: 是否跳过LLM生成，只计算检索指标（默认False）
    """
    result = await service.evaluate_by_id(question_id=question_id, top_k=top_k, skip_llm=skip_llm)
    if "error" in result:
        return Response.error(result["error"], code=404)
    return Response.ok(result)


@router.post("/evaluate-all", summary="评估整个数据集")
async def evaluate_all(
    top_k: Optional[int] = None,
    skip_llm: Optional[bool] = None,
    service: RAGEvaluationService = Depends(get_evaluation_service),
):
    """
    评估整个内置数据集，返回综合评估报告

    - **top_k**: 检索返回数量（不传则读取 EVAL_TOP_K 配置，默认5）
    - **skip_llm**: 是否跳过LLM生成（不传则读取 EVAL_SKIP_LLM 配置，默认False）。日常调参建议在 config 中设为 True。
    """
    result = await service.evaluate_dataset(top_k=top_k, skip_llm=skip_llm)
    return Response.ok(result)


@router.post("/regression", summary="运行回归测试")
async def regression_test():
    """
    运行 RAG 回归测试，检查系统性能是否符合基准
    """
    result = await run_regression_test()
    return Response.ok(result)


@router.post("/baseline", summary="建立基准")
async def baseline():
    """
    建立 RAG 系统的性能基准，用于后续回归测试对比
    """
    result = await establish_baseline()
    return Response.ok(result)


@router.get("/statistics", summary="获取评估统计信息")
async def statistics():
    """
    获取 RAGAS 评估统计信息和监控状态
    """
    result = await get_evaluation_statistics()
    return Response.ok(result)


@router.post("/regression/{case_id}", summary="运行单个回归测试用例")
async def regression_single(case_id: str):
    """
    运行单个回归测试用例
    
    - **case_id**: 测试用例ID（如 bench_001）
    """
    result = await run_single_test(case_id)
    if "error" in result:
        return Response.error(result["error"], code=404)
    return Response.ok(result)


@router.get("/agent/categories", summary="获取 Agent 基准测试类别")
async def agent_benchmark_categories():
    """
    获取所有 Agent 基准测试类别
    """
    categories = get_benchmark_categories()
    return Response.ok(categories)


@router.get("/agent/difficulties", summary="获取 Agent 基准测试难度级别")
async def agent_benchmark_difficulties():
    """
    获取所有 Agent 基准测试难度级别
    """
    difficulties = get_difficulty_levels()
    return Response.ok(difficulties)


@router.post("/agent/benchmark", summary="运行 Agent 基准测试")
async def agent_benchmark(
    category: Optional[str] = Query(None, description="测试类别"),
    difficulty: Optional[str] = Query(None, description="难度级别"),
    limit: Optional[int] = Query(None, description="测试数量限制")
):
    """
    运行 Agent 基准测试，返回综合评估报告
    
    - **category**: 测试类别（如 MEETING_SUMMARY, TODO_EXTRACTION）
    - **difficulty**: 难度级别（EASY, MEDIUM, HARD）
    - **limit**: 测试数量限制
    """
    result = await run_agent_benchmark(
        category=category,
        difficulty=difficulty,
        limit=limit
    )
    return Response.ok(result)


@router.post("/agent/benchmark/{case_id}", summary="运行单个 Agent 测试用例")
async def agent_benchmark_single(case_id: str):
    """
    运行单个 Agent 测试用例
    
    - **case_id**: 测试用例ID（如 agent_001）
    """
    result = await run_single_agent_test(case_id)
    if "error" in result:
        return Response.error(result["error"], code=404)
    return Response.ok(result)


@router.get("/agent/statistics", summary="获取 Agent 评估统计信息")
async def agent_statistics():
    """
    获取 Agent 评估统计信息
    """
    result = await get_agent_evaluation_statistics()
    return Response.ok(result)


@router.post("/agent/evaluate", summary="评估单个 Agent 响应")
async def evaluate_agent(
    query: str = Query(..., description="用户查询"),
    answer: str = Query(..., description="Agent 返回的答案"),
    ground_truth: Optional[str] = Query(None, description="预期答案"),
    expected_route: Optional[str] = Query(None, description="预期路由"),
    actual_route: Optional[str] = Query(None, description="实际路由"),
    retry_count: Optional[int] = Query(0, description="重试次数"),
    execution_time_ms: Optional[float] = Query(0.0, description="执行时间(ms)"),
    token_cost_usd: Optional[float] = Query(0.0, description="令牌成本(美元)"),
    reflection_score: Optional[float] = Query(0.0, description="反思分数"),
    hallucination_detected: Optional[bool] = Query(False, description="是否检测到幻觉")
):
    """
    评估单个 Agent 响应的质量
    
    - **query**: 用户查询
    - **answer**: Agent 返回的答案
    - **ground_truth**: 预期答案
    - **expected_route**: 预期路由
    - **actual_route**: 实际路由
    - **retry_count**: 重试次数
    - **execution_time_ms**: 执行时间(ms)
    - **token_cost_usd**: 令牌成本(美元)
    - **reflection_score**: 反思分数
    - **hallucination_detected**: 是否检测到幻觉
    """
    result = await evaluate_agent_response(
        query=query,
        answer=answer,
        ground_truth=ground_truth,
        expected_route=expected_route,
        actual_route=actual_route,
        retry_count=retry_count,
        execution_time_ms=execution_time_ms,
        token_cost_usd=token_cost_usd,
        reflection_score=reflection_score,
        hallucination_detected=hallucination_detected
    )
    return Response.ok(result)


@router.get("/agent/monitor", summary="获取 Agent 监控统计")
async def agent_monitor_stats():
    """
    获取 Agent 监控统计信息，包括请求量、成功率、延迟、成本等指标
    """
    monitor = get_monitor()
    stats = monitor.get_agent_stats()
    return Response.ok(stats)


@router.get("/agent/benchmark-tasks", summary="获取基准测试任务列表")
async def get_benchmark_tasks(
    category: Optional[str] = Query(None, description="按类别筛选"),
    difficulty: Optional[str] = Query(None, description="按难度筛选"),
    limit: int = Query(100, description="返回数量限制")
):
    """
    获取基准测试任务列表
    
    - **category**: 类别（general/document/analysis/calendar/task）
    - **difficulty**: 难度（easy/medium/hard）
    - **limit**: 返回数量限制
    """
    benchmark = get_agent_benchmark()
    tasks = benchmark.get_tasks(category=category, difficulty=difficulty)
    
    return Response.ok({
        "total_tasks": len(tasks),
        "tasks": [task.to_dict() for task in tasks[:limit]]
    })


@router.get("/agent/benchmark-tasks/{task_id}", summary="获取单个基准测试任务")
async def get_benchmark_task(task_id: str):
    """
    获取单个基准测试任务详情
    
    - **task_id**: 任务 ID
    """
    benchmark = get_agent_benchmark()
    task = benchmark.get_task_by_id(task_id)
    
    if task:
        return Response.ok(task.to_dict())
    else:
        return Response.error(f"任务 {task_id} 未找到", code=404)


@router.post("/agent/benchmark-tasks", summary="添加基准测试任务")
async def add_benchmark_task(
    query: str = Query(..., description="测试查询"),
    ground_truth: str = Query(..., description="标准答案"),
    expected_route: Optional[str] = Query(None, description="预期路由"),
    expected_tools: Optional[List[str]] = Query(None, description="预期工具列表"),
    category: str = Query("general", description="类别"),
    difficulty: str = Query("medium", description="难度")
):
    """
    添加新的基准测试任务
    
    - **query**: 测试查询
    - **ground_truth**: 标准答案
    - **expected_route**: 预期路由（direct/retrieve/tool）
    - **expected_tools**: 预期工具列表
    - **category**: 类别（general/document/analysis/calendar/task）
    - **difficulty**: 难度（easy/medium/hard）
    """
    benchmark = get_agent_benchmark()
    
    task = BenchmarkTask(
        task_id=f"bm_{len(benchmark.get_tasks()) + 1:03d}",
        query=query,
        ground_truth=ground_truth,
        expected_route=expected_route,
        expected_tools=expected_tools,
        category=category,
        difficulty=difficulty
    )
    
    benchmark.add_task(task)
    
    return Response.ok({"message": "任务添加成功", "task": task.to_dict()})


@router.post("/agent/benchmark-run", summary="运行基准测试并生成报告")
async def run_benchmark_and_report(
    task_results: List[Dict[str, Any]] = Body(..., description="任务结果列表")
):
    """
    批量运行基准测试并生成综合报告
    
    请求体示例：
    [
        {
            "task_id": "bm_001",
            "answer": "Agent 是智能实体",
            "actual_route": "direct",
            "execution_time_ms": 500.0,
            "token_cost_usd": 0.002
        }
    ]
    
    - **task_id**: 任务 ID
    - **answer**: Agent 的回答
    - **actual_route**: 实际路由
    - **tools_used**: 实际使用的工具
    - **retry_count**: 重试次数
    - **execution_time_ms**: 执行时间(ms)
    - **token_cost_usd**: Token 成本
    - **reflection_score**: 反思分数
    - **hallucination_detected**: 是否检测到幻觉
    """
    benchmark = get_agent_benchmark()
    
    results = await benchmark.run_batch(task_results)
    report = benchmark.generate_report()
    
    return Response.ok({
        "results": results,
        "report": report
    })


@router.get("/agent/benchmark-report", summary="获取基准测试报告")
async def get_benchmark_report():
    """
    获取最近一次基准测试的综合报告
    """
    benchmark = get_agent_benchmark()
    report = benchmark.generate_report()
    
    return Response.ok(report)


@router.get("/agent/benchmark-results", summary="获取基准测试结果")
async def get_benchmark_results(limit: int = Query(100, description="返回数量限制")):
    """
    获取最近的基准测试结果
    
    - **limit**: 返回数量限制
    """
    benchmark = get_agent_benchmark()
    results = benchmark.get_results(limit=limit)
    
    return Response.ok({
        "total_results": len(results),
        "results": results
    })


@router.post("/agent/evaluate-batch", summary="批量评估 Agent 响应")
async def evaluate_agent_batch(
    items: List[Dict[str, Any]] = Body(..., description="待评估的项目列表")
):
    """
    批量评估多个 Agent 响应
    
    请求体示例：
    [
        {
            "query": "什么是 Agent？",
            "answer": "Agent 是智能实体",
            "ground_truth": "标准答案",
            "expected_route": "direct",
            "actual_route": "direct"
        }
    ]
    """
    results = await evaluate_batch_agent(items)
    return Response.ok(results)
