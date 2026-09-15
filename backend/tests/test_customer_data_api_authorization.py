"""Authorization and tenant-boundary tests for customer-data APIs."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
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


def _override_user(client: TestClient, role: str) -> None:
    app.dependency_overrides[get_current_user] = lambda: _user(role)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/admin/customer-data/stats"),
        ("get", "/api/v1/admin/customer-data/identities"),
        ("get", "/api/v1/admin/customer-data/merges"),
        ("get", "/api/v1/admin/customer-data/requests"),
    ],
)
def test_customer_data_read_apis_require_authentication(
    client: TestClient,
    method: str,
    path: str,
) -> None:
    response = getattr(client, method)(path)
    assert response.status_code == 401, response.text


def test_viewer_cannot_mutate_customer_data(api_client: TestClient) -> None:
    previous = app.dependency_overrides.get(get_current_user)
    _override_user(api_client, "viewer")
    try:
        response = api_client.post(
            "/api/v1/admin/customer-data/identities/resolve",
            json={
                "identity_type": "email",
                "identity_value": "viewer@example.com",
                "create_if_missing": False,
            },
        )
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous
    assert response.status_code == 403, response.text


def test_only_admin_can_approve_merges(api_client: TestClient) -> None:
    previous = app.dependency_overrides.get(get_current_user)
    _override_user(api_client, "operator")
    merge_id = "00000000-0000-0000-0000-000000000001"
    try:
        response = api_client.post(
            f"/api/v1/admin/customer-data/merges/{merge_id}/approve",
            json={"reason": "operator must not approve"},
        )
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous
    assert response.status_code == 403, response.text


def test_identity_metadata_rejects_pii(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/admin/customer-data/identities",
        json={
            "customer_account_id": "00000000-0000-0000-0000-000000000001",
            "identity_type": "email",
            "identity_value": "buyer@example.com",
            "channel": "email",
            "external_system": "store",
            "source": "test",
            "metadata": {"email_address": "buyer@example.com"},
        },
    )
    assert response.status_code == 422, response.text


def test_consent_evidence_rejects_pii(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/admin/customer-data/consent/events",
        json={
            "customer_account_id": "00000000-0000-0000-0000-000000000001",
            "purpose": "marketing_email",
            "channel": "email",
            "status": "granted",
            "policy_version": "test-v1",
            "source": "test",
            "idempotency_key": "pii-evidence-test",
            "evidence": {"phone": "+14155550123"},
        },
    )
    assert response.status_code == 422, response.text
