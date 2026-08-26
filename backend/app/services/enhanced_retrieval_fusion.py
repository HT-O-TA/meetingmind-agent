"""正式 RAG 主链的 BM25 + Dense 加权融合与重排序。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.logger import app_logger


class EnhancedMultiRetrievalFusion:
    """保留原类名以兼容调用方；实现仅包含已评测的策略 A。"""

    def __init__(self, strategy: str = "A"):
        if strategy != "A":
            raise ValueError("正式检索链仅支持策略 A：BM25 + Dense + Reranker")
        self.strategy = "A"
        self.rerank_top_n = settings.RERANK_TOP_N
        self.bm25_weight = settings.BM25_WEIGHT
        self.vector_weight = settings.VECTOR_WEIGHT

        from app.services.bm25_retriever import get_bm25_retriever
        from app.services.reranker import get_reranker

        self.bm25_retriever = get_bm25_retriever()
        self.reranker = get_reranker()

    @staticmethod
    def _normalized_score(result: Dict[str, Any], maximum: float) -> float:
        raw = float(result.get("score", result.get("similarity", 0.0)) or 0.0)
        return raw / maximum if maximum > 0 else 0.0

    def _weighted_fusion(
        self,
        bm25_results: List[Dict[str, Any]],
        dense_results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        bm25_max = max(
            (float(item.get("score", item.get("similarity", 0.0)) or 0.0) for item in bm25_results),
            default=0.0,
        )
        dense_max = max(
            (float(item.get("score", item.get("similarity", 0.0)) or 0.0) for item in dense_results),
            default=0.0,
        )
        fused: Dict[Any, Dict[str, Any]] = {}

        for item in bm25_results:
            chunk_id = item.get("chunk_id", item.get("doc_id", item.get("document_id", 0)))
            text = item.get("chunk_text", item.get("content", ""))
            fused[chunk_id] = {
                "doc_id": chunk_id,
                "chunk_id": chunk_id,
                "document_id": item.get("document_id"),
                "score": self._normalized_score(item, bm25_max) * self.bm25_weight,
                "content": text,
                "chunk_text": text,
                "sources": ["bm25"],
            }

        for item in dense_results:
            chunk_id = item.get("chunk_id", item.get("doc_id", item.get("document_id", 0)))
            text = item.get("chunk_text", item.get("content", ""))
            contribution = self._normalized_score(item, dense_max) * self.vector_weight
            if chunk_id in fused:
                fused[chunk_id]["score"] += contribution
                fused[chunk_id]["sources"].append("dense")
                if text:
                    fused[chunk_id]["content"] = text
                    fused[chunk_id]["chunk_text"] = text
                fused[chunk_id]["document_id"] = item.get("document_id") or fused[chunk_id]["document_id"]
            else:
                fused[chunk_id] = {
                    "doc_id": chunk_id,
                    "chunk_id": chunk_id,
                    "document_id": item.get("document_id"),
                    "score": contribution,
                    "content": text,
                    "chunk_text": text,
                    "sources": ["dense"],
                }

        return sorted(fused.values(), key=lambda item: item["score"], reverse=True)

    async def retrieve(
        self,
        query: str,
        bm25_results: Optional[List[Dict[str, Any]]] = None,
        dense_results: Optional[List[Dict[str, Any]]] = None,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        if bm25_results is None:
            bm25_results = await self.bm25_retriever.search(query, top_k=top_k * 2)
        candidates = self._weighted_fusion(bm25_results, dense_results or [])
        results = await self.rerank_candidates(query, candidates, top_k)
        app_logger.debug(
            "[RetrievalFusion] BM25=%s Dense=%s Final=%s",
            len(bm25_results),
            len(dense_results or []),
            len(results),
        )
        return results

    async def rerank_candidates(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        pool = candidates[:max(top_k, self.rerank_top_n)]
        if not pool:
            return []
        return await self.reranker.arerank(query, pool, top_n=top_k)

    def get_strategy(self) -> str:
        return self.strategy


_enhanced_fusion: Optional[EnhancedMultiRetrievalFusion] = None


def get_enhanced_retrieval_fusion(strategy: str = "A") -> EnhancedMultiRetrievalFusion:
    global _enhanced_fusion
    if strategy != "A":
        raise ValueError("正式检索链仅支持策略 A")
    if _enhanced_fusion is None:
        _enhanced_fusion = EnhancedMultiRetrievalFusion()
    return _enhanced_fusion


def create_enhanced_retrieval_fusion(strategy: str = "A") -> EnhancedMultiRetrievalFusion:
    return EnhancedMultiRetrievalFusion(strategy=strategy)
