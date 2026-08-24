"""
批量导入 AliMeeting 会议文档用于 RAG 评估

数据源: tests/chunking/data/meeting_docs_plain/ (1.txt ~ 217.txt)
目标:
  1. documents 表插入 217 个文档
  2. vector_chunks 表插入分块+向量
  3. Milvus 集合 meetingmind_docs 插入向量

运行: cd backend && python scripts/seed_eval_docs.py
"""

import asyncio
import json
import os
import sys

# 确保在 backend 目录下运行
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.database import AsyncSessionLocal, engine
from app.models.document import Document
from app.models.vector import VectorChunk
from app.services.embedding_service import EmbeddingService
from app.services.vector_store_milvus import get_milvus_vector_store
from app.core.config import settings
from app.core.logger import app_logger

# AliMeeting 数据目录
ALI_MEETING_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tests", "chunking", "data", "meeting_docs_plain"
)

# 分块配置
CHUNK_SIZE = settings.CHUNK_SIZE  # 300
CHUNK_OVERLAP = settings.CHUNK_OVERLAP  # 30


def simple_chunk(text: str) -> list[str]:
    """简单固定大小分块（按字符数）"""
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk)
        start = end - CHUNK_OVERLAP
        if start >= len(text):
            break
    return chunks


async def check_existing_docs(db: AsyncSession) -> set:
    """检查已存在的文档ID"""
    result = await db.execute(select(Document.id))
    existing = set(row[0] for row in result.fetchall())
    return existing


async def main():
    print("=" * 60)
    print("📚 AliMeeting 会议文档批量导入")
    print("=" * 60)
    print(f"📂 数据目录: {ALI_MEETING_DIR}")

    # 检查目录
    if not os.path.exists(ALI_MEETING_DIR):
        print(f"❌ 目录不存在: {ALI_MEETING_DIR}")
        return

    # 获取文件列表
    files = sorted(
        [f for f in os.listdir(ALI_MEETING_DIR) if f.endswith('.txt')],
        key=lambda x: int(x.replace('.txt', ''))
    )
    print(f"📄 发现 {len(files)} 个 txt 文件")

    # 初始化服务
    print("\n🔧 初始化服务...")
    embed_service = EmbeddingService()
    embedding_status = embed_service.get_status()
    print(f"   Embedding 设备: {embedding_status.get('device')}")
    print(f"   Embedding 模型: {embedding_status.get('model')}")
    print(f"   向量维度: {embedding_status.get('dimension')}")

    # 初始化 Milvus
    milvus_store = get_milvus_vector_store()
    if milvus_store:
        print(f"   Milvus 集合: {settings.VECTOR_COLLECTION_NAME}")
    else:
        print("   ⚠️ Milvus 不可用，跳过 Milvus 向量存储")

    async with AsyncSessionLocal() as db:
        # 检查已存在的文档
        existing_docs = await check_existing_docs(db)
        print(f"   已存在文档: {len(existing_docs)} 个")

        # 处理每个文件
        total_chunks = 0
        total_new_docs = 0

        for idx, filename in enumerate(files, 1):
            doc_id = int(filename.replace('.txt', ''))

            # 跳过已存在的文档
            if doc_id in existing_docs:
                print(f"   [{idx}/{len(files)}] 跳过已存在: {filename}")
                continue

            filepath = os.path.join(ALI_MEETING_DIR, filename)
            text = open(filepath, 'r', encoding='utf-8').read().strip()

            if not text:
                print(f"   [{idx}/{len(files)}] 空文件跳过: {filename}")
                continue

            # 1. 插入 Document
            doc = Document(
                id=doc_id,
                filename=filename,
                original_filename=filename,
                file_path=filepath,
                file_size=len(text),
                file_type='txt',
                content=text,
                status='parsed',
                department='ali_meeting',
                is_public=True,
            )
            db.add(doc)

            # 2. 分块
            chunks = simple_chunk(text)

            # 3. 批量生成向量
            if chunks:
                embeddings = embed_service.encode_batch(chunks)

                # 4. 插入 VectorChunk + Milvus
                for cid, (chunk_text, emb) in enumerate(zip(chunks, embeddings), 1):
                    # PG
                    vc = VectorChunk(
                        document_id=doc_id,
                        chunk_index=cid,
                        chunk_text=chunk_text,
                        speaker_name="",
                        embedding=json.dumps(emb.tolist() if hasattr(emb, 'tolist') else emb),
                        embedding_array=emb.tolist() if hasattr(emb, 'tolist') else emb,
                        embedding_model=settings.EMBEDDING_MODEL_NAME,
                        department='ali_meeting',
                    )
                    db.add(vc)

                    # Milvus
                    if milvus_store:
                        try:
                            await milvus_store.insert_one({
                                "document_id": str(doc_id),
                                "chunk_id": f"{doc_id}_{cid}",
                                "dense": emb.tolist() if hasattr(emb, 'tolist') else emb,
                                "chunk_text": chunk_text,
                                "department": "ali_meeting",
                            })
                        except Exception as e:
                            app_logger.warning(f"Milvus 插入失败 doc={doc_id} chunk={cid}: {e}")

                total_chunks += len(chunks)
                total_new_docs += 1

            # 每 20 个文档提交一次
            if idx % 20 == 0 or idx == len(files):
                await db.commit()
                print(f"   [{idx}/{len(files)}] 已导入 {total_new_docs} 个新文档, {total_chunks} 个分块")

        # 最终提交
        await db.commit()

        # 验证
        final_docs = await check_existing_docs(db)
        chunk_count_result = await db.execute(
            select(func.count(VectorChunk.id))
        )
        chunk_count = chunk_count_result.scalar()

        print("\n" + "=" * 60)
        print("✅ 导入完成！")
        print("=" * 60)
        print(f"   总文档数: {len(final_docs)}")
        print(f"   总分块数: {chunk_count}")
        print(f"   新增文档: {total_new_docs}")
        print(f"   新增分块: {total_chunks}")

    # 清理
    await engine.dispose()
    print("\n🎉 数据导入完成，可以开始评估了！")


if __name__ == "__main__":
    asyncio.run(main())
