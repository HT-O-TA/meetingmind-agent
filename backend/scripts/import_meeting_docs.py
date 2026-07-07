import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal

async def reset_database():
    """重置数据库，清除旧数据并重置ID序列"""
    async with AsyncSessionLocal() as session:
        try:
            # 清除旧数据
            print("正在清除旧数据...")
            await session.execute(text("DELETE FROM todo_items"))
            await session.execute(text("DELETE FROM vector_chunks"))
            await session.execute(text("DELETE FROM documents"))
            await session.execute(text("DELETE FROM meetings"))
            await session.execute(text("DELETE FROM speech_records"))
            
            # 重置ID序列（PostgreSQL）
            print("正在重置ID序列...")
            await session.execute(text("ALTER SEQUENCE meetings_id_seq RESTART WITH 1"))
            await session.execute(text("ALTER SEQUENCE documents_id_seq RESTART WITH 1"))
            await session.execute(text("ALTER SEQUENCE todo_items_id_seq RESTART WITH 1"))
            await session.execute(text("ALTER SEQUENCE vector_chunks_id_seq RESTART WITH 1"))
            await session.execute(text("ALTER SEQUENCE speech_records_id_seq RESTART WITH 1"))
            
            await session.commit()
            print("数据库重置完成")
        except Exception as e:
            await session.rollback()
            print(f"重置数据库失败: {e}")
            raise

async def import_new_documents(data_dir: str):
    """导入新的会议文档"""
    # 获取所有文件并排序
    files = sorted(Path(data_dir).glob("*.md"), key=lambda x: int(x.stem))
    
    print(f"找到 {len(files)} 个文档文件")
    
    # 先导入会议
    async with AsyncSessionLocal() as session:
        for idx, file_path in enumerate(files, 1):
            doc_id = int(file_path.stem)
            
            # 读取文件内容
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 提取会议主题（如果有）
            lines = content.strip().split('\n')
            meeting_topic = f"会议 {doc_id}"
            if lines and lines[0].startswith('[会议主题]'):
                meeting_topic = lines[0].replace('[会议主题]', '').strip()
            
            print(f"正在导入会议 {doc_id}: {meeting_topic}")
            
            await session.execute(
                text("""
                    INSERT INTO meetings (id, title, description, status)
                    VALUES (:id, :title, :description, 'completed')
                """),
                {"id": doc_id, "title": meeting_topic, "description": f"会议 {doc_id} - {meeting_topic}"}
            )
        
        await session.commit()
        print("会议导入完成")
    
    # 再导入文档
    async with AsyncSessionLocal() as session:
        for idx, file_path in enumerate(files, 1):
            doc_id = int(file_path.stem)
            
            # 读取文件内容
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            print(f"正在导入文档 {doc_id}")
            
            await session.execute(
                text("""
                    INSERT INTO documents (id, meeting_id, filename, original_filename, file_path, content, status)
                    VALUES (:id, :meeting_id, :filename, :original_filename, :file_path, :content, 'parsed')
                """),
                {
                    "id": doc_id,
                    "meeting_id": doc_id,
                    "filename": file_path.name,
                    "original_filename": file_path.name,
                    "file_path": str(file_path),
                    "content": content
                }
            )
        
        await session.commit()
        print("文档导入完成")

async def verify_import():
    """验证导入结果"""
    async with AsyncSessionLocal() as session:
        meeting_count = await session.execute(text("SELECT COUNT(*) FROM meetings"))
        doc_count = await session.execute(text("SELECT COUNT(*) FROM documents"))
        
        print(f"\n导入验证结果:")
        print(f"会议数量: {meeting_count.scalar_one()}")
        print(f"文档数量: {doc_count.scalar_one()}")
        
        # 检查ID范围
        min_max = await session.execute(text("SELECT MIN(id), MAX(id) FROM meetings"))
        min_id, max_id = min_max.one()
        print(f"会议ID范围: {min_id} - {max_id}")

async def main():
    data_dir = r"F:\project\meetingmind-agent\backend\tests\chunking\data\meeting_docs_with_speaker"
    
    if not os.path.exists(data_dir):
        print(f"数据目录不存在: {data_dir}")
        return
    
    print("=" * 60)
    print("开始导入会议文档")
    print("=" * 60)
    
    # 重置数据库
    await reset_database()
    
    # 导入新文档
    await import_new_documents(data_dir)
    
    # 验证导入
    await verify_import()
    
    print("=" * 60)
    print("所有操作完成")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())