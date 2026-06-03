"""知识图谱索引 + 实体关系管理"""
import json
import re
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from app.core.logger import app_logger
from app.core.config import settings


class EntityType(str, Enum):
    """实体类型"""
    PERSON = "PERSON"
    ORGANIZATION = "ORGANIZATION"
    PROJECT = "PROJECT"
    PRODUCT = "PRODUCT"
    TECHNOLOGY = "TECHNOLOGY"
    TIME = "TIME"
    LOCATION = "LOCATION"
    MEETING = "MEETING"
    TASK = "TASK"
    DECISION = "DECISION"
    GENERAL = "GENERAL"


class RelationType(str, Enum):
    """关系类型"""
    PARTICIPATED_IN = "参与"         # 参与会议
    ASSIGNED_TO = "负责"            # 负责任务
    REPORTED_TO = "汇报给"          # 汇报关系
    RELATED_TO = "相关"            # 一般关联
    PART_OF = "属于"               # 属于
    CREATED = "创建"               # 创建
    DECIDED = "决定"               # 决定
    SCHEDULED = "安排"             # 安排
    COMPLETED = "完成"             # 完成
    DEPENDS_ON = "依赖"            # 依赖


@dataclass
class Entity:
    """实体"""
    entity_id: str
    name: str
    type: EntityType
    aliases: List[str] = field(default_factory=list)
    description: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)
    source_chunks: List[str] = field(default_factory=list)
    frequency: int = 1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "type": self.type.value,
            "aliases": self.aliases,
            "description": self.description,
            "properties": self.properties,
            "source_chunks": self.source_chunks,
            "frequency": self.frequency
        }


@dataclass
class Relation:
    """关系"""
    relation_id: str
    source_id: str
    target_id: str
    relation_type: RelationType
    weight: float = 1.0
    description: str = ""
    source_chunks: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "relation_id": self.relation_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type.value,
            "weight": self.weight,
            "description": self.description,
            "source_chunks": self.source_chunks
        }


