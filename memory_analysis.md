# Memory System Analysis Report

## File 1: F:\project\meetingmind-agent\backend\app\services\long_term_memory.py

### TTL Constants (Lines 32-38)
- _MEMORY_TTL = 60 * 60 * 24 * 365 (line 33) → 1 year for individual memories
- _INDEX_TTL = 60 * 60 * 24 * 365 (line 34) → 1 year for index sets
- _CONTEXT_TTL = 60 * 60 * 24 * 90 (line 35) → 90 days for meeting contexts
- MAX_MEMORIES = 2000 (line 38) → LRU eviction threshold

### Storage Backends
- **Redis**: Primary cache via cache_get, cache_set, cache_delete, cache_delete_pattern
- **In-memory**: OrderedDict-based LRU cache (_memories, line 164)
- **Keys**: ltm:memory:{id}, ltm:index:all, ltm:idx:meeting:{id}, ltm:idx:type:{type}, ltm:ctx:{meeting_id}

### Redis cache_get/cache_set Calls
| Line | Operation | Key Pattern |
|------|-----------|------------|
| 198 | cache_get | _REDIS_INDEX_KEY |
| 204 | cache_get | _REDIS_MEMORY_KEY.format(memory_id=memory_id) |
| 219 | cache_get | _REDIS_PREFIX + "ctx_index:all" |
| 222 | cache_get | _REDIS_CONTEXT_KEY.format(meeting_id=mid) |
| 239 | cache_set | _REDIS_MEMORY_KEY.format(memory_id=entry.memory_id) TTL: _MEMORY_TTL |
| 242 | cache_get | _REDIS_INDEX_KEY |
| 246 | cache_set | _REDIS_INDEX_KEY TTL: _INDEX_TTL |
| 254 | cache_get | _REDIS_INDEX_KEY |
| 258 | cache_set | _REDIS_INDEX_KEY TTL: _INDEX_TTL |
| 265 | cache_set | _REDIS_CONTEXT_KEY.format(meeting_id=context.meeting_id) TTL: _CONTEXT_TTL |
| 270 | cache_get | _REDIS_PREFIX + "ctx_index:all" |
| 274 | cache_set | _REDIS_PREFIX + "ctx_index:all" TTL: _INDEX_TTL |
| 253 | cache_delete | _REDIS_MEMORY_KEY.format(memory_id=memory_id) |
| 684 | cache_delete | _REDIS_INDEX_KEY |
| 685 | cache_delete | _REDIS_PREFIX + "ctx_index:all" |
| 686 | cache_delete_pattern | _REDIS_PREFIX + "*" |

### Classes and Methods

#### MemoryEntry (lines 60-117)
- __init__ (dataclass, lines 62-74)
- is_expired() (lines 76-83) - checks if memory is expired
- 	o_dict() (lines 85-99)
- rom_dict(cls, data) (classmethod, lines 101-116)

#### MeetingContext (lines 119-150)
- __init__ (dataclass, lines 122-131)
- 	o_dict() (lines 133-145)
- rom_dict(cls, data) (classmethod, lines 147-149)

#### LongTermMemory (lines 152-690)
**Initialization:**
- __init__() (lines 162-179)

**Persistence Layer (Async):**
- _ensure_loaded() (lines 185-193)
- _load_from_redis() (async, lines 195-232)
- _persist_memory(entry) (async, lines 234-248)
- _remove_from_redis(memory_id) (async, lines 250-260)
- _persist_context(context) (async, lines 262-276)

**Memory Index Management:**
- _add_to_index(entry) (lines 282-299)
- _remove_from_index(entry) (lines 301-322)

**Vector Embedding (Lazy Load):**
- _get_embedder() (lines 328-354)
- _compute_similarity(query, texts) (lines 356-370)

**Public API (Async):**
- dd_memory() (async, lines 381-413)
- _link_related_memories(entry) (async, lines 415-434)
- dd_meeting_context(context) (async, lines 436-473)
- get_memory(memory_id) (lines 475-480)
- get_memories_by_type(type) (lines 482-486)
- get_memories_by_scope(scope) (lines 488-492)
- get_memories_by_meeting(meeting_id) (lines 494-498)
- delete_memory(memory_id) (async, lines 500-509)
- purge_expired() (async, lines 511-523)
- search_memories(query, limit=10) (async, lines 525-584)
- ind_relevant_memories(query, context) (async, lines 586-604)
- generate_context_prompt(query, context) (async, lines 606-634)
- get_cross_meeting_context(current_meeting_id) (async, lines 636-656)
- get_statistics() (lines 658-672)
- clear() (async, lines 674-689)

**Static/Singleton:**
- _generate_memory_id() (static, lines 376-379)

### Module-Level Functions (lines 699-817)
- get_long_term_memory() (lines 699-704) - singleton getter
- dd_meeting_memory() (async, lines 707-734)
- search_related_memories() (async, lines 737-741)
- get_context_prompt() (async, lines 744-747)
- get_memory_statistics() (lines 750-752)
- dd_memory() (async, lines 755-782)
- get_memory() (lines 785-786)
- get_memories_by_type() (lines 789-794)
- get_memories_by_scope() (lines 797-802)
- get_memories_by_meeting() (lines 805-806)
- delete_memory() (async, lines 809-810)
- search_memories() (async, lines 813-816)

---

## File 2: F:\project\meetingmind-agent\backend\app\agents\memory.py

