"""Task queue over Redis Streams (Phase 1; no Celery/Kafka).

A modular-monolith queue: producers ``XADD`` task messages into one stream,
the worker consumes them through a consumer group (``XREADGROUP``/``XACK``).
Delayed retries live in a Redis ZSET (score = retry timestamp) so they
survive worker restarts; the worker re-adds due messages to the stream.

The backend is a small protocol so tests can use the in-memory
:class:`MemoryStreamBackend` (identical semantics, no Redis server needed).
Every queue mutation is audit-first: the caller writes ``event_log`` rows and
the task row remains the source of truth (the worker re-checks task status
before starting, making redeliveries idempotent).

Delivery semantics (M5.3, documented - never claim more than this):
- Redis Streams provide **at-least-once** delivery: a message may be
  delivered more than once (producer retry, worker crash + XAUTOCLAIM,
  duplicate XADD). Redis does NOT provide exactly-once.
- The PostgreSQL task/execution rows are the **business source of truth**;
  the worker only executes a task whose row is still ``pending``, so the
  business effect is **effectively-once / idempotent**.
- Message-level dedup (``dedup_key`` = idempotency_key + attempt when the
  task has one, else workspace + task + attempt) is a Redis-side
  optimization that stops concurrent duplicate deliveries before they reach
  the DB guard. It is never the source of truth.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from redis.asyncio import Redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Fields stored inside each stream message.
FIELD_TASK_ID = "task_id"
FIELD_WORKSPACE_ID = "workspace_id"
FIELD_ATTEMPT = "attempt"
FIELD_DEDUP_KEY = "dedup_key"


@dataclass(frozen=True)
class StreamMessage:
    """One message read from a stream consumer group."""

    message_id: str
    fields: dict[str, str]


class TaskQueueBackend(Protocol):
    """Minimal Redis-Stream-compatible interface used by producer/worker."""

    async def add(self, stream: str, fields: dict[str, str], *, maxlen: int = 1000) -> str: ...
    async def read_group(
        self,
        stream: str,
        group: str,
        consumer: str,
        *,
        count: int = 10,
        block_ms: int = 0,
    ) -> list[StreamMessage]: ...
    async def ack(self, stream: str, group: str, message_id: str) -> None: ...
    async def reclaim_orphaned(
        self,
        stream: str,
        group: str,
        consumer: str,
        *,
        min_idle_ms: int,
        count: int,
    ) -> list[StreamMessage]: ...
    async def stream_length(self, stream: str) -> int: ...
    async def ensure_group(self, stream: str, group: str) -> None: ...
    async def add_delayed(self, key: str, member: str, score: float) -> None: ...
    async def pop_delayed_due(self, key: str, now: float) -> list[str]: ...
    async def delayed_count(self, key: str) -> int: ...
    async def dedup_claim(
        self, key: str, ttl_seconds: int, *, stale_after_seconds: float
    ) -> bool: ...
    async def dedup_release(self, key: str) -> None: ...
    async def ping(self) -> bool: ...
    async def healthcheck(self) -> dict[str, Any]: ...
    async def hash_set(self, key: str, mapping: dict[str, str], ttl_seconds: int) -> None: ...
    async def hash_get_all(self, key: str) -> dict[str, str]: ...
    async def scan_keys(self, pattern: str) -> list[str]: ...
    async def key_ttl(self, key: str) -> int: ...
    async def close(self) -> None: ...


class RedisStreamBackend:
    """Production backend backed by Redis Streams (consumer groups)."""

    def __init__(self, redis: Redis, *, decode: bool = True) -> None:
        self.redis = redis

    async def add(self, stream: str, fields: dict[str, str], *, maxlen: int = 1000) -> str:
        message_id = await self.redis.xadd(stream, fields, maxlen=maxlen, approximate=True)
        return message_id

    async def read_group(
        self,
        stream: str,
        group: str,
        consumer: str,
        *,
        count: int = 10,
        block_ms: int = 0,
    ) -> list[StreamMessage]:
        await self.ensure_group(stream, group)
        # ``block_ms == 0`` means "do not block" in this codebase's protocol
        # (memory backend semantics). redis-py sends ``BLOCK 0`` when ``0`` is
        # passed, which blocks *forever* in the Redis protocol - so only pass
        # BLOCK for a bounded wait.
        result = await self.redis.xreadgroup(
            group,
            consumer,
            {stream: ">"},
            count=count,
            block=block_ms if block_ms > 0 else None,
        )
        messages: list[StreamMessage] = []
        for _stream_name, entries in result or []:
            for message_id, fields in entries:
                messages.append(StreamMessage(message_id=message_id, fields=dict(fields)))
        return messages

    async def ack(self, stream: str, group: str, message_id: str) -> None:
        await self.redis.xack(stream, group, message_id)

    async def reclaim_orphaned(
        self,
        stream: str,
        group: str,
        consumer: str,
        *,
        min_idle_ms: int,
        count: int,
    ) -> list[StreamMessage]:
        """Reclaim PEL messages left by crashed workers (XAUTOCLAIM)."""
        await self.ensure_group(stream, group)
        result = await self.redis.xautoclaim(
            stream,
            group,
            consumer,
            min_idle_ms,
            start_id="0-0",
            count=count,
        )
        entries: list[tuple[str, dict]] = []
        if isinstance(result, dict):
            # RESP3 style: {"next": ..., "entries": [...], "deleted": [...]}
            entries = result.get("entries") or []
        elif isinstance(result, (list, tuple)) and len(result) >= 2:
            entries = result[1]
        reclaimed: list[StreamMessage] = []
        for message_id, fields in entries:
            reclaimed.append(StreamMessage(message_id=message_id, fields=dict(fields)))
        if reclaimed:
            logger.info(
                "reclaimed %s orphaned message(s) from %s (consumer=%s)",
                len(reclaimed),
                stream,
                consumer,
            )
        return reclaimed

    async def stream_length(self, stream: str) -> int:
        return int(await self.redis.xlen(stream) or 0)

    async def ensure_group(self, stream: str, group: str) -> None:
        try:
            await self.redis.xgroup_create(stream, group, id="0", mkstream=True)
        except Exception:
            pass

    async def add_delayed(self, key: str, member: str, score: float) -> None:
        await self.redis.zadd(key, {member: score})

    async def pop_delayed_due(self, key: str, now: float) -> list[str]:
        due = await self.redis.zrangebyscore(key, 0, now, start=0, num=100)
        if due:
            await self.redis.zrem(key, *due)
        return due

    async def delayed_count(self, key: str) -> int:
        return int(await self.redis.zcard(key) or 0)

    async def dedup_claim(self, key: str, ttl_seconds: int, *, stale_after_seconds: float) -> bool:
        """Atomically claim a message-level dedup token (SET NX EX).

        The token stores the claim time so a token orphaned by a crashed
        worker becomes stealable after ``stale_after_seconds`` (aligned with
        the reclaim idle threshold): duplicate deliveries of a *live* message
        are skipped, while a message left by a crashed worker can still be
        reclaimed and reprocessed. Returns True when this worker may proceed.
        """
        value = json.dumps({"claimed_at": time.time()})
        if await self.redis.set(key, value, nx=True, ex=ttl_seconds):
            return True
        existing = await self.redis.get(key)
        claimed_at = 0.0
        if existing:
            try:
                claimed_at = float(json.loads(existing).get("claimed_at", 0.0) or 0.0)
            except (TypeError, ValueError):
                claimed_at = 0.0
        # A fresh claim blocks duplicates; an orphaned (stale) claim is
        # stealable so a crashed worker's message can still be recovered.
        if time.time() - claimed_at < stale_after_seconds:
            return False
        await self.redis.set(key, value, ex=ttl_seconds)
        return True

    async def dedup_release(self, key: str) -> None:
        """Drop a dedup token (used when a message is deferred, never failed)."""
        await self.redis.delete(key)

    async def ping(self) -> bool:
        """Return True when the Redis server answers PING."""
        try:
            return bool(await self.redis.ping())
        except Exception:
            return False

    async def healthcheck(self) -> dict[str, Any]:
        """Raw backend health facts consumed by the queue health service."""
        settings = get_settings()
        stream = task_stream()
        group = settings.task_queue_group
        info: dict[str, Any] = {
            "ping": False,
            "stream_exists": False,
            "group_exists": False,
            "pending_count": 0,
            "stale_pending_count": 0,
        }
        info["ping"] = await self.ping()
        if not info["ping"]:
            return info
        try:
            info["stream_exists"] = bool(await self.redis.exists(stream))
        except Exception:
            return info
        if not info["stream_exists"]:
            return info
        try:
            groups = await self.redis.xinfo_groups(stream)
            info["group_exists"] = any(str(group_row.get("name")) == group for group_row in groups)
        except Exception:
            pass
        try:
            pending = await self.redis.xpending(stream, group)
            if isinstance(pending, dict):
                info["pending_count"] = int(pending.get("pending", 0) or 0)
            elif isinstance(pending, (list, tuple)):
                info["pending_count"] = len(pending)
        except Exception:
            pass
        try:
            stale = await self.redis.xpending(
                stream,
                group,
                idle=settings.task_queue_reclaim_idle_ms,
                min="-",
                max="+",
                count=10,
            )
            info["stale_pending_count"] = len(stale)
        except Exception:
            pass
        return info

    async def hash_set(self, key: str, mapping: dict[str, str], ttl_seconds: int) -> None:
        await self.redis.hset(key, mapping=mapping)
        await self.redis.expire(key, ttl_seconds)

    async def hash_get_all(self, key: str) -> dict[str, str]:
        return dict(await self.redis.hgetall(key) or {})

    async def scan_keys(self, pattern: str) -> list[str]:
        return [key async for key in self.redis.scan_iter(match=pattern)]

    async def key_ttl(self, key: str) -> int:
        return int(await self.redis.ttl(key) or 0)

    async def close(self) -> None:
        await self.redis.aclose()


class MemoryStreamBackend:
    """In-memory backend with the same semantics (used by tests/dev)."""

    def __init__(self) -> None:
        self._streams: dict[str, list[StreamMessage]] = {}
        # message_id -> (claimed_at, message) for messages delivered but not
        # yet acked (the in-memory analog of the Redis PEL).
        self._pending: dict[str, dict[str, tuple[float, StreamMessage]]] = {}
        self._delayed: dict[str, list[tuple[float, str]]] = {}
        self._dedup: dict[str, tuple[float, float]] = {}
        self._hashes: dict[str, tuple[float, dict[str, str]]] = {}
        self._counter: int = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"{int(time.time() * 1000)}-{self._counter}"

    async def add(self, stream: str, fields: dict[str, str], *, maxlen: int = 1000) -> str:
        message = StreamMessage(message_id=self._next_id(), fields=dict(fields))
        bucket = self._streams.setdefault(stream, [])
        bucket.append(message)
        if len(bucket) > maxlen:
            del bucket[: len(bucket) - maxlen]
        return message.message_id

    async def read_group(
        self,
        stream: str,
        group: str,
        consumer: str,
        *,
        count: int = 10,
        block_ms: int = 0,
    ) -> list[StreamMessage]:
        await self.ensure_group(stream, group)
        bucket = self._streams.setdefault(stream, [])
        taken = bucket[:count]
        del bucket[:count]
        now = time.time()
        pending = self._pending.setdefault(stream, {})
        for message in taken:
            pending[message.message_id] = (now, message)
        return taken

    async def ack(self, stream: str, group: str, message_id: str) -> None:
        self._pending.setdefault(stream, {}).pop(message_id, None)

    async def reclaim_orphaned(
        self,
        stream: str,
        group: str,
        consumer: str,
        *,
        min_idle_ms: int,
        count: int,
    ) -> list[StreamMessage]:
        """Return pending messages idle for >= min_idle_ms and re-claim them."""
        self._pending.setdefault(stream, {})
        now = time.time()
        threshold = now - (min_idle_ms / 1000.0)
        candidates = [
            (claimed_at, message)
            for claimed_at, message in self._pending[stream].values()
            if claimed_at <= threshold
        ]
        candidates.sort(key=lambda item: item[0])
        reclaimed = [message for _claimed_at, message in candidates[:count]]
        for message in reclaimed:
            self._pending[stream][message.message_id] = (now, message)
        return reclaimed

    async def stream_length(self, stream: str) -> int:
        return len(self._streams.get(stream, []))

    async def ensure_group(self, stream: str, group: str) -> None:
        self._streams.setdefault(stream, [])
        self._pending.setdefault(stream, {})

    async def add_delayed(self, key: str, member: str, score: float) -> None:
        bucket = self._delayed.setdefault(key, [])
        bucket.append((score, member))
        bucket.sort(key=lambda item: item[0])

    async def pop_delayed_due(self, key: str, now: float) -> list[str]:
        bucket = self._delayed.get(key, [])
        due = [member for score, member in bucket if score <= now]
        self._delayed[key] = [(score, member) for score, member in bucket if score > now]
        return due

    async def delayed_count(self, key: str) -> int:
        return len(self._delayed.get(key, []))

    async def dedup_claim(self, key: str, ttl_seconds: int, *, stale_after_seconds: float) -> bool:
        now = time.time()
        existing = self._dedup.get(key)
        if existing is not None:
            expires_at, claimed_at = existing
            if expires_at > now and now - claimed_at < stale_after_seconds:
                return False
        self._dedup[key] = (now + ttl_seconds, now)
        return True

    async def dedup_release(self, key: str) -> None:
        self._dedup.pop(key, None)

    async def ping(self) -> bool:
        return True

    async def healthcheck(self) -> dict[str, Any]:
        stream = task_stream()
        return {
            "ping": True,
            "stream_exists": True,
            "group_exists": True,
            "pending_count": len(self._pending.get(stream, {})),
            "stale_pending_count": 0,
        }

    async def hash_set(self, key: str, mapping: dict[str, str], ttl_seconds: int) -> None:
        self._hashes[key] = (time.time() + ttl_seconds, dict(mapping))

    async def hash_get_all(self, key: str) -> dict[str, str]:
        entry = self._hashes.get(key)
        if entry is None:
            return {}
        expires_at, mapping = entry
        if expires_at <= time.time():
            self._hashes.pop(key, None)
            return {}
        return dict(mapping)

    async def scan_keys(self, pattern: str) -> list[str]:
        prefix = pattern.rstrip("*")
        return [key for key in self._hashes if key.startswith(prefix)]

    async def key_ttl(self, key: str) -> int:
        entry = self._dedup.get(key)
        if entry is None:
            return -2
        remaining = int(entry[0] - time.time())
        return max(remaining, 0)

    async def close(self) -> None:
        return None


_BACKEND_CACHE: dict[str, TaskQueueBackend] = {}


def get_queue_backend() -> TaskQueueBackend:
    """Return the configured queue backend singleton (redis or memory)."""
    settings = get_settings()
    key = f"{settings.task_queue_backend}:{settings.redis_url}"
    if key in _BACKEND_CACHE:
        return _BACKEND_CACHE[key]
    if settings.task_queue_backend == "memory":
        backend: TaskQueueBackend = MemoryStreamBackend()
    else:
        backend = RedisStreamBackend(
            Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
        )
    _BACKEND_CACHE[key] = backend
    return backend


def reset_queue_backend_cache() -> None:
    """Drop cached backends (used by tests to switch backend mode)."""
    _BACKEND_CACHE.clear()


def task_stream() -> str:
    """Return the configured task stream name."""
    return get_settings().task_queue_stream


def retry_key() -> str:
    """Return the configured delayed-retry ZSET key."""
    return get_settings().task_queue_retry_key


def build_dedup_key(
    *,
    workspace_id: UUID,
    task_id: UUID,
    attempt: int,
    idempotency_key: str | None = None,
) -> str:
    """Stable message-level dedup identity (never a random UUID).

    Prefers the producer idempotency key (task-level, stable across producer
    retries) combined with the attempt number so retries remain distinct;
    falls back to ``workspace_id + task_id + attempt``.
    """
    if idempotency_key:
        prefix = get_settings().task_queue_dedup_key_prefix
        return f"{prefix}:idem:{workspace_id}:{idempotency_key}:{attempt}"
    return f"{get_settings().task_queue_dedup_key_prefix}:{workspace_id}:{task_id}:{attempt}"


def build_message(
    *,
    workspace_id: UUID,
    task_id: UUID,
    attempt: int,
    idempotency_key: str | None = None,
) -> dict[str, str]:
    """Build the stream message fields for one task attempt."""
    return {
        FIELD_WORKSPACE_ID: str(workspace_id),
        FIELD_TASK_ID: str(task_id),
        FIELD_ATTEMPT: str(attempt),
        FIELD_DEDUP_KEY: build_dedup_key(
            workspace_id=workspace_id,
            task_id=task_id,
            attempt=attempt,
            idempotency_key=idempotency_key,
        ),
    }


def parse_message(fields: dict[str, str]) -> dict[str, Any]:
    """Decode stream message fields into typed values."""
    return {
        "workspace_id": UUID(fields[FIELD_WORKSPACE_ID]),
        "task_id": UUID(fields[FIELD_TASK_ID]),
        "attempt": int(fields.get(FIELD_ATTEMPT, "1")),
        "dedup_key": fields.get(FIELD_DEDUP_KEY),
    }


async def enqueue_task(
    backend: TaskQueueBackend,
    *,
    workspace_id: UUID,
    task_id: UUID,
    attempt: int = 1,
    idempotency_key: str | None = None,
) -> str:
    """Publish one task message into the stream."""
    return await backend.add(
        task_stream(),
        build_message(
            workspace_id=workspace_id,
            task_id=task_id,
            attempt=attempt,
            idempotency_key=idempotency_key,
        ),
        maxlen=get_settings().task_queue_maxlen,
    )


async def enqueue_delayed_retry(
    backend: TaskQueueBackend,
    *,
    workspace_id: UUID,
    task_id: UUID,
    attempt: int,
    delay_seconds: float,
    idempotency_key: str | None = None,
) -> None:
    """Schedule a retry at ``now + delay_seconds`` in the delayed ZSET."""
    member = json.dumps(
        build_message(
            workspace_id=workspace_id,
            task_id=task_id,
            attempt=attempt,
            idempotency_key=idempotency_key,
        )
    )
    await backend.add_delayed(retry_key(), member, time.time() + delay_seconds)


async def flush_delayed(backend: TaskQueueBackend) -> int:
    """Re-add due delayed retries to the stream; returns number flushed."""
    due = await backend.pop_delayed_due(retry_key(), time.time())
    for member in due:
        fields = json.loads(member)
        await backend.add(
            task_stream(),
            fields,
            maxlen=get_settings().task_queue_maxlen,
        )
    return len(due)


async def queue_stats(backend: TaskQueueBackend) -> dict[str, Any]:
    """Return shallow queue health stats (no business data)."""
    return {
        "backend": get_settings().task_queue_backend,
        "stream": task_stream(),
        "stream_length": await backend.stream_length(task_stream()),
        "delayed_count": await backend.delayed_count(retry_key()),
    }
