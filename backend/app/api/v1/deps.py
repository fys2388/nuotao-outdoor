"""Shared API dependencies (auth, role checks, etc).

Centralizes reusable FastAPI dependencies so endpoint modules can import
them without circular imports. ``get_current_user`` and ``require_role``
were originally defined in ``endpoints/auth.py`` and are re-exported here
for backwards compatibility.
"""

from __future__ import annotations

from app.api.v1.endpoints.auth import get_current_user, require_role

__all__ = ["get_current_user", "require_role"]