class KnowledgeGraph:
    """知识图谱"""
    
    def __init__(self):
        self.entities: Dict[str, Entity] = {}
        self.relations: Dict[str, Relation] = {}
        self.entity_index: Dict[str, Set[str]] = defaultdict(set)
        self.type_index: Dict[EntityType, Set[str]] = defaultdict(set)
        self.name_index: Dict[str, str] = {}
    
    def add_entity(self, entity: Entity) -> str:
        """添加实体"""
        if entity.entity_id in self.entities:
            self.entities[entity.entity_id].frequency += 1
            return entity.entity_id
        
        self.entities[entity.entity_id] = entity
        self.name_index[entity.name.lower()] = entity.entity_id
        
        for alias in entity.aliases:
            self.name_index[alias.lower()] = entity.entity_id
        
        self.type_index[entity.type].add(entity.entity_id)
        
        return entity.entity_id
    
    def add_relation(self, relation: Relation) -> str:
        """添加关系"""
        if relation.relation_id in self.relations:
            return relation.relation_id
        
        self.relations[relation.relation_id] = relation
        
        self.entity_index[relation.source_id].add(relation.relation_id)
        self.entity_index[relation.target_id].add(relation.relation_id)
        
        return relation.relation_id
    
    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """获取实体"""
        return self.entities.get(entity_id)
    
    def get_entity_by_name(self, name: str) -> Optional[Entity]:
        """通过名称获取实体"""
        entity_id = self.name_index.get(name.lower())
        return self.entities.get(entity_id)
    
    def get_entities_by_type(self, entity_type: EntityType) -> List[Entity]:
        """获取指定类型的实体"""
        entity_ids = self.type_index.get(entity_type, set())
        return [self.entities[eid] for eid in entity_ids]
    
    def get_relations(self, entity_id: str) -> List[Relation]:
        """获取实体的所有关系"""
        relation_ids = self.entity_index.get(entity_id, set())
        return [self.relations[rid] for rid in relation_ids]
    
    def get_neighbors(
        self,
        entity_id: str,
        depth: int = 1,
        relation_types: List[RelationType] = None
    ) -> List[Tuple[Entity, Relation]]:
        """获取邻居实体"""
        result = []
        visited = {entity_id}
        current_level = {entity_id}
        
        for _ in range(depth):
            next_level = set()
            
            for eid in current_level:
                for relation in self.get_relations(eid):
                    if relation_types and relation.relation_type not in relation_types:
                        continue
                    
                    neighbor_id = relation.target_id if relation.source_id == eid else relation.source_id
                    
                    if neighbor_id not in visited:
                        neighbor = self.entities.get(neighbor_id)
                        if neighbor:
                            result.append((neighbor, relation))
                            next_level.add(neighbor_id)
                            visited.add(neighbor_id)
            
            current_level = next_level
        
        return result
    
    def search_by_query(self, query: str) -> List[Entity]:
        """通过查询搜索实体"""
        query_lower = query.lower()
        results = []
        
        for entity in self.entities.values():
            if query_lower in entity.name.lower():
                results.append(entity)
                continue
            
            for alias in entity.aliases:
                if query_lower in alias.lower():
                    results.append(entity)
                    break
        
        return results
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        type_counts = {
            etype.value: len(eids) 
            for etype, eids in self.type_index.items()
        }
        
        return {
            "total_entities": len(self.entities),
            "total_relations": len(self.relations),
            "entity_types": type_counts,
            "most_common_types": sorted(
                type_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
        }


class EntityExtractor:
    """实体抽取器"""
    
    def __init__(self, llm_service=None):
        self._llm = llm_service
        self._entity_patterns = self._init_patterns()
    
    def _init_patterns(self) -> Dict[EntityType, List[str]]:
        """初始化实体模式"""
        return {
            EntityType.PERSON: [r"[A-Z\u4e00-\u9fa5]{2,4}(?:先生|女士|经理|总监|工程师)?"],
            EntityType.PROJECT: [r"项目[A-Z0-9]+", r"[A-Z]+项目", r".*计划"],
            EntityType.MEETING: [r"会议", r"讨论会", r"评审会"],
            EntityType.TASK: [r"待办", r"任务", r"TODO"],
            EntityType.DECISION: [r"决定", r"决议", r"方案"],
        }
    
    def _get_llm(self):
        if self._llm is None:
            try:
                from app.services.llm_service import LLMService
                self._llm = LLMService()
            except Exception as e:
                app_logger.warning(f"Could not load LLM service: {e}")
        return self._llm
    
    async def extract_entities(self, text: str, doc_id: str) -> List[Entity]:
        """
        抽取实体
        
        Args:
            text: 文本内容
            doc_id: 文档ID
            
        Returns:
            实体列表
        """
        entities = []
        entity_id_map = {}
        
        for etype, patterns in self._entity_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text)
                for match in matches:
                    name = match.group()
                    if len(name) < 2:
                        continue
                    
                    key = f"{etype.value}_{name}"
                    if key not in entity_id_map:
                        entity_id = f"{doc_id}_ent_{len(entities)}"
                        entity_id_map[key] = entity_id
                        
                        entity = Entity(
                            entity_id=entity_id,
                            name=name,
                            type=etype,
                            source_chunks=[doc_id]
                        )
                        entities.append(entity)
                    else:
                        entity = next(
                            (e for e in entities if e.entity_id == entity_id_map[key]),
                            None
                        )
                        if entity:
                            entity.frequency += 1
                            if doc_id not in entity.source_chunks:
                                entity.source_chunks.append(doc_id)
        
        llm = self._get_llm()
        if llm:
            llm_entities = await self._extract_with_llm(text, doc_id)
            entities.extend(llm_entities)
        
        return entities
    
    async def _extract_with_llm(self, text: str, doc_id: str) -> List[Entity]:
        """使用LLM抽取实体"""
        try:
            prompt = f"""从以下文本中抽取实体及其类型：

文本：
{text[:2000]}

实体类型：
- PERSON: 人名
- ORGANIZATION: 组织/公司
- PROJECT: 项目
- PRODUCT: 产品
- TECHNOLOGY: 技术
- MEETING: 会议
- TASK: 任务
- DECISION: 决策

输出格式（JSON数组）：
[
  {{
    "name": "实体名称",
    "type": "实体类型",
    "aliases": ["别名1", "别名2"],
    "description": "描述"
  }}
]

只输出JSON："""
            
            response = await self._llm._call(prompt)
            
            return self._parse_response(response, doc_id)
            
        except Exception as e:
            app_logger.error(f"LLM entity extraction failed: {e}")
            return []
    
    def _parse_response(self, response: str, doc_id: str) -> List[Entity]:
        """解析LLM响应"""
        try:
            start = response.find('[')
            end = response.rfind(']') + 1
            if start != -1 and end != 0:
                data = json.loads(response[start:end])
                
                entities = []
                for i, item in enumerate(data):
                    try:
                        etype = EntityType(item.get("type", "GENERAL"))
                    except:
                        etype = EntityType.GENERAL
                    
                    entity = Entity(
                        entity_id=f"{doc_id}_llm_ent_{i}",
                        name=item.get("name", ""),
                        type=etype,
                        aliases=item.get("aliases", []),
                        description=item.get("description", ""),
                        source_chunks=[doc_id]
                    )
                    entities.append(entity)
                
                return entities
                
        except json.JSONDecodeError:
            pass
        
        return []


