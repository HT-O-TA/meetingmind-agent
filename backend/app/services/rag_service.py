"""RAG 服务：方案 A（PostgreSQL BM25 + Milvus Dense + Reranker）。"""
from typing import List, Optional, Dict
from app.services.vector_search_service import VectorSearchService
from app.services.llm_service import LLMService
from app.services.knowledge_graph import enhance_search_results
from app.services.knowledge_graph import get_knowledge_graph_index
from app.services.enhanced_retrieval_fusion import get_enhanced_retrieval_fusion
from app.core.logger import app_logger
from app.core.config import settings


class RAGService:
    """RAG 服务类，整合检索与生成"""

    def __init__(self, vector_service: VectorSearchService, llm_service: LLMService = None, enable_evaluation: bool = False):
        self.vector_service = vector_service
        self.llm_service = llm_service or LLMService()
        self.enable_evaluation = enable_evaluation
        self._evaluator = None
    
    def _get_evaluator(self):
        """延迟加载评估器"""
        if self._evaluator is None and self.enable_evaluation:
            try:
                from app.services.ragas_evaluator import get_ragas_evaluator
                self._evaluator = get_ragas_evaluator()
            except Exception as e:
                app_logger.warning(f"无法加载评估器: {e}")
                self.enable_evaluation = False
        return self._evaluator

    async def ask(
        self,
        question: str,
        top_k: int = 5,
        meeting_id: Optional[int] = None,
        department: Optional[str] = None,
        similarity_threshold: float = 0.0,
        use_llm: bool = True,
    ) -> Dict:
        """
        RAG 问答：BM25 + Dense 多路召回、融合、Reranker 精排和可选图谱增强。

        检索流程：
        1. PostgreSQL BM25 与 Milvus Dense 并行召回
        2. 加权融合并使用 BGE Reranker 精排
        3. 可选知识图谱增强

        Args:
            question: 用户问题
            top_k: 检索返回数量
            meeting_id: 指定会议ID（可选）
            department: 指定部门（可选）
            similarity_threshold: 相似度阈值
            use_llm: 是否使用 LLM 生成回答

        Returns:
            包含 answer、chunks、mode 等信息的字典
        """
        # 方案 A：单一查询走 PostgreSQL BM25 + Milvus dense，统一融合后由 Reranker 精排。
        # HyDE、问题分解和复杂查询编排保留在 Query Optimizer 中，后续按评测结果接入。
        search_queries = [question]
        merged_results = await self.vector_service.multi_retrieval_search(
            query_text=question,
            top_k=top_k,
            meeting_id=meeting_id,
            department=department,
            similarity_threshold=similarity_threshold,
            enable_bm25=True,
            enable_vector=True,
            enable_rerank=False,
            strategy="A",
        )
        
        # KG 在 Reranker 前扩展候选；复杂 NER/分类后续接入当前分析接口。
        kg_analysis = get_knowledge_graph_index().get_graph().analyze_query(question)
        if settings.ENABLE_KNOWLEDGE_GRAPH and merged_results:
            try:
                primary_query = search_queries[0] if search_queries else question
                merged_results = await enhance_search_results(
                    primary_query, merged_results, depth=2, max_added_chunks=5,
                    query_analysis=kg_analysis,
                )
                app_logger.info(f"[RAG] 知识图谱增强完成，结果数: {len(merged_results)}")
            except Exception as e:
                app_logger.warning(f"[RAG] 知识图谱增强失败: {e}")

        if settings.ENABLE_RERANK and merged_results:
            fusion = get_enhanced_retrieval_fusion(strategy="A")
            merged_results = await fusion.rerank_candidates(question, merged_results, top_k=top_k)

        # 4. 提取文本片段
        chunks = [r["chunk_text"] for r in merged_results if r.get("chunk_text")]

        # 5. 如果没有检索到结果
        if not chunks:
            return {
                "answer": "抱歉，我在知识库中没有找到与您问题相关的内容。",
                "chunks": [],
                "count": 0,
                "mode": self.vector_service.use_milvus if hasattr(self.vector_service, 'use_milvus') else "unknown",
                "query_type": "standard",
                "original_query": question,
                "rewritten_query": search_queries,
            }

        # 6. LLM 生成回答
        if use_llm:
            try:
                answer = await self.llm_service.generate_answer(
                    question=question,
                    context=chunks,
                )
            except Exception as e:
                app_logger.error(f"LLM 生成失败: {e}")
                answer = "抱歉，AI 生成回答失败。以下是检索到的相关内容：\n\n" + "\n\n".join(
                    [f"[{i+1}] {c}" for i, c in enumerate(chunks[:3])]
                )
        else:
            answer = "以下是检索到的相关内容：\n\n" + "\n\n".join(
                [f"[{i+1}] {c}" for i, c in enumerate(chunks[:3])]
            )

        result = {
            "answer": answer,
            "chunks": merged_results,
            "count": len(merged_results),
            "mode": "milvus" if getattr(self.vector_service, 'use_milvus', False) else 
                    ("pgvector" if getattr(self.vector_service, 'use_pgvector', False) else "lightweight"),
            "query_type": "standard",
            "original_query": question,
            "rewritten_query": search_queries,
            "expanded_query_count": 1,
            "retrieval_strategy": "A",
            "retrieval_sources": sorted({source for r in merged_results for source in r.get("sources", [])}),
        }

        # 如果启用评估，添加评估指标
        if self.enable_evaluation and self._get_evaluator():
            contexts = [r["chunk_text"] for r in merged_results if r.get("chunk_text")]
            try:
                metrics = await self._evaluator.evaluate(
                    query=question,
                    answer=answer,
                    contexts=contexts
                )
                result["evaluation"] = {
                    "metrics": metrics.to_dict() if hasattr(metrics, "to_dict") else metrics,
                    "avg_score": metrics.avg_score() if hasattr(metrics, "avg_score") else None,
                }
            except Exception as e:
                app_logger.warning(f"评估失败: {e}")

        return result
    
