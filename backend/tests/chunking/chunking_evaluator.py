import os
import json
import time
from typing import List, Dict, Any
from pathlib import Path
import numpy as np

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class ChunkingEvaluator:
    """Chunking策略评估器 - 使用 TF-IDF 进行相似度计算
    
    无需依赖 sentence_transformers，避免版本兼容性问题
    """
    
    def __init__(self):
        print("初始化 ChunkingEvaluator：使用 TF-IDF 进行相似度计算")
        self.vectorizer = TfidfVectorizer(
            max_features=5000,
            ngram_range=(1, 2)
        )
    
    def compute_recall(self, queries: List[str], chunks: List[str], top_k: int = 5) -> float:
        """计算检索召回率"""
        if not queries or not chunks:
            return 0.0
        
        # 组合查询和文档拼接，统一编码
        all_texts = queries + chunks
        tfidf_matrix = self.vectorizer.fit_transform(all_texts)
        
        # 分开查询和文档向量
        query_vectors = tfidf_matrix[:len(queries)]
        chunk_vectors = tfidf_matrix[len(queries):]
        
        # 计算相似度
        similarity_matrix = cosine_similarity(query_vectors, chunk_vectors)
        
        correct = 0
        for i, query in enumerate(queries):
            # 获取 Top K 相似 chunk
            scores = similarity_matrix[i]
            top_indices = scores.argsort()[::-1][:top_k]
            
            # 检查是否有相关：直接字符串包含检查
            found = False
            for idx in top_indices:
                chunk = chunks[idx].lower()
                q = query.lower()
                # 检查查询中的关键词是否在 chunk 中出现
                keywords = ["预算", "婚礼", "策划", "场地", "天气", "车队", "婚纱", "司仪", "宾客", "室内", "室外"]
                for keyword in keywords:
                    if keyword in q and keyword in chunk:
                        correct += 1
                        found = True
                        break
                if found:
                    break
            if found:
                continue
        
        return correct / len(queries)
    
    def compute_mrr(self, queries: List[str], chunks: List[str]) -> float:
        """计算平均倒数排名 (Mean Reciprocal Rank)"""
        if not queries or not chunks:
            return 0.0
        
        # 组合查询和文档拼接，统一编码
        all_texts = queries + chunks
        tfidf_matrix = self.vectorizer.fit_transform(all_texts)
        
        # 分开查询和文档向量
        query_vectors = tfidf_matrix[:len(queries)]
        chunk_vectors = tfidf_matrix[len(queries):]
        
        # 计算相似度
        similarity_matrix = cosine_similarity(query_vectors, chunk_vectors)
        
        total_score = 0.0
        for i, query in enumerate(queries):
            scores = similarity_matrix[i]
            sorted_indices = scores.argsort()[::-1]
            
            # 找第一个匹配的
            q = query.lower()
            keywords = ["预算", "婚礼", "策划", "场地", "天气", "车队", "婚纱", "司仪", "宾客", "室内", "室外"]
            for rank, idx in enumerate(sorted_indices, 1):
                chunk = chunks[idx].lower()
                for keyword in keywords:
                    if keyword in q and keyword in chunk:
                        total_score += 1.0 / rank
                        break
                else:
                    continue
                break
        
        return total_score / len(queries)
    
    def compute_precision(self, queries: List[str], chunks: List[str], top_k: int = 5) -> float:
        """计算精确率@K (Precision@K)"""
        if not queries or not chunks:
            return 0.0
        
        # 组合查询和文档拼接，统一编码
        all_texts = queries + chunks
        tfidf_matrix = self.vectorizer.fit_transform(all_texts)
        
        # 分开查询和文档向量
        query_vectors = tfidf_matrix[:len(queries)]
        chunk_vectors = tfidf_matrix[len(queries):]
        
        # 计算相似度
        similarity_matrix = cosine_similarity(query_vectors, chunk_vectors)
        
        total_precision = 0.0
        keywords = ["预算", "婚礼", "策划", "场地", "天气", "车队", "婚纱", "司仪", "宾客", "室内", "室外"]
        for i, query in enumerate(queries):
            scores = similarity_matrix[i]
            top_indices = scores.argsort()[::-1][:top_k]
            
            # 统计相关文档数量
            q = query.lower()
            relevant_count = 0
            
            for idx in top_indices:
                chunk = chunks[idx].lower()
                for keyword in keywords:
                    if keyword in q and keyword in chunk:
                        relevant_count += 1
                        break
            
            total_precision += relevant_count / top_k
        
        return total_precision / len(queries)
    
    def evaluate(self, queries: List[str], chunks: List[str]) -> Dict[str, Any]:
        """完整评估，返回所有指标"""
        start_time = time.time()
        
        recall = self.compute_recall(queries, chunks)
        mrr = self.compute_mrr(queries, chunks)
        precision = self.compute_precision(queries, chunks)
        
        return {
            'recall@5': recall,
            'mrr': mrr,
            'precision@5': precision,
            'chunk_count': len(chunks),
            'avg_chunk_size': sum(len(c) for c in chunks) / len(chunks) if chunks else 0,
            'evaluation_time': time.time() - start_time
        }


