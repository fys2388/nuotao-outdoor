"""Rate limiting configuration for API protection.

Implements IP-based rate limiting to prevent brute force attacks and abuse.
"""

# Fix Windows GBK encoding issue when reading .env file
import starlette.config
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

_original_read_file = starlette.config.Config._read_file


def _fixed_read_file(self, *args, **kwargs):
    # starlette>=1.0 调用 _read_file(env_file, encoding)，旧版只传 env_file。
    # 用 *args/**kwargs 兼容两种签名;核心修复:未提供 encoding 时补 utf-8,
    # 委托回原始 _read_file(保持其 dict 返回契约),避免 Windows GBK 报错。
    if len(args) < 2 and "encoding" not in kwargs:
        kwargs["encoding"] = "utf-8"
    return _original_read_file(self, *args, **kwargs)


starlette.config.Config._read_file = _fixed_read_file

# Rate limits:
# - Default: 100 requests per minute per IP
# - Auth endpoints: 10 requests per minute (brute force protection)
# - Admin endpoints: 50 requests per minute
RATE_LIMIT_DEFAULT = "100/minute"
RATE_LIMIT_AUTH = "10/minute"
RATE_LIMIT_ADMIN = "50/minute"

# Create limiter instance
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[RATE_LIMIT_DEFAULT],
    storage_uri="memory://",  # In-memory for now; can be Redis in production
)


def rate_limit_exceeded_handler(app, exc: RateLimitExceeded):
    """Handle rate limit exceeded errors with JSON response."""
    return {
        "error": "rate_limit_exceeded",
        "message": f"Rate limit exceeded. Limit: {exc.limit}",
        "retry_after": exc.time_to_expiration,
    }
