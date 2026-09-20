"""Authorization regressions for B2B P1 write and operations APIs."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.auth import get_current_user
from app.main import app
from app.schemas.user import UserResponse


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", "/api/v1/admin/b2b/price-books", None),
        (
            "post",
            "/api/v1/admin/b2b/orders/00000000-0000-0000-0000-000000000001/fulfillment/reserve",
            {"warehouse_location": "MAIN", "reservation_key": "auth-check"},
        ),
        ("get", "/api/v1/agent-runtime/overview", None),
        ("get", "/api/v1/agent-tasks", None),
        ("post", "/api/v1/agent-alerts/evaluate", None),
    ],
)
def test_p1_operational_apis_require_authentication(
    client: TestClient,
    method: str,
    path: str,
    payload: dict[str, object] | None,
) -> None:
    request_kwargs = {"json": payload} if payload is not None else {}
    response = getattr(client, method)(path, **request_kwargs)
    assert response.status_code == 401, response.text


def _viewer() -> UserResponse:
    return UserResponse(
        id="test-viewer",
        username="viewer",
        email="viewer@example.com",
        role="viewer",
        is_active=True,
        created_at=datetime.now(UTC),
    )


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/api/v1/admin/b2b/price-books",
            {
                "code": "AUTH",
                "name": "Auth",
                "currency": "USD",
            },
        ),
        (
            "/api/v1/admin/b2b/orders/00000000-0000-0000-0000-000000000001/fulfillment/reserve",
            {"warehouse_location": "MAIN", "reservation_key": "viewer-check"},
        ),
        (
            "/api/v1/agent-queue/dead-letters/00000000-0000-0000-0000-000000000001/replay",
            {"reason": "viewer must not replay"},
        ),
    ],
)
def test_p1_write_apis_reject_viewer_role(
    api_client: TestClient,
    path: str,
    payload: dict[str, object],
) -> None:
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = _viewer
    try:
        response = api_client.post(path, json=payload)
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous
    assert response.status_code == 403, response.text
