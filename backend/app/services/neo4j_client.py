"""Neo4j 图数据库客户端服务"""
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from neo4j import AsyncGraphDatabase, AsyncSession, Record
from neo4j.exceptions import Neo4jError
from app.core.logger import app_logger
from app.core.config import settings
from app.services.knowledge_graph import Entity, Relation, EntityType, RelationType


class Neo4jClient:
    """Neo4j 异步客户端"""
    
    _instance: Optional['Neo4jClient'] = None
    _lock = asyncio.Lock()
    
    def __init__(self):
        self._driver = None
        self._initialized = False
    
    @classmethod
    async def get_instance(cls) -> 'Neo4jClient':
        """获取单例实例"""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = Neo4jClient()
                await cls._instance.connect()
        return cls._instance
    
    async def connect(self) -> bool:
        """连接到 Neo4j 数据库"""
        if not settings.ENABLE_NEO4J_PERSISTENCE:
            app_logger.info("[Neo4j] 持久化已禁用")
            return False
        
        try:
            self._driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
                database=settings.NEO4J_DATABASE,
                connection_timeout=30,
                max_connection_lifetime=3600
            )
            
            async with self._driver.session() as session:
                result = await session.run("RETURN 1")
                await result.data()
            
            self._initialized = True
            app_logger.info(f"[Neo4j] 连接成功: {settings.NEO4J_URI}")
            return True
        
        except Exception as e:
            app_logger.error(f"[Neo4j] 连接失败: {e}")
            self._driver = None
            return False
    
    async def close(self):
        """关闭连接"""
        if self._driver:
            await self._driver.close()
            app_logger.info("[Neo4j] 连接已关闭")
    
    async def save_entity(self, entity: Entity) -> bool:
        """保存实体到 Neo4j"""
        if not self._initialized:
            return False
        
        try:
            async with self._driver.session() as session:
                query = """
                MERGE (e:Entity {entity_id: $entity_id})
                ON CREATE SET e.name = $name, e.type = $type, e.frequency = $frequency
                ON MATCH SET e.frequency = e.frequency + 1
                SET e.aliases = $aliases, e.description = $description, e.properties = $properties, e.source_chunks = $source_chunks
                RETURN e
                """
                
                result = await session.run(query, {
                    "entity_id": entity.entity_id,
                    "name": entity.name,
                    "type": entity.type.value,
                    "frequency": entity.frequency,
                    "aliases": entity.aliases,
                    "description": entity.description,
                    "properties": entity.properties,
                    "source_chunks": entity.source_chunks
                })
                
                await result.data()
                app_logger.debug(f"[Neo4j] 实体保存成功: {entity.name}")
                return True
        
        except Neo4jError as e:
            app_logger.error(f"[Neo4j] 保存实体失败 {entity.entity_id}: {e}")
            return False
    
    async def save_relation(self, relation: Relation) -> bool:
        """保存关系到 Neo4j"""
        if not self._initialized:
            return False
        
        try:
            async with self._driver.session() as session:
                query = """
                MATCH (source:Entity {entity_id: $source_id})
                MATCH (target:Entity {entity_id: $target_id})
                MERGE (source)-[r:RELATION {relation_id: $relation_id}]->(target)
                ON CREATE SET r.type = $relation_type, r.weight = $weight
                ON MATCH SET r.weight = r.weight + $weight
                SET r.description = $description, r.source_chunks = $source_chunks
                RETURN r
                """
                
                result = await session.run(query, {
                    "relation_id": relation.relation_id,
                    "source_id": relation.source_id,
                    "target_id": relation.target_id,
                    "relation_type": relation.relation_type.value,
                    "weight": relation.weight,
                    "description": relation.description,
                    "source_chunks": relation.source_chunks
                })
                
                await result.data()
                app_logger.debug(f"[Neo4j] 关系保存成功: {relation.relation_id}")
                return True
        
        except Neo4jError as e:
            app_logger.error(f"[Neo4j] 保存关系失败 {relation.relation_id}: {e}")
            return False
    
    async def get_entity(self, entity_id: str) -> Optional[Entity]:
        """从 Neo4j 获取实体"""
        if not self._initialized:
            return None
        
        try:
            async with self._driver.session() as session:
                query = """
                MATCH (e:Entity {entity_id: $entity_id})
                RETURN e
                """
                
                result = await session.run(query, {"entity_id": entity_id})
                record = await result.single()
                
                if record:
                    return self._record_to_entity(record)
                
                return None
        
        except Neo4jError as e:
            app_logger.error(f"[Neo4j] 获取实体失败 {entity_id}: {e}")
            return None
    
    async def get_entity_by_name(self, name: str) -> Optional[Entity]:
        """通过名称获取实体"""
        if not self._initialized:
            return None
        
        try:
            async with self._driver.session() as session:
                query = """
                MATCH (e:Entity)
                WHERE e.name = $name OR $name IN e.aliases
                RETURN e
                LIMIT 1
                """
                
                result = await session.run(query, {"name": name})
                record = await result.single()
                
                if record:
                    return self._record_to_entity(record)
                
                return None
        
        except Neo4jError as e:
            app_logger.error(f"[Neo4j] 通过名称获取实体失败 {name}: {e}")
            return None
    
    async def get_all_entities(self) -> List[Entity]:
        """获取所有实体"""
        if not self._initialized:
            return []
        
        try:
            async with self._driver.session() as session:
                query = "MATCH (e:Entity) RETURN e"
                
                result = await session.run(query)
                records = await result.data()
                
                return [self._record_to_entity(rec) for rec in records]
        
        except Neo4jError as e:
            app_logger.error(f"[Neo4j] 获取所有实体失败: {e}")
            return []
    
    async def get_all_relations(self) -> List[Relation]:
        """获取所有关系"""
        if not self._initialized:
            return []
        
        try:
            async with self._driver.session() as session:
                query = """
                MATCH (source)-[r:RELATION]->(target)
                RETURN r, source.entity_id as source_id, target.entity_id as target_id
                """
                
                result = await session.run(query)
                records = await result.data()
                
                return [self._record_to_relation(rec) for rec in records]
        
        except Neo4jError as e:
            app_logger.error(f"[Neo4j] 获取所有关系失败: {e}")
            return []
    
    async def get_neighbors(self, entity_id: str, depth: int = 2) -> List[Tuple[Entity, Relation]]:
        """获取实体的邻居节点"""
        if not self._initialized:
            return []
        
        try:
            async with self._driver.session() as session:
                query = f"""
                MATCH path = (e:Entity {{entity_id: $entity_id}})-[r:RELATION*1..{depth}]->(neighbor)
                RETURN neighbor, r[-1] as relation
                UNION
                MATCH path = (neighbor)-[r:RELATION*1..{depth}]->(e:Entity {{entity_id: $entity_id}})
                RETURN neighbor, r[-1] as relation
                """
                
                result = await session.run(query, {"entity_id": entity_id})
                records = await result.data()
                
                return [
                    (self._record_to_entity({"e": rec["neighbor"]}),
                     self._record_to_relation({"r": rec["relation"]}))
                    for rec in records
                ]
        
        except Neo4jError as e:
            app_logger.error(f"[Neo4j] 获取邻居失败 {entity_id}: {e}")
            return []
    
    async def delete_entity(self, entity_id: str) -> bool:
        """删除实体及其相关关系"""
        if not self._initialized:
            return False
        
        try:
            async with self._driver.session() as session:
                query = """
                MATCH (e:Entity {entity_id: $entity_id})
                DETACH DELETE e
                """
                
                result = await session.run(query, {"entity_id": entity_id})
                await result.consume()
                
                app_logger.debug(f"[Neo4j] 实体删除成功: {entity_id}")
                return True
        
        except Neo4jError as e:
            app_logger.error(f"[Neo4j] 删除实体失败 {entity_id}: {e}")
            return False
    
    async def delete_relation(self, relation_id: str) -> bool:
        """删除关系"""
        if not self._initialized:
            return False
        
        try:
            async with self._driver.session() as session:
                query = """
                MATCH ()-[r:RELATION {relation_id: $relation_id}]->()
                DELETE r
                """
                
                result = await session.run(query, {"relation_id": relation_id})
                await result.consume()
                
                app_logger.debug(f"[Neo4j] 关系删除成功: {relation_id}")
                return True
        
        except Neo4jError as e:
            app_logger.error(f"[Neo4j] 删除关系失败 {relation_id}: {e}")
            return False
    
    async def clear_all(self) -> bool:
        """清空所有数据"""
        if not self._initialized:
            return False
        
        try:
            async with self._driver.session() as session:
                query = "MATCH (n) DETACH DELETE n"
                
                result = await session.run(query)
                await result.consume()
                
                app_logger.info("[Neo4j] 所有数据已清空")
                return True
        
        except Neo4jError as e:
            app_logger.error(f"[Neo4j] 清空数据失败: {e}")
            return False
    
    async def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        if not self._initialized:
            return {"total_entities": 0, "total_relations": 0}
        
        try:
            async with self._driver.session() as session:
                entity_count = await session.run("MATCH (e:Entity) RETURN count(e) as count")
                relation_count = await session.run("MATCH ()-[r:RELATION]->() RETURN count(r) as count")
                
                entity_data = await entity_count.single()
                relation_data = await relation_count.single()
                
                return {
                    "total_entities": entity_data["count"] if entity_data else 0,
                    "total_relations": relation_data["count"] if relation_data else 0
                }
        
        except Neo4jError as e:
            app_logger.error(f"[Neo4j] 获取统计信息失败: {e}")
            return {"total_entities": 0, "total_relations": 0}
    
    def _record_to_entity(self, record: Dict[str, Any]) -> Entity:
        """将 Neo4j 记录转换为 Entity 对象"""
        node = record.get("e", record)
        if isinstance(node, Record):
            node = dict(node)
        
        node_data = node if isinstance(node, dict) else {}
        
        return Entity(
            entity_id=node_data.get("entity_id", ""),
            name=node_data.get("name", ""),
            type=EntityType(node_data.get("type", "GENERAL")),
            aliases=node_data.get("aliases", []),
            description=node_data.get("description", ""),
            properties=node_data.get("properties", {}),
            source_chunks=node_data.get("source_chunks", []),
            frequency=node_data.get("frequency", 1)
        )
    
    def _record_to_relation(self, record: Dict[str, Any]) -> Relation:
        """将 Neo4j 记录转换为 Relation 对象"""
        rel = record.get("r", record)
        if isinstance(rel, Record):
            rel = dict(rel)
        
        rel_data = rel if isinstance(rel, dict) else {}
        
        return Relation(
            relation_id=rel_data.get("relation_id", ""),
            source_id=record.get("source_id", rel_data.get("source_id", "")),
            target_id=record.get("target_id", rel_data.get("target_id", "")),
            relation_type=RelationType(rel_data.get("type", "RELATED_TO")),
            weight=rel_data.get("weight", 1.0),
            description=rel_data.get("description", ""),
            source_chunks=rel_data.get("source_chunks", [])
        )
    
    @property
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized


async def get_neo4j_client() -> Neo4jClient:
    """获取 Neo4j 客户端实例"""
    return await Neo4jClient.get_instance()


async def init_neo4j():
    """初始化 Neo4j 连接（用于应用启动时）"""
    if settings.ENABLE_NEO4J_PERSISTENCE:
        await get_neo4j_client()
