"""Async Redis client factory and FastAPI dependency."""

from collections.abc import AsyncIterator

from fastapi import Request
from redis.asyncio import Redis

from app.core.config import get_settings


def create_redis_client() -> Redis:
    """Create a Redis client bound to the configured URL.

    The client connects lazily; explicit ``await client.ping()`` is used by
    health checks to verify availability. Short timeouts make readiness
    probes fail fast instead of hanging.
    """
    return Redis.from_url(
        get_settings().redis_url,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
        protocol=2,  # RESP2 for broad compatibility (Redis 3.0+; avoids HELLO on old servers)
    )


async def get_redis(request: Request) -> AsyncIterator[Redis]:
    """FastAPI dependency returning the application-wide Redis client."""
    yield request.app.state.redis
