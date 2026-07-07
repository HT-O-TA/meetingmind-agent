import asyncio
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text
from app.db.database import AsyncSessionLocal
from app.services.document_service import DocumentService
from app.models.document import Document

async def process_all_documents():
    """对所有文档进行向量化处理"""
    async with AsyncSessionLocal() as session:
        # 获取所有需要向量化的文档
        result = await session.execute(select(Document).where(Document.status == 'parsed'))
        documents = result.scalars().all()
        
        print(f"找到 {len(documents)} 个文档需要向量化")
        
        doc_service = DocumentService(session)
        
        success_count = 0
        fail_count = 0
        
        for doc in documents:
            print(f"正在处理文档 {doc.id}: {doc.filename}")
            
            try:
                # 更新文档内容（触发向量化）
                await doc_service.update_content(doc.id, doc.content)
                success_count += 1
                print(f"文档 {doc.id} 向量化成功")
                
            except Exception as e:
                print(f"文档 {doc.id} 向量化失败: {e}")
                fail_count += 1
        
        print(f"\n向量化完成，成功: {success_count}, 失败: {fail_count}")

async def verify_vector_chunks():
    """验证向量化结果"""
    async with AsyncSessionLocal() as session:
        chunk_count = await session.execute(text("SELECT COUNT(*) FROM vector_chunks"))
        doc_count = await session.execute(text("SELECT COUNT(*) FROM documents"))
        
        print(f"\n向量化验证结果:")
        print(f"文档数量: {doc_count.scalar_one()}")
        print(f"向量块数量: {chunk_count.scalar_one()}")

async def main():
    print("=" * 60)
    print("开始向量化处理")
    print("=" * 60)
    
    await process_all_documents()
    await verify_vector_chunks()
    
    print("=" * 60)
    print("向量化处理完成")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())