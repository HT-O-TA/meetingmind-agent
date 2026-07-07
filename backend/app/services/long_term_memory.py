"""长期记忆服务 - 支持跨会议记忆关联和组织级知识存储"""
import asyncio
import json
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import deque, defaultdict
from app.core.logger import app_logger
from app.services.knowledge_graph import get_knowledge_graph_index
from app.core.config import settings


class MemoryType(str, Enum):
    """记忆类型"""
    MEETING_SUMMARY = "meeting_summary"      # 会议纪要
    DECISION = "decision"                      # 决策
    ACTION_ITEM = "action_item"                # 行动项
    CONTROVERSY = "controversy"                # 争议点
    TOPIC = "topic"                            # 讨论主题
    KNOWLEDGE = "knowledge"                    # 组织知识
    RELATIONSHIP = "relationship"              # 关系


class MemoryScope(str, Enum):
    """记忆范围"""
    TEAM = "team"                              # 团队级别
    DEPARTMENT = "department"                  # 部门级别
    ORGANIZATION = "organization"              # 组织级别
    PROJECT = "project"                        # 项目级别


@dataclass
class MemoryEntry:
    """记忆条目"""
    memory_id: str
    type: MemoryType
    scope: MemoryScope
    content: str
    meeting_id: Optional[str] = None
    meeting_topic: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    entities: List[str] = field(default_factory=list)
    related_memories: List[str] = field(default_factory=list)
    confidence: float = 1.0
    expires_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "type": self.type.value,
            "scope": self.scope.value,
            "content": self.content,
            "meeting_id": self.meeting_id,
            "meeting_topic": self.meeting_topic,
            "timestamp": self.timestamp,
            "entities": self.entities,
            "related_memories": self.related_memories,
            "confidence": self.confidence,
            "expires_at": self.expires_at,
            "metadata": self.metadata,
        }


@dataclass
class MeetingContext:
    """会议上下文"""
    meeting_id: str
    topic: str
    date: str
    participants: List[str]
    summary: str
    decisions: List[str]
    action_items: List[str]
    controversies: List[str]
    related_topics: List[str] = field(default_factory=list)
    referenced_memories: List[str] = field(default_factory=list)