class RelationExtractor:
    """关系抽取器"""
    
    def __init__(self, llm_service=None):
        self._llm = llm_service
    
    def _get_llm(self):
        if self._llm is None:
            try:
                from app.services.llm_service import LLMService
                self._llm = LLMService()
            except Exception as e:
                app_logger.warning(f"Could not load LLM service: {e}")
        return self._llm
    
    async def extract_relations(
        self,
        text: str,
        entities: List[Entity],
        doc_id: str
    ) -> List[Relation]:
        """抽取关系"""
        relations = []
        
        relation_patterns = [
            (r"(\w+)参与.*?(\w+)", RelationType.PARTICIPATED_IN),
            (r"(\w+)负责.*?(\w+)", RelationType.ASSIGNED_TO),
            (r"(\w+)决定.*?(\w+)", RelationType.DECIDED),
        ]
        
        for pattern, rtype in relation_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                source_name = match.group(1)
                target_name = match.group(2)
                
                source_entity = self._find_entity(entities, source_name)
                target_entity = self._find_entity(entities, target_name)
                
                if source_entity and target_entity:
                    relation = Relation(
                        relation_id=f"{doc_id}_rel_{len(relations)}",
                        source_id=source_entity.entity_id,
                        target_id=target_entity.entity_id,
                        relation_type=rtype,
                        description=f"{source_name} - {rtype.value} - {target_name}",
                        source_chunks=[doc_id]
                    )
                    relations.append(relation)
        
        llm = self._get_llm()
        if llm:
            llm_relations = await self._extract_with_llm(text, entities, doc_id)
            relations.extend(llm_relations)
        
        return relations
    
    def _find_entity(self, entities: List[Entity], name: str) -> Optional[Entity]:
        """查找实体"""
        for entity in entities:
            if entity.name == name:
                return entity
            if name in entity.aliases:
                return entity
        return None
    
    async def _extract_with_llm(
        self,
        text: str,
        entities: List[Entity],
        doc_id: str
    ) -> List[Relation]:
        """使用LLM抽取关系"""
        try:
            entity_list = "\n".join([
                f"- {e.name} ({e.type.value})" for e in entities
            ])
            
            prompt = f"""从以下文本中抽取实体之间的关系：

文本：
{text[:2000]}

实体列表：
{entity_list}

关系类型：
- PARTICIPATED_IN: 参与
- ASSIGNED_TO: 负责
- REPORTED_TO: 汇报给
- RELATED_TO: 相关
- DECIDED: 决定
- SCHEDULED: 安排

输出格式（JSON数组）：
[
  {{
    "source": "实体1名称",
    "target": "实体2名称",
    "relation_type": "关系类型",
    "description": "关系描述"
  }}
]

只输出JSON："""
            
            response = await self._llm._call(prompt)
            
            return self._parse_response(response, entities, doc_id)
            
        except Exception as e:
            app_logger.error(f"LLM relation extraction failed: {e}")
            return []
    
    def _parse_response(
        self,
        response: str,
        entities: List[Entity],
        doc_id: str
    ) -> List[Relation]:
        """解析LLM响应"""
        try:
            start = response.find('[')
            end = response.rfind(']') + 1
            if start != -1 and end != 0:
                data = json.loads(response[start:end])
                
                relations = []
                for i, item in enumerate(data):
                    source = self._find_entity(entities, item.get("source", ""))
                    target = self._find_entity(entities, item.get("target", ""))
                    
                    if source and target:
                        try:
                            rtype = RelationType(item.get("relation_type", "RELATED_TO"))
                        except:
                            rtype = RelationType.RELATED_TO
                        
                        relation = Relation(
                            relation_id=f"{doc_id}_llm_rel_{i}",
                            source_id=source.entity_id,
                            target_id=target.entity_id,
                            relation_type=rtype,
                            description=item.get("description", ""),
                            source_chunks=[doc_id]
                        )
                        relations.append(relation)
                
                return relations
                
        except json.JSONDecodeError:
            pass
        
        return []