### TTL Constants
- Line 113: 	tl=3600 - short-term memory cache (1 hour)
- Line 114: 	tl=3600 - short-term memory save to cache
- Line 260: 	tl=300 - search cache (5 minutes)
- Line 299: 	tl=3600 - hot cache for long-term memory

### Storage Backends
- **PostgreSQL**: Primary storage via MemoryStore (long-term memory, entities, relations)
- **Redis**: Cache layer via cache_get, cache_set, cache_delete
- **In-memory**: _short_term_memory list, _entities dict, _entity_relations dict

### Redis cache_get/cache_set Calls
| Line | Operation | Key Pattern | TTL |
|------|-----------|------------|-----|
| 102 | cache_get | "memory:{self._session_id}:short_term" | - |
| 113 | cache_set | "memory:{self._session_id}:short_term" | 3600 |
| 204 | cache_set | "memory:hot:{db_memory.memory_id}" | 3600 |
| 230 | cache_get | "memory:search:{hash(query) % 10000}" | - |
| 260 | cache_set | cache_key (search results) | 300 |
| 276 | cache_get | "memory:hot:{memory_id}" | - |
| 299 | cache_set | cache_key (hot cache) | 3600 |
| 326 | cache_delete | "memory:hot:{memory_id}" | - |
| 348 | cache_delete | "memory:hot:{memory_id}" | - |

### Classes and Methods

#### MemoryItem (lines 36-54) - Dataclass
- __init__ (dataclass, lines 39-46)
- __post_init__() (lines 49-53)

#### Entity (lines 56-69) - Dataclass
- __init__ (dataclass, lines 59-63)
- __post_init__() (lines 66-68)

#### MemorySystem (lines 71-537)
**Initialization:**
- __init__(session_id, db) (lines 74-86)
- memory_store (property, lines 88-93)

**Short-Term Memory (Async):**
- load_short_term_from_cache() (async, lines 97-105)
- save_short_term_to_cache() (async, lines 107-114)
- dd_short_term_memory(content, metadata) (lines 116-133)
- get_short_term_memory() (lines 135-137)
- clear_short_term_memory() (lines 139-142)
- consolidate_short_term() (async, lines 144-161)

**Long-Term Memory (Async):**
- dd_long_term_memory() (async, lines 165-213)
- search_long_term_memory() (async, lines 215-267)
- get_long_term_memory(memory_id) (async, lines 269-306)
- update_long_term_memory() (async, lines 308-334)
- rchive_long_term_memory() (async, lines 336-356)

**Entity Relations (Async):**
- dd_entity() (async, lines 360-397)
- get_entity(entity_id) (async, lines 399-427)
- dd_entity_relation() (async, lines 429-457)

**Helper Methods:**
- _add_long_term_memory_in_memory() (lines 461-477)
- _search_long_term_memory_in_memory() (lines 479-481)
- _get_long_term_memory_in_memory() (lines 483-485)
- _add_entity_in_memory() (lines 487-497)
- _add_entity_relation_in_memory() (lines 499-504)
- _serialize_memory_item(item) (lines 506-514)
- _deserialize_memory_item(data) (lines 516-528)
- get_memory_summary() (lines 530-537)

#### ShortTermMemory (lines 542-594) - Compatibility Class
- __init__(max_raw_turns) (lines 545-550)
- dd_turn(question, answer, **kwargs) (lines 552-565)
- mark_for_compression() (lines 567-570)
- get_recent_turns(n) (lines 572-573)
- get_context() (lines 575-582)
- compress(summary) (lines 584-586)
- get_summary() (lines 588-593)

#### LongTermMemory (lines 596-636) - Compatibility Class
- __init__(max_items) (lines 599-602)
- dd_memory(category, content, **kwargs) (lines 604-615)
- _prune_low_importance() (lines 617-621)
- search_by_content(query) (lines 623-625)
- dd_key_fact(content, category, **kwargs) (lines 627-636)

#### MemoryCompressor (lines 639-666)
- __init__(llm_service) (lines 642-643)
- compress_turns(turns) (async, lines 645-666)

#### MemoryManager (lines 669-734)
- __init__() (lines 672-682)
- dd_conversation(question, answer, **kwargs) (lines 685-686)
- get_context_for_query(query, n_recent) (lines 688-696)
- get_memory_stats() (lines 698-706)
- clear_all() (lines 708-710)
- enable_checkpoint() (lines 712-713)
- save_checkpoint(session_id) (lines 715-721)
- load_checkpoint(checkpoint) (lines 723-725)
- compress_if_needed() (async, lines 727-734)

### Module-Level Functions
- get_memory_system() (lines 737-739) - factory function

### Database Write Points (MemoryStore calls)
- Line 181: self.memory_store.create_memory() - inserts to PostgreSQL
- Line 237: self.memory_store.search_memories() - reads from PostgreSQL
- Line 283: self.memory_store.get_memory_by_id() - reads from PostgreSQL
- Line 319: self.memory_store.update_memory() - updates PostgreSQL
- Line 342: self.memory_store.update_memory() - updates PostgreSQL (archive)
- Line 373: self.memory_store.create_entity() - inserts entity to PostgreSQL
- Line 409: self.memory_store.get_entity_by_id() - reads from PostgreSQL
- Line 441: self.memory_store.create_relation() - inserts relation to PostgreSQL

### TODO Comments
- None explicitly marked as TODO in provided files
