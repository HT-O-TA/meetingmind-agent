"""增强版多路召回融合器 - BM25 + Milvus混合检索 + Reranker"""
from typing import List, Dict, Any, Optional, Literal
from app.core.logger import app_logger
from app.core.config import settings

class EnhancedMultiRetrievalFusion:
    """
    增强版多路召回融合器
    
    支持三种策略：
    - 策略A（当前）：BM25 + dense向量 + 加权融合
    - 策略B（目标）：BM25 + dense向量 + sparse向量 + RRF融合（PostgreSQL回退）
    - 策略M（Milvus）：PostgreSQL BM25 + Milvus Dense+Sparse混合检索 + 加权融合
    
    策略M说明：
    - Milvus 内部使用 WeightedRanker 完成 Dense + Sparse 融合
    - 只需要将 PostgreSQL BM25 结果与 Milvus 结果进行融合
    """
    
    # 类级别的模型缓存
    _model_cache: Dict[str, Any] = {}
    
    def __init__(self, strategy: Literal['A', 'B', 'M'] = 'A'):
        self.strategy = strategy
        self.rrf_k = settings.RRF_K if hasattr(settings, 'RRF_K') else 60
        self.rerank_top_n = settings.RERANK_TOP_N
        self.bm25_weight = settings.BM25_WEIGHT
        self.vector_weight = settings.VECTOR_WEIGHT
        
        self.local_model_path = settings.LOCAL_EMBEDDING_MODEL_PATH
        
        from app.services.bm25_retriever import get_bm25_retriever
        from app.services.reranker import get_reranker
        
        self.bm25_retriever = get_bm25_retriever()
        self.reranker = get_reranker()
        
        app_logger.info(f"[EnhancedFusion] 初始化完成，策略: {strategy}")
    
    def _extract_sparse_vector(self, sparse_vec) -> Dict[int, float]:
        """
        从稀疏向量中提取索引-权重字典
        
        Args:
            sparse_vec: 稀疏向量（可能是scipy.sparse.csr_matrix或字典）
            
        Returns:
            索引-权重字典
        """
        if sparse_vec is None:
            return {}
        
        try:
            # 处理scipy.sparse.csr_matrix格式
            import scipy.sparse
            if isinstance(sparse_vec, scipy.sparse.csr_matrix):
                indices = sparse_vec.indices
                values = sparse_vec.data
                return dict(zip(indices.tolist(), values.tolist()))
            # 处理numpy数组
            elif hasattr(sparse_vec, 'tolist'):
                vec_list = sparse_vec.tolist()
                return {i: v for i, v in enumerate(vec_list) if v > 0}
            # 处理字典
            elif isinstance(sparse_vec, dict):
                return sparse_vec
            else:
                return {}
        except Exception as e:
            app_logger.warning(f"[EnhancedFusion] 解析稀疏向量失败: {e}")
            return {}
    
    def _convert_lexical_weights(self, lexical_weights) -> Dict[int, float]:
        """
        将BGE-M3的lexical_weights转换为稀疏向量格式
        
        Args:
            lexical_weights: BGE-M3返回的词权重，格式为 defaultdict
                             例如: {'6': np.float32(0.3358), '49125': np.float32(0.1982), ...}
            
        Returns:
            token哈希到权重的映射
        """
        sparse_vec = {}
        
        try:
            # lexical_weights 是 defaultdict，键是token_id字符串，值是numpy.float32
            if isinstance(lexical_weights, dict):
                for token_id, weight in lexical_weights.items():
                    if isinstance(token_id, str):
                        # 检查权重是否为数值类型（包括numpy类型）
                        if isinstance(weight, (int, float)) or hasattr(weight, 'dtype'):
                            # 使用token_id的哈希作为索引
                            idx = hash(token_id) % 100000
                            weight_value = float(weight)
                            if idx in sparse_vec:
                                sparse_vec[idx] = max(sparse_vec[idx], weight_value)
                            else:
                                sparse_vec[idx] = weight_value
        except Exception as e:
            app_logger.warning(f"[EnhancedFusion] 转换lexical_weights失败: {e}")
        
        return sparse_vec
    
    def _sparse_similarity(self, query_sparse: Dict[int, float], doc_sparse: Dict[int, float]) -> float:
        """
        计算两个稀疏向量的相似度（内积）
        
        Args:
            query_sparse: 查询稀疏向量
            doc_sparse: 文档稀疏向量
            
        Returns:
            相似度分数
        """
        if not query_sparse or not doc_sparse:
            return 0.0
        
        # 计算内积
        score = 0.0
        for idx, weight in query_sparse.items():
            if idx in doc_sparse:
                score += weight * doc_sparse[idx]
        
        return score
    
    def _build_tfidf_index(self, documents: List[Dict[str, Any]]) -> Dict[int, Dict[int, float]]:
        """
        使用TF-IDF构建稀疏索引（备用方案）
        
        Args:
            documents: 文档列表
            
        Returns:
            文档ID到稀疏向量的映射
        """
        sparse_index = {}
        
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            
            contents = [doc.get('content', '') for doc in documents]
            doc_ids = [doc['id'] for doc in documents]
            
            # 使用TF-IDF向量化
            vectorizer = TfidfVectorizer(
                tokenizer=self._tokenize,
                max_features=10000,
                ngram_range=(1, 2)
            )
            
            tfidf_matrix = vectorizer.fit_transform(contents)
            
            # 转换为稀疏向量格式
            for idx, doc_id in enumerate(doc_ids):
                row = tfidf_matrix[idx]
                sparse_vec = {}
                for jdx in row.indices:
                    sparse_vec[jdx] = float(row[jdx])
                sparse_index[doc_id] = sparse_vec
            
            app_logger.info(f"[EnhancedFusion] 使用TF-IDF构建稀疏索引，文档数: {len(sparse_index)}")
            
        except Exception as e:
            app_logger.warning(f"[EnhancedFusion] TF-IDF构建稀疏索引失败: {e}")
            # 返回空索引
            sparse_index = {}
        
        return sparse_index
    
    def _build_sparse_index(self, documents: List[Dict[str, Any]]) -> Dict[int, Dict[int, float]]:
        """
        使用BGE-M3构建稀疏索引（优先），失败时使用TF-IDF备用
        
        Args:
            documents: 文档列表
            
        Returns:
            文档ID到稀疏向量的映射
        """
        # 优先尝试使用BGE-M3
        try:
            from FlagEmbedding import BGEM3FlagModel
            
            # 使用模型缓存
            cache_key = self.local_model_path
            if cache_key not in EnhancedMultiRetrievalFusion._model_cache:
                app_logger.info(f"[EnhancedFusion] 加载本地BGE-M3模型: {self.local_model_path}")
                try:
                    from FlagEmbedding import BGEM3FlagModel
                    model_instance = BGEM3FlagModel(cache_key, use_fp16=True)
                except ImportError as e:
                    app_logger.warning(f"[EnhancedFusion] FlagEmbedding不可用: {e}")
                    raise
                except Exception as e:
                    app_logger.warning(f"[EnhancedFusion] GPU模式失败，尝试CPU: {e}")
                    try:
                        model_instance = BGEM3FlagModel(cache_key, use_fp16=False, device='cpu')
                    except Exception as e2:
                        app_logger.error(f"[EnhancedFusion] CPU模式也失败: {e2}")
                        raise
                EnhancedMultiRetrievalFusion._model_cache[cache_key] = model_instance
            
            model = EnhancedMultiRetrievalFusion._model_cache[cache_key]
            
            # 获取所有文档内容
            contents = [doc.get('content', '') for doc in documents]
            
            # 使用BGE-M3编码
            results = model.encode(contents, return_dense=False, return_sparse=True)
            
            # 构建稀疏索引
            sparse_index = {}
            for doc_idx, doc in enumerate(documents):
                lexical_weights = results['lexical_weights'][doc_idx]
                sparse_vec = self._convert_lexical_weights(lexical_weights)
                sparse_index[doc['id']] = sparse_vec
            
            app_logger.info(f"[EnhancedFusion] 使用BGE-M3构建稀疏索引，文档数: {len(sparse_index)}")
            return sparse_index
            
        except Exception as e:
            app_logger.warning(f"[EnhancedFusion] BGE-M3构建稀疏索引失败，使用TF-IDF备用: {e}")
            return self._build_tfidf_index(documents)
    
    def _tokenize(self, text: str) -> List[str]:
        """中文分词，使用jieba"""
        import re
        try:
            import jieba
            # 使用jieba进行中文分词
            tokens = jieba.lcut(text.lower())
        except ImportError:
            # 如果没有jieba，使用简单分词
            text = re.sub(r'[^\w\s]', ' ', text.lower())
            tokens = text.split()
        
        # 过滤停用词和单字
        stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
                      'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
                      'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
                      'ought', 'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by',
                      'from', 'as', 'into', 'through', 'during', 'before', 'after',
                      'above', 'below', 'between', 'under', 'again', 'further', 'then',
                      'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all',
                      'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no',
                      'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very',
                      'just', 'but', 'if', 'or', 'because', 'until', 'while', 'this',
                      'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they'}
        return [token for token in tokens if token not in stop_words and len(token) > 1]
    
    def _sparse_search(self, query: str, sparse_index: Dict[int, Dict[int, float]], top_k: int = 10) -> List[Dict[str, Any]]:
        """
        执行稀疏向量检索
        
        Args:
            query: 查询文本
            sparse_index: 稀疏索引
            top_k: 返回数量
            
        Returns:
            检索结果列表
        """
        if not sparse_index:
            return []
        
        # 获取查询的稀疏向量
        try:
            from FlagEmbedding import BGEM3FlagModel
            
            # 使用模型缓存，避免重复加载
            cache_key = self.local_model_path
            if cache_key not in EnhancedMultiRetrievalFusion._model_cache:
                app_logger.info(f"[EnhancedFusion] 加载本地BGE-M3模型: {self.local_model_path}")
                try:
                    # 尝试GPU模式
                    model_instance = BGEM3FlagModel(self.local_model_path, use_fp16=True)
                except Exception as e:
                    app_logger.warning(f"[EnhancedFusion] GPU模式加载失败，尝试CPU模式: {e}")
                    try:
                        # 尝试CPU模式
                        model_instance = BGEM3FlagModel(self.local_model_path, use_fp16=False, device='cpu')
                        app_logger.info(f"[EnhancedFusion] CPU模式加载成功")
                    except Exception as e2:
                        app_logger.error(f"[EnhancedFusion] CPU模式也加载失败: {e2}")
                        raise
                
                EnhancedMultiRetrievalFusion._model_cache[cache_key] = model_instance
            
            model = EnhancedMultiRetrievalFusion._model_cache[cache_key]
            results = model.encode(
                [query],
                return_dense=False,
                return_sparse=True,
                return_colbert_vecs=False
            )
            # 使用lexical_weights字段
            query_sparse = self._convert_lexical_weights(results['lexical_weights'][0])
        except Exception as e:
            app_logger.warning(f"[EnhancedFusion] 获取查询稀疏向量失败，使用TF-IDF: {e}")
            # 使用TF-IDF作为备用
            query_terms = self._tokenize(query)
            query_sparse = {hash(term) % 100000: 1.0 for term in query_terms}
        
        # 计算相似度
        results = []
        for doc_id, doc_sparse in sparse_index.items():
            similarity = self._sparse_similarity(query_sparse, doc_sparse)
            if similarity > 0:
                results.append({
                    'doc_id': doc_id,
                    'score': similarity,
                    'source': 'sparse'
                })
        
        # 按分数排序
        results.sort(key=lambda x: x['score'], reverse=True)
        
        return results[:top_k]
    
    def _rerank_with_scores(self, results: List[Dict[str, Any]]) -> List[Dict[str, int]]:
        """
        为结果列表添加排名
        
        Args:
            results: 检索结果列表（已按分数排序）
            
        Returns:
            添加了排名的结果列表
        """
        for idx, result in enumerate(results):
            result['rank'] = idx + 1  # 排名从1开始
        return results
    
    def _rrf_fusion(self, 
                     bm25_results: List[Dict[str, Any]],
                     dense_results: List[Dict[str, Any]],
                     sparse_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        使用RRF（Reciprocal Rank Fusion）融合多路召回结果
        
        Args:
            bm25_results: BM25检索结果（已排序）
            dense_results: 稠密向量检索结果（已排序）
            sparse_results: 稀疏向量检索结果（已排序）
            
        Returns:
            融合后的结果列表
        """
        # 添加排名
        bm25_results = self._rerank_with_scores(bm25_results)
        dense_results = self._rerank_with_scores(dense_results)
        sparse_results = self._rerank_with_scores(sparse_results)
        
        # 构建融合字典
        fused = {}
        
        # BM25结果
        for result in bm25_results:
            doc_id = result.get('doc_id', result.get('document_id', result.get('chunk_id', 0)))
            rank = result.get('rank', 1)
            rrf_score = 1.0 / (self.rrf_k + rank)
            
            if doc_id not in fused:
                fused[doc_id] = {
                    'doc_id': doc_id,
                    'rrf_score': rrf_score,
                    'bm25_rank': rank,
                    'dense_rank': None,
                    'sparse_rank': None,
                    'content': result.get('content', ''),
                    'sources': ['bm25']
                }
            else:
                fused[doc_id]['rrf_score'] += rrf_score
                fused[doc_id]['bm25_rank'] = rank
                fused[doc_id]['sources'].append('bm25')
        
        # 稠密向量结果
        for result in dense_results:
            doc_id = result.get('doc_id', result.get('document_id', result.get('chunk_id', 0)))
            rank = result.get('rank', 1)
            rrf_score = 1.0 / (self.rrf_k + rank)
            
            if doc_id not in fused:
                fused[doc_id] = {
                    'doc_id': doc_id,
                    'rrf_score': rrf_score,
                    'bm25_rank': None,
                    'dense_rank': rank,
                    'sparse_rank': None,
                    'content': result.get('content', result.get('chunk_text', '')),
                    'sources': ['dense']
                }
            else:
                fused[doc_id]['rrf_score'] += rrf_score
                fused[doc_id]['dense_rank'] = rank
                fused[doc_id]['sources'].append('dense')
        
        # 稀疏向量结果（策略B时）
        if self.strategy == 'B':
            for result in sparse_results:
                doc_id = result.get('doc_id', result.get('document_id', result.get('chunk_id', 0)))
                rank = result.get('rank', 1)
                rrf_score = 1.0 / (self.rrf_k + rank)
                
                if doc_id not in fused:
                    fused[doc_id] = {
                        'doc_id': doc_id,
                        'rrf_score': rrf_score,
                        'bm25_rank': None,
                        'dense_rank': None,
                        'sparse_rank': rank,
                        'content': result.get('content', ''),
                        'sources': ['sparse']
                    }
                else:
                    fused[doc_id]['rrf_score'] += rrf_score
                    fused[doc_id]['sparse_rank'] = rank
                    fused[doc_id]['sources'].append('sparse')
        
        # 转换为列表并按RRF分数排序
        results = list(fused.values())
        results.sort(key=lambda x: x['rrf_score'], reverse=True)
        
        app_logger.debug(f"[EnhancedFusion] RRF融合完成，BM25: {len(bm25_results)} 条，dense: {len(dense_results)} 条，sparse: {len(sparse_results)} 条，融合后: {len(results)} 条")
        
        return results
    
    def _weighted_fusion(self,
                         bm25_results: List[Dict[str, Any]],
                         dense_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        使用加权融合（策略A）
        
        Args:
            bm25_results: BM25检索结果
            dense_results: 稠密向量检索结果
            
        Returns:
            融合后的结果列表
        """
        bm25_weight = settings.BM25_WEIGHT
        vector_weight = settings.VECTOR_WEIGHT
        
        # 归一化分数
        def normalize_scores(results):
            if not results:
                return results
            max_score = max(r.get('score', r.get('similarity', 0)) for r in results)
            if max_score == 0:
                return results
            for r in results:
                score = r.get('score', r.get('similarity', 0))
                r['normalized_score'] = score / max_score
            return results
        
        bm25_results = normalize_scores(bm25_results)
        dense_results = normalize_scores(dense_results)
        
        # 融合
        fused = {}
        
        for result in bm25_results:
            doc_id = result.get('chunk_id', result.get('doc_id', result.get('document_id', 0)))
            fused[doc_id] = {
                'doc_id': doc_id,
                'chunk_id': result.get('chunk_id', doc_id),
                'document_id': result.get('document_id'),
                'score': result.get('normalized_score', 0) * bm25_weight,
                'content': result.get('content', ''),
                'chunk_text': result.get('chunk_text', result.get('content', '')),
                'sources': ['bm25']
            }
        
        for result in dense_results:
            doc_id = result.get('chunk_id', result.get('doc_id', result.get('document_id', 0)))
            if doc_id in fused:
                fused[doc_id]['score'] += result.get('normalized_score', 0) * vector_weight
                fused[doc_id]['sources'].append('dense')
                # Dense 结果来自 PostgreSQL 正文回查，优先保留完整文本，
                # 避免 BM25 的展示片段覆盖 LLM/Reranker 所需的完整上下文。
                dense_text = result.get('chunk_text', result.get('content', ''))
                if dense_text:
                    fused[doc_id]['chunk_text'] = dense_text
                    fused[doc_id]['content'] = dense_text
            else:
                fused[doc_id] = {
                    'doc_id': doc_id,
                    'chunk_id': result.get('chunk_id', doc_id),
                    'document_id': result.get('document_id'),
                    'score': result.get('normalized_score', 0) * vector_weight,
                    'content': result.get('content', result.get('chunk_text', '')),
                    'chunk_text': result.get('chunk_text', result.get('content', '')),
                    'sources': ['dense']
                }
        
        results = list(fused.values())
        results.sort(key=lambda x: x['score'], reverse=True)
        
        return results
    
    async def retrieve(self, 
                       query: str,
                       bm25_results: Optional[List[Dict[str, Any]]] = None,
                       dense_results: Optional[List[Dict[str, Any]]] = None,
                       sparse_results: Optional[List[Dict[str, Any]]] = None,
                       sparse_index: Optional[Dict[int, Dict[int, float]]] = None,
                       milvus_results: Optional[List[Dict[str, Any]]] = None,
                       top_k: int = 10) -> List[Dict[str, Any]]:
        """
        执行多路召回和融合
        
        Args:
            query: 查询文本
            bm25_results: 预计算的BM25结果（可选）
            dense_results: 预计算的稠密向量结果（可选）
            sparse_results: 预计算的稀疏向量结果（可选）
            sparse_index: 稀疏向量索引（可选，策略B时需要）
            milvus_results: 预计算的Milvus混合检索结果（可选，策略M时需要）
            top_k: 返回前k个结果
            
        Returns:
            重排序后的检索结果
        """
        # 策略M：Milvus模式
        if self.strategy == 'M':
            return await self._retrieve_milvus_mode(query, bm25_results, milvus_results, top_k)
        
        # 策略A/B：传统模式
        if bm25_results is None:
            bm25_results = await self.bm25_retriever.search(query, top_k=top_k * 2)
        
        if dense_results is None:
            dense_results = []
        
        if self.strategy == 'B' and sparse_results is None:
            if sparse_index is not None:
                sparse_results = self._sparse_search(query, sparse_index, top_k=top_k * 2)
            else:
                sparse_results = []
        
        if self.strategy == 'B':
            fused_results = self._rrf_fusion(bm25_results, dense_results, sparse_results)
        else:
            fused_results = self._weighted_fusion(bm25_results, dense_results)
        
        if not fused_results:
            return []
        
        reranked_results = await self.rerank_candidates(query, fused_results, top_k)
        
        app_logger.debug(f"[EnhancedFusion] 检索完成（策略{self.strategy}），最终返回 {len(reranked_results)} 条结果")
        
        return reranked_results

    async def rerank_candidates(self, query: str, candidates: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        """统一 Reranker 入口，供 KG 在精排前扩展候选。"""
        # 候选池至少覆盖调用方要求的输出数量；RERANK_TOP_N 是默认池深度，
        # 不能把合法的 top_k 请求静默截断为更小的结果集。
        candidates = candidates[:max(top_k, self.rerank_top_n)]
        if not candidates:
            return []
        return await self.reranker.arerank(query, candidates, top_n=top_k)
    
    async def _retrieve_milvus_mode(self, 
                                   query: str,
                                   bm25_results: Optional[List[Dict[str, Any]]] = None,
                                   milvus_results: Optional[List[Dict[str, Any]]] = None,
                                   top_k: int = 10) -> List[Dict[str, Any]]:
        """
        Milvus模式检索：PostgreSQL BM25 + Milvus Dense+Sparse混合检索
        
        Args:
            query: 查询文本
            bm25_results: 预计算的BM25结果
            milvus_results: 预计算的Milvus结果
            top_k: 返回前k个结果
            
        Returns:
            重排序后的检索结果
        """
        if bm25_results is None:
            bm25_results = await self.bm25_retriever.search(query, top_k=top_k * 2)
        
        if milvus_results is None:
            try:
                from app.services.vector_store_milvus import get_milvus_vector_store
                milvus_store = get_milvus_vector_store()
                if milvus_store is None:
                    raise Exception("Milvus store not available")
                milvus_results = await milvus_store.search(
                    query=query,
                    top_k=top_k * 2,
                    dense_weight=self.vector_weight,
                    sparse_weight=self.bm25_weight,
                )
            except Exception as e:
                app_logger.warning(f"Milvus检索失败: {e}")
                milvus_results = []
        
        fused_results = self._weighted_fusion(bm25_results, milvus_results)
        
        if not fused_results:
            return []
        
        candidates = fused_results[:self.rerank_top_n]
        reranked_results = await self.reranker.arerank(query, candidates, top_n=top_k)
        
        app_logger.debug(f"[EnhancedFusion] Milvus模式检索完成，BM25: {len(bm25_results)} 条，Milvus: {len(milvus_results)} 条，最终返回 {len(reranked_results)} 条结果")
        
        return reranked_results
    
    def set_strategy(self, strategy: Literal['A', 'B']):
        """
        设置当前策略
        
        Args:
            strategy: 'A' 或 'B'
        """
        self.strategy = strategy
        app_logger.info(f"[EnhancedFusion] 策略已切换为: {strategy}")
    
    def get_strategy(self) -> str:
        """获取当前策略"""
        return self.strategy


# 全局增强版多路召回融合器实例
_enhanced_fusion = None

def get_enhanced_retrieval_fusion(strategy: Literal['A', 'B'] = 'A') -> EnhancedMultiRetrievalFusion:
    """获取全局增强版多路召回融合器实例"""
    global _enhanced_fusion
    if _enhanced_fusion is None:
        _enhanced_fusion = EnhancedMultiRetrievalFusion(strategy=strategy)
    return _enhanced_fusion

def create_enhanced_retrieval_fusion(strategy: Literal['A', 'B'] = 'A') -> EnhancedMultiRetrievalFusion:
    """创建新的增强版多路召回融合器实例"""
    return EnhancedMultiRetrievalFusion(strategy=strategy)
