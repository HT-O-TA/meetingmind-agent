"""Agent checkpoint persistence and state-scope rules.

The application deliberately keeps conversational memory bounded.  This module
adds a small, replaceable LangGraph checkpoint saver for execution recovery;
it is not a long-term knowledge store.  The default implementation uses an
atomic local file so development and single-process deployments work without
another service.  Production can replace it with ``AsyncPostgresSaver`` from
``langgraph-checkpoint-postgres`` without changing the graph contract.
"""

from __future__ import annotations

import copy
import base64
import hashlib
import json
import os
import pickle
import threading
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Optional

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_checkpoint_metadata,
)
from langgraph.checkpoint.memory import InMemorySaver

from app.core.logger import app_logger


def _compact_checkpoint_value(value: Any, *, max_chars: int = 4000) -> Any:
    """限制工具结果进入 checkpoint 的体积，保留可恢复所需的简短信息。"""
    if isinstance(value, (str, int, float, bool)) or value is None:
        if isinstance(value, str) and len(value) > max_chars:
            digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
            preview_chars = max(40, max_chars - 80)
            return {"_truncated": True, "sha256": digest, "preview": value[:preview_chars]}
        return value
    if isinstance(value, list):
        return [_compact_checkpoint_value(item, max_chars=max_chars // 2) for item in value[:20]]
    if isinstance(value, dict):
        blocked = {"cot", "chain_of_thought", "prompt", "raw_tool_output", "tool_log"}
        return {
            str(key): _compact_checkpoint_value(item, max_chars=max_chars // 2)
            for key, item in list(value.items())[:40]
            if str(key).lower() not in blocked
        }
    return str(value)[:max_chars]


def _checkpoint_task_contexts(value: Any) -> Dict[str, Any]:
    """工具上下文只保留恢复需要的状态，不把整个响应原样长期保存。"""
    if not isinstance(value, dict):
        return {}
    compacted: Dict[str, Any] = {}
    for name, raw in value.items():
        if not isinstance(raw, dict):
            continue
        compacted[str(name)] = {
            key: _compact_checkpoint_value(raw.get(key))
            for key in ("task_id", "status", "output", "error", "data", "metadata")
            if raw.get(key) is not None
        }
    return compacted


# State needed to continue a task is retained.  Evidence text, private
# reasoning and runtime callbacks are deliberately excluded from durable state.
CHECKPOINT_STATE_FIELDS = frozenset(
    {
        "question",
        "agent_run_id",
        "user_id",
        "session_id",
        "conversation_id",
        "thread_id",
        "task_id",
        "task_namespace",
        "input_envelope",
        "task_anchor",
        "input_blocked",
        "planning_blocked",
        "input_block_reason",
        "injection_check",
        "injection_blocked",
        "injection_block_reason",
        "approved_tool_call",
        "resume_from_tool_index",
        "meeting_id",
        "document_ids",
        "context_manifest",
        "current_phase",
        "task_type",
        "workflow_type",
        "reasoning_mode",
        "complexity_score",
        "complexity_level",
        "is_multi_task",
        "route_reason",
        "route_decision",
        "route_confidence",
        "route_candidates",
        "route_decision_trace",
        "explicit_write_authorization",
        "retrieval_required",
        "retrieval_confidence",
        "plan_confidence",
        "uncertainty_flags",
        "planner_iterations",
        "last_plan_fingerprint",
        "repeated_failure_count",
        "last_failure_fingerprint",
        "citations",
        "validation_errors",
        "policy_results",
        "repair_count",
        "max_repair_attempts",
        "risk_level",
        "requires_confirmation",
        "confirmation_status",
        "pending_action",
        "plan",
        "task_contexts",
        "minutes",
        "todos",
        "controversies",
        "answer",
        "structured_outputs",
        "reflection",
        "error",
        "execution_steps",
        "agents_involved",
        "last_strategy",
        "fallback_count",
        "last_executed_node",
        "enable_human_in_the_loop",
        "access_scope",
    }
)

CHECKPOINT_SCHEMA_VERSION = 2

_REDACTED_CHANNEL_DEFAULTS: Dict[str, Any] = {
    # These values make the boundary explicit and prevent an older checkpoint
    # from carrying them forward through a delta channel.
    "context": [],
    "raw_context": [],
    "cot_thoughts": [],
    "human_confirmations": [],
    "session_context": None,
    "event_callback": None,
}


def checkpoint_state_scope(channel_values: Dict[str, Any]) -> Dict[str, Any]:
    """Return the durable subset of a LangGraph state snapshot.

    ``question`` and the validated envelope are task inputs required for
    recovery.  Full retrieved chunks, raw conversation context, CoT and
    callbacks are not persisted.  The access scope is retained as a snapshot
    for diagnostics only; authorization must be rebuilt from the current user
    on resume.
    """

    scoped: Dict[str, Any] = {
        key: copy.deepcopy(value)
        for key, value in channel_values.items()
        if key in CHECKPOINT_STATE_FIELDS
    }
    scoped.update(copy.deepcopy(_REDACTED_CHANNEL_DEFAULTS))
    if "task_contexts" in scoped:
        scoped["task_contexts"] = _checkpoint_task_contexts(scoped["task_contexts"])
    scoped["checkpoint_schema_version"] = CHECKPOINT_SCHEMA_VERSION
    return scoped


def migrate_checkpoint_state(channel_values: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate old checkpoint channel values without changing task semantics."""
    state = dict(channel_values or {})
    version = state.get("checkpoint_schema_version", 1)
    if version == 1:
        # Version 1 had the same fields but no explicit schema marker.
        state["checkpoint_schema_version"] = CHECKPOINT_SCHEMA_VERSION
        return state
    if version != CHECKPOINT_SCHEMA_VERSION:
        raise ValueError(f"unsupported checkpoint schema version: {version}")
    return state


def _checkpoint_cipher():
    """Derive a Fernet key from the application's secret without storing it."""
    from cryptography.fernet import Fernet
    from app.core.config import settings

    digest = hashlib.sha256(
        (settings.SECRET_KEY + ":meetingmind-agent-checkpoint:v1").encode("utf-8")
    ).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _serialize_checkpoint(value: Any, *, max_bytes: Optional[int] = None) -> tuple[str, bytes]:
    """Serialize with LangGraph's safe typed serializer and enforce a byte cap."""
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    type_tag, payload = JsonPlusSerializer().dumps_typed(value)
    if max_bytes and len(payload) > max_bytes:
        raise ValueError(
            f"checkpoint payload exceeds AGENT_CHECKPOINT_MAX_BYTES ({len(payload)} > {max_bytes})"
        )
    return type_tag, payload


def _deserialize_checkpoint(payload: bytes, type_tag: str = "msgpack") -> Any:
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    return JsonPlusSerializer().loads_typed((type_tag, payload))


class PersistentCheckpointSaver(InMemorySaver):
    """A small file-backed LangGraph saver with an explicit state boundary.

    The saver keeps the normal LangGraph API and writes the in-memory indexes
    atomically after each checkpoint mutation.  It is suitable for local or
    single-process deployments; multi-process production should inject the
    official PostgreSQL saver through the same ``checkpointer`` argument.
    """

    FORMAT_VERSION = 1

    def __init__(self, path: str | os.PathLike[str]):
        super().__init__()
        self.path = Path(path)
        self._lock = threading.RLock()
        self._updated_at: Dict[str, float] = {}
        from app.core.config import settings
        self._max_bytes = int(settings.AGENT_CHECKPOINT_MAX_BYTES)
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with self.path.open("rb") as handle:
                raw = handle.read()
                try:
                    raw = _checkpoint_cipher().decrypt(raw)
                except Exception:
                    # Read legacy development files written before encryption.
                    pass
                payload = pickle.loads(raw)
            if payload.get("format_version") != self.FORMAT_VERSION:
                return
            stored = payload.get("storage")
            if isinstance(stored, dict):
                self.storage = defaultdict(
                    lambda: defaultdict(dict),
                    {
                        thread_id: defaultdict(dict, namespaces)
                        for thread_id, namespaces in stored.items()
                    },
                )
            if isinstance(payload.get("writes"), dict):
                self.writes = defaultdict(dict, payload["writes"])
            if isinstance(payload.get("blobs"), dict):
                self.blobs = defaultdict(dict, payload["blobs"])
            self._updated_at = dict(payload.get("updated_at") or {})
            for namespaces in self.storage.values():
                for checkpoints in namespaces.values():
                    for item in checkpoints.values():
                        if isinstance(item, tuple) and len(item) == 3:
                            try:
                                item_checkpoint = self.serde.loads_typed(item[0])
                                item_checkpoint["channel_values"] = migrate_checkpoint_state(
                                    item_checkpoint.get("channel_values", {})
                                )
                            except Exception:
                                continue
        except (OSError, EOFError, pickle.PickleError, AttributeError, KeyError, TypeError, ValueError):
            # Do not silently destroy evidence of corruption.  Preserve the file
            # for operator inspection and start empty only after logging loudly.
            app_logger.exception("Agent checkpoint 文件损坏，已忽略并启动空存储: %s", self.path)
            self.storage.clear()
            self.writes.clear()
            self.blobs.clear()

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        payload = {
            "format_version": self.FORMAT_VERSION,
            # defaultdict factories are lambdas and cannot be pickled.  Store
            # plain dictionaries and recreate the containers during loading.
            "storage": {
                thread_id: {namespace: dict(checkpoints) for namespace, checkpoints in namespaces.items()}
                for thread_id, namespaces in self.storage.items()
            },
            "writes": dict(self.writes),
            "blobs": dict(self.blobs),
            "updated_at": self._updated_at,
        }
        with temporary.open("wb") as handle:
            raw = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
            if len(raw) > self._max_bytes:
                raise ValueError(
                    f"checkpoint file exceeds AGENT_CHECKPOINT_MAX_BYTES ({len(raw)} > {self._max_bytes})"
                )
            handle.write(_checkpoint_cipher().encrypt(raw))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)

    @staticmethod
    def _check_thread_owner(config) -> None:
        configurable = (config or {}).get("configurable", {})
        thread_id = configurable.get("thread_id")
        user_id = configurable.get("user_id")
        if not thread_id:
            return
        owner = str(thread_id).split(":", 1)[0]
        if user_id is None:
            if owner != "anonymous":
                raise PermissionError("anonymous caller cannot access an owned checkpoint")
            return
        if owner != str(user_id):
            raise PermissionError("checkpoint thread belongs to another user")

    def get_tuple(self, config):
        self._check_thread_owner(config)
        with self._lock:
            result = super().get_tuple(config)
            if result:
                result.checkpoint["channel_values"] = migrate_checkpoint_state(
                    result.checkpoint.get("channel_values", {})
                )
            return result

    def list(self, config, *args, **kwargs):
        self._check_thread_owner(config)
        with self._lock:
            yield from super().list(config, *args, **kwargs)

    def put(self, config, checkpoint, metadata, new_versions):
        self._check_thread_owner(config)
        scoped_checkpoint = copy.deepcopy(checkpoint)
        scoped_checkpoint["channel_values"] = checkpoint_state_scope(
            scoped_checkpoint.get("channel_values", {})
        )
        with self._lock:
            result = super().put(config, scoped_checkpoint, metadata, new_versions)
            key = f"{config['configurable']['thread_id']}::{config['configurable'].get('checkpoint_ns', '')}"
            self._updated_at[key] = time.time()
            self._persist()
            return result

    def put_writes(self, config, writes, task_id, task_path=""):
        self._check_thread_owner(config)
        with self._lock:
            result = super().put_writes(config, writes, task_id, task_path)
            key = f"{config['configurable']['thread_id']}::{config['configurable'].get('checkpoint_ns', '')}"
            self._updated_at[key] = time.time()
            self._persist()
            return result

    def delete_thread(self, thread_id: str, user_id: Optional[int] = None) -> None:
        self._check_thread_owner({"configurable": {"thread_id": thread_id, "user_id": user_id}})
        with self._lock:
            super().delete_thread(thread_id)
            for key in list(self._updated_at):
                if key.startswith(f"{thread_id}::"):
                    self._updated_at.pop(key, None)
            self._persist()

    def delete_namespace(self, thread_id: str, checkpoint_ns: str, user_id: Optional[int] = None, *, _system: bool = False) -> None:
        """Remove one completed run while retaining the conversation's other runs."""
        if not _system:
            self._check_thread_owner({"configurable": {"thread_id": thread_id, "user_id": user_id}})
        with self._lock:
            namespaces = self.storage.get(thread_id)
            if namespaces and checkpoint_ns in namespaces:
                del namespaces[checkpoint_ns]
                for key in list(self.writes):
                    if key[0] == thread_id and key[1] == checkpoint_ns:
                        del self.writes[key]
                for key in list(self.blobs):
                    if key[0] == thread_id and key[1] == checkpoint_ns:
                        del self.blobs[key]
            self._updated_at.pop(f"{thread_id}::{checkpoint_ns}", None)
            self._persist()

    def cleanup_expired(self, max_age_seconds: Optional[int] = None) -> int:
        """Delete old namespaces and return the number removed."""
        from app.core.config import settings
        age = int(max_age_seconds or settings.AGENT_CHECKPOINT_RETENTION_SECONDS)
        cutoff = time.time() - max(1, age)
        removed = 0
        with self._lock:
            for key, updated in list(self._updated_at.items()):
                if updated >= cutoff:
                    continue
                thread_id, checkpoint_ns = key.split("::", 1)
                self.delete_namespace(thread_id, checkpoint_ns, _system=True)
                removed += 1
        return removed


class PostgresCheckpointSaver(BaseCheckpointSaver):
    """Shared PostgreSQL checkpoint store used by multi-worker deployments.

    The implementation stores the complete scoped checkpoint row (rather than
    relying on process-local delta blobs), so a worker can resume a run created
    by another worker.  ``asyncpg`` is already a runtime dependency.  The table
    is created lazily by :func:`initialize_checkpoint_store`.
    """

    FORMAT_VERSION = 2
    ASYNC_ONLY = True

    def __init__(self, dsn: str, *, max_bytes: Optional[int] = None):
        super().__init__()
        self.dsn = dsn
        self._pool = None
        self._setup_lock = None
        from app.core.config import settings
        self._max_bytes = int(max_bytes or settings.AGENT_CHECKPOINT_MAX_BYTES)

    async def setup(self) -> None:
        import asyncio
        import asyncpg

        if self._pool is None:
            self._pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=10)
        if self._setup_lock is None:
            self._setup_lock = asyncio.Lock()
        async with self._setup_lock:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agent_checkpoints (
                        thread_id TEXT NOT NULL,
                        checkpoint_ns TEXT NOT NULL DEFAULT '',
                        checkpoint_id TEXT NOT NULL,
                        schema_version INTEGER NOT NULL DEFAULT 2,
                        owner_user_id TEXT,
                        parent_checkpoint_id TEXT,
                        checkpoint_type TEXT NOT NULL,
                        checkpoint_payload BYTEA NOT NULL,
                        metadata_type TEXT NOT NULL,
                        metadata_payload BYTEA NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
                    );
                    CREATE INDEX IF NOT EXISTS ix_agent_checkpoints_latest
                        ON agent_checkpoints (thread_id, checkpoint_ns, updated_at DESC);
                    ALTER TABLE agent_checkpoints ADD COLUMN IF NOT EXISTS schema_version INTEGER NOT NULL DEFAULT 2;
                    CREATE TABLE IF NOT EXISTS agent_checkpoint_writes (
                        thread_id TEXT NOT NULL,
                        checkpoint_ns TEXT NOT NULL DEFAULT '',
                        checkpoint_id TEXT NOT NULL,
                        task_id TEXT NOT NULL,
                        write_idx INTEGER NOT NULL,
                        channel TEXT NOT NULL,
                        value_type TEXT NOT NULL,
                        value_payload BYTEA NOT NULL,
                        task_path TEXT NOT NULL DEFAULT '',
                        PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx)
                    );
                    """
                )

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def _get_pool(self):
        if self._pool is None:
            await self.setup()
        return self._pool

    @staticmethod
    def _owner(config: Dict[str, Any]) -> Optional[str]:
        configurable = (config or {}).get("configurable", {})
        user_id = configurable.get("user_id")
        thread_id = configurable.get("thread_id")
        owner = str(thread_id).split(":", 1)[0] if thread_id else None
        if user_id is None and owner and owner != "anonymous":
            raise PermissionError("anonymous caller cannot access an owned checkpoint")
        if user_id is not None and owner and owner != str(user_id):
            raise PermissionError("checkpoint thread belongs to another user")
        return str(user_id) if user_id is not None else owner

    @staticmethod
    def _ciphertext(payload: bytes) -> bytes:
        return _checkpoint_cipher().encrypt(payload)

    @staticmethod
    def _plaintext(payload: bytes) -> bytes:
        return _checkpoint_cipher().decrypt(payload)

    async def aget_tuple(self, config):
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        owner = self._owner(config)
        checkpoint_id = get_checkpoint_id(config)
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if checkpoint_id:
                row = await conn.fetchrow(
                    "SELECT * FROM agent_checkpoints WHERE thread_id=$1 AND checkpoint_ns=$2 AND checkpoint_id=$3 AND (owner_user_id IS NULL OR owner_user_id=$4)",
                    thread_id, checkpoint_ns, checkpoint_id, owner,
                )
            else:
                row = await conn.fetchrow(
                    "SELECT * FROM agent_checkpoints WHERE thread_id=$1 AND checkpoint_ns=$2 AND (owner_user_id IS NULL OR owner_user_id=$3) ORDER BY checkpoint_id DESC LIMIT 1",
                    thread_id, checkpoint_ns, owner,
                )
            if not row:
                return None
            checkpoint = _deserialize_checkpoint(
                self._plaintext(row["checkpoint_payload"]), row["checkpoint_type"]
            )
            checkpoint["channel_values"] = migrate_checkpoint_state(
                checkpoint.get("channel_values", {})
            )
            metadata = _deserialize_checkpoint(
                self._plaintext(row["metadata_payload"]), row["metadata_type"]
            )
            writes_rows = await conn.fetch(
                "SELECT task_id, channel, value_type, value_payload, task_path FROM agent_checkpoint_writes WHERE thread_id=$1 AND checkpoint_ns=$2 AND checkpoint_id=$3 ORDER BY task_id, write_idx",
                thread_id, checkpoint_ns, row["checkpoint_id"],
            )
            pending_writes = [
                (r["task_id"], r["channel"], _deserialize_checkpoint(self._plaintext(r["value_payload"]), r["value_type"]))
                for r in writes_rows
            ]
            parent = row["parent_checkpoint_id"]
            return CheckpointTuple(
                config={"configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "checkpoint_id": row["checkpoint_id"], "user_id": owner}},
                checkpoint=checkpoint,
                metadata=metadata,
                pending_writes=pending_writes,
                parent_config=(
                    {"configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "checkpoint_id": parent, "user_id": owner}}
                    if parent else None
                ),
            )

    async def aput(self, config, checkpoint: Checkpoint, metadata: CheckpointMetadata, new_versions: ChannelVersions):
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        owner = self._owner(config)
        scoped = copy.deepcopy(checkpoint)
        scoped["channel_values"] = checkpoint_state_scope(scoped.get("channel_values", {}))
        checkpoint_type, checkpoint_payload = _serialize_checkpoint(scoped, max_bytes=self._max_bytes)
        metadata_value = get_checkpoint_metadata(config, metadata)
        metadata_type, metadata_payload = _serialize_checkpoint(metadata_value, max_bytes=self._max_bytes)
        parent = config["configurable"].get("checkpoint_id")
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_checkpoints
                    (thread_id, checkpoint_ns, checkpoint_id, schema_version, owner_user_id, parent_checkpoint_id,
                     checkpoint_type, checkpoint_payload, metadata_type, metadata_payload)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id) DO UPDATE SET
                    checkpoint_payload=EXCLUDED.checkpoint_payload,
                    metadata_payload=EXCLUDED.metadata_payload,
                    updated_at=NOW()
                """,
                thread_id, checkpoint_ns, scoped["id"], self.FORMAT_VERSION, owner, parent,
                checkpoint_type, self._ciphertext(checkpoint_payload),
                metadata_type, self._ciphertext(metadata_payload),
            )
        return {"configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "checkpoint_id": scoped["id"], "user_id": owner}}

    async def aput_writes(self, config, writes, task_id: str, task_path: str = "") -> None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"]["checkpoint_id"]
        self._owner(config)
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            for idx, (channel, value) in enumerate(writes):
                value_type, payload = _serialize_checkpoint(value, max_bytes=self._max_bytes)
                await conn.execute(
                    """
                    INSERT INTO agent_checkpoint_writes
                        (thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx, channel, value_type, value_payload, task_path)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                    ON CONFLICT DO NOTHING
                    """,
                    thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel,
                    value_type, self._ciphertext(payload), task_path,
                )

    async def alist(self, config, *, filter=None, before=None, limit=None):
        if not config:
            return
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        self._owner(config)
        pool = await self._get_pool()
        query = "SELECT checkpoint_id FROM agent_checkpoints WHERE thread_id=$1 AND checkpoint_ns=$2 ORDER BY checkpoint_id DESC"
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, thread_id, checkpoint_ns)
        count = 0
        for row in rows:
            if limit is not None and count >= limit:
                break
            item = await self.aget_tuple({"configurable": {**config["configurable"], "checkpoint_id": row["checkpoint_id"]}})
            if item:
                count += 1
                yield item

    async def adelete_thread(self, thread_id: str, user_id: Optional[int] = None) -> None:
        self._owner({"configurable": {"thread_id": thread_id, "user_id": user_id}})
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM agent_checkpoints WHERE thread_id=$1", thread_id)
            await conn.execute("DELETE FROM agent_checkpoint_writes WHERE thread_id=$1", thread_id)

    async def adelete_namespace(self, thread_id: str, checkpoint_ns: str, user_id: Optional[int] = None) -> None:
        self._owner({"configurable": {"thread_id": thread_id, "user_id": user_id}})
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM agent_checkpoint_writes WHERE thread_id=$1 AND checkpoint_ns=$2", thread_id, checkpoint_ns)
            await conn.execute("DELETE FROM agent_checkpoints WHERE thread_id=$1 AND checkpoint_ns=$2", thread_id, checkpoint_ns)

    async def cleanup_expired(self, max_age_seconds: Optional[int] = None) -> int:
        from app.core.config import settings
        age = int(max_age_seconds or settings.AGENT_CHECKPOINT_RETENTION_SECONDS)
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM agent_checkpoints WHERE updated_at < NOW() - ($1::text || ' seconds')::interval",
                age,
            )
            await conn.execute(
                "DELETE FROM agent_checkpoint_writes w WHERE NOT EXISTS (SELECT 1 FROM agent_checkpoints c WHERE c.thread_id=w.thread_id AND c.checkpoint_ns=w.checkpoint_ns AND c.checkpoint_id=w.checkpoint_id)"
            )
        try:
            return int(result.rsplit(" ", 1)[-1])
        except (ValueError, IndexError):
            return 0

    # Synchronous methods are intentionally unavailable for the async Postgres saver.
    def get_tuple(self, config):
        raise RuntimeError("PostgresCheckpointSaver 必须通过 aget_tuple 使用")

    def put(self, *args, **kwargs):
        raise RuntimeError("PostgresCheckpointSaver 必须通过 aput 使用")

    def put_writes(self, *args, **kwargs):
        raise RuntimeError("PostgresCheckpointSaver 必须通过 aput_writes 使用")


