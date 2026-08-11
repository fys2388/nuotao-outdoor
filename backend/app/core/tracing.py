"""Request tracing: propagates a trace_id through logs and responses.

The middleware assigns (or forwards) a ``trace_id`` per request and stores it
in a context variable so any log emitted during handling carries it. The same
id is written into ``event_log``, rule execution logs and order rows, enabling
full-chain audit trails.
"""

import logging
from contextvars import ContextVar
from uuid import uuid4

_trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)

TRACE_ID_HEADER = "x-trace-id"


def get_trace_id() -> str | None:
    """Return the trace id for the current request context (if any)."""
    return _trace_id_var.get()


def new_trace_id() -> str:
    """Generate a new trace id."""
    return uuid4().hex


def set_trace_id(trace_id: str) -> object:
    """Set the trace id for the current context; returns a reset token."""
    return _trace_id_var.set(trace_id)


def reset_trace_id(token: object) -> None:
    """Restore the previous trace id context using the reset token."""
    _trace_id_var.reset(token)


class TraceIdFilter(logging.Filter):
    """Logging filter that attaches the current trace_id to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = _trace_id_var.get() or "-"
        return True
