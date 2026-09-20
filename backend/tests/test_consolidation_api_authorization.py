"""Authorization tests for consolidation master data and elimination decisions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

from app.api.v1.endpoints.auth import get_current_user
from app.main import app
from app.schemas.user import UserResponse


def _user(role: str) -> UserResponse:
    return UserResponse(
        id=f"test-{role}",
        username=role,
        email=f"{role}@example.com",
        role=role,
        is_active=True,
        created_at=datetime.now(UTC),
    )


def _override_user(role: str) -> None:
    app.dependency_overrides[get_current_user] = lambda: _user(role)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/admin/consolidation/brands"),
        ("get", "/api/v1/admin/consolidation/legal-entities"),
        ("get", "/api/v1/admin/consolidation/attributions"),
        ("get", "/api/v1/admin/consolidation/product-brand-gaps"),
        ("get", "/api/v1/admin/consolidation/attribution-gaps"),
        ("get", "/api/v1/analytics/consolidation"),
    ],
)
def test_consolidation_read_apis_require_authentication(
    client: TestClient,
    method: str,
    path: str,
) -> None:
    response = getattr(client, method)(path)
    assert response.status_code == 401, response.text


def test_viewer_cannot_create_brand(api_client: TestClient) -> None:
    previous = app.dependency_overrides.get(get_current_user)
    _override_user("viewer")
    try:
        response = api_client.post(
            "/api/v1/admin/consolidation/brands",
            json={"code": "viewer-brand", "name": "Viewer Brand"},
        )
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous
    assert response.status_code == 403, response.text


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/api/v1/admin/consolidation/product-brands/bulk",
            {
                "product_ids": ["00000000-0000-0000-0000-000000000001"],
                "brand_id": "00000000-0000-0000-0000-000000000002",
            },
        ),
        ("/api/v1/admin/consolidation/attribution-gaps/reconcile", None),
    ],
)
def test_viewer_cannot_run_consolidation_governance_writes(
    api_client: TestClient,
    path: str,
    payload: dict | None,
) -> None:
    previous = app.dependency_overrides.get(get_current_user)
    _override_user("viewer")
    try:
        response = api_client.post(path, json=payload)
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous
    assert response.status_code == 403, response.text


def test_only_admin_can_approve_intercompany_elimination(
    api_client: TestClient,
) -> None:
    previous = app.dependency_overrides.get(get_current_user)
    _override_user("operator")
    attribution_id = "00000000-0000-0000-0000-000000000001"
    try:
        response = api_client.post(
            f"/api/v1/admin/consolidation/attributions/{attribution_id}"
            "/approve-elimination",
            json={"elimination_amount": "100.00", "evidence": {}},
        )
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous
    assert response.status_code == 403, response.text
