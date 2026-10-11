"""Rate limiting configuration for API protection.

Implements IP-based rate limiting to prevent brute force attacks and abuse.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Fix Windows GBK encoding issue when reading .env file
import starlette.config
_original_read_file = starlette.config.Config._read_file
def _fixed_read_file(self, env_file):
    with open(env_file, 'r', encoding='utf-8', errors='replace') as f:
        return f.readlines()
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