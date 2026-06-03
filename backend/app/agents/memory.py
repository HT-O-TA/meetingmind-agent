"""记忆系统 - 支持短期记忆、长期记忆和记忆网络（带Redis持久化）"""
import json
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
from datetime import datetime
from dataclasses import dataclass, asdict
from app.core.logger import app_logger
from app.core.config_center import get_config
from app.core.cache import cache_get, cache_set, cache_delete


class MemoryType(str, Enum):
    """记忆类型"""
    SHORT_TERM = "short_term"    # 短期记忆（当前对话）
    LONG_TERM = "long_term"      # 长期记忆（跨会话）
    EPISODIC = "episodic"        # 情景记忆（事件记录）
    SEMANTIC = "semantic"        # 语义记忆（知识事实）
    WORKING = "working"          # 工作记忆（当前任务）


class MemoryStatus(str, Enum):
    """记忆状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


@dataclass
class MemoryItem:
    """记忆项"""
    memory_id: str
    type: MemoryType
    content: str
    metadata: Dict[str, Any]
    created_at: datetime = None
    updated_at: datetime = None
    expires_at: Optional[datetime] = None
    status: MemoryStatus = MemoryStatus.ACTIVE
    relevance_score: float = 1.0
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()


@dataclass
class Entity:
    """实体"""
    entity_id: str
    name: str
    type: str
    properties: Dict[str, Any]
    relations: List[Tuple[str, str, str]]  # [(target_entity_id, relation_type, description)]
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class MemorySystem:
    """记忆系统（带Redis持久化）"""
    
    def __init__(self, session_id: Optional[str] = None):
        self._session_id = session_id
        self._short_term_memory: List[MemoryItem] = []
        self._long_term_memory: Dict[str, MemoryItem] = {}
        self._entities: Dict[str, Entity] = {}
        self._entity_relations: Dict[str, List[Tuple[str, str]]] = {}  # entity_id -> [(target_id, relation)]
        self._max_short_term = get_config("agent.max_short_term_memory", 100)
        self._memory_index = {}  # 关键词索引
    
    async def load_from_cache(self):
        """从Redis加载记忆数据"""
        if not self._session_id:
            return
        
        # 加载短期记忆
        short_term_data = await cache_get(f"memory:{self._session_id}:short_term")
        if short_term_data:
            self._short_term_memory = [self._deserialize_memory_item(item) for item in short_term_data]
        
        # 加载长期记忆
        long_term_data = await cache_get(f"memory:{self._session_id}:long_term")
        if long_term_data:
            self._long_term_memory = {item["memory_id"]: self._deserialize_memory_item(item) for item in long_term_data}
        
        app_logger.info(f"[Memory] 从缓存加载会话 {self._session_id} 的记忆数据")
    
    async def save_to_cache(self):
        """保存记忆数据到Redis"""
        if not self._session_id:
            return
        
        # 保存短期记忆
        short_term_data = [self._serialize_memory_item(item) for item in self._short_term_memory]
        await cache_set(f"memory:{self._session_id}:short_term", short_term_data, ttl=3600)  # 1小时
        
        # 保存长期记忆
        long_term_data = [self._serialize_memory_item(item) for item in self._long_term_memory.values()]
        await cache_set(f"memory:{self._session_id}:long_term", long_term_data, ttl=86400)  # 24小时
        
        app_logger.info(f"[Memory] 会话 {self._session_id} 的记忆数据已保存到缓存")
    
    async def clear_cache(self):
        """清除会话的缓存数据"""
        if not self._session_id:
            return
        
        await cache_delete(f"memory:{self._session_id}:short_term")
        await cache_delete(f"memory:{self._session_id}:long_term")
        app_logger.info(f"[Memory] 会话 {self._session_id} 的缓存已清除")
    
    def _serialize_memory_item(self, item: MemoryItem) -> Dict[str, Any]:
        """序列化记忆项"""
        data = asdict(item)
        data["type"] = item.type.value
        data["status"] = item.status.value
        data["created_at"] = item.created_at.isoformat()
        data["updated_at"] = item.updated_at.isoformat()
        data["expires_at"] = item.expires_at.isoformat() if item.expires_at else None
        return data
    
    def _deserialize_memory_item(self, data: Dict[str, Any]) -> MemoryItem:
        """反序列化记忆项"""
        return MemoryItem(
            memory_id=data["memory_id"],
            type=MemoryType(data["type"]),
            content=data["content"],
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            status=MemoryStatus(data.get("status", "active")),
            relevance_score=data.get("relevance_score", 1.0)
        )
    
    def add_short_term_memory(self, content: str, metadata: Optional[Dict[str, Any]] = None):
        """添加短期记忆"""
        memory = MemoryItem(
            memory_id=f"st_{int(datetime.now().timestamp())}",
            type=MemoryType.SHORT_TERM,
            content=content,
            metadata=metadata or {}
        )
        
        self._short_term_memory.append(memory)
        
        # 保持短期记忆在限制范围内
        while len(self._short_term_memory) > self._max_short_term:
            removed = self._short_term_memory.pop(0)
            app_logger.debug(f"[Memory] 短期记忆已过期: {removed.memory_id}")
        
        app_logger.debug(f"[Memory] 添加短期记忆: {memory.memory_id}")
        return memory
    
    def get_short_term_memory(self) -> List[MemoryItem]:
        """获取短期记忆"""
        return self._short_term_memory
    
    def clear_short_term_memory(self):
        """清空短期记忆"""
        self._short_term_memory.clear()
        app_logger.info("[Memory] 短期记忆已清空")
    
    def consolidate_short_term(self) -> Optional[str]:
        """整合短期记忆为摘要"""
        if not self._short_term_memory:
            return None
        
        contents = [m.content for m in self._short_term_memory]
        consolidated = " | ".join(contents[:10])
        
        self.add_long_term_memory(
            content=consolidated,
            metadata={"type": "consolidated", "source": "short_term"}
        )
        
        self.clear_short_term_memory()
        app_logger.info("[Memory] 短期记忆已整合为长期记忆")
        
        return consolidated
    
    def add_long_term_memory(self, content: str, metadata: Optional[Dict[str, Any]] = None, expires_at: Optional[datetime] = None):
        """添加长期记忆"""
        memory = MemoryItem(
            memory_id=f"lt_{int(datetime.now().timestamp())}_{id(self)}",
            type=MemoryType.LONG_TERM,
            content=content,
            metadata=metadata or {},
            expires_at=expires_at
        )
        
        self._long_term_memory[memory.memory_id] = memory
        
        # 更新索引
        self._update_memory_index(memory)
        
        app_logger.info(f"[Memory] 添加长期记忆: {memory.memory_id}")
        return memory
    
    def _update_memory_index(self, memory: MemoryItem):
        """更新记忆索引"""
        content = memory.content.lower()
        keywords = self._extract_keywords(content)
        
        for keyword in keywords:
            if keyword not in self._memory_index:
                self._memory_index[keyword] = []
            self._memory_index[keyword].append(memory.memory_id)
    
    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        import re
        words = re.findall(r'\w{3,}', text)
        return list(set(words))[:10]  # 最多10个关键词
    
    def search_long_term_memory(self, query: str, top_k: int = 5) -> List[MemoryItem]:
        """搜索长期记忆"""
        query_keywords = self._extract_keywords(query)
        scores: Dict[str, float] = {}
        
        for keyword in query_keywords:
            if keyword in self._memory_index:
                for memory_id in self._memory_index[keyword]:
                    if memory_id not in scores:
                        scores[memory_id] = 0
                    scores[memory_id] += 1 / len(query_keywords)
        
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)[:top_k]
        
        results = []
        for memory_id in sorted_ids:
            memory = self._long_term_memory.get(memory_id)
            if memory and memory.status == MemoryStatus.ACTIVE:
                memory.relevance_score = scores[memory_id]
                results.append(memory)
        
        app_logger.debug(f"[Memory] 搜索长期记忆: '{query}' -> {len(results)} 条结果")
        return results
    
    def get_long_term_memory(self, memory_id: str) -> Optional[MemoryItem]:
        """获取长期记忆"""
        return self._long_term_memory.get(memory_id)
    
    def update_long_term_memory(self, memory_id: str, content: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        """更新长期记忆"""
        if memory_id not in self._long_term_memory:
            return False
        
        memory = self._long_term_memory[memory_id]
        
        if content:
            memory.content = content
        if metadata:
            memory.metadata.update(metadata)
        
        memory.updated_at = datetime.now()
        self._update_memory_index(memory)
        
        app_logger.info(f"[Memory] 更新长期记忆: {memory_id}")
        return True
    
    def archive_long_term_memory(self, memory_id: str):
        """归档长期记忆"""
        if memory_id in self._long_term_memory:
            self._long_term_memory[memory_id].status = MemoryStatus.ARCHIVED
            app_logger.info(f"[Memory] 归档长期记忆: {memory_id}")
    
    def add_entity(self, name: str, entity_type: str, properties: Optional[Dict[str, Any]] = None) -> Entity:
        """添加实体"""
        entity = Entity(
            entity_id=f"ent_{int(datetime.now().timestamp())}",
            name=name,
            type=entity_type,
            properties=properties or {},
            relations=[]
        )
        
        self._entities[entity.entity_id] = entity
        app_logger.info(f"[Memory] 添加实体: {entity.name} ({entity_type})")
        return entity
    
    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """获取实体"""
        return self._entities.get(entity_id)
    
    def get_entity_by_name(self, name: str) -> Optional[Entity]:
        """按名称查找实体"""
        for entity in self._entities.values():
            if entity.name.lower() == name.lower():
                return entity
        return None
    
    def add_entity_relation(self, source_id: str, target_id: str, relation_type: str, description: str = ""):
        """添加实体关系"""
        if source_id not in self._entities or target_id not in self._entities:
            return False
        
        source_entity = self._entities[source_id]
        source_entity.relations.append((target_id, relation_type, description))
        
        if source_id not in self._entity_relations:
            self._entity_relations[source_id] = []
        self._entity_relations[source_id].append((target_id, relation_type))
        
        app_logger.info(f"[Memory] 添加关系: {source_id} -{relation_type}-> {target_id}")
        return True
    
    def get_entity_relations(self, entity_id: str) -> List[Tuple[str, str, str]]:
        """获取实体的关系"""
        entity = self._entities.get(entity_id)
        if not entity:
            return []
        return entity.relations
    
    def get_related_entities(self, entity_id: str, relation_type: Optional[str] = None) -> List[Entity]:
        """获取相关实体"""
        relations = self.get_entity_relations(entity_id)
        result = []
        
        for target_id, rel_type, _ in relations:
            if relation_type is None or rel_type == relation_type:
                entity = self._entities.get(target_id)
                if entity:
                    result.append(entity)
        
        return result
    
    def get_memory_summary(self) -> Dict[str, Any]:
        """获取记忆系统摘要"""
        return {
            "short_term_count": len(self._short_term_memory),
            "long_term_count": len(self._long_term_memory),
            "active_long_term_count": sum(1 for m in self._long_term_memory.values() if m.status == MemoryStatus.ACTIVE),
            "entity_count": len(self._entities),
            "relation_count": sum(len(e.relations) for e in self._entities.values())
        }
    
    def export_memory(self, memory_type: Optional[MemoryType] = None) -> List[Dict[str, Any]]:
        """导出记忆"""
        result = []
        
        if memory_type is None or memory_type == MemoryType.SHORT_TERM:
            for memory in self._short_term_memory:
                data = asdict(memory)
                data["created_at"] = memory.created_at.isoformat()
                data["updated_at"] = memory.updated_at.isoformat()
                data["expires_at"] = memory.expires_at.isoformat() if memory.expires_at else None
                result.append(data)
        
        if memory_type is None or memory_type == MemoryType.LONG_TERM:
            for memory in self._long_term_memory.values():
                data = asdict(memory)
                data["created_at"] = memory.created_at.isoformat()
                data["updated_at"] = memory.updated_at.isoformat()
                data["expires_at"] = memory.expires_at.isoformat() if memory.expires_at else None
                result.append(data)
        
        return result
    
    def import_memory(self, memories: List[Dict[str, Any]]):
        """导入记忆"""
        for data in memories:
            memory = MemoryItem(
                memory_id=data["memory_id"],
                type=MemoryType(data["type"]),
                content=data["content"],
                metadata=data.get("metadata", {}),
                created_at=datetime.fromisoformat(data["created_at"]),
                updated_at=datetime.fromisoformat(data["updated_at"]),
                expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
                status=MemoryStatus(data.get("status", "active")),
                relevance_score=data.get("relevance_score", 1.0)
            )
            
            if memory.type == MemoryType.SHORT_TERM:
                self._short_term_memory.append(memory)
            else:
                self._long_term_memory[memory.memory_id] = memory
                self._update_memory_index(memory)
        
        app_logger.info(f"[Memory] 导入 {len(memories)} 条记忆")


# ==================== 测试兼容类 ====================

class ShortTermMemory:
    """短期记忆类（测试兼容）"""
    
    def __init__(self, max_raw_turns: int = 10):
        self.max_raw_turns = max_raw_turns
        self.raw_turns: List[Dict[str, Any]] = []
        self.pending_for_compression: List[Dict[str, Any]] = []
        self.summarized_turns: List[Dict[str, Any]] = []
        self._next_turn_id = 1
    
    def add_turn(self, question: str, answer: str, **kwargs) -> Dict[str, Any]:
        """添加对话轮次"""
        turn = {
            "turn_id": self._next_turn_id,
            "question": question,
            "answer": answer,
            "timestamp": datetime.now().isoformat(),
            "task_type": kwargs.get("task_type", "qa"),
            "success": kwargs.get("success", True),
            **kwargs
        }
        self._next_turn_id += 1
        self.raw_turns.append(turn)
        
        # 检查是否需要压缩
        self.mark_for_compression()
        
        return turn
    
    def mark_for_compression(self):
        """标记需要压缩的轮次"""
        while len(self.raw_turns) > self.max_raw_turns:
            removed = self.raw_turns.pop(0)
            self.pending_for_compression.append(removed)
    
    def get_recent_turns(self, n: int) -> List[Dict[str, Any]]:
        """获取最近的n个轮次"""
        return self.raw_turns[-n:]
    
    def get_context(self) -> str:
        """获取上下文文本"""
        if not self.raw_turns:
            return ""
        
        context_parts = []
        for turn in self.raw_turns:
            context_parts.append(f"问: {turn['question']}")
            context_parts.append(f"答: {turn['answer']}")
        
        return "\n".join(context_parts)
    
    def compress(self, summary: Dict[str, Any]):
        """压缩记忆"""
        self.summarized_turns.append(summary)
        self.pending_for_compression.clear()
    
    def get_summary(self) -> Dict[str, Any]:
        """获取摘要"""
        return {
            "raw_turns": len(self.raw_turns),
            "summarized_turns": len(self.summarized_turns),
            "pending_for_compression": len(self.pending_for_compression)
        }


class LongTermMemory:
    """长期记忆类（测试兼容）"""
    
    def __init__(self, max_items: int = 1000):
        self.max_items = max_items
        self.items: List[Dict[str, Any]] = []
        self.key_facts: List[Dict[str, Any]] = []
    
    def add_memory(self, category: str, content: str, **kwargs) -> Dict[str, Any]:
        """添加记忆"""
        memory = {
            "memory_id": f"mem_{len(self.items) + 1}",
            "category": category,
            "content": content,
            "importance": kwargs.get("importance", 0.5),
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        self.items.append(memory)
        self._prune_low_importance()
        return memory
    
    def _prune_low_importance(self):
        """剪枝低重要性记忆"""
        if len(self.items) <= self.max_items:
            return
        
        self.items.sort(key=lambda x: x["importance"], reverse=True)
        self.items = self.items[:self.max_items]
    
    def search_by_content(self, query: str) -> List[Dict[str, Any]]:
        """按内容搜索"""
        query_lower = query.lower()
        return [item for item in self.items if query_lower in item["content"].lower()]
    
    def add_key_fact(self, content: str, category: str, **kwargs) -> Dict[str, Any]:
        """添加关键事实"""
        fact = {
            "fact_id": f"fact_{len(self.key_facts) + 1}",
            "content": content,
            "category": category,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        self.key_facts.append(fact)
        return fact


class MemoryCompressor:
    """记忆压缩器（测试兼容）"""
    
    def __init__(self, llm_service=None):
        self.llm_service = llm_service
    
    async def compress_turns(self, turns: List[Dict[str, Any]]) -> Dict[str, Any]:
        """压缩对话轮次"""
        if not turns:
            return {
                "turn_id": 0,
                "summary": "无对话记录",
                "key_points": [],
                "original_turn_ids": [],
                "timestamp": datetime.now().isoformat(),
                "task_type": "qa"
            }
        
        # 简单模拟压缩
        questions = [t["question"] for t in turns if "question" in t]
        answers = [t["answer"] for t in turns if "answer" in t]
        
        return {
            "turn_id": turns[-1]["turn_id"],
            "summary": f"对话摘要：{' '.join(questions)} -> {' '.join(answers)}",
            "key_points": [],
            "original_turn_ids": [t["turn_id"] for t in turns],
            "timestamp": datetime.now().isoformat(),
            "task_type": turns[-1].get("task_type", "qa")
        }


class MemoryManager:
    """记忆管理器（测试兼容）"""
    
    def __init__(
        self,
        max_short_term_turns: int = 10,
        max_long_term_items: int = 1000,
        enable_compression: bool = True,
        llm_service=None
    ):
        self.short_term = ShortTermMemory(max_raw_turns=max_short_term_turns // 2)
        self.long_term = LongTermMemory(max_items=max_long_term_items)
        self.enable_compression = enable_compression
        self.compressor = MemoryCompressor(llm_service) if enable_compression else None
        self._checkpoint_enabled = False
    
    def add_conversation(self, question: str, answer: str, **kwargs):
        """添加对话"""
        self.short_term.add_turn(question, answer, **kwargs)
    
    def get_context_for_query(self, query: str, n_recent: int = 3) -> str:
        """获取查询上下文"""
        recent_turns = self.short_term.get_recent_turns(n_recent)
        if not recent_turns:
            return ""
        
        context_parts = []
        for turn in recent_turns:
            context_parts.append(f"问: {turn['question']}")
            context_parts.append(f"答: {turn['answer']}")
        
        return "\n".join(context_parts)
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """获取记忆统计"""
        short_term_summary = self.short_term.get_summary()
        return {
            "short_term": short_term_summary,
            "long_term": {
                "items": len(self.long_term.items),
                "key_facts": len(self.long_term.key_facts)
            }
        }
    
    def clear_all(self):
        """清空所有记忆"""
        self.short_term = ShortTermMemory(max_raw_turns=self.short_term.max_raw_turns)
        self.long_term = LongTermMemory(max_items=self.long_term.max_items)
    
    def enable_checkpoint(self):
        """启用检查点"""
        self._checkpoint_enabled = True
    
    def save_checkpoint(self, session_id: str) -> Dict[str, Any]:
        """保存检查点"""
        return {
            "session_id": session_id,
            "short_term": self.short_term.raw_turns,
            "long_term": self.long_term.items,
            "timestamp": datetime.now().isoformat()
        }
    
    def load_checkpoint(self, checkpoint: Dict[str, Any]):
        """加载检查点"""
        self.short_term.raw_turns = checkpoint.get("short_term", [])
        self.long_term.items = checkpoint.get("long_term", [])
    
    async def compress_if_needed(self) -> bool:
        """如果需要则压缩"""
        if not self.enable_compression or not self.compressor:
            return False
        
        if self.short_term.pending_for_compression:
            summary = await self.compressor.compress_turns(self.short_term.pending_for_compression)
            self.short_term.compress(summary)
            return True
        
        return False


# 全局记忆系统实例
memory_system = MemorySystem()


def get_memory_system() -> MemorySystem:
    """获取记忆系统实例"""
    return memory_system
