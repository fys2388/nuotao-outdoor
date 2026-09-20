"""RBAC regressions for the B2B credit, hold, and insurance APIs."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.b2b_portal import _portal_sales_http_error
from app.api.v1.endpoints.b2b_sales import _sales_http_error
from app.api.v1.endpoints.auth import get_current_user
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.main import app
from app.schemas.user import UserResponse
from app.services import b2b_credit_service

WORKSPACE = DEFAULT_WORKSPACE_ID


@pytest.mark.parametrize(
    "mapper",
    [_sales_http_error, _portal_sales_http_error],
)
def test_order_entry_maps_credit_blocks_to_conflict(mapper) -> None:
    error = b2b_credit_service.B2BCreditStateError(
        "customer credit status is hold: overdue review"
    )
    response = mapper(error)
    assert response.status_code == 409
    assert response.detail == str(error)


def _user(role: str) -> UserResponse:
    return UserResponse(
        id=f"test-{role}",
        username=role,
        email=f"{role}@example.com",
        role=role,
        is_active=True,
        created_at=datetime.now(UTC),
    )


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", "/api/v1/admin/b2b/credit/policies", None),
        (
            "post",
            "/api/v1/admin/b2b/credit/policies",
            {"watch_score": 35, "hold_score": 60, "freeze_score": 80},
        ),
        ("get", "/api/v1/admin/b2b/credit/risks", None),
        ("get", "/api/v1/admin/b2b/credit/insurance", None),
        ("get", "/api/v1/admin/b2b/credit/claims", None),
    ],
)
def test_credit_apis_require_authentication(
    client: TestClient,
    method: str,
    path: str,
    payload: dict[str, object] | None,
) -> None:
    request_kwargs = {"json": payload} if payload is not None else {}
    response = getattr(client, method)(path, **request_kwargs)
    assert response.status_code == 401, response.text


def test_credit_api_enforces_editor_and_admin_separation(
    api_client: TestClient,
) -> None:
    previous = app.dependency_overrides[get_current_user]
    operator = _user("operator")
    viewer = _user("viewer")
    missing_id = "00000000-0000-0000-0000-000000000001"

    try:
        app.dependency_overrides[get_current_user] = lambda: operator
        create = api_client.post(
            "/api/v1/admin/b2b/credit/policies",
            json={
                "watch_score": 35,
                "hold_score": 60,
                "freeze_score": 80,
                "auto_hold_enabled": True,
                "auto_freeze_enabled": False,
            },
        )
        assert create.status_code == 201, create.text
        policy_id = create.json()["id"]

        submit = api_client.post(
            f"/api/v1/admin/b2b/credit/policies/{policy_id}/submit"
        )
        assert submit.status_code == 200, submit.text

        for path in (
            f"/api/v1/admin/b2b/credit/policies/{policy_id}/approve",
            f"/api/v1/admin/b2b/credit/agents/{missing_id}/status",
            f"/api/v1/admin/b2b/credit/claims/{missing_id}/approve",
            f"/api/v1/admin/b2b/credit/claims/{missing_id}/reject",
            f"/api/v1/admin/b2b/credit/claims/{missing_id}/settle",
        ):
            payload = (
                {"status": "hold", "reason": "operator must not freeze"}
                if path.endswith("/status")
                else {"reason": "operator must not decide"}
                if path.endswith("/reject")
                else {"settlement_reference": "OP-MUST-NOT-SETTLE"}
                if path.endswith("/settle")
                else None
            )
            response = api_client.post(path, json=payload)
            assert response.status_code == 403, (path, response.text)

        app.dependency_overrides[get_current_user] = lambda: viewer
        assert (
            api_client.get("/api/v1/admin/b2b/credit/policies").status_code
            == 200
        )
        viewer_create = api_client.post(
            "/api/v1/admin/b2b/credit/policies",
            json={
                "watch_score": 35,
                "hold_score": 60,
                "freeze_score": 80,
            },
        )
        assert viewer_create.status_code == 403, viewer_create.text

        app.dependency_overrides[get_current_user] = previous
        approve = api_client.post(
            f"/api/v1/admin/b2b/credit/policies/{policy_id}/approve"
        )
        assert approve.status_code == 200, approve.text
        assert approve.json()["status"] == "active"
    finally:
        app.dependency_overrides[get_current_user] = previous


def test_credit_policy_and_risk_reads_are_workspace_scoped(
    api_client: TestClient,
) -> None:
    created = api_client.post(
        "/api/v1/admin/b2b/credit/policies",
        json={
            "watch_score": 35,
            "hold_score": 60,
            "freeze_score": 80,
        },
    )
    assert created.status_code == 201, created.text

    async def other_workspace() -> UUID:
        return UUID("00000000-0000-0000-0000-000000000099")

    from app.api.v1.endpoints.auth import get_current_workspace_id

    previous = app.dependency_overrides[get_current_workspace_id]
    app.dependency_overrides[get_current_workspace_id] = other_workspace
    try:
        policies = api_client.get("/api/v1/admin/b2b/credit/policies")
        risks = api_client.get("/api/v1/admin/b2b/credit/risks")
        insurance = api_client.get("/api/v1/admin/b2b/credit/insurance")
        claims = api_client.get("/api/v1/admin/b2b/credit/claims")
        assert policies.status_code == 200, policies.text
        assert policies.json()["items"] == []
        assert risks.status_code == 200, risks.text
        assert risks.json()["items"] == []
        assert insurance.status_code == 200, insurance.text
        assert insurance.json()["items"] == []
        assert claims.status_code == 200, claims.text
        assert claims.json()["items"] == []
    finally:
        app.dependency_overrides[get_current_workspace_id] = previous
