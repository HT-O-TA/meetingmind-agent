"""BM25 检索器 - 用于多路召回"""
import math
from typing import List, Dict, Optional, Any
from collections import defaultdict

class BM25Retriever:
    """
    BM25 检索器实现
    
    BM25 (Best Matching 25) 是一种基于概率模型的信息检索算法，
    用于计算查询与文档之间的相关性分数。
    """
    
    def __init__(self, k1: float = 1.5, b: float = 0.75, epsilon: float = 0.25):
        """
        初始化 BM25 检索器
        
        Args:
            k1: 控制词频对分数的影响程度，通常在1.2-2.0之间
            b: 控制文档长度对分数的影响，通常在0.75左右
            epsilon: 平滑参数，防止零概率
        """
        self.k1 = k1
        self.b = b
        self.epsilon = epsilon
        
        # 文档数据
        self.documents = []  # 存储所有文档
        self.document_terms = []  # 每个文档的词项列表
        self.document_lengths = []  # 每个文档的长度
        self.average_document_length = 0.0
        
        # 全局词频统计
        self.total_terms = 0
        self.document_frequencies = defaultdict(int)  # 词项出现的文档数
        self.term_frequencies = []  # 每个文档的词频字典
    
    def _tokenize(self, text: str) -> List[str]:
        """
        中文文本分词，使用jieba
        
        Args:
            text: 输入文本
            
        Returns:
            分词后的词项列表
        """
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
        tokens = [token for token in tokens if token not in stop_words and len(token) > 1]
        return tokens
    
    def add_document(self, doc_id: int, content: str):
        """
        添加文档到检索器
        
        Args:
            doc_id: 文档ID
            content: 文档内容
        """
        terms = self._tokenize(content)
        self.documents.append({'id': doc_id, 'content': content})
        self.document_terms.append(terms)
        self.document_lengths.append(len(terms))
        
        # 更新词频统计
        term_freq = defaultdict(int)
        unique_terms = set()
        for term in terms:
            term_freq[term] += 1
            unique_terms.add(term)
        
        self.term_frequencies.append(term_freq)
        
        # 更新文档频率
        for term in unique_terms:
            self.document_frequencies[term] += 1
        
        self.total_terms += len(terms)
        self.average_document_length = self.total_terms / len(self.documents)
    
    def add_documents(self, documents: List[Dict[str, Any]]):
        """
        批量添加文档
        
        Args:
            documents: 文档列表，每个文档包含 'id' 和 'content'
        """
        for doc in documents:
            self.add_document(doc['id'], doc['content'])
    
    def _calculate_idf(self, term: str) -> float:
        """
        计算逆文档频率 (IDF)
        
        Args:
            term: 词项
            
        Returns:
            IDF 值
        """
        doc_count = len(self.documents)
        df = self.document_frequencies.get(term, 0)
        
        # 使用平滑的 IDF 计算
        return math.log((doc_count - df + 0.5) / (df + 0.5) + 1.0)
    
    def _calculate_term_score(self, term: str, doc_idx: int) -> float:
        """
        计算单个词项在文档中的分数
        
        Args:
            term: 词项
            doc_idx: 文档索引
            
        Returns:
            词项分数
        """
        tf = self.term_frequencies[doc_idx].get(term, 0)
        if tf == 0:
            return 0.0
        
        idf = self._calculate_idf(term)
        doc_len = self.document_lengths[doc_idx]
        
        # BM25 公式
        numerator = tf * (self.k1 + 1)
        denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.average_document_length)
        
        return idf * numerator / denominator
    
    def score_document(self, query: str, doc_idx: int) -> float:
        """
        计算查询与文档的相关性分数
        
        Args:
            query: 查询文本
            doc_idx: 文档索引
            
        Returns:
            BM25 分数
        """
        query_terms = self._tokenize(query)
        if not query_terms:
            return 0.0
        
        score = 0.0
        for term in query_terms:
            score += self._calculate_term_score(term, doc_idx)
        
        return score
    
    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        执行 BM25 检索
        
        Args:
            query: 查询文本
            top_k: 返回前k个结果
            
        Returns:
            检索结果列表，包含 doc_id, score, content
        """
        results = []
        
        for idx, doc in enumerate(self.documents):
            score = self.score_document(query, idx)
            if score > 0:
                results.append({
                    'doc_id': doc['id'],
                    'score': score,
                    'content': doc['content'][:200] + '...' if len(doc['content']) > 200 else doc['content']
                })
        
        # 按分数降序排序
        results.sort(key=lambda x: x['score'], reverse=True)
        
        return results[:top_k]
    
    def get_document_count(self) -> int:
        """获取文档数量"""
        return len(self.documents)
    
    def clear(self):
        """清空所有文档"""
        self.documents = []
        self.document_terms = []
        self.document_lengths = []
        self.average_document_length = 0.0
        self.total_terms = 0
        self.document_frequencies = defaultdict(int)
        self.term_frequencies = []


# 全局 BM25 检索器实例
_bm25_retriever = None

def get_bm25_retriever() -> BM25Retriever:
    """获取全局 BM25 检索器实例"""
    global _bm25_retriever
    if _bm25_retriever is None:
        _bm25_retriever = BM25Retriever(k1=1.5, b=0.75)
    return _bm25_retriever

def init_bm25_retriever(documents: List[Dict[str, Any]]):
    """初始化 BM25 检索器，添加所有文档"""
    retriever = get_bm25_retriever()
    retriever.clear()
    retriever.add_documents(documents)
    return retriever
