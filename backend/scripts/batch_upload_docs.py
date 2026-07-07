"""批量上传测试文档到数据库 - 简化版"""

import os
import sys
import asyncio
from pathlib import Path

# 添加项目路径
sys.path.append(str(Path(__file__).parent.parent))

from app.db.database import get_db
from app.services.document_service import DocumentService


class MockUploadFile:
    """模拟UploadFile对象"""
    def __init__(self, filename, content):
        self.filename = filename
        self._content = content.encode('utf-8')
    
    async def read(self):
        return self._content
    
    async def close(self):
        pass


async def main():
    """批量上传文档"""
    docs_dir = Path(__file__).parent.parent / "tests"
    md_files = sorted([f for f in os.listdir(docs_dir) if f.endswith('.md') and f != 'rag评估.md'])
    
    print(f"找到 {len(md_files)} 个文档文件")
    
    async for db in get_db():
        svc = DocumentService(db)
        uploader_id = 1  # 默认管理员ID
        
        success_count = 0
        fail_count = 0
        
        for i, filename in enumerate(md_files, 1):
            file_path = os.path.join(docs_dir, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                mock_file = MockUploadFile(filename, content)
                doc = await svc.upload(mock_file, None, None, uploader_id)
                print(f"✅ [{i}/{len(md_files)}] 上传成功: {filename} -> ID: {doc.id}")
                success_count += 1
                
            except Exception as e:
                print(f"❌ [{i}/{len(md_files)}] 上传失败: {filename} - {str(e)}")
                fail_count += 1
        
        print(f"\n上传完成！成功: {success_count}, 失败: {fail_count}")


if __name__ == "__main__":
    asyncio.run(main())