"""M5.14 identity foundation - real FastAPI integration tests.

Walks the full chain through HTTP: trusted JWT -> authentication ->
workspace mapping -> RBAC. Proves hard boundaries: X-Actor / body actor are
never accepted under the header provider, cross-workspace access is denied,
agent/system identities cannot authenticate, and audit events never contain
PII or secrets.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import require_authenticated_actor, require_permission, require_workspace_context
from app.core.config import get_settings
from app.core.database import get_db
from app.core.identity import Identity
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.event import EventLog
from app.services import approval_rbac, workspace_identity
from tests.identity_helpers import (
    AUDIENCE,
    ISSUER,
    KID,
    make_key_pair,
    mint_token,
    public_key_pem,
)

TRUSTED_HEADER = "CF-Access-Jwt-Assertion"
WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-0000000000ab")
ORG = "org_2abc123"


@pytest.fixture
def identity_env(monkeypatch) -> tuple[str, str]:
    """Configure header provider with a preloaded ephemeral JWKS client."""
    private_pem, _ = make_key_pair()
    settings = get_settings()
    monkeypatch.setattr(settings, "actor_provider", "header")
    monkeypatch.setattr(
        settings, "clerk_jwks_url", "https://staging.clerk.accounts.dev/.well-known/jwks.json"
    )
    monkeypatch.setattr(settings, "clerk_issuer", ISSUER)
    monkeypatch.setattr(settings, "clerk_audience", AUDIENCE)
    monkeypatch.setattr(settings, "jwt_clock_skew_seconds", 30)
    from app.services.clerk_jwks import ClerkJwksClient

    client = ClerkJwksClient.from_keys({KID: public_key_pem(private_pem)})
    monkeypatch.setattr("app.core.identity.get_jwks_client", lambda **kw: client)
    return private_pem, "user_2abc123"


@pytest.fixture
def identity_api_client(db_session, identity_env) -> TestClient:
    """A minimal FastAPI app exercising the M5.14 dependency chain."""

    mini = FastAPI()

    async def _override_db():
        yield db_session

    mini.dependency_overrides[get_db] = _override_db

    @mini.get("/whoami")
    async def whoami(
        identity: Annotated[Identity, Depends(require_authenticated_actor)],
        workspace_id: Annotated[UUID, Depends(require_workspace_context)],
    ) -> dict:
        return {"actor_id": identity.actor_id, "workspace_id": str(workspace_id)}

    @mini.post("/decide")
    async def decide(
        identity: Annotated[Identity, Depends(require_permission("product.decision.approve"))],
    ) -> dict:
        return {"actor_id": identity.actor_id}

    with TestClient(mini) as test_client:
        yield test_client


def _auth_headers(token: str, *, workspace: UUID | None = None) -> dict:
    headers = {TRUSTED_HEADER: token}
    if workspace is not None:
        headers["X-Workspace-Id"] = str(workspace)
    return headers


async def _link_workspace(
    db_session, *, organization_id: str = ORG, workspace_id: UUID = WORKSPACE
) -> None:
    await workspace_identity.link_workspace_identity(
        db_session,
        workspace_id=workspace_id,
        organization_id=organization_id,
        role="operator",
        trace_id="test-identity",
    )


async def _seed_approver_role(db_session, *, actor: str, permissions: list[str]) -> None:
    await approval_rbac.create_role(
        db_session,
        workspace_id=WORKSPACE,
        role_name="operator",
        permissions=permissions,
        actors=[actor],
        enabled=True,
        trace_id="test-identity",
    )


# --------------------------------------------------------------------------- #
# Happy path + boundary tests through HTTP
# --------------------------------------------------------------------------- #


async def test_valid_jwt_resolves_identity_and_workspace(
    identity_api_client, db_session, identity_env
) -> None:
    private_pem, sub = identity_env
    await _link_workspace(db_session)
    token = mint_token(private_pem=private_pem, sub=sub)
    response = identity_api_client.get("/whoami", headers=_auth_headers(token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["actor_id"] == sub
    assert body["workspace_id"] == str(WORKSPACE)


async def test_missing_jwt_401(identity_api_client, db_session, identity_env) -> None:
    response = identity_api_client.get("/whoami")
    assert response.status_code == 401, response.text


async def test_invalid_signature_401(identity_api_client, db_session, identity_env) -> None:
    private_pem, sub = identity_env
    other_pem, _ = make_key_pair()
    token = mint_token(private_pem=other_pem, sub=sub)
    response = identity_api_client.get("/whoami", headers=_auth_headers(token))
    assert response.status_code == 401, response.text


async def test_expired_token_401(identity_api_client, db_session, identity_env) -> None:
    private_pem, sub = identity_env
    from datetime import timedelta

    token = mint_token(private_pem=private_pem, sub=sub, exp_delta=timedelta(minutes=-5))
    response = identity_api_client.get("/whoami", headers=_auth_headers(token))
    assert response.status_code == 401, response.text


async def test_body_actor_ignored_under_header_provider(
    identity_api_client, db_session, identity_env
) -> None:
    """A body actor cannot authenticate without a JWT."""
    response = identity_api_client.post("/decide", json={"actor": "attacker"})
    assert response.status_code == 401, response.text


async def test_x_actor_ignored(identity_api_client, db_session, identity_env) -> None:
    """A raw X-Actor header never authenticates."""
    response = identity_api_client.get("/whoami", headers={"X-Actor": "ops@nuotao.example"})
    assert response.status_code == 401, response.text


async def test_workspace_mapping_missing_403(identity_api_client, db_session, identity_env) -> None:
    private_pem, sub = identity_env
    token = mint_token(private_pem=private_pem, sub=sub)
    response = identity_api_client.get("/whoami", headers=_auth_headers(token))
    assert response.status_code == 403, response.text


async def test_workspace_header_mismatch_403(identity_api_client, db_session, identity_env) -> None:
    """X-Workspace-Id cannot move an identity across workspaces."""

    private_pem, sub = identity_env
    await _link_workspace(db_session)
    token = mint_token(private_pem=private_pem, sub=sub)
    response = identity_api_client.get(
        "/whoami", headers=_auth_headers(token, workspace=OTHER_WORKSPACE)
    )
    assert response.status_code == 403, response.text
    assert "mismatch" in response.json()["detail"]


async def test_workspace_header_agrees_200(identity_api_client, db_session, identity_env) -> None:
    """The routing hint is accepted when it matches the identity mapping."""

    private_pem, sub = identity_env
    await _link_workspace(db_session)
    token = mint_token(private_pem=private_pem, sub=sub)
    response = identity_api_client.get("/whoami", headers=_auth_headers(token, workspace=WORKSPACE))
    assert response.status_code == 200, response.text


async def test_rbac_permission_allowed(identity_api_client, db_session, identity_env) -> None:

    private_pem, sub = identity_env
    await _link_workspace(db_session)
    await _seed_approver_role(db_session, actor=sub, permissions=["product.decision.approve"])
    token = mint_token(private_pem=private_pem, sub=sub)
    response = identity_api_client.post(
        "/decide", headers=_auth_headers(token, workspace=WORKSPACE)
    )
    assert response.status_code == 200, response.text
    assert response.json()["actor_id"] == sub


async def test_rbac_permission_denied_403(identity_api_client, db_session, identity_env) -> None:

    private_pem, sub = identity_env
    await _link_workspace(db_session)
    await _seed_approver_role(db_session, actor=sub, permissions=["tool.approve"])
    token = mint_token(private_pem=private_pem, sub=sub)
    response = identity_api_client.post(
        "/decide", headers=_auth_headers(token, workspace=WORKSPACE)
    )
    assert response.status_code == 403, response.text


@pytest.mark.parametrize("reserved", ["agent", "system"])
async def test_agent_system_cannot_authenticate(
    identity_api_client, db_session, identity_env, reserved: str
) -> None:

    private_pem, _ = identity_env
    await _link_workspace(db_session)
    token = mint_token(private_pem=private_pem, sub=reserved)
    response = identity_api_client.get("/whoami", headers=_auth_headers(token))
    assert response.status_code == 401, response.text


# --------------------------------------------------------------------------- #
# Audit: identity.* events, no PII / no secrets
# --------------------------------------------------------------------------- #


async def test_identity_events_recorded_without_pii_or_secret(
    identity_api_client, db_session, identity_env
) -> None:

    private_pem, sub = identity_env
    await _link_workspace(db_session)
    token = mint_token(private_pem=private_pem, sub=sub, email="ops@nuotao.example")
    response = identity_api_client.get("/whoami", headers=_auth_headers(token))
    assert response.status_code == 200, response.text

    rows = await _events(db_session)
    event_types = [row.event_type for row in rows]
    assert "identity.authenticated" in event_types
    assert "identity.workspace_resolved" in event_types

    serialized = " ".join(str(row.payload) for row in rows)
    assert "ops@nuotao.example" not in serialized  # no PII
    for row in rows:
        keys = set(row.payload.keys())
        assert not (keys & {"email", "jwt", "token", "secret", "signature", "api_key"}), keys
        assert "ops@nuotao.example" not in str(row.payload)


async def test_authentication_failed_event_has_no_credentials(
    identity_api_client, db_session, identity_env
) -> None:

    private_pem, _ = identity_env
    response = identity_api_client.get(
        "/whoami", headers={TRUSTED_HEADER: "eyJhbGciOiJub25lIn0.broken."}
    )
    assert response.status_code == 401, response.text
    rows = await _events(db_session)
    failed = [row for row in rows if row.event_type == "identity.authentication_failed"]
    assert failed
    payload = failed[0].payload
    assert "token" not in payload and "jwt" not in payload
    assert "broken" not in str(payload)


async def _events(db_session) -> list[EventLog]:
    rows = (await db_session.execute(select(EventLog))).scalars().all()
    return list(rows)
