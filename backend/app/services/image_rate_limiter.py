"""Rate limiter for image generation.

Implements batch-level rate limiting for Agnes AI (and other providers)
to avoid hitting free-tier quotas (10 images/session).

Strategy:
- Token bucket: allows N requests per window, refills over time
- Batch queue: limits concurrent image generations
- Exponential backoff: 429 retries with 3s → 6s → 12s delays
- Quota tracking: warns when approaching quota limit

Usage:
    from app.services.image_rate_limiter import get_rate_limiter

    limiter = get_rate_limiter("agnes")
    await limiter.acquire()  # blocks until token available
    result = await generate_image(...)
    limiter.record_success()
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limit configuration
# ---------------------------------------------------------------------------

# Agnes free tier: ~10 images per session/window
AGNES_RATE_LIMIT = {
    "max_concurrent": 3,  # Max concurrent requests
    "requests_per_minute": 5,  # Conservative: 5/min to avoid 429
    "burst_limit": 10,  # Max burst before throttling
    "retry_delays": (3.0, 6.0, 12.0),  # Exponential backoff
    "quota_per_session": 50,  # Session quota (conservative estimate)
}

# Default rate limit config for other providers
DEFAULT_RATE_LIMIT = {
    "max_concurrent": 5,
    "requests_per_minute": 20,
    "burst_limit": 20,
    "retry_delays": (1.0, 2.0, 4.0),
    "quota_per_session": 100,
}

# Rate limit configs by provider/model
RATE_LIMIT_CONFIGS: dict[str, dict[str, Any]] = {
    "agnes": AGNES_RATE_LIMIT,
    "default": DEFAULT_RATE_LIMIT,
}


# ---------------------------------------------------------------------------
# Token bucket rate limiter
# ---------------------------------------------------------------------------


@dataclass
class TokenBucket:
    """Simple token bucket rate limiter."""

    max_tokens: int
    refill_rate: float  # tokens per second
    tokens: float = 0.0
    last_refill: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        self.tokens = float(self.max_tokens)
        self.last_refill = time.monotonic()

    async def acquire(self, tokens: int = 1) -> bool:
        """Acquire tokens, blocking until available."""
        async with self.lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_refill
                self.tokens = min(
                    self.max_tokens,
                    self.tokens + elapsed * self.refill_rate,
                )
                self.last_refill = now

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True

                # Wait for tokens to refill
                needed = tokens - self.tokens
                wait_time = needed / self.refill_rate if self.refill_rate > 0 else 1.0
                await asyncio.sleep(min(wait_time, 1.0))


# ---------------------------------------------------------------------------
# Rate limiter class
# ---------------------------------------------------------------------------


class RateLimiter:
    """Rate limiter for image generation.

    Combines:
    - Token bucket for request rate limiting
    - Semaphore for concurrent request limiting
    - Quota tracking for session limits
    """

    def __init__(self, name: str = "default") -> None:
        self.name = name
        config = RATE_LIMIT_CONFIGS.get(name, DEFAULT_RATE_LIMIT)

        # Token bucket: requests per minute
        self.bucket = TokenBucket(
            max_tokens=config["burst_limit"],
            refill_rate=config["requests_per_minute"] / 60.0,
        )

        # Semaphore for concurrent requests
        self.semaphore = asyncio.Semaphore(config["max_concurrent"])

        # Quota tracking
        self._session_count = 0
        self._quota = config["quota_per_session"]
        self._lock = asyncio.Lock()

    @property
    def remaining_quota(self) -> int:
        """Remaining session quota."""
        return max(0, self._quota - self._session_count)

    @property
    def is_quota_exhausted(self) -> bool:
        """Check if session quota is exhausted."""
        return self._session_count >= self._quota

    async def acquire(self, *, timeout: float | None = None) -> bool:
        """Acquire a slot for image generation.

        Blocks until:
        1. A token is available (rate limit)
        2. A concurrent slot is available (concurrency limit)

        Returns False if quota is exhausted or timeout occurs.
        """
        if self.is_quota_exhausted:
            logger.warning(
                "Rate limiter %s: session quota exhausted (%d/%d)",
                self.name, self._session_count, self._quota,
            )
            return False

        # Acquire token (rate limit)
        acquired = await self._acquire_with_timeout(timeout)
        if not acquired:
            return False

        # Acquire concurrent slot
        if timeout is not None:
            try:
                await asyncio.wait_for(self.semaphore.acquire(), timeout=timeout)
            except asyncio.TimeoutError:
                return False
        else:
            await self.semaphore.acquire()

        return True

    async def _acquire_with_timeout(self, timeout: float | None) -> bool:
        """Acquire token with optional timeout."""
        if timeout is None:
            await self.bucket.acquire()
            return True
        try:
            async with asyncio.timeout(timeout):
                await self.bucket.acquire()
                return True
        except TimeoutError:
            return False

    def release(self) -> None:
        """Release a concurrent slot."""
        self.semaphore.release()

    async def record_success(self) -> None:
        """Record a successful image generation."""
        async with self._lock:
            self._session_count += 1
            remaining = self.remaining_quota
            if remaining <= 5:
                logger.warning(
                    "Rate limiter %s: approaching quota limit (%d remaining)",
                    self.name, remaining,
                )

    async def record_failure(self) -> None:
        """Record a failed image generation (does not count against quota)."""
        pass  # Failures don't consume quota

    def reset_session(self) -> None:
        """Reset session quota (e.g., on new API key rotation)."""
        self._session_count = 0
        logger.info("Rate limiter %s: session quota reset", self.name)

    def get_status(self) -> dict[str, Any]:
        """Get current rate limiter status."""
        return {
            "name": self.name,
            "concurrent_available": self.semaphore._value,
            "session_count": self._session_count,
            "remaining_quota": self.remaining_quota,
            "quota_exhausted": self.is_quota_exhausted,
            "tokens_available": round(self.bucket.tokens, 1),
        }


# ---------------------------------------------------------------------------
# Global rate limiters (lazy singleton)
# ---------------------------------------------------------------------------

_limiters: dict[str, RateLimiter] = {}


def get_rate_limiter(name: str = "default") -> RateLimiter:
    """Get or create a rate limiter by name."""
    if name not in _limiters:
        _limiters[name] = RateLimiter(name)
    return _limiters[name]


def get_agnes_limiter() -> RateLimiter:
    """Get the Agnes-specific rate limiter."""
    return get_rate_limiter("agnes")


def get_all_limiter_statuses() -> dict[str, dict[str, Any]]:
    """Get status of all rate limiters."""
    return {name: limiter.get_status() for name, limiter in _limiters.items()}


# ---------------------------------------------------------------------------
# Batch generation helper
# ---------------------------------------------------------------------------


async def generate_with_rate_limit(
    generator,
    *,
    limiter_name: str = "agnes",
    max_retries: int = 3,
) -> Any:
    """Generate an image with rate limiting.

    Args:
        generator: Async callable that generates the image.
        limiter_name: Rate limiter name.
        max_retries: Max retries on 429/rate limit errors.

    Returns:
        The generator result.

    Raises:
        Exception: If all retries are exhausted.
    """
    limiter = get_rate_limiter(limiter_name)
    retry_delays = RATE_LIMIT_CONFIGS.get(
        limiter_name, DEFAULT_RATE_LIMIT
    ).get("retry_delays", (1.0, 2.0, 4.0))

    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        # Acquire rate limit slot
        acquired = await limiter.acquire(timeout=60.0)
        if not acquired:
            if limiter.is_quota_exhausted:
                raise RuntimeError(
                    f"Rate limiter {limiter_name}: quota exhausted, "
                    f"wait for quota refresh"
                )
            raise RuntimeError(
                f"Rate limiter {limiter_name}: timeout waiting for slot"
            )

        try:
            result = await generator()
            await limiter.record_success()
            return result

        except Exception as exc:
            last_error = exc
            error_str = str(exc)

            # Check if this is a rate limit error
            is_rate_limit = (
                "429" in error_str
                or "rate limit" in error_str.lower()
                or "quota" in error_str.lower()
                or "too many" in error_str.lower()
            )

            if is_rate_limit and attempt < max_retries:
                delay = retry_delays[attempt] if attempt < len(retry_delays) else retry_delays[-1]
                logger.warning(
                    "Rate limited (attempt %d/%d), retrying in %.1fs",
                    attempt + 1, max_retries, delay,
                )
                await asyncio.sleep(delay)
                # Don't record failure against quota for rate limits
                continue

            # Non-rate-limit error or max retries reached
            await limiter.record_failure()
            raise

        finally:
            limiter.release()

    raise last_error or RuntimeError("Rate limiter: max retries exceeded")
