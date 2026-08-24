"""
批量导入 AliMeeting 会议文档用于 RAG 评估（原生 SQL 版本）

数据源: tests/chunking/data/meeting_docs_plain/ (1.txt ~ 217.txt)
目标:
  1. documents 表插入 217 个文档
  2. vector_chunks 表插入分块+向量
  3. Milvus 集合 meetingmind_docs 插入向量

运行: cd backend && python scripts/seed_eval_docs_sql.py
"""

import asyncio
import json
import os
import sys

# 禁用 stdout 缓冲
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(line_buffering=True)

# 确保在 backend 目录下运行
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from app.core.config import settings

# 检查 CUDA 是否可用，优先使用 GPU
try:
    import torch
    if torch.cuda.is_available():
        print(f"✅ CUDA 可用: {torch.cuda.get_device_name(0)}")
        settings.EMBEDDING_DEVICE = "cuda"
        settings.USE_GPU = True
        settings.USE_FP16 = True
    else:
        print("⚠️ CUDA 不可用，使用 CPU 模式")
        settings.EMBEDDING_DEVICE = "cpu"
except ImportError:
    print("⚠️ PyTorch 未安装，使用 CPU 模式")
    settings.EMBEDDING_DEVICE = "cpu"

from app.services.embedding_service import EmbeddingService

# AliMeeting 数据目录
ALI_MEETING_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tests", "chunking", "data", "meeting_docs_plain"
)

# 分块配置
CHUNK_SIZE = settings.CHUNK_SIZE  # 300
CHUNK_OVERLAP = settings.CHUNK_OVERLAP  # 30


def simple_chunk(text_content: str) -> list[str]:
    """简单固定大小分块（按字符数）"""
    chunks = []
    start = 0
    while start < len(text_content):
        end = start + CHUNK_SIZE
        chunk = text_content[start:end]
        if chunk.strip():
            chunks.append(chunk)
        start = end - CHUNK_OVERLAP
        if start >= len(text_content):
            break
    return chunks


async def main():
    print("=" * 60)
    print("📚 AliMeeting 会议文档批量导入（SQL版本）")
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

    # 创建引擎
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        future=True,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )

    async with AsyncSession(engine) as db:
        # 检查已存在的文档
        result = await db.execute(sql_text("SELECT id FROM documents ORDER BY id"))
        existing_docs = set(row[0] for row in result.fetchall())
        print(f"   已存在文档: {len(existing_docs)} 个")

        # 注意：跳过 Milvus 初始化（BGEM3EmbeddingFunction 加载耗时过长）
        # 向量数据存储在 PostgreSQL 中，评估时使用 pgvector/轻量模式检索
        milvus_available = False
        print("   跳过 Milvus 初始化（使用 PostgreSQL 向量存储）")

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
            file_content = open(filepath, 'r', encoding='utf-8').read().strip()

            if not file_content:
                print(f"   [{idx}/{len(files)}] 空文件跳过: {filename}")
                continue

            # 1. 插入 Document (原生 SQL)
            await db.execute(sql_text("""
                INSERT INTO documents (id, filename, original_filename, file_path, file_size, file_type, content, status, department, is_public)
                VALUES (:id, :filename, :original_filename, :file_path, :file_size, :file_type, :content, :status, :department, :is_public)
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": doc_id,
                "filename": filename,
                "original_filename": filename,
                "file_path": filepath,
                "file_size": len(file_content),
                "file_type": "txt",
                "content": file_content,
                "status": "parsed",
                "department": "ali_meeting",
                "is_public": True,
            })

            # 2. 分块
            chunks = simple_chunk(file_content)

            # 3. 批量生成向量
            if chunks:
                embeddings = embed_service.encode_batch(chunks)

                # 4. 插入 VectorChunk + Milvus
                for cid, (chunk_text, emb) in enumerate(zip(chunks, embeddings), 1):
                    emb_list = emb.tolist() if hasattr(emb, 'tolist') else list(emb)
                    emb_json = json.dumps(emb_list)

                    # PG (原生 SQL) - 只存储 embedding (JSON格式)，兼容轻量模式
                    await db.execute(sql_text("""
                        INSERT INTO vector_chunks (document_id, chunk_index, chunk_text, speaker_name, embedding, embedding_model, department)
                        VALUES (:document_id, :chunk_index, :chunk_text, :speaker_name, :embedding, :embedding_model, :department)
                    """), {
                        "document_id": doc_id,
                        "chunk_index": cid,
                        "chunk_text": chunk_text,
                        "speaker_name": "",
                        "embedding": emb_json,
                        "embedding_model": settings.EMBEDDING_MODEL_NAME,
                        "department": "ali_meeting",
                    })

                    # Milvus
                    if milvus_available and milvus_store:
                        try:
                            await milvus_store.insert_one({
                                "document_id": str(doc_id),
                                "chunk_id": f"{doc_id}_{cid}",
                                "dense": emb_list,
                                "chunk_text": chunk_text,
                                "department": "ali_meeting",
                            })
                        except Exception as e:
                            print(f"   ⚠️ Milvus 插入失败 doc={doc_id} chunk={cid}: {e}")

                total_chunks += len(chunks)
                total_new_docs += 1

            # 每 20 个文档提交一次
            if idx % 20 == 0 or idx == len(files):
                await db.commit()
                print(f"   [{idx}/{len(files)}] 已导入 {total_new_docs} 个新文档, {total_chunks} 个分块")

        # 最终提交
        await db.commit()

        # 验证
        final_docs_result = await db.execute(sql_text("SELECT count(*) FROM documents"))
        final_docs = final_docs_result.scalar()

        chunk_count_result = await db.execute(sql_text("SELECT count(*) FROM vector_chunks"))
        chunk_count = chunk_count_result.scalar()

        print("\n" + "=" * 60)
        print("✅ 导入完成！")
        print("=" * 60)
        print(f"   总文档数: {final_docs}")
        print(f"   总分块数: {chunk_count}")
        print(f"   新增文档: {total_new_docs}")
        print(f"   新增分块: {total_chunks}")

    # 清理
    await engine.dispose()
    print("\n🎉 数据导入完成，可以开始评估了！")


if __name__ == "__main__":
    asyncio.run(main())