_DEFAULT_SAVER: Optional[Any] = None
_DEFAULT_SAVER_PATH: Optional[str] = None
_DEFAULT_SAVER_LOCK = threading.Lock()


def get_default_checkpoint_saver() -> Optional[Any]:
    """Return the configured process/shared checkpoint saver."""

    from app.core.config import settings

    if not settings.AGENT_CHECKPOINT_ENABLED:
        return None
    global _DEFAULT_SAVER, _DEFAULT_SAVER_PATH
    backend = settings.AGENT_CHECKPOINT_BACKEND.lower().strip()
    path = (
        settings.AGENT_CHECKPOINT_POSTGRES_URL
        if backend == "postgres"
        else str(Path(settings.AGENT_CHECKPOINT_PATH).resolve())
    )
    with _DEFAULT_SAVER_LOCK:
        if _DEFAULT_SAVER is None or _DEFAULT_SAVER_PATH != path:
            if backend == "postgres":
                _DEFAULT_SAVER = PostgresCheckpointSaver(
                    settings.AGENT_CHECKPOINT_POSTGRES_URL,
                    max_bytes=settings.AGENT_CHECKPOINT_MAX_BYTES,
                )
            elif backend == "file":
                _DEFAULT_SAVER = PersistentCheckpointSaver(path)
            else:
                raise ValueError("AGENT_CHECKPOINT_BACKEND 只能是 file 或 postgres")
            _DEFAULT_SAVER_PATH = path
        return _DEFAULT_SAVER


async def initialize_checkpoint_store() -> None:
    saver = get_default_checkpoint_saver()
    if saver is not None and hasattr(saver, "setup"):
        await saver.setup()
    if saver is not None and hasattr(saver, "cleanup_expired"):
        cleanup = saver.cleanup_expired()
        if hasattr(cleanup, "__await__"):
            await cleanup


async def close_checkpoint_store() -> None:
    global _DEFAULT_SAVER
    saver = _DEFAULT_SAVER
    if saver is not None and hasattr(saver, "close"):
        await saver.close()
