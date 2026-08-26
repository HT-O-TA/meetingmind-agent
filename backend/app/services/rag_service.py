"""RAG 服务：方案 A（PostgreSQL BM25 + Milvus Dense + Reranker）。"""
import time
from typing import Any, List, Optional, Dict
from app.services.vector_search_service import VectorSearchService
from app.services.llm_service import LLMService
from app.services.enhanced_retrieval_fusion import get_enhanced_retrieval_fusion
from app.core.logger import app_logger
from app.core.config import settings
from app.schemas.rag import Citation, RAGResult


class RAGService:
    """RAG 服务类，整合检索与生成"""

    def __init__(self, vector_service: VectorSearchService, llm_service: LLMService = None):
        self.vector_service = vector_service
        self.llm_service = llm_service or LLMService()

    def _retrieval_mode(self) -> str:
        """将底层布尔能力标记转换为稳定的 API 字符串。"""
        if getattr(self.vector_service, "use_milvus", False):
            return "milvus"
        if getattr(self.vector_service, "use_pgvector", False):
            return "pgvector"
        return "lightweight"

    @staticmethod
    def _build_citations(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """从最终排序后的片段生成稳定、可追溯的引用。"""
        citations = []
        for index, result in enumerate(results, start=1):
            chunk_id = result.get("chunk_id") or result.get("id")
            document_id = result.get("document_id")
            meeting_id = result.get("meeting_id")
            source_id = chunk_id if chunk_id is not None else document_id
            content = result.get("chunk_text") or result.get("content") or ""
            citation = Citation(
                citation_id=f"[{index}]",
                source_id=str(source_id if source_id is not None else f"rank-{index}"),
                source_type="meeting_chunk" if meeting_id is not None else "document_chunk",
                chunk_id=chunk_id,
                document_id=document_id,
                meeting_id=meeting_id,
                chunk_index=result.get("chunk_index"),
                speaker=result.get("speaker_name") or result.get("speaker"),
                time_offset=result.get("time_offset"),
                score=float(result.get("score", result.get("similarity", 0.0)) or 0.0),
                retrieval_sources=sorted(result.get("sources", [])),
                text_excerpt=str(content)[:240],
            )
            citations.append(citation.model_dump())
        return citations

    async def ask(
        self,
        question: str,
        top_k: int = 5,
        meeting_id: Optional[int] = None,
        department: Optional[str] = None,
        similarity_threshold: float = 0.0,
        use_llm: bool = True,
        access_context: Optional[Any] = None,
    ) -> Dict:
        """
        RAG 问答：BM25 + Dense 多路召回、融合和 Reranker 精排。

        检索流程：
        1. Dense 与 PostgreSQL BM25 顺序召回（当前实现尚未并行化）
        2. 加权融合
        3. BGE Reranker 精排

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
        started_at = time.perf_counter()
        degradation_reasons: List[str] = []
        degradation_actions: List[str] = []

        # 方案 A：单一查询走 PostgreSQL BM25 + Milvus dense，统一融合后由 Reranker 精排。
        search_queries = [question]
        candidate_top_k = max(top_k, settings.RERANK_TOP_N) if settings.ENABLE_RERANK else top_k
        merged_results = await self.vector_service.search_with_multi_retrieval(
            query_text=question,
            top_k=candidate_top_k,
            meeting_id=meeting_id,
            department=department,
            similarity_threshold=similarity_threshold,
            enable_rerank=False,
            access_context=access_context,
        )
        retrieval_stage_metrics = dict(
            getattr(self.vector_service, "last_retrieval_trace", {}) or {}
        )
        
        if settings.ENABLE_RERANK and merged_results:
            rerank_started_at = time.perf_counter()
            fusion = get_enhanced_retrieval_fusion(strategy="A")
            merged_results = await fusion.rerank_candidates(question, merged_results, top_k=top_k)
            retrieval_stage_metrics["rerank_latency_ms"] = (
                time.perf_counter() - rerank_started_at
            ) * 1000

        retrieval_latency_ms = (time.perf_counter() - started_at) * 1000

        # 4. 提取文本片段
        chunks = [r["chunk_text"] for r in merged_results if r.get("chunk_text")]
        citations = self._build_citations(merged_results)

        # 5. 如果没有检索到结果
        if not chunks:
            degradation_reasons.append("no_retrieval_results")
            degradation_actions.append("returned_knowledge_base_miss_message")
            result = {
                "answer": "抱歉，我在知识库中没有找到与您问题相关的内容。",
                "chunks": [],
                "citations": [],
                "count": 0,
                "mode": self._retrieval_mode(),
                "query_type": "standard",
                "original_query": question,
                "rewritten_query": search_queries,
                "expanded_query_count": 1,
                "retrieval_strategy": "A",
                "retrieval_sources": [],
                "retrieval_stage_metrics": retrieval_stage_metrics,
                "retrieval_latency_ms": retrieval_latency_ms,
                "generation_latency_ms": 0.0,
                "total_latency_ms": (time.perf_counter() - started_at) * 1000,
                "degradation": {
                    "applied": True,
                    "reasons": degradation_reasons,
                    "actions": degradation_actions,
                },
                "provenance": {"citation_count": 0, "access_control_applied": access_context is not None},
            }
            return RAGResult.model_validate(result).model_dump()

        # 6. LLM 生成回答
        generation_started_at = time.perf_counter()
        if use_llm:
            try:
                answer = await self.llm_service.generate_answer(
                    question=question,
                    context=chunks,
                )
            except Exception as e:
                app_logger.error(f"LLM 生成失败: {e}")
                degradation_reasons.append("llm_generation_failed")
                degradation_actions.append("returned_ranked_retrieval_excerpts")
                answer = "抱歉，AI 生成回答失败。以下是检索到的相关内容：\n\n" + "\n\n".join(
                    [f"[{i+1}] {c}" for i, c in enumerate(chunks[:3])]
                )
        else:
            answer = "以下是检索到的相关内容：\n\n" + "\n\n".join(
                [f"[{i+1}] {c}" for i, c in enumerate(chunks[:3])]
            )
        generation_latency_ms = (time.perf_counter() - generation_started_at) * 1000

        result = {
            "answer": answer,
            "chunks": merged_results,
            "citations": citations,
            "count": len(merged_results),
            "mode": self._retrieval_mode(),
            "query_type": "standard",
            "original_query": question,
            "rewritten_query": search_queries,
            "expanded_query_count": 1,
            "retrieval_strategy": "A",
            "retrieval_sources": sorted({source for r in merged_results for source in r.get("sources", [])}),
            "retrieval_stage_metrics": retrieval_stage_metrics,
            "retrieval_latency_ms": retrieval_latency_ms,
            "generation_latency_ms": generation_latency_ms,
            "total_latency_ms": (time.perf_counter() - started_at) * 1000,
            "degradation": {
                "applied": bool(degradation_reasons),
                "reasons": degradation_reasons,
                "actions": degradation_actions,
            },
            "provenance": {
                "citation_count": len(citations),
                "access_control_applied": access_context is not None,
            },
        }

        return RAGResult.model_validate(result).model_dump()
    