class KnowledgeGraphIndex:
    """知识图谱索引"""
    
    def __init__(self):
        self._graph = KnowledgeGraph()
        self._entity_extractor = EntityExtractor()
        self._relation_extractor = RelationExtractor()
    
    async def build_index(
        self,
        documents: List[Dict[str, Any]]
    ) -> KnowledgeGraph:
        """构建知识图谱索引
        
        Args:
            documents: 文档列表 [{"chunk_id": "...", "content": "...", ...}]
            
        Returns:
            KnowledgeGraph
        """
        for doc in documents:
            chunk_id = doc.get("chunk_id", "")
            content = doc.get("content", doc.get("chunk_text", ""))
            
            entities = await self._entity_extractor.extract_entities(content, chunk_id)
            
            for entity in entities:
                self._graph.add_entity(entity)
            
            relations = await self._relation_extractor.extract_relations(
                content, entities, chunk_id
            )
            
            for relation in relations:
                self._graph.add_relation(relation)
        
        return self._graph
    
    def search_with_graph(
        self,
        query: str,
        vector_results: List[Dict[str, Any]],
        depth: int = 2
    ) -> List[Dict[str, Any]]:
        """结合图谱增强检索
        
        Args:
            query: 查询文本
            vector_results: 向量检索结果
            depth: 图谱扩展深度
            
        Returns:
            增强后的检索结果
        """
        entities = self._graph.search_by_query(query)
        
        expanded_chunks = set()
        for entity in entities:
            neighbors = self._graph.get_neighbors(entity.entity_id, depth=depth)
            
            for neighbor, relation in neighbors:
                expanded_chunks.update(neighbor.source_chunks)
        
        entity_ids = {e.entity_id for e in entities}
        
        enhanced_results = []
        seen_chunks = set()
        
        for result in vector_results:
            chunk_id = result.get("chunk_id")
            if chunk_id not in seen_chunks:
                enhanced_results.append(result)
                seen_chunks.add(chunk_id)
            
            if chunk_id in expanded_chunks:
                result["graph_enhanced"] = True
                result["related_entities"] = [
                    e.name for e in entities
                    if chunk_id in e.source_chunks
                ]
        
        for chunk_id in expanded_chunks:
            if chunk_id not in seen_chunks:
                seen_chunks.add(chunk_id)
                enhanced_results.append({
                    "chunk_id": chunk_id,
                    "score": 0.3,
                    "source": "graph",
                    "graph_enhanced": True
                })
        
        return enhanced_results
    
    def get_subgraph(
        self,
        entity_name: str,
        depth: int = 2
    ) -> Dict[str, Any]:
        """获取实体子图"""
        entity = self._graph.get_entity_by_name(entity_name)
        
        if not entity:
            return {"error": "Entity not found"}
        
        neighbors = self._graph.get_neighbors(entity.entity_id, depth=depth)
        
        nodes = [{
            "id": entity.entity_id,
            "name": entity.name,
            "type": entity.type.value
        }]
        
        edges = []
        
        for neighbor, relation in neighbors:
            nodes.append({
                "id": neighbor.entity_id,
                "name": neighbor.name,
                "type": neighbor.type.value
            })
            
            edges.append({
                "source": entity.entity_id,
                "target": neighbor.entity_id,
                "type": relation.relation_type.value,
                "description": relation.description
            })
        
        return {
            "nodes": nodes,
            "edges": edges
        }
    
    def get_graph(self) -> KnowledgeGraph:
        """获取知识图谱"""
        return self._graph


_knowledge_graph_index: Optional[KnowledgeGraphIndex] = None


def get_knowledge_graph_index() -> KnowledgeGraphIndex:
    """获取知识图谱索引"""
    global _knowledge_graph_index
    if _knowledge_graph_index is None:
        _knowledge_graph_index = KnowledgeGraphIndex()
    return _knowledge_graph_index


async def build_graph_from_chunks(chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    从文档块构建知识图谱
    
    Args:
        chunks: 文档块列表，每个包含 chunk_id, chunk_text 等字段
        
    Returns:
        图谱统计信息
    """
    index = get_knowledge_graph_index()
    graph = await index.build_index(chunks)
    return graph.get_statistics()


async def enhance_search_results(
    query: str,
    vector_results: List[Dict[str, Any]],
    depth: int = 2
) -> List[Dict[str, Any]]:
    """
    使用知识图谱增强检索结果
    
    Args:
        query: 查询文本
        vector_results: 向量检索结果
        depth: 图谱扩展深度
        
    Returns:
        增强后的检索结果
    """
    index = get_knowledge_graph_index()
    return index.search_with_graph(query, vector_results, depth=depth)


def get_entity_subgraph(entity_name: str, depth: int = 2) -> Dict[str, Any]:
    """
    获取实体的子图信息
    
    Args:
        entity_name: 实体名称
        depth: 扩展深度
        
    Returns:
        子图信息（节点和边）
    """
    index = get_knowledge_graph_index()
    return index.get_subgraph(entity_name, depth=depth)


def get_graph_statistics() -> Dict[str, Any]:
    """
    获取图谱统计信息
    
    Returns:
        统计信息
    """
    index = get_knowledge_graph_index()
    return index.get_graph().get_statistics()


def clear_graph():
    """
    清空知识图谱
    """
    global _knowledge_graph_index
    _knowledge_graph_index = None
