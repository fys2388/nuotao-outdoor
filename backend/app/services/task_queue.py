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
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from redis.asyncio import Redis

from app.core.config import get_settings

# Fields stored inside each stream message.
FIELD_TASK_ID = "task_id"
FIELD_WORKSPACE_ID = "workspace_id"
FIELD_ATTEMPT = "attempt"


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
    async def stream_length(self, stream: str) -> int: ...
    async def ensure_group(self, stream: str, group: str) -> None: ...
    async def add_delayed(self, key: str, member: str, score: float) -> None: ...
    async def pop_delayed_due(self, key: str, now: float) -> list[str]: ...
    async def delayed_count(self, key: str) -> int: ...
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
        result = await self.redis.xreadgroup(
            group,
            consumer,
            {stream: ">"},
            count=count,
            block=block_ms,
        )
        messages: list[StreamMessage] = []
        for _stream_name, entries in result or []:
            for message_id, fields in entries:
                messages.append(StreamMessage(message_id=message_id, fields=dict(fields)))
        return messages

    async def ack(self, stream: str, group: str, message_id: str) -> None:
        await self.redis.xack(stream, group, message_id)

    async def stream_length(self, stream: str) -> int:
        return int(await self.redis.xlen(stream) or 0)

    async def ensure_group(self, stream: str, group: str) -> None:
        try:
            await self.redis.xgroup_create(stream, group, id="0", mkstream=True)
        except Exception:  # noqa: BLE001 - group already exists
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

    async def close(self) -> None:
        await self.redis.aclose()


class MemoryStreamBackend:
    """In-memory backend with the same semantics (used by tests/dev)."""

    def __init__(self) -> None:
        self._streams: dict[str, list[StreamMessage]] = {}
        self._pending: dict[str, set[str]] = {}
        self._delayed: dict[str, list[tuple[float, str]]] = {}
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
        self._pending.setdefault(stream, set()).update(m.message_id for m in taken)
        return taken

    async def ack(self, stream: str, group: str, message_id: str) -> None:
        self._pending.setdefault(stream, set()).discard(message_id)

    async def stream_length(self, stream: str) -> int:
        return len(self._streams.get(stream, []))

    async def ensure_group(self, stream: str, group: str) -> None:
        self._streams.setdefault(stream, [])
        self._pending.setdefault(stream, set())

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


def build_message(
    *,
    workspace_id: UUID,
    task_id: UUID,
    attempt: int,
) -> dict[str, str]:
    """Build the stream message fields for one task attempt."""
    return {
        FIELD_WORKSPACE_ID: str(workspace_id),
        FIELD_TASK_ID: str(task_id),
        FIELD_ATTEMPT: str(attempt),
    }


def parse_message(fields: dict[str, str]) -> dict[str, Any]:
    """Decode stream message fields into typed values."""
    return {
        "workspace_id": UUID(fields[FIELD_WORKSPACE_ID]),
        "task_id": UUID(fields[FIELD_TASK_ID]),
        "attempt": int(fields.get(FIELD_ATTEMPT, "1")),
    }


async def enqueue_task(
    backend: TaskQueueBackend,
    *,
    workspace_id: UUID,
    task_id: UUID,
    attempt: int = 1,
) -> str:
    """Publish one task message into the stream."""
    return await backend.add(
        task_stream(),
        build_message(workspace_id=workspace_id, task_id=task_id, attempt=attempt),
        maxlen=get_settings().task_queue_maxlen,
    )


async def enqueue_delayed_retry(
    backend: TaskQueueBackend,
    *,
    workspace_id: UUID,
    task_id: UUID,
    attempt: int,
    delay_seconds: float,
) -> None:
    """Schedule a retry at ``now + delay_seconds`` in the delayed ZSET."""
    member = json.dumps(build_message(workspace_id=workspace_id, task_id=task_id, attempt=attempt))
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