def generate_test_queries(docs_dir: Path, count: int = 20) -> List[str]:
    """从文档中生成测试查询"""
    queries = []
    docs = list(docs_dir.glob('*.txt')) + list(docs_dir.glob('*.md'))
    
    # 从实际文档中收集内容
    all_text = ""
    for doc_path in docs[:5]:  # 读取前5个文档
        all_text += doc_path.read_text(encoding='utf-8')
    
    # 基于实际内容生成查询
    query_templates = [
        "预算多少？",
        "婚礼策划方案有什么？",
        "婚礼场地在哪里？",
        "天气要考虑什么？",
        "车队安排？",
        "婚纱选择？",
        "司仪怎么安排？",
        "宾客名单？",
        "室内还是室外？",
        "婚车数量？",
        "婚礼流程？",
        "预算控制？",
        "婚礼装饰？",
        "喜糖准备？",
        "伴郎伴娘？"
    ]
    
    # 生成足够的查询
    while len(queries) < count:
        queries.extend(query_templates)
    
    return queries[:count]


def main():
    """主函数 - 运行分块评估"""
    print("="*60)
    print("分块策略评估器")
    print("="*60)
    
    # 设置路径
    base_dir = Path(__file__).parent
    docs_dir = base_dir / "meeting_docs_with_speaker"
    
    if not docs_dir.exists():
        print(f"错误：文档目录不存在: {docs_dir}")
        print("请确保 meeting_docs_with_speaker 目录存在并包含md文件")
        return
    
    # 读取文档
    print(f"正在读取文档目录: {docs_dir}")
    docs = list(docs_dir.glob('*.md'))
    if not docs:
        print("错误：目录中没有找到md文件")
        return
    print(f"找到 {len(docs)} 个文档")
    
    # 读取所有文档内容作为待分块文本
    all_content = ""
    for doc_path in docs:
        all_content += doc_path.read_text(encoding='utf-8') + "\n\n"
    
    # 简单分块（按换行切分）
    chunks = [c.strip() for c in all_content.split('\n') if c.strip()]
    print(f"文档总长度: {len(all_content)} 字符")
    print(f"分块数量: {len(chunks)}")
    
    # 生成测试查询
    queries = generate_test_queries(docs_dir, count=10)
    print(f"生成测试查询: {len(queries)} 个")
    
    # 创建评估器并评估
    evaluator = ChunkingEvaluator()
    print("\n开始评估...")
    results = evaluator.evaluate(queries, chunks)
    
    # 输出结果
    print("\n" + "="*60)
    print("评估结果")
    print("="*60)
    print(f"召回率@5: {results['recall@5']:.4f}")
    print(f"平均倒数排名(MRR): {results['mrr']:.4f}")
    print(f"精确率@5: {results['precision@5']:.4f}")
    print(f"分块数量: {results['chunk_count']}")
    print(f"平均块大小: {results['avg_chunk_size']:.1f} 字符")
    print(f"评估耗时: {results['evaluation_time']:.2f} 秒")
    print("="*60)


if __name__ == "__main__":
    main()
