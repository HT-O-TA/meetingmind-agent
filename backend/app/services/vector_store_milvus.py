"""Milvus向量存储 - 原生支持BGE-M3稀疏向量和混合检索（pymilvus 3.0 兼容）"""
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from pymilvus import (
    MilvusClient,
    DataType,
    AnnSearchRequest,
)
from pymilvus.model.hybrid import BGEM3EmbeddingFunction
from app.core.config import settings
from app.core.logger import app_logger


logger = logging.getLogger(__name__)


def _sparse_to_dict(sparse_vec) -> Dict[int, float]:
    """将稀疏向量转换为 Milvus 接受的 {index: value} 格式"""
    if hasattr(sparse_vec, 'indices') and hasattr(sparse_vec, 'data'):
        # scipy csr_matrix 格式
        result = {}
        for idx, val in zip(sparse_vec.indices, sparse_vec.data):
            if val > 0:
                result[int(idx)] = float(val)
        return result
    elif isinstance(sparse_vec, dict):
        # 已经是 dict 格式
        return {int(k): float(v) for k, v in sparse_vec.items()}
    elif isinstance(sparse_vec, tuple) and len(sparse_vec) == 2:
        # (indices, values) 格式
        indices, values = sparse_vec
        return {int(idx): float(val) for idx, val in zip(indices, values) if val > 0}
    else:
        # 尝试从 numpy 数组转换
        try:
            if hasattr(sparse_vec, 'nonzero'):
                nonzero_indices = np.nonzero(sparse_vec)[0]
                return {int(idx): float(sparse_vec[idx]) for idx in nonzero_indices if sparse_vec[idx] > 0}
        except Exception:
            pass
        return {}


