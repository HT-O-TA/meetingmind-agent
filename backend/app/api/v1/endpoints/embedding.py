from fastapi import APIRouter
from typing import List, Dict
from pydantic import BaseModel, Field
from app.core.response import Response
from app.services.embedding_service import EmbeddingService
from app.schemas.text_process import TextExtractRequest

router = APIRouter(tags=["向量化服务"])


class BatchEncodeRequest(BaseModel):
    texts: List[str] = Field(..., min_length=1, description="待向量化的文本列表")


class SimilarityRequest(BaseModel):
    text1: str = Field(..., min_length=1, description="文本1")
    text2: str = Field(..., min_length=1, description="文本2")


@router.post("/encode", summary="文本向量化")
async def encode_text(request: TextExtractRequest):
    """
    将文本转换为向量表示
    
    - **content**: 输入文本
    """
    embedding_service = EmbeddingService()
    embedding = embedding_service.encode_text(request.content)
    
    return Response(data={
        "text": request.content,
        "embedding": embedding,
        "dimension": len(embedding),
        "model": "sentence-transformers/all-MiniLM-L6-v2"
    })


@router.post("/batch-encode", summary="批量文本向量化")
async def encode_batch(request: BatchEncodeRequest):
    """
    批量将文本转换为向量表示

    - **texts**: 文本列表
    """
    texts = request.texts

    if not texts:
        return Response(data={"embeddings": [], "count": 0})

    embedding_service = EmbeddingService()
    embeddings = embedding_service.encode_batch(texts)

    results = []
    for text, embedding in zip(texts, embeddings):
        results.append({
            "text": text,
            "embedding": embedding,
            "dimension": len(embedding)
        })

    return Response(data={
        "results": results,
        "count": len(results)
    })


@router.post("/similarity", summary="计算相似度")
async def calculate_similarity(request: SimilarityRequest):
    """
    计算两个文本之间的余弦相似度

    - **text1**: 文本1
    - **text2**: 文本2
    """
    embedding_service = EmbeddingService()
    vec1 = embedding_service.encode_text(request.text1)
    vec2 = embedding_service.encode_text(request.text2)

    similarity = embedding_service.cosine_similarity(vec1, vec2)

    return Response(data={
        "text1": request.text1,
        "text2": request.text2,
        "similarity": round(similarity, 4),
        "dimension": len(vec1)
    })


@router.get("/status", summary="向量化服务状态")
async def get_embedding_status():
    """
    获取向量化服务状态和模型信息
    """
    try:
        embedding_service = EmbeddingService()
        status = embedding_service.get_status()
        
        return Response(data=status)
    except Exception as e:
        return Response(data={
            "status": "error",
            "message": str(e)
        }, code=500)
