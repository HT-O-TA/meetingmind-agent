"""多路召回融合器 - BM25 + 向量检索 + 重排序"""
from typing import List, Dict, Any, Optional
from app.core.logger import app_logger
from app.core.config import settings

class MultiRetrievalFusion:
    """
    多路召回融合器
    
    实现 BM25 + 向量检索的多路召回策略，
    并通过重排序器进行精排，提升检索效果。
    """
    
    def __init__(self):
        self.bm25_weight = settings.BM25_WEIGHT
        self.vector_weight = settings.VECTOR_WEIGHT
        self.rerank_top_n = settings.RERANK_TOP_N
        
        # 延迟导入，避免循环依赖
        from app.services.bm25_retriever import get_bm25_retriever
        from app.services.reranker import get_reranker
        
        self.bm25_retriever = get_bm25_retriever()
        self.reranker = get_reranker()
    
    def _normalize_scores(self, results: List[Dict[str, Any]], max_score: float = None) -> List[Dict[str, Any]]:
        """
        归一化分数
        
        Args:
            results: 检索结果列表
            max_score: 最大分数（可选，用于归一化）
            
        Returns:
            归一化后的结果列表
        """
        if not results:
            return results
        
        if max_score is None:
            max_score = max(result.get('score', 0) for result in results)
        
        if max_score == 0:
            return results
        
        for result in results:
            result['normalized_score'] = result.get('score', 0) / max_score
        
        return results
    
    def _fuse_results(self, bm25_results: List[Dict[str, Any]], 
                      vector_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        融合 BM25 和向量检索结果
        
        Args:
            bm25_results: BM25 检索结果
            vector_results: 向量检索结果
            
        Returns:
            融合后的结果列表
        """
        # 归一化分数
        bm25_results = self._normalize_scores(bm25_results)
        vector_results = self._normalize_scores(vector_results)
        
        # 构建融合字典
        fused = {}
        
        # 添加 BM25 结果
        for result in bm25_results:
            doc_id = result.get('doc_id', result.get('document_id', result.get('chunk_id', 0)))
            if doc_id not in fused:
                fused[doc_id] = {
                    'doc_id': doc_id,
                    'bm25_score': result.get('normalized_score', 0) * self.bm25_weight,
                    'vector_score': 0,
                    'content': result.get('content', ''),
                    'sources': ['bm25']
                }
            else:
                fused[doc_id]['bm25_score'] = result.get('normalized_score', 0) * self.bm25_weight
                fused[doc_id]['sources'].append('bm25')
        
        # 添加向量检索结果
        for result in vector_results:
            doc_id = result.get('document_id', result.get('chunk_id', result.get('doc_id', 0)))
            if doc_id not in fused:
                fused[doc_id] = {
                    'doc_id': doc_id,
                    'bm25_score': 0,
                    'vector_score': result.get('normalized_score', 0) * self.vector_weight,
                    'content': result.get('content', result.get('chunk_text', '')),
                    'sources': ['vector']
                }
            else:
                fused[doc_id]['vector_score'] = result.get('normalized_score', 0) * self.vector_weight
                fused[doc_id]['sources'].append('vector')
        
        # 计算综合分数
        results = []
        for doc_id, data in fused.items():
            combined_score = data['bm25_score'] + data['vector_score']
            results.append({
                'doc_id': doc_id,
                'score': combined_score,
                'bm25_score': data['bm25_score'],
                'vector_score': data['vector_score'],
                'content': data['content'],
                'sources': data['sources'],
                **({k: v for k, v in data.items() if k not in ['doc_id', 'bm25_score', 'vector_score', 'content', 'sources', 'score']})
            })
        
        # 按综合分数降序排序
        results.sort(key=lambda x: x['score'], reverse=True)
        
        app_logger.debug(f"[Fusion] 融合完成，BM25: {len(bm25_results)} 条，向量: {len(vector_results)} 条，融合后: {len(results)} 条")
        
        return results
    
    async def retrieve(self, query: str, 
                      bm25_results: Optional[List[Dict[str, Any]]] = None,
                      vector_results: Optional[List[Dict[str, Any]]] = None,
                      top_k: int = 10) -> List[Dict[str, Any]]:
        """
        执行多路召回和融合
        
        Args:
            query: 查询文本
            bm25_results: 预计算的 BM25 结果（可选）
            vector_results: 预计算的向量检索结果（可选）
            top_k: 返回前k个结果
            
        Returns:
            重排序后的检索结果
        """
        # 如果没有提供预计算结果，执行 BM25 检索
        if bm25_results is None:
            bm25_results = await self.bm25_retriever.search(query, top_k=top_k * 2)
        
        # 如果没有提供向量结果，返回空列表（向量检索由外部传入）
        if vector_results is None:
            vector_results = []
        
        # 融合结果
        fused_results = self._fuse_results(bm25_results, vector_results)
        
        # 如果没有结果，直接返回
        if not fused_results:
            return []
        
        # 取前 N 个进行重排序
        candidates = fused_results[:self.rerank_top_n]
        
        # 执行重排序
        reranked_results = await self.reranker.arerank(query, candidates, top_n=top_k)
        
        app_logger.debug(f"[MultiRetrieval] 检索完成，最终返回 {len(reranked_results)} 条结果")
        
        return reranked_results
    
    def update_bm25_index(self, documents: List[Dict[str, Any]]):
        """
        更新 BM25 索引
        
        Args:
            documents: 文档列表，每个文档包含 'id' 和 'content'
        """
        from app.services.bm25_retriever import init_bm25_retriever
        init_bm25_retriever(documents)
        app_logger.info(f"[MultiRetrieval] BM25 索引已更新，共 {len(documents)} 个文档")


# 全局多路召回融合器实例
_multi_retrieval_fusion = None

def get_multi_retrieval_fusion() -> MultiRetrievalFusion:
    """获取全局多路召回融合器实例"""
    global _multi_retrieval_fusion
    if _multi_retrieval_fusion is None:
        _multi_retrieval_fusion = MultiRetrievalFusion()
    return _multi_retrieval_fusion