class MilvusVectorStore:
    def __init__(self):
        self.client = MilvusClient(
            uri=settings.MILVUS_URI,
            token=settings.MILVUS_TOKEN if hasattr(settings, 'MILVUS_TOKEN') else None,
        )
        self.embedding_fn = BGEM3EmbeddingFunction(
            model_name=settings.BGE_M3_MODEL_PATH if hasattr(settings, 'BGE_M3_MODEL_PATH') else "BAAI/bge-m3",
            use_fp16=settings.USE_FP16 if hasattr(settings, 'USE_FP16') else False,
            device="cuda" if hasattr(settings, 'USE_GPU') and settings.USE_GPU else "cpu",
        )
        self.dense_dim = self.embedding_fn.dim["dense"]
        self.sparse_dim = self.embedding_fn.dim["sparse"]
        self.collection_name = settings.VECTOR_COLLECTION_NAME

        self._init_collection()

    def _init_collection(self):
        """初始化Milvus集合"""
        if not self.client.has_collection(self.collection_name):
            schema = self.client.create_schema(
                auto_id=True,
                enable_dynamic_field=True,
            )
            schema.add_field(
                field_name="pk",
                datatype=DataType.INT64,
                is_primary=True,
                auto_id=True,
            )
            schema.add_field(
                field_name="document_id",
                datatype=DataType.VARCHAR,
                max_length=255,
            )
            schema.add_field(
                field_name="chunk_id",
                datatype=DataType.VARCHAR,
                max_length=255,
            )
            schema.add_field(
                field_name="content",
                datatype=DataType.VARCHAR,
                max_length=4096,
            )
            schema.add_field(
                field_name="meeting_id",
                datatype=DataType.VARCHAR,
                max_length=255,
            )
            schema.add_field(
                field_name="department",
                datatype=DataType.VARCHAR,
                max_length=64,
            )
            schema.add_field(
                field_name="metadata",
                datatype=DataType.JSON,
            )
            schema.add_field(
                field_name="dense_vector",
                datatype=DataType.FLOAT_VECTOR,
                dim=self.dense_dim,
            )
            index_params = self.client.prepare_index_params()
            index_params.add_index(
                field_name="dense_vector",
                index_type="AUTOINDEX",
                metric_type="IP",
            )
            self.client.create_collection(
                collection_name=self.collection_name,
                schema=schema,
                index_params=index_params,
                enable_dynamic_field=True,
            )
            app_logger.info(f"✅ Milvus集合创建成功: {self.collection_name}")
        else:
            self.client.load_collection(self.collection_name)
            app_logger.info(f"✅ Milvus集合已加载: {self.collection_name}")

    async def add_documents(self, documents: List[Dict[str, Any]]) -> int:
        """
        添加文档到Milvus

        Args:
            documents: 文档列表，每个文档包含content和metadata

        Returns:
            插入的文档数量
        """
        contents = [doc["content"] for doc in documents]
        embeddings = self.embedding_fn.encode_documents(contents)

        # 处理 dense 向量
        dense_vectors = embeddings["dense"]  # list of numpy arrays or lists

        entities = []
        for i, doc in enumerate(documents):
            entity = {
                "document_id": doc.get("document_id", ""),
                "chunk_id": doc.get("chunk_id", ""),
                "content": doc["content"],
                "meeting_id": str(doc.get("meeting_id", "")),
                "department": doc.get("department", ""),
                "metadata": doc.get("metadata", {}),
                "dense_vector": dense_vectors[i] if isinstance(dense_vectors[i], list) else dense_vectors[i].tolist(),
            }
            entities.append(entity)

        result = self.client.insert(
            collection_name=self.collection_name,
            data=entities,
        )
        self.client.flush(self.collection_name)

        return result.get('insert_count', 0)

    async def search(
        self,
        query: str,
        top_k: int = 10,
        filters: Dict[str, Any] = None,
        dense_weight: float = 1.0,
        sparse_weight: float = 1.0,
    ) -> List[Dict[str, Any]]:
        """
        混合检索 - 同时使用Dense和Sparse向量

        Args:
            query: 查询文本
            top_k: 返回结果数量
            filters: 过滤条件
            dense_weight: 稠密向量权重
            sparse_weight: 稀疏向量权重

        Returns:
            检索结果列表
        """
        query_embeddings = self.embedding_fn.encode_queries([query])

        # 处理 dense 查询向量
        dense_embedding = query_embeddings["dense"][0]
        if not isinstance(dense_embedding, list):
            dense_embedding = dense_embedding.tolist()

        req_list = []

        dense_search_param = {
            "data": [dense_embedding],
            "anns_field": "dense_vector",
            "param": {"metric_type": "IP"},
            "limit": top_k * 3,
        }
        if filters:
            dense_search_param["expr"] = self._build_filter_expr(filters)
        dense_req = AnnSearchRequest(**dense_search_param)
        req_list.append(dense_req)

        results = self.client.search(
            collection_name=self.collection_name,
            data=[dense_embedding],
            anns_field="dense_vector",
            search_params={"metric_type": "IP"},
            limit=top_k,
            filter=dense_search_param.get("expr"),
            output_fields=["content", "document_id", "chunk_id", "metadata", "meeting_id", "department"],
        )

        search_results = []
        for hit in results[0]:
            search_results.append({
                "content": hit.get("content", ""),
                "document_id": hit.get("document_id", ""),
                "chunk_id": hit.get("chunk_id", ""),
                "metadata": hit.get("metadata", {}),
                "meeting_id": hit.get("meeting_id", ""),
                "department": hit.get("department", ""),
                "score": hit.get("score", 0.0),
            })

        return search_results

    def _build_filter_expr(self, filters: Dict[str, Any]) -> str:
        """构建Milvus过滤表达式"""
        conditions = []
        for key, value in filters.items():
            if isinstance(value, list):
                values_str = ",".join([f'"{v}"' for v in value])
                conditions.append(f'{key} in [{values_str}]')
            elif isinstance(value, str):
                conditions.append(f'{key} == "{value}"')
            else:
                conditions.append(f'{key} == {value}')
        return " and ".join(conditions)

    async def delete_documents(self, document_ids: List[str]) -> int:
        """删除指定文档"""
        values_str = ",".join(['"' + str(id) + '"' for id in document_ids])
        expr = f"document_id in [{values_str}]"
        result = self.client.delete(
            collection_name=self.collection_name,
            expr=expr,
        )
        return result.delete_count

    async def get_document_count(self) -> int:
        """获取文档数量"""
        return self.client.get_collection_stats(self.collection_name).get("row_count", 0)

    async def update_document(self, document_id: str, content: str, metadata: Dict[str, Any]) -> bool:
        """更新文档"""
        embeddings = self.embedding_fn.encode_documents([content])

        # 处理 dense 向量
        dense_vec = embeddings["dense"][0]
        if not isinstance(dense_vec, list):
            dense_vec = dense_vec.tolist()

        result = self.client.upsert(
            collection_name=self.collection_name,
            data=[{
                "document_id": document_id,
                "content": content,
                "metadata": metadata,
                "dense_vector": dense_vec,
            }],
        )
        return result.get('insert_count', 0) > 0


_milvus_vector_store = None


def get_milvus_vector_store() -> Optional['MilvusVectorStore']:
    """懒加载获取Milvus向量存储实例"""
    global _milvus_vector_store
    if _milvus_vector_store is None:
        try:
            _milvus_vector_store = MilvusVectorStore()
            app_logger.info("✅ Milvus向量存储初始化成功")
        except Exception as e:
            app_logger.warning(f"❌ Milvus向量存储初始化失败: {e}")
            _milvus_vector_store = None
    return _milvus_vector_store
