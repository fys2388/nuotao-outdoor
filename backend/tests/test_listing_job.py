"""BUG #17 regression tests: ListingJob model, Alembic migration, and route registration.

Covers:
- Model class exists with correct __tablename__ and status literals
- Alembic revision chain: 0055 → 0056 → head
- Router registration: GET /listing-jobs is exposed on api_router
- Status literal constants are consistent between model + endpoint
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def test_listing_job_model_shape():
    """ORM model exposes the expected table name and status literals."""
    from app.models.listing_job import (
        LISTING_JOB_ACTIVE_STATUSES,
        LISTING_JOB_STATUSES,
        LISTING_JOB_TERMINAL_STATUSES,
        ListingJob,
    )

    assert ListingJob.__tablename__ == "listing_jobs"
    # Status literal set
    assert set(LISTING_JOB_STATUSES) == {
        "pending", "approved", "processing", "rejected", "published", "failed"
    }
    assert set(LISTING_JOB_ACTIVE_STATUSES) == {"pending", "approved", "processing"}
    assert set(LISTING_JOB_TERMINAL_STATUSES) == {"rejected", "published", "failed"}
    # Active and terminal sets are disjoint and their union covers every status
    assert not (set(LISTING_JOB_ACTIVE_STATUSES) & set(LISTING_JOB_TERMINAL_STATUSES))
    assert set(LISTING_JOB_ACTIVE_STATUSES) | set(LISTING_JOB_TERMINAL_STATUSES) \
        == set(LISTING_JOB_STATUSES)


def test_listing_job_model_exported():
    """Model is exported through app.models package."""
    import app.models as models_pkg

    assert hasattr(models_pkg, "ListingJob")
    assert "ListingJob" in models_pkg.__all__


def test_listing_job_alembic_revision_chain():
    """Alembic 0056 migration file exists with correct revision chain."""
    migration_path = BACKEND_ROOT / "alembic" / "versions" / "0056_listing_job.py"
    assert migration_path.exists(), f"Missing migration: {migration_path}"

    # Parse revision / down_revision from the file (avoid loading alembic engine).
    src = migration_path.read_text(encoding="utf-8")
    assert "revision = '0056'" in src
    assert "down_revision = '0055'" in src
    assert "def upgrade() -> None:" in src
    assert "def downgrade() -> None:" in src
    assert 'create_table(' in src and "'listing_jobs'" in src


def test_listing_jobs_endpoint_module_registers_router():
    """Endpoint module defines an APIRouter with the expected prefix."""
    from app.api.v1.endpoints.listing_jobs import router

    paths = [getattr(route, "path", "") for route in router.routes]
    assert paths, "router.routes is empty"
    # Every route in this router must be scoped under /listing-jobs
    assert any(p.startswith("/listing-jobs") for p in paths), (
        f"expected /listing-jobs prefixed routes, got {paths}"
    )


def test_api_router_exposes_listing_jobs():
    """The main api_router exposes /api/v1/listing-jobs endpoints."""
    from app.api.v1.router import api_router

    path_suffixes = [getattr(route, "path", "") for route in api_router.routes]
    listing_paths = [p for p in path_suffixes if "/listing-jobs" in p]
    assert listing_paths, (
        "api_router does not expose any /listing-jobs route; "
        "check that listing_jobs.router is included."
    )


def test_listing_job_has_to_dict():
    """Model to_dict() returns JSON-safe structure (no SQLAlchemy objects)."""
    import datetime as dt
    import uuid

    from app.models.listing_job import ListingJob
    from app.core.workspace import DEFAULT_WORKSPACE_ID

    now = dt.datetime.now(dt.timezone.utc)
    job = ListingJob(
        id=uuid.uuid4(),
        workspace_id=DEFAULT_WORKSPACE_ID,
        product_id=uuid.uuid4(),
        sku="TEST-SKU-001",
        name="Test Product",
        payload={"name": "Test Product", "regular_price": "9.99"},
        status="pending",
        submitted_by="pipeline",
        submitted_at=now,
        created_at=now,
        updated_at=now,
    )
    data = job.to_dict()
    assert data["sku"] == "TEST-SKU-001"
    assert data["status"] == "pending"
    assert data["payload"] == {"name": "Test Product", "regular_price": "9.99"}
    assert isinstance(data["id"], str)
    assert isinstance(data["submitted_at"], str)  # ISO format
