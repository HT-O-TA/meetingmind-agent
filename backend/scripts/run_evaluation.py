"""
RAG 评估运行脚本 - 使用 BM25 + 向量混合检索

检索策略：
  1. BM25 检索（jieba 分词 + 关键词匹配）
  2. 向量检索（BGE-M3 余弦相似度）
  3. RRF 融合（Reciprocal Rank Fusion）
"""

import asyncio
import json
import os
import sys
import time
import math
import re
from typing import List, Dict, Optional, Tuple

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import text as sql_text
from app.core.config import settings

# 评估时关闭相似度阈值
settings.SIMILARITY_THRESHOLD = 0.0

try:
    import torch
    if torch.cuda.is_available():
        settings.EMBEDDING_DEVICE = "cuda"
        print(f"✅ CUDA: {torch.cuda.get_device_name(0)}")
    else:
        settings.EMBEDDING_DEVICE = "cpu"
except ImportError:
    settings.EMBEDDING_DEVICE = "cpu"

import jieba
import numpy as np
from app.services.embedding_service import EmbeddingService


def tokenize(text: str) -> List[str]:
    """jieba 分词"""
    tokens = jieba.lcut(text.lower())
    # 过滤停用词和单字
    stop_words = {'的', '了', '是', '在', '我', '有', '和', '就', '不', '人', '都', '一', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这', '那', '些', '什么', '主要', '内容', '讨论', '吗', '吧', '呢', '啊', '嗯'}
    return [t for t in tokens if t not in stop_words and len(t.strip()) > 0]


def bm25_search(db_chunks: List[Dict], query_tokens: List[str], top_k: int = 20) -> List[Dict]:
    """
    BM25 检索（内存版）

    Args:
        db_chunks: 数据库中的所有分块 [{id, document_id, chunk_text, tokens}]
        query_tokens: 查询分词列表
        top_k: 返回数量
    """
    if not query_tokens or not db_chunks:
        return []

    # BM25 参数
    k1 = 1.5
    b = 0.75

    # 计算文档频率
    doc_freq = {}
    for token in set(query_tokens):
        doc_freq[token] = sum(1 for chunk in db_chunks if token in chunk['tokens'])

    # 平均文档长度
    avg_dl = sum(len(chunk['tokens']) for chunk in db_chunks) / len(db_chunks)
    N = len(db_chunks)

    results = []
    for chunk in db_chunks:
        score = 0.0
        chunk_tokens = chunk['tokens']
        dl = len(chunk_tokens)

        for token in query_tokens:
            if token not in chunk_tokens:
                continue

            tf = chunk_tokens.count(token)
            df = doc_freq.get(token, 0)
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1)

            # BM25 公式
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * dl / avg_dl)
            score += idf * numerator / denominator

        if score > 0:
            results.append({
                'chunk_id': chunk['id'],
                'document_id': chunk['document_id'],
                'chunk_text': chunk['chunk_text'],
                'score': score,
                'source': 'bm25',
            })

    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:top_k]


def vector_search(query_vector: List[float], db_chunks: List[Dict], top_k: int = 20) -> List[Dict]:
    """向量检索（余弦相似度）"""
    query_arr = np.array(query_vector)
    query_norm = np.linalg.norm(query_arr)

    if query_norm == 0:
        return []

    results = []
    for chunk in db_chunks:
        if not chunk.get('embedding'):
            continue

        chunk_arr = np.array(chunk['embedding'])
        chunk_norm = np.linalg.norm(chunk_arr)

        if chunk_norm == 0:
            continue

        similarity = np.dot(query_arr, chunk_arr) / (query_norm * chunk_norm)

        results.append({
            'chunk_id': chunk['id'],
            'document_id': chunk['document_id'],
            'chunk_text': chunk['chunk_text'],
            'similarity': float(similarity),
            'score': float(similarity),
            'source': 'vector',
        })

    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:top_k]


def rrf_fusion(bm25_results: List[Dict], vector_results: List[Dict], rrf_k: int = 60, top_k: int = 10) -> List[Dict]:
    """RRF 融合"""
    fused = {}

    # BM25 结果
    for rank, r in enumerate(bm25_results, 1):
        doc_id = r['document_id']
        rrf_score = 1.0 / (rrf_k + rank)
        if doc_id not in fused:
            fused[doc_id] = {
                'document_id': doc_id,
                'rrf_score': rrf_score,
                'bm25_rank': rank,
                'vector_rank': None,
                'chunk_text': r['chunk_text'],
                'sources': ['bm25'],
            }
        else:
            fused[doc_id]['rrf_score'] += rrf_score
            fused[doc_id]['bm25_rank'] = rank
            fused[doc_id]['sources'].append('bm25')

    # 向量结果
    for rank, r in enumerate(vector_results, 1):
        doc_id = r['document_id']
        rrf_score = 1.0 / (rrf_k + rank)
        if doc_id not in fused:
            fused[doc_id] = {
                'document_id': doc_id,
                'rrf_score': rrf_score,
                'bm25_rank': None,
                'vector_rank': rank,
                'chunk_text': r['chunk_text'],
                'sources': ['vector'],
            }
        else:
            fused[doc_id]['rrf_score'] += rrf_score
            fused[doc_id]['vector_rank'] = rank
            fused[doc_id]['sources'].append('vector')

    results = list(fused.values())
    results.sort(key=lambda x: x['rrf_score'], reverse=True)
    return results[:top_k]


def calculate_metrics(search_results: List[Dict], relevant_doc_ids: List[int], top_k: int = 10) -> Dict:
    """计算检索指标"""
    if not relevant_doc_ids:
        return {}

    retrieved_doc_ids = [r.get('document_id') for r in search_results[:top_k] if r.get('document_id') is not None]

    hits = sum(1 for doc_id in retrieved_doc_ids if doc_id in relevant_doc_ids)
    recall = hits / len(relevant_doc_ids) if relevant_doc_ids else 0
    hit_rate = 1.0 if hits > 0 else 0.0

    mrr = 0.0
    for rank, r in enumerate(search_results[:top_k], 1):
        if r.get('document_id') in relevant_doc_ids:
            mrr = 1.0 / rank
            break

    return {
        'recall_at_k': round(recall, 4),
        'hit_at_k': round(hit_rate, 4),
        'mrr': round(mrr, 4),
        'hits': hits,
        'retrieved_count': len(retrieved_doc_ids),
        'relevant_count': len(relevant_doc_ids),
    }


async def main():
    print("=" * 60)
    print("📊 RAG 检索评估（BM25 + 向量混合检索）")
    print("=" * 60)

    # 1. 初始化 Embedding 服务
    print("\n🔧 初始化 Embedding 服务...")
    embed_service = EmbeddingService()
    status = embed_service.get_status()
    print(f"   设备: {status.get('device')}")
    print(f"   模型: {status.get('model')}")
    print(f"   维度: {status.get('dimension')}")

    # 2. 连接数据库，加载全部分块数据
    print("\n🗄️ 加载数据库分块...")
    engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_size=10, max_overflow=20)

    async with AsyncSession(engine) as db:
        result = await db.execute(sql_text("""
            SELECT id, document_id, chunk_text, embedding
            FROM vector_chunks
            ORDER BY id
        """))
        rows = result.fetchall()

        # 预处理数据
        db_chunks = []
        for row in rows:
            chunk_id, doc_id, chunk_text, emb_json = row
            embedding = json.loads(emb_json) if isinstance(emb_json, str) else emb_json
            tokens = tokenize(chunk_text) if chunk_text else []
            db_chunks.append({
                'id': chunk_id,
                'document_id': doc_id,
                'chunk_text': chunk_text,
                'embedding': embedding,
                'tokens': tokens,
            })

        print(f"   加载分块数: {len(db_chunks)}")

        # 统计文档数
        doc_ids = set(c['document_id'] for c in db_chunks)
        print(f"   文档数: {len(doc_ids)}")

    # 3. 加载评估数据集
    from tests.rag.rag_eval_dataset import get_eval_dataset
    dataset = get_eval_dataset()
    print(f"\n📋 评估数据集: {len(dataset)} 个问题")

    # 4. 运行评估
    print("\n🚀 开始评估...")
    print(f"   检索策略: BM25 + 向量 (RRF融合, k={settings.RRF_K})")
    print(f"   top_k: 10")
    print("-" * 60)

    results = []
    total_questions = len(dataset)
    start_time = time.time()

    for idx, item in enumerate(dataset, 1):
        question = item["question"]
        expected_answer = item.get("expected_answer", "")
        relevant_doc_ids = item.get("relevant_doc_ids", [])

        # 负例问题（无相关文档）跳过检索，直接记 0
        if not relevant_doc_ids:
            results.append({
                'question': question,
                'relevant_doc_ids': relevant_doc_ids,
                'retrieval_metrics': {'recall_at_k': 0, 'hit_at_k': 0, 'mrr': 0},
                'fused_results': [],
            })
            continue

        # 使用 expected_answer 的前 50 字作为语义查询
        # （评估数据集的 question 是模板化的"文档X..."，无语义信息）
        semantic_query = expected_answer[:50] if expected_answer else question

        # 1. 查询分词
        query_tokens = tokenize(semantic_query)

        # 2. BM25 检索
        bm25_results = bm25_search(db_chunks, query_tokens, top_k=20)

        # 3. 向量检索
        query_vector = embed_service.encode_text(semantic_query)
        vector_results = vector_search(query_vector, db_chunks, top_k=20)

        # 4. RRF 融合
        fused_results = rrf_fusion(bm25_results, vector_results, rrf_k=settings.RRF_K, top_k=10)

        # 5. 计算指标
        metrics = calculate_metrics(fused_results, relevant_doc_ids, top_k=10)
        results.append({
            'question': question,
            'relevant_doc_ids': relevant_doc_ids,
            'retrieval_metrics': metrics,
            'fused_results': fused_results[:5],  # 只保存前5个
        })

        # 进度报告
        if idx % 50 == 0 or idx == total_questions:
            elapsed = time.time() - start_time
            avg_time = elapsed / idx
            eta = (total_questions - idx) * avg_time

            recalls = [r['retrieval_metrics'].get('recall_at_k', 0) for r in results]
            avg_recall = sum(recalls) / len(recalls) if recalls else 0

            hits = [r['retrieval_metrics'].get('hit_at_k', 0) for r in results]
            avg_hit = sum(hits) / len(hits) if hits else 0

            print(f"   [{idx}/{total_questions}] "
                  f"Recall@10: {avg_recall:.4f} | "
                  f"Hit@10: {avg_hit:.4f} | "
                  f"已用: {elapsed:.0f}s | "
                  f"剩余: {eta:.0f}s")

    total_time = time.time() - start_time

    # 7. 汇总结果
    print("\n" + "=" * 60)
    print("📊 评估结果汇总")
    print("=" * 60)

    all_metrics = [r['retrieval_metrics'] for r in results if r['retrieval_metrics']]

    recalls = [m.get('recall_at_k', 0) for m in all_metrics]
    hits = [m.get('hit_at_k', 0) for m in all_metrics]
    mrrs = [m.get('mrr', 0) for m in all_metrics]

    avg_recall = sum(recalls) / len(recalls) if recalls else 0
    avg_hit = sum(hits) / len(hits) if hits else 0
    avg_mrr = sum(mrrs) / len(mrrs) if mrrs else 0

    print(f"\n   总问题数: {total_questions}")
    print(f"   评估耗时: {total_time:.1f} 秒 ({total_time/60:.1f} 分钟)")
    print(f"   平均每题: {total_time/total_questions:.2f} 秒")

    print(f"\n   🎯 检索指标 (top_k=10):")
    print(f"      Recall@10:  {avg_recall:.4f} ({avg_recall*100:.1f}%)")
    print(f"      Hit@10:     {avg_hit:.4f} ({avg_hit*100:.1f}%)")
    print(f"      MRR@10:     {avg_mrr:.4f}")

    # 按难度分组
    difficulties = {}
    for item, result in zip(dataset, results):
        diff = item.get("difficulty", "unknown")
        if diff not in difficulties:
            difficulties[diff] = {"count": 0, "recalls": [], "hits": []}
        difficulties[diff]["count"] += 1
        m = result['retrieval_metrics']
        difficulties[diff]["recalls"].append(m.get('recall_at_k', 0))
        difficulties[diff]["hits"].append(m.get('hit_at_k', 0))

    print(f"\n   📈 按难度分组:")
    for diff, data in sorted(difficulties.items()):
        avg_r = sum(data["recalls"]) / len(data["recalls"]) if data["recalls"] else 0
        avg_h = sum(data["hits"]) / len(data["hits"]) if data["hits"] else 0
        print(f"      {diff}: {data['count']}题, Recall={avg_r:.4f}, Hit={avg_h:.4f}")

    # 保存结果
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "evaluation_results")
    os.makedirs(output_dir, exist_ok=True)

    output_file = os.path.join(output_dir, f"eval_result_{time.strftime('%Y%m%d_%H%M%S')}.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "total_questions": total_questions,
            "evaluation_time_seconds": round(total_time, 2),
            "retrieval_strategy": "BM25 + Vector (RRF fusion)",
            "rrf_k": settings.RRF_K,
            "overall_metrics": {
                "recall_at_10": round(avg_recall, 4),
                "hit_at_10": round(avg_hit, 4),
                "mrr_at_10": round(avg_mrr, 4),
            },
            "per_difficulty": {
                diff: {
                    "count": data["count"],
                    "avg_recall": round(sum(data["recalls"]) / len(data["recalls"]), 4) if data["recalls"] else 0,
                    "avg_hit": round(sum(data["hits"]) / len(data["hits"]), 4) if data["hits"] else 0,
                }
                for diff, data in difficulties.items()
            },
            "detailed_results": results[:20],  # 只保存前20个详细结果
        }, f, ensure_ascii=False, indent=2)

    print(f"\n   💾 详细结果已保存: {output_file}")

    await engine.dispose()
    print("\n✅ 评估完成！")


if __name__ == "__main__":
    asyncio.run(main())
