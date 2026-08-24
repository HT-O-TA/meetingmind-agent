"""RAG 评估服务"""
import time
from typing import List, Dict, Optional
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from app.services.vector_search_service import VectorSearchService
from app.services.llm_service import LLMService
from app.services.embedding_service import EmbeddingService
try:
    from tests.rag.rag_eval_dataset import get_eval_dataset, get_question_by_id
except ImportError:
    try:
        from tests.rag_eval_dataset import get_eval_dataset, get_question_by_id
    except ImportError:
        from app.tests.data.rag_eval_dataset import get_eval_dataset, get_question_by_id
from app.core.logger import app_logger
from app.core.config import settings


class RAGEvaluationService:
    """RAG 评估服务类"""

    def __init__(self, vector_service: VectorSearchService, llm_service: LLMService = None):
        self.vector_service = vector_service
        self.llm_service = llm_service
        self.embedding_service = EmbeddingService()

    async def evaluate_single_question(
        self,
        question: str,
        expected_answer: str,
        relevant_doc_ids: List[int] = None,
        top_k: Optional[int] = None,
        skip_llm: bool = False,
    ) -> Dict:
        """
        评估单个问题的检索和回答质量

        Args:
            question: 用户问题
            expected_answer: 期望的正确回答
            relevant_doc_ids: 相关文档ID列表
            top_k: 检索返回数量

        Returns:
            评估结果字典
        """
        try:
            # 使用配置中的默认值，如果传入参数则使用传入的值
            effective_top_k = top_k if top_k is not None else settings.TOP_K_DEFAULT
            
            search_results = await self.vector_service.search_by_text(
                query_text=question,
                top_k=effective_top_k,
                similarity_threshold=settings.SIMILARITY_THRESHOLD,
            )

            retrieval_metrics = self._calculate_retrieval_metrics(
                search_results, relevant_doc_ids or [], top_k=effective_top_k
            )

            answer = None
            generation_metrics = {}
            if self.llm_service and not skip_llm:
                try:
                    context = [r["chunk_text"] for r in search_results if r.get("chunk_text")]
                    if context:  # 只有当有上下文时才生成答案
                        answer = await self.llm_service.generate_answer(
                            question=question,
                            context=context,
                            model=settings.EVAL_LLM_MODEL or None,
                            max_tokens=settings.EVAL_LLM_MAX_TOKENS,
                            api_key=settings.EVAL_LLM_API_KEY or None,
                            api_base=settings.EVAL_LLM_API_BASE or None,
                        )
                        generation_metrics = self._calculate_generation_metrics(
                            answer, expected_answer, context
                        )
                        app_logger.debug(f"LLM 生成成功，答案长度: {len(answer) if answer else 0}")
                    else:
                        app_logger.warning("没有检索到上下文，跳过 LLM 生成")
                except Exception as e:
                    app_logger.warning(f"LLM 生成失败: {e}")
                    # 即使 LLM 失败，也记录详细错误信息
                    import traceback
                    app_logger.debug(f"LLM 错误详情: {traceback.format_exc()}")

            return {
                "question": question,
                "expected_answer": expected_answer,
                "actual_answer": answer,
                "retrieval_results": search_results,
                "retrieval_metrics": retrieval_metrics,
                "generation_metrics": generation_metrics,
            }
        except Exception as e:
            app_logger.error(f"评估单个问题失败: {e}")
            return {"error": str(e)}

    def _calculate_retrieval_metrics(
        self,
        search_results: List[Dict],
        relevant_doc_ids: List[int],
        top_k: int = 5,
    ) -> Dict:
        """
        计算检索指标

        Args:
            search_results: 检索结果列表
            relevant_doc_ids: 相关文档ID列表
            top_k: 评估的前k个结果

        Returns:
            指标字典
        """
        similarities = [r.get("similarity", 0) for r in search_results[:top_k]]
        avg_similarity = sum(similarities) / len(similarities) if similarities else 0

        if not relevant_doc_ids:
            return {
                "mean_average_similarity": round(avg_similarity, 4),
                "max_similarity": max(similarities) if similarities else 0,
                "min_similarity": min(similarities) if similarities else 0,
                "has_results": len(search_results) > 0,
                "result_count": len(search_results),
            }

        retrieved_doc_ids = [r.get("document_id") for r in search_results[:top_k] if r.get("document_id")]
        retrieved_doc_ids = [d for d in retrieved_doc_ids if d is not None]

        hits = sum(1 for doc_id in retrieved_doc_ids if doc_id in relevant_doc_ids)

        recall_at_k = hits / len(relevant_doc_ids) if relevant_doc_ids else 0
        hit_at_k = 1.0 if hits > 0 else 0.0

        mrr = 0.0
        for rank, r in enumerate(search_results[:top_k], 1):
            doc_id = r.get("document_id")
            if doc_id in relevant_doc_ids:
                mrr = 1.0 / rank
                break

        return {
            "mean_average_similarity": round(avg_similarity, 4),
            "recall_at_k": round(recall_at_k, 4),
            "hit_at_k": round(hit_at_k, 4),
            "mrr": round(mrr, 4),
            "hits": hits,
            "retrieved_count": len(retrieved_doc_ids),
            "relevant_count": len(relevant_doc_ids),
        }

    def _calculate_generation_metrics(
        self,
        answer: str,
        expected_answer: str,
        context: List[str],
    ) -> Dict:
        """
        计算生成指标

        Args:
            answer: 实际生成的回答
            expected_answer: 期望的正确回答
            context: 检索到的上下文

        Returns:
            指标字典
        """
        if not answer or not expected_answer:
            return {}

        # 一次批量 encode：[answer, expected_answer, ctx1, ctx2, ...]
        all_texts = [answer, expected_answer] + context
        all_embeddings = self.embedding_service.encode_batch(all_texts)

        if len(all_embeddings) < 2:
            return {}

        emb_answer = all_embeddings[0]
        emb_expected = all_embeddings[1]
        emb_contexts = all_embeddings[2:]

        answer_similarity = float(cosine_similarity([emb_answer], [emb_expected])[0][0])

        context_relevance = 0.0
        max_context_similarity = 0.0
        avg_context_similarity = 0.0
        if emb_contexts:
            sims = [float(cosine_similarity([emb_answer], [emb_ctx])[0][0]) for emb_ctx in emb_contexts]
            max_context_similarity = max(sims)
            avg_context_similarity = sum(sims) / len(sims)
            context_relevance = avg_context_similarity

        answer_length = len(answer)

        return {
            "answer_similarity": round(answer_similarity, 4),
            "context_relevance": round(context_relevance, 4),
            "max_context_similarity": round(max_context_similarity, 4),
            "avg_context_similarity": round(avg_context_similarity, 4),
            "answer_length": answer_length,
        }

    def _text_similarity(self, text1: str, text2: str) -> float:
        """
        计算两段文本的相似度

        Args:
            text1: 文本1
            text2: 文本2

        Returns:
            相似度分数 (0-1)
        """
        try:
            emb1 = self.embedding_service.encode_text(text1)
            emb2 = self.embedding_service.encode_text(text2)

            if not emb1 or not emb2:
                return 0.0

            similarity = cosine_similarity([emb1], [emb2])[0][0]
            return float(similarity)
        except Exception as e:
            app_logger.warning(f"计算文本相似度失败: {e}")
            return 0.0

    async def evaluate_dataset(self, dataset: Optional[List[Dict]] = None, top_k: Optional[int] = None, skip_llm: Optional[bool] = None) -> Dict:
        """
        评估整个数据集

        Args:
            dataset: 评估数据集（默认使用内置数据集）
            top_k: 检索返回数量（None 时读取 EVAL_TOP_K 配置）
            skip_llm: 是否跳过LLM生成（None 时读取 EVAL_SKIP_LLM 配置）

        Returns:
            综合评估结果（包含耗时统计）
        """
        # 优先使用传入参数，否则读取评估专用配置
        effective_top_k = top_k if top_k is not None else settings.EVAL_TOP_K
        effective_skip_llm = skip_llm if skip_llm is not None else settings.EVAL_SKIP_LLM
        
        if dataset is None:
            dataset = get_eval_dataset()

        results = []
        total_count = len(dataset)
        start_time = time.time()
        
        app_logger.info(f"开始评估数据集，共 {total_count} 个问题，top_k={effective_top_k}，skip_llm={effective_skip_llm}")

        # 输出 embedding 设备状态
        embedding_status = self.embedding_service.get_status()
        device_info = embedding_status.get("device", "unknown")
        model_info = embedding_status.get("model", "unknown")
        fallback_mode = embedding_status.get("fallback_mode", False)
        dimension = embedding_status.get("dimension", 0)
        app_logger.info(f"[EVAL] Embedding 设备: {device_info} | 模型: {model_info} | 维度: {dimension} | Fallback模式: {fallback_mode}")

        for idx, item in enumerate(dataset, 1):
            result = await self.evaluate_single_question(
                question=item["question"],
                expected_answer=item["expected_answer"],
                relevant_doc_ids=item.get("relevant_doc_ids") or [],
                top_k=effective_top_k,
                skip_llm=effective_skip_llm,
            )
            
            # 清理检索结果中的向量数据，避免输出
            if "retrieval_results" in result:
                for r in result["retrieval_results"]:
                    r.pop("vector", None)  # 移除向量数据
            
            results.append(result)
            
            # 输出进度（每10个问题输出一次）
            if idx % 10 == 0 or idx == total_count:
                elapsed = time.time() - start_time
                progress = (idx / total_count) * 100
                app_logger.info(f"评估进度: {idx}/{total_count} ({progress:.1f}%) - 已耗时: {elapsed:.2f}秒")

        end_time = time.time()
        total_time = end_time - start_time
        
        overall_metrics = self._calculate_overall_metrics(results)

        app_logger.info(f"评估完成！共 {total_count} 个问题，总耗时: {total_time:.2f}秒，平均每个问题: {(total_time/total_count):.2f}秒")

        return {
            "total_questions": total_count,
            "results": results,
            "overall_metrics": overall_metrics,
            "evaluation_time": {
                "total_seconds": round(total_time, 2),
                "average_per_question": round(total_time / total_count, 2),
                "formatted": f"{int(total_time // 60)}分{int(total_time % 60)}秒"
            },
        }

    def _calculate_overall_metrics(self, results: List[Dict]) -> Dict:
        """
        计算综合评估指标

        Args:
            results: 所有问题的评估结果

        Returns:
            综合指标字典
        """
        retrieval_metrics_list = [r.get("retrieval_metrics", {}) for r in results]
        generation_metrics_list = [r.get("generation_metrics", {}) for r in results]

        avg_similarities = [m.get("mean_average_similarity", 0) for m in retrieval_metrics_list]
        avg_recall_at_k = [m.get("recall_at_k", 0) for m in retrieval_metrics_list]
        avg_hit_at_k = [m.get("hit_at_k", 0) for m in retrieval_metrics_list]
        mrrs = [m.get("mrr", 0) for m in retrieval_metrics_list]

        answer_similarities = [m.get("answer_similarity", 0) for m in generation_metrics_list]
        context_relevances = [m.get("context_relevance", 0) for m in generation_metrics_list]

        return {
            "retrieval": {
                "mean_average_similarity": round(sum(avg_similarities) / len(avg_similarities), 4) if avg_similarities else 0,
                "mean_recall_at_k": round(sum(avg_recall_at_k) / len(avg_recall_at_k), 4) if avg_recall_at_k else 0,
                "mean_hit_at_k": round(sum(avg_hit_at_k) / len(avg_hit_at_k), 4) if avg_hit_at_k else 0,
                "mean_mrr": round(sum(mrrs) / len(mrrs), 4) if mrrs else 0,
                "success_rate": round(sum(1 for m in retrieval_metrics_list if m.get("has_results", False)) / len(retrieval_metrics_list), 4) if retrieval_metrics_list else 0,
            },
            "generation": {
                "mean_answer_similarity": round(sum(answer_similarities) / len(answer_similarities), 4) if answer_similarities else 0,
                "mean_context_relevance": round(sum(context_relevances) / len(context_relevances), 4) if context_relevances else 0,
            },
            "total_questions": len(results),
        }

    async def evaluate_by_id(self, question_id: str, top_k: int = 5, skip_llm: bool = False) -> Dict:
        """
        根据问题ID评估单个问题

        Args:
            question_id: 问题ID
            top_k: 检索返回数量
            skip_llm: 是否跳过LLM生成

        Returns:
            评估结果
        """
        item = get_question_by_id(question_id)
        if not item:
            return {"error": "问题不存在"}

        return await self.evaluate_single_question(
            question=item["question"],
            expected_answer=item["expected_answer"],
            relevant_doc_ids=item.get("relevant_doc_ids") or [],
            top_k=top_k,
            skip_llm=skip_llm,
        )
