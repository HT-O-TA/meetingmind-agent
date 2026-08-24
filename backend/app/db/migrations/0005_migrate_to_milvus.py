"""数据库迁移脚本 - 将 documents 数据分块并迁移到 Milvus"""
import asyncio
import sys
import re
sys.path.insert(0, "F:/project/meetingmind-agent/backend")

from sqlalchemy import select, text
from app.db.database import engine
from app.models.document import Document


# 分块配置
CHUNK_SIZE = 500  # 每个块的字符数
CHUNK_OVERLAP = 50  # 块之间的重叠字符数


def simple_chunk_text(text: str, chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP) -> list:
    """简单的文本分块 - 按段落分割，再按大小合并"""
    if not text or not text.strip():
        return []

    # 按段落分割
    paragraphs = re.split(r'\n\s*\n', text.strip())
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        # 如果单个段落超过 chunk_size，按句子分割
        if len(para) > chunk_size:
            sentences = re.split(r'([。！？.!?])', para)
            # 重组句子
            sent_list = []
            i = 0
            while i < len(sentences):
                sent = sentences[i]
                if i + 1 < len(sentences) and re.match(r'[。！？.!?]', sentences[i + 1]):
                    sent += sentences[i + 1]
                    i += 2
                else:
                    i += 1
                if sent.strip():
                    sent_list.append(sent.strip())

            # 合并句子到 chunk
            for sent in sent_list:
                if len(current_chunk) + len(sent) <= chunk_size:
                    current_chunk += ("\n" if current_chunk else "") + sent
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    # 如果句子本身超过 chunk_size，强制分割
                    if len(sent) > chunk_size:
                        for j in range(0, len(sent), chunk_size - chunk_overlap):
                            sub_chunk = sent[j:j + chunk_size]
                            if len(sub_chunk.strip()) >= 10:
                                chunks.append(sub_chunk)
                        current_chunk = ""
                    else:
                        current_chunk = sent
        else:
            # 段落加入当前 chunk
            if len(current_chunk) + len(para) <= chunk_size:
                current_chunk += ("\n\n" if current_chunk else "") + para
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                # 如果段落超过 chunk_size，按句子分割
                if len(para) > chunk_size:
                    sentences = re.split(r'(?<=[。！？.!?])\s*', para)
                    for sent in sentences:
                        if len(current_chunk) + len(sent) <= chunk_size:
                            current_chunk += (" " if current_chunk else "") + sent
                        else:
                            if current_chunk:
                                chunks.append(current_chunk)
                            current_chunk = sent
                            # 保留部分重叠
                            if chunk_overlap > 0 and len(current_chunk) > chunk_overlap:
                                overlap_text = current_chunk[-chunk_overlap:]
                                current_chunk = overlap_text + current_chunk[chunk_overlap:]
                else:
                    current_chunk = para

    # 添加最后一个 chunk
    if current_chunk and len(current_chunk.strip()) >= 10:
        chunks.append(current_chunk)

    return chunks


async def migrate_documents_to_milvus():
    """将 documents 表中的数据分块并迁移到 Milvus"""
    try:
        from app.services.vector_store_milvus import get_milvus_vector_store

        milvus_store = get_milvus_vector_store()
        if milvus_store is None:
            print("❌ Milvus 未初始化，跳过数据迁移")
            return

        print("=" * 60)
        print("开始数据迁移到 Milvus")
        print("=" * 60)

        # 1. 检查 documents 表
        async with engine.connect() as conn:
            doc_count_result = await conn.execute(text("SELECT COUNT(*) FROM documents WHERE content IS NOT NULL AND content != ''"))
            doc_count = doc_count_result.scalar()
            print(f"\n📊 有内容的文档数量: {doc_count}")

            if doc_count == 0:
                print("⚠️ 没有可迁移的文档数据")
                return

        # 2. 分批读取文档并处理
        batch_size = 10
        offset = 0
        total_chunks = 0
        processed_docs = 0

        while True:
            async with engine.connect() as conn:
                result = await conn.execute(
                    select(Document.id, Document.content, Document.department, Document.meeting_id)
                    .where(Document.content.isnot(None))
                    .where(Document.content != '')
                    .offset(offset)
                    .limit(batch_size)
                )

                rows = result.fetchall()
                if not rows:
                    break

                batch_chunks = []

                for row in rows:
                    doc_id, content, department, meeting_id = row

                    if not content or len(content.strip()) < 10:
                        continue

                    # 分块
                    chunks = simple_chunk_text(content)

                    for i, chunk_text in enumerate(chunks):
                        if len(chunk_text.strip()) < 10:
                            continue

                        batch_chunks.append({
                            "document_id": str(doc_id),
                            "chunk_id": f"doc_{doc_id}_chunk_{i}",
                            "content": chunk_text,
                            "meeting_id": str(meeting_id) if meeting_id else "",
                            "department": department or "",
                            "metadata": {
                                "chunk_index": i,
                                "total_chunks": len(chunks),
                            },
                        })

                if batch_chunks:
                    # 批量添加到 Milvus
                    inserted = await milvus_store.add_documents(batch_chunks)
                    total_chunks += inserted
                    processed_docs += len(rows)
                    print(f"📥 批次 {offset // batch_size + 1}: 处理 {len(rows)} 个文档，生成 {inserted} 个向量块")

                offset += batch_size

        print("\n" + "=" * 60)
        print(f"✅ 数据迁移完成！")
        print(f"   - 处理文档数: {processed_docs}")
        print(f"   - 生成向量块数: {total_chunks}")
        print("=" * 60)

        # 3. 验证 Milvus 数据
        try:
            stats = milvus_store.client.get_collection_stats(milvus_store.collection_name)
            print(f"\n📊 Milvus 集合统计:")
            print(f"   - 总行数: {stats.get('row_count', 0)}")
        except Exception as e:
            print(f"⚠️ 获取 Milvus 统计失败: {e}")

    except Exception as e:
        print(f"❌ 数据迁移失败: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(migrate_documents_to_milvus())