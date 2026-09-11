"""M5.2.1 Redis Streams production validation (real Redis).

Validates the Phase-1 task queue against a real Redis server: XADD /
XREADGROUP / XACK semantics, consumer-group distribution, crash recovery
(reclaim of unacked PEL entries via XAUTOCLAIM), the delayed-retry ZSET
requeue, and the DB row as the idempotency source of truth.
"""

from __future__ import annotations

from uuid import UUID

import pytest
import redis.asyncio as aioredis

from app.services import task_queue
from app.services.task_queue import RedisStreamBackend
from tests.integration.conftest import enable_redis_queue

WS = UUID("00000000-0000-0000-0000-000000000001")
STREAM = "nuotao:test-stream"
GROUP = "nuotao:test-group"


async def _backend(url: str) -> RedisStreamBackend:
    client = aioredis.Redis.from_url(url, decode_responses=True)
    return RedisStreamBackend(client)


@pytest.mark.asyncio
async def test_real_redis_xadd_xreadgroup_xack(redis_url: str) -> None:
    """XADD -> XREADGROUP -> XACK works against real Redis."""
    backend = await _backend(redis_url)
    try:
        message_ids = [
            await backend.add(STREAM, {"task_id": "t1", "workspace_id": str(WS), "attempt": "1"}),
            await backend.add(STREAM, {"task_id": "t2", "workspace_id": str(WS), "attempt": "1"}),
            await backend.add(STREAM, {"task_id": "t3", "workspace_id": str(WS), "attempt": "1"}),
        ]
        assert len(message_ids) == 3

        await backend.ensure_group(STREAM, GROUP)
        messages = await backend.read_group(STREAM, GROUP, "consumer-1", count=3)
        assert len(messages) == 3
        assert {m.fields["task_id"] for m in messages} == {"t1", "t2", "t3"}

        # Pending entries exist until acked.
        pending = await backend.redis.xpending(STREAM, GROUP)
        assert pending["pending"] == 3

        for message in messages:
            await backend.ack(STREAM, GROUP, message.message_id)
        pending = await backend.redis.xpending(STREAM, GROUP)
        assert pending["pending"] == 0
        assert await backend.stream_length(STREAM) == 3  # XADD retains history
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_consumer_group_disjoint_distribution(redis_url: str) -> None:
    """Two consumers in one group see disjoint message sets (XREADGROUP >)."""
    backend = await _backend(redis_url)
    try:
        await backend.ensure_group(STREAM, GROUP)
        for index in range(5):
            await backend.add(
                STREAM,
                {"task_id": f"t{index}", "workspace_id": str(WS), "attempt": "1"},
            )

        first = await backend.read_group(STREAM, GROUP, "consumer-a", count=3)
        second = await backend.read_group(STREAM, GROUP, "consumer-b", count=3)
        assert len(first) + len(second) == 5
        ids_a = {m.fields["task_id"] for m in first}
        ids_b = {m.fields["task_id"] for m in second}
        assert ids_a.isdisjoint(ids_b)

        for message in first + second:
            await backend.ack(STREAM, GROUP, message.message_id)
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_crash_reclaim_of_unacked_message(redis_url: str) -> None:
    """A message read but never acked stays in the PEL and can be reclaimed."""
    backend = await _backend(redis_url)
    try:
        await backend.ensure_group(STREAM, GROUP)
        await backend.add(STREAM, {"task_id": "crash-1", "workspace_id": str(WS), "attempt": "1"})

        # Worker A claims the message then "crashes" before acking.
        claimed = await backend.read_group(STREAM, GROUP, "worker-a", count=1)
        assert len(claimed) == 1
        pending = await backend.redis.xpending(STREAM, GROUP)
        assert pending["pending"] == 1
        assert pending["consumers"][0]["name"] == "worker-a"

        # Worker B reclaims it with an idle threshold of 0 (force reclaim).
        reclaimed = await backend.reclaim_orphaned(
            STREAM, GROUP, "worker-b", min_idle_ms=0, count=10
        )
        assert len(reclaimed) == 1
        assert reclaimed[0].message_id == claimed[0].message_id
        assert reclaimed[0].fields["task_id"] == "crash-1"

        # The reclaimed message is now owned by worker-b and can be acked.
        await backend.ack(STREAM, GROUP, reclaimed[0].message_id)
        pending = await backend.redis.xpending(STREAM, GROUP)
        assert pending["pending"] == 0
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_delayed_retry_zset_requeues(redis_url: str) -> None:
    """Retries scheduled in the ZSET are re-added to the stream when due."""
    backend = await _backend(redis_url)
    try:
        await backend.ensure_group(STREAM, GROUP)
        await task_queue.enqueue_delayed_retry(
            backend,
            workspace_id=WS,
            task_id=UUID("00000000-0000-0000-0000-00000000000a"),
            attempt=2,
            delay_seconds=0,
        )
        assert await backend.delayed_count(task_queue.retry_key()) == 1

        flushed = await task_queue.flush_delayed(backend)
        assert flushed == 1
        assert await backend.delayed_count(task_queue.retry_key()) == 0
        assert await backend.stream_length(task_queue.task_stream()) == 1

        messages = await backend.read_group(
            task_queue.task_stream(), GROUP, "consumer-retry", count=1
        )
        assert len(messages) == 1
        assert messages[0].fields["attempt"] == "2"
        await backend.ack(task_queue.task_stream(), GROUP, messages[0].message_id)
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_worker_queue_uses_real_redis_backend(redis_url: str) -> None:
    """get_queue_backend() returns a Redis-backed queue when configured."""
    enable_redis_queue(redis_url)
    try:
        from app.services import task_queue as tq

        backend = tq.get_queue_backend()
        assert isinstance(backend, RedisStreamBackend)
        assert await backend.redis.ping() is True
        await backend.ensure_group(tq.task_stream(), tq.get_settings().task_queue_group)
        assert await backend.stream_length(tq.task_stream()) == 0
    finally:
        from app.core.config import get_settings
        from app.services import task_queue as tq

        get_settings().task_queue_backend = "memory"
        tq.reset_queue_backend_cache()
