"""知识图谱迁移脚本 - 将数据迁移到 Neo4j"""
import asyncio
import sys
import os

# 添加项目路径到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.services.knowledge_graph import (
    get_knowledge_graph_index,
    save_graph_to_neo4j,
    load_graph_from_neo4j,
    clear_graph_in_neo4j,
    get_graph_statistics,
    get_graph_neo4j_statistics
)
from app.core.logger import app_logger


async def show_statistics():
    """显示当前图谱统计信息"""
    print("\n" + "="*50)
    print("当前图谱统计信息")
    print("="*50)
    
    # 内存图谱统计
    memory_stats = get_graph_statistics()
    print(f"\n📦 内存图谱:")
    print(f"  - 实体数量: {memory_stats.get('total_entities', 0)}")
    print(f"  - 关系数量: {memory_stats.get('total_relations', 0)}")
    
    # Neo4j 统计
    neo4j_stats = await get_graph_neo4j_statistics()
    print(f"\n🗄️ Neo4j 图谱:")
    if neo4j_stats.get("neo4j_enabled"):
        if neo4j_stats.get("connected"):
            print(f"  - 连接状态: ✅ 已连接")
            print(f"  - 实体数量: {neo4j_stats.get('total_entities', 0)}")
            print(f"  - 关系数量: {neo4j_stats.get('total_relations', 0)}")
        else:
            print(f"  - 连接状态: ❌ 未连接")
    else:
        print(f"  - Neo4j 持久化: ❌ 未启用")


async def migrate_to_neo4j():
    """将内存图谱迁移到 Neo4j"""
    print("\n" + "="*50)
    print("开始迁移数据到 Neo4j")
    print("="*50)
    
    print("\n📤 正在保存图谱到 Neo4j...")
    result = await save_graph_to_neo4j()
    
    print(f"\n✅ 迁移完成!")
    print(f"  - 保存实体数: {result.get('saved_entities', 0)}")
    print(f"  - 保存关系数: {result.get('saved_relations', 0)}")
    
    await show_statistics()


async def restore_from_neo4j():
    """从 Neo4j 恢复图谱到内存"""
    print("\n" + "="*50)
    print("从 Neo4j 恢复图谱")
    print("="*50)
    
    print("\n📥 正在从 Neo4j 加载图谱...")
    result = await load_graph_from_neo4j()
    
    print(f"\n✅ 恢复完成!")
    print(f"  - 加载实体数: {result.get('loaded_entities', 0)}")
    print(f"  - 加载关系数: {result.get('loaded_relations', 0)}")
    
    await show_statistics()


async def clear_neo4j_data():
    """清空 Neo4j 数据"""
    print("\n" + "="*50)
    print("清空 Neo4j 数据")
    print("="*50)
    
    confirm = input("⚠️  确认要清空 Neo4j 中的所有图谱数据吗? (y/N): ")
    if confirm.lower() != 'y':
        print("❌ 操作已取消")
        return
    
    print("\n🗑️ 正在清空...")
    result = await clear_graph_in_neo4j()
    
    if result:
        print("✅ 清空成功")
    else:
        print("❌ 清空失败")
    
    await show_statistics()


async def build_and_migrate():
    """构建图谱并迁移到 Neo4j"""
    print("\n" + "="*50)
    print("构建图谱并迁移到 Neo4j")
    print("="*50)
    
    from app.db.database import init_db
    from app.services.document_service import get_all_document_chunks
    
    print("\n📦 初始化数据库...")
    await init_db()
    
    print("\n📄 获取文档块...")
    chunks = await get_all_document_chunks()
    print(f"   共获取 {len(chunks)} 个文档块")
    
    print("\n🔨 构建知识图谱...")
    index = get_knowledge_graph_index()
    await index.build_index(chunks)
    
    print("\n📤 迁移到 Neo4j...")
    result = await save_graph_to_neo4j()
    
    print(f"\n✅ 构建并迁移完成!")
    print(f"  - 保存实体数: {result.get('saved_entities', 0)}")
    print(f"  - 保存关系数: {result.get('saved_relations', 0)}")
    
    await show_statistics()


async def main():
    """主函数"""
    print("="*60)
    print("     MeetingMind 知识图谱迁移工具")
    print("="*60)
    
    menu = """
可用命令:
  1. 显示统计信息 (stats)
  2. 迁移到 Neo4j (migrate)
  3. 从 Neo4j 恢复 (restore)
  4. 清空 Neo4j (clear)
  5. 构建并迁移 (build)
  6. 退出 (exit)
"""
    
    while True:
        print(menu)
        choice = input("请输入命令编号或名称: ").strip().lower()
        
        if choice in ['1', 'stats']:
            await show_statistics()
        elif choice in ['2', 'migrate']:
            await migrate_to_neo4j()
        elif choice in ['3', 'restore']:
            await restore_from_neo4j()
        elif choice in ['4', 'clear']:
            await clear_neo4j_data()
        elif choice in ['5', 'build']:
            await build_and_migrate()
        elif choice in ['6', 'exit', 'quit']:
            print("\n👋 退出工具")
            break
        else:
            print(f"\n❌ 未知命令: {choice}")
        
        if choice not in ['6', 'exit', 'quit']:
            input("\n按 Enter 键继续...")


if __name__ == "__main__":
    asyncio.run(main())
