"""向量索引对比测试框架"""
import time
import numpy as np
import faiss
from typing import List, Dict, Any, Tuple
from app.db.database import get_db
from app.models.vector import VectorChunk
from sqlalchemy import select


class VectorIndexBenchmark:
    """向量索引性能基准测试"""
    
    def __init__(self):
        self.embedding_dim = 1024  # BGE-M3 维度
        self.test_queries = [
            "会议讨论了哪些要点",
            "销售数据增长趋势",
            "下一步行动计划",
            "项目进度报告",
            "预算讨论结果"
        ]
    
    async def load_test_data(self, limit: int = 1000) -> List[Tuple[int, np.ndarray]]:
        """加载测试数据，如果没有真实数据则使用模拟数据"""
        try:
            async for session in get_db():
                result = await session.execute(
                    select(VectorChunk.id, VectorChunk.embedding)
                    .limit(limit)
                )
                chunks = result.all()
                break  # 只取一次会话
            
            data = []
            print(f"从数据库加载了 {len(chunks)} 条记录")
            
            for chunk_id, embedding in chunks:
                if embedding is not None:
                    # embedding 是 JSON 字符串，需要解析
                    if isinstance(embedding, str):
                        import json
                        embedding_list = json.loads(embedding)
                    else:
                        embedding_list = embedding
                    
                    # 确保是列表
                    if isinstance(embedding_list, list):
                        data.append((chunk_id, np.array(embedding_list, dtype=np.float32)))
            
            print(f"成功解析 {len(data)} 条向量数据")
            
        except Exception as e:
            print(f"数据库加载失败: {e}，使用模拟数据")
            data = []
        
        # 如果没有真实数据，使用模拟数据
        if len(data) == 0:
            print(f"使用模拟数据: {limit} 条向量")
            # 生成随机向量作为模拟数据
            np.random.seed(42)  # 固定随机种子以保证可重复性
            for i in range(limit):
                vector = np.random.randn(self.embedding_dim).astype(np.float32)
                data.append((i + 1, vector))
        
        if len(data) > 0:
            print(f"向量维度: {data[0][1].shape}")
        
        return data
    
    def build_faiss_index(self, embeddings: List[np.ndarray], index_type: str = "IVF"):
        """构建FAISS索引"""
        # 确保 embeddings 是 2D 数组
        if len(embeddings) > 0 and isinstance(embeddings[0], np.ndarray):
            d = embeddings[0].shape[0]
        else:
            d = self.embedding_dim
        
        # 将向量列表转换为 2D 数组
        vectors = np.vstack(embeddings) if len(embeddings) > 0 else np.array([])
        
        if index_type == "Flat":
            index = faiss.IndexFlatL2(d)
        elif index_type == "IVF":
            nlist = int(np.sqrt(len(embeddings)))
            quantizer = faiss.IndexFlatL2(d)
            index = faiss.IndexIVFFlat(quantizer, d, nlist, faiss.METRIC_L2)
            index.train(vectors)
        elif index_type == "HNSW":
            index = faiss.IndexHNSWFlat(d, 32)
        elif index_type == "PQ":
            m = 8  # 每个向量分成8段
            nbits = 8
            index = faiss.IndexPQ(d, m, nbits)
            index.train(vectors)
        else:
            raise ValueError(f"Unknown index type: {index_type}")
        
        index.add(vectors)
        return index
    
    async def benchmark_faiss(self, index_type: str = "IVF", top_k: int = 10):
        """基准测试FAISS索引"""
        data = await self.load_test_data()
        chunk_ids = [item[0] for item in data]
        embeddings = [item[1] for item in data]
        
        # 构建索引时间
        start_time = time.time()
        index = self.build_faiss_index(embeddings, index_type)
        build_time = time.time() - start_time
        
        # 查询时间
        query_times = []
        for i in range(len(self.test_queries)):
            # 使用随机向量作为查询
            query_vec = np.random.randn(self.embedding_dim).astype(np.float32)
            
            start_time = time.time()
            distances, indices = index.search(query_vec.reshape(1, -1), top_k)
            query_time = time.time() - start_time
            query_times.append(query_time)
        
        avg_query_time = np.mean(query_times)
        std_query_time = np.std(query_times)
        
        return {
            "index_type": index_type,
            "build_time": build_time,
            "avg_query_time": avg_query_time,
            "std_query_time": std_query_time,
            "data_count": len(data),
            "index_size": index.ntotal
        }
    
    async def benchmark_pgvector(self, top_k: int = 10):
        """基准测试PostgreSQL + pgvector"""
        from app.services.vector_search_service import VectorSearchService
        
        search_service = VectorSearchService()
        
        query_times = []
        for query in self.test_queries:
            start_time = time.time()
            await search_service.search(query, top_k=top_k)
            query_time = time.time() - start_time
            query_times.append(query_time)
        
        avg_query_time = np.mean(query_times)
        std_query_time = np.std(query_times)
        
        return {
            "index_type": "pgvector",
            "build_time": 0,  # pgvector索引已在数据库中构建
            "avg_query_time": avg_query_time,
            "std_query_time": std_query_time,
            "data_count": await self._get_pgvector_count(),
            "index_size": await self._get_pgvector_count()
        }
    
    async def _get_pgvector_count(self) -> int:
        """获取pgvector中的向量数量"""
        async for session in get_db():
            result = await session.execute(
                select(VectorChunk.id)
            )
            count = len(result.all())
            break
        return count
    
    async def run_all_benchmarks(self) -> List[Dict[str, Any]]:
        """运行所有基准测试"""
        results = []
        
        # FAISS Flat
        results.append(await self.benchmark_faiss("Flat"))
        
        # FAISS IVF
        results.append(await self.benchmark_faiss("IVF"))
        
        # FAISS HNSW
        results.append(await self.benchmark_faiss("HNSW"))
        
        # FAISS PQ
        results.append(await self.benchmark_faiss("PQ"))
        
        # pgvector 测试跳过（需要真实向量搜索服务）
        print("跳过 pgvector 测试（需要真实向量搜索服务）")
        
        return results
    
    def print_results(self, results: List[Dict[str, Any]]):
        """打印测试结果"""
        print("=" * 80)
        print("向量索引对比测试结果")
        print("=" * 80)
        print(f"{'索引类型':<12} {'数据量':<8} {'构建时间(ms)':<15} {'平均查询时间(ms)':<20} {'标准差(ms)':<15}")
        print("-" * 80)
        
        for result in results:
            build_time_ms = result["build_time"] * 1000
            query_time_ms = result["avg_query_time"] * 1000
            std_ms = result["std_query_time"] * 1000
            
            print(f"{result['index_type']:<12} {result['data_count']:<8} "
                  f"{build_time_ms:<15.2f} {query_time_ms:<20.2f} {std_ms:<15.2f}")
        
        print("=" * 80)
    
    def compare_indices(self) -> Dict[str, Any]:
        """对比分析各索引方案"""
        analysis = {
            "recommendations": [],
            "comparison": []
        }
        
        # 方案对比
        index_comparison = [
            {
                "name": "pgvector",
                "pros": ["与PostgreSQL深度集成", "支持SQL查询", "事务支持", "适合小规模数据"],
                "cons": ["查询速度较慢", "索引构建复杂", "需要数据库维护"],
                "best_for": "小规模到中等规模数据，需要与其他业务数据联合查询"
            },
            {
                "name": "FAISS Flat",
                "pros": ["最高精度", "无量化损失", "实现简单"],
                "cons": ["内存占用大", "查询速度较慢(O(n))", "不适合大数据"],
                "best_for": "小规模数据，需要最高检索精度"
            },
            {
                "name": "FAISS IVF",
                "pros": ["较好的精度/速度平衡", "支持大数据量", "可扩展性好"],
                "cons": ["需要训练", "有一定量化损失", "调参复杂"],
                "best_for": "中等规模到大规模数据，需要平衡精度和速度"
            },
            {
                "name": "FAISS HNSW",
                "pros": ["最快的查询速度", "支持近实时插入", "良好的精度"],
                "cons": ["内存占用大", "构建时间长", "不支持删除"],
                "best_for": "大规模数据，需要低延迟查询"
            },
            {
                "name": "FAISS PQ",
                "pros": ["内存占用最小", "支持超大规模数据", "存储效率高"],
                "cons": ["精度损失较大", "需要训练", "不适合对精度要求高的场景"],
                "best_for": "超大规模数据，存储空间有限，可接受一定精度损失"
            }
        ]
        
        analysis["comparison"] = index_comparison
        
        # 推荐建议
        analysis["recommendations"] = [
            "当前项目规模（<10万向量）：pgvector 或 FAISS IVF",
            "需要最高精度：FAISS Flat",
            "需要最快查询：FAISS HNSW",
            "超大规模数据：FAISS PQ",
            "需要与业务数据联合查询：pgvector"
        ]
        
        return analysis


async def main():
    """运行对比测试"""
    benchmark = VectorIndexBenchmark()
    
    print("🚀 开始向量索引对比测试...")
    
    # 运行基准测试
    results = await benchmark.run_all_benchmarks()
    
    # 打印结果
    benchmark.print_results(results)
    
    # 输出对比分析
    analysis = benchmark.compare_indices()
    print("\n📊 索引方案对比分析：")
    for rec in analysis["recommendations"]:
        print(f"  - {rec}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())