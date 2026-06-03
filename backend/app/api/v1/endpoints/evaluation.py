"""RAG 评估 API"""
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.services.rag_evaluation_service import RAGEvaluationService
from app.services.vector_search_service import VectorSearchService
from app.services.rag_regression import run_regression_test, establish_baseline, run_single_test
from app.services.ragas_evaluator import get_evaluation_statistics
from app.core.response import Response
try:
    from tests.rag_eval_dataset import get_eval_dataset
except ImportError:
    from app.tests.data.rag_eval_dataset import get_eval_dataset

router = APIRouter(tags=["RAG 评估"])


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
    result = get_evaluation_statistics()
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