class LongTermMemory:
    """长期记忆系统"""

    def __init__(self):
        self._memories: Dict[str, MemoryEntry] = {}
        self._meeting_contexts: Dict[str, MeetingContext] = {}
        self._entity_index: Dict[str, List[str]] = defaultdict(list)
        self._type_index: Dict[MemoryType, List[str]] = defaultdict(list)
        self._scope_index: Dict[MemoryScope, List[str]] = defaultdict(list)
        self._meeting_index: Dict[str, List[str]] = defaultdict(list)
        self._topic_index: Dict[str, List[str]] = defaultdict(list)
        self._next_memory_id = 0
        self._graph_index = get_knowledge_graph_index()

    def _generate_memory_id(self) -> str:
        self._next_memory_id += 1
        return f"mem_{self._next_memory_id}_{int(datetime.now().timestamp())}"

    async def add_memory(
        self,
        type: MemoryType,
        scope: MemoryScope,
        content: str,
        meeting_id: Optional[str] = None,
        meeting_topic: Optional[str] = None,
        entities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        expires_at: Optional[str] = None
    ) -> MemoryEntry:
        """添加记忆"""
        memory_id = self._generate_memory_id()
        
        entry = MemoryEntry(
            memory_id=memory_id,
            type=type,
            scope=scope,
            content=content,
            meeting_id=meeting_id,
            meeting_topic=meeting_topic,
            entities=entities or [],
            metadata=metadata or {},
            expires_at=expires_at
        )

        self._memories[memory_id] = entry
        
        self._type_index[type].append(memory_id)
        self._scope_index[scope].append(memory_id)
        
        if meeting_id:
            self._meeting_index[meeting_id].append(memory_id)
        
        if meeting_topic:
            self._topic_index[meeting_topic.lower()].append(memory_id)
        
        for entity in entry.entities:
            self._entity_index[entity.lower()].append(memory_id)

        await self._link_related_memories(entry)
        
        app_logger.info(f"[Memory] 添加记忆: {memory_id} - {type.value}")
        return entry

    async def _link_related_memories(self, entry: MemoryEntry):
        """关联相关记忆"""
        related_memory_ids = set()

        for entity in entry.entities:
            for memory_id in self._entity_index.get(entity.lower(), []):
                if memory_id != entry.memory_id:
                    related_memory_ids.add(memory_id)

        if entry.meeting_topic:
            for memory_id in self._topic_index.get(entry.meeting_topic.lower(), []):
                if memory_id != entry.memory_id:
                    related_memory_ids.add(memory_id)

        entry.related_memories = list(related_memory_ids)

        for memory_id in related_memory_ids:
            related_entry = self._memories.get(memory_id)
            if related_entry and entry.memory_id not in related_entry.related_memories:
                related_entry.related_memories.append(entry.memory_id)

    async def add_meeting_context(self, context: MeetingContext):
        """添加会议上下文"""
        self._meeting_contexts[context.meeting_id] = context
        
        await self.add_memory(
            type=MemoryType.MEETING_SUMMARY,
            scope=MemoryScope.TEAM,
            content=context.summary,
            meeting_id=context.meeting_id,
            meeting_topic=context.topic,
            entities=context.participants
        )

        for decision in context.decisions:
            await self.add_memory(
                type=MemoryType.DECISION,
                scope=MemoryScope.TEAM,
                content=decision,
                meeting_id=context.meeting_id,
                meeting_topic=context.topic
            )

        for action_item in context.action_items:
            await self.add_memory(
                type=MemoryType.ACTION_ITEM,
                scope=MemoryScope.TEAM,
                content=action_item,
                meeting_id=context.meeting_id,
                meeting_topic=context.topic
            )

        app_logger.info(f"[Memory] 添加会议上下文: {context.meeting_id}")

    def get_memory(self, memory_id: str) -> Optional[MemoryEntry]:
        """获取记忆"""
        return self._memories.get(memory_id)

    def get_memories_by_type(self, type: MemoryType) -> List[MemoryEntry]:
        """按类型获取记忆"""
        return [self._memories[m_id] for m_id in self._type_index.get(type, [])]

    def get_memories_by_scope(self, scope: MemoryScope) -> List[MemoryEntry]:
        """按范围获取记忆"""
        return [self._memories[m_id] for m_id in self._scope_index.get(scope, [])]

    def get_memories_by_meeting(self, meeting_id: str) -> List[MemoryEntry]:
        """按会议获取记忆"""
        return [self._memories[m_id] for m_id in self._meeting_index.get(meeting_id, [])]

    def delete_memory(self, memory_id: str) -> bool:
        """删除记忆"""
        if memory_id not in self._memories:
            return False
        
        entry = self._memories[memory_id]
        
        self._type_index[entry.type].remove(memory_id)
        self._scope_index[entry.scope].remove(memory_id)
        
        if entry.meeting_id and memory_id in self._meeting_index.get(entry.meeting_id, []):
            self._meeting_index[entry.meeting_id].remove(memory_id)
        
        if entry.meeting_topic and memory_id in self._topic_index.get(entry.meeting_topic.lower(), []):
            self._topic_index[entry.meeting_topic.lower()].remove(memory_id)
        
        for entity in entry.entities:
            if memory_id in self._entity_index.get(entity.lower(), []):
                self._entity_index[entity.lower()].remove(memory_id)
        
        for related_id in entry.related_memories:
            related_entry = self._memories.get(related_id)
            if related_entry and memory_id in related_entry.related_memories:
                related_entry.related_memories.remove(memory_id)
        
        del self._memories[memory_id]
        app_logger.info(f"[Memory] 删除记忆: {memory_id}")
        return True

    async def search_memories(self, query: str, limit: int = 10) -> List[Tuple[MemoryEntry, float]]:
        """搜索相关记忆"""
        query_lower = query.lower()
        results = []

        for memory_id, entry in self._memories.items():
            score = 0.0

            if query_lower in entry.content.lower():
                score += 0.5
            if query_lower in (entry.meeting_topic or "").lower():
                score += 0.3
            for entity in entry.entities:
                if query_lower in entity.lower():
                    score += 0.2

            if score > 0:
                age = datetime.now() - datetime.fromisoformat(entry.timestamp)
                recency_factor = max(0.1, 1.0 - age.days / 30)
                score *= recency_factor * entry.confidence
                results.append((entry, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    async def find_relevant_memories(self, query: str, context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """查找相关记忆并返回引用格式"""
        results = await self.search_memories(query, limit=5)
        
        referenced_memories = []
        for entry, score in results:
            related_info = {
                "memory_id": entry.memory_id,
                "type": entry.type.value,
                "content": entry.content[:200] + "..." if len(entry.content) > 200 else entry.content,
                "meeting_topic": entry.meeting_topic,
                "meeting_id": entry.meeting_id,
                "timestamp": entry.timestamp,
                "relevance_score": round(score, 3),
                "entities": entry.entities,
                "related_memories": entry.related_memories[:3]
            }
            referenced_memories.append(related_info)

        return referenced_memories

    async def generate_context_prompt(self, query: str, context: Optional[Dict[str, Any]] = None) -> str:
        """生成包含历史记忆的上下文提示词"""
        memories = await self.find_relevant_memories(query, context)
        
        if not memories:
            return ""

        prompt_parts = ["【历史会议参考】"]
        for i, memory in enumerate(memories, 1):
            time_ago = ""
            try:
                timestamp = datetime.fromisoformat(memory["timestamp"])
                days_ago = (datetime.now() - timestamp).days
                if days_ago == 0:
                    time_ago = "今天"
                elif days_ago == 1:
                    time_ago = "昨天"
                elif days_ago < 7:
                    time_ago = f"{days_ago}天前"
                else:
                    time_ago = f"{timestamp.strftime('%m-%d')}"
            except:
                time_ago = "之前"

            prompt_parts.append(
                f"{i}. [{memory['type']}] {memory['content']}\n"
                f"   (来源: {memory['meeting_topic'] or '历史会议'}, {time_ago})\n"
            )

        return "\n".join(prompt_parts)

    async def get_cross_meeting_context(self, current_meeting_id: str) -> List[Dict[str, Any]]:
        """获取跨会议上下文"""
        current_context = self._meeting_contexts.get(current_meeting_id)
        if not current_context:
            return []

        related_topics = current_context.related_topics
        all_related = []

        for topic in related_topics:
            for memory_id in self._topic_index.get(topic.lower(), []):
                entry = self._memories.get(memory_id)
                if entry and entry.meeting_id != current_meeting_id:
                    all_related.append(entry.to_dict())

        unique_meetings = {}
        for memory in all_related:
            meeting_id = memory.get("meeting_id")
            if meeting_id and meeting_id not in unique_meetings:
                unique_meetings[meeting_id] = memory

        return list(unique_meetings.values())

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        type_counts = {t.value: len(ids) for t, ids in self._type_index.items()}
        scope_counts = {s.value: len(ids) for s, ids in self._scope_index.items()}

        return {
            "total_memories": len(self._memories),
            "total_meetings": len(self._meeting_contexts),
            "by_type": type_counts,
            "by_scope": scope_counts,
            "total_entities": len(self._entity_index),
        }

    def clear(self):
        """清空记忆"""
        self._memories.clear()
        self._meeting_contexts.clear()
        self._entity_index.clear()
        self._type_index.clear()
        self._scope_index.clear()
        self._meeting_index.clear()
        self._topic_index.clear()
        app_logger.info("[Memory] 已清空所有记忆")


_long_term_memory: Optional[LongTermMemory] = None


def get_long_term_memory() -> LongTermMemory:
    """获取长期记忆服务实例"""
    global _long_term_memory
    if _long_term_memory is None:
        _long_term_memory = LongTermMemory()
    return _long_term_memory


async def add_meeting_memory(
    meeting_id: str,
    topic: str,
    date: str,
    participants: List[str],
    summary: str,
    decisions: List[str],
    action_items: List[str],
    controversies: List[str]
) -> Dict[str, Any]:
    """添加会议记忆"""
    memory = get_long_term_memory()
    
    context = MeetingContext(
        meeting_id=meeting_id,
        topic=topic,
        date=date,
        participants=participants,
        summary=summary,
        decisions=decisions,
        action_items=action_items,
        controversies=controversies
    )
    
    await memory.add_meeting_context(context)
    return {"success": True, "meeting_id": meeting_id, "added_memories": len(memory.get_memories_by_meeting(meeting_id))}


async def search_related_memories(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """搜索相关记忆"""
    memory = get_long_term_memory()
    results = await memory.search_memories(query, limit)
    return [{"memory": m.to_dict(), "score": round(s, 3)} for m, s in results]


async def get_context_prompt(query: str) -> str:
    """获取上下文提示词"""
    memory = get_long_term_memory()
    return await memory.generate_context_prompt(query)


def get_memory_statistics() -> Dict[str, Any]:
    """获取记忆统计信息"""
    memory = get_long_term_memory()
    return memory.get_statistics()


async def add_memory(
    content: str,
    type: str,
    scope: str,
    meeting_id: Optional[str] = None,
    meeting_topic: Optional[str] = None,
    entities: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> MemoryEntry:
    """添加记忆"""
    memory = get_long_term_memory()
    try:
        memory_type = MemoryType(type)
        memory_scope = MemoryScope(scope)
    except ValueError:
        memory_type = MemoryType.MEETING_SUMMARY
        memory_scope = MemoryScope.TEAM
    
    return await memory.add_memory(
        type=memory_type,
        scope=memory_scope,
        content=content,
        meeting_id=meeting_id,
        meeting_topic=meeting_topic,
        entities=entities or [],
        metadata=metadata or {},
    )


def get_memory(memory_id: str) -> Optional[MemoryEntry]:
    """获取单个记忆"""
    memory = get_long_term_memory()
    return memory.get_memory(memory_id)


def get_memories_by_type(memory_type: str) -> List[MemoryEntry]:
    """按类型获取记忆"""
    memory = get_long_term_memory()
    try:
        m_type = MemoryType(memory_type)
    except ValueError:
        return []
    return memory.get_memories_by_type(m_type)


def get_memories_by_scope(scope: str) -> List[MemoryEntry]:
    """按范围获取记忆"""
    memory = get_long_term_memory()
    try:
        m_scope = MemoryScope(scope)
    except ValueError:
        return []
    return memory.get_memories_by_scope(m_scope)


def get_memories_by_meeting(meeting_id: str) -> List[MemoryEntry]:
    """按会议获取记忆"""
    memory = get_long_term_memory()
    return memory.get_memories_by_meeting(meeting_id)


def delete_memory(memory_id: str) -> bool:
    """删除记忆"""
    memory = get_long_term_memory()
    return memory.delete_memory(memory_id)


async def search_memories(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """搜索记忆"""
    memory = get_long_term_memory()
    results = await memory.search_memories(query, limit)
    return [{"memory": m.to_dict(), "score": round(s, 3)} for m, s in results]