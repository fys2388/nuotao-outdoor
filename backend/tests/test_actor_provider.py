"""M5.8 actor resolution extension point tests (AUTHENTICATION_GAP).

The approval/audit actor is declared in the request body (staging-safe
default provider, ``body``). Server-side RBAC is never bypassed; the resolved
actor must still pass the workspace role/permission checks. Under the M5.14
``header`` provider the actor comes ONLY from a verified RS256 JWT; raw
``X-Actor`` headers and request body actors are never accepted.

Covers: body provider validation, reserved identities, JWT provider behavior,
provider configuration and API-level guarantees (reserved actor -> 400,
JWT actor source, X-Actor -> 401, RBAC not bypassed).
"""

import pytest
from app.core.actor import (
    ActorResolutionError,
    BodyActorProvider,
    JwtActorProvider,
    get_actor_provider,
    resolve_actor,
)
from app.core.config import get_settings
from app.core.identity import JwtAuthenticationError
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.product_intelligence import ProductDecision
from app.schemas.rule import RuleCreate
from app.services import approval_rbac, rule_engine
from app.services.clerk_jwks import ClerkJwksClient
from fastapi import Request
from sqlalchemy import select
from starlette.datastructures import Headers, QueryParams
from tests.identity_helpers import (
    AUDIENCE,
    ISSUER,
    KID,
    make_key_pair,
    mint_token,
    public_key_pem,
)

WORKSPACE = DEFAULT_WORKSPACE_ID

INTAKE_URL = "/api/v1/products/intake"
DECISIONS_URL = "/api/v1/products/{product_id}/decisions"
APPROVE_URL = "/api/v1/product-decisions/{decision_id}/approve"


def _request(headers: dict | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/test",
            "headers": Headers(headers or {}).raw,
            "query_string": b"",
            "client": ("127.0.0.1", 1234),
            "server": ("test", 80),
            "scheme": "http",
            "query_params": QueryParams(""),
            "path_params": {},
        }
    )


def _headers(workspace=None) -> dict:
    return {"X-Workspace-Id": str(workspace)} if workspace else {}


# --------------------------------------------------------------------------- #
# Unit: body provider validation
# --------------------------------------------------------------------------- #


def test_body_provider_accepts_valid_actor() -> None:
    provider = BodyActorProvider()
    assert provider.resolve(_request(), "ops@nuotao.example") == "ops@nuotao.example"


def test_body_provider_rejects_empty_actor() -> None:
    provider = BodyActorProvider()
    with pytest.raises(ActorResolutionError):
        provider.resolve(_request(), None)
    with pytest.raises(ActorResolutionError):
        provider.resolve(_request(), "   ")


@pytest.mark.parametrize("reserved", ["agent", "system"])
def test_body_provider_rejects_reserved_identity(reserved: str) -> None:
    provider = BodyActorProvider()
    with pytest.raises(ActorResolutionError):
        provider.resolve(_request(), reserved)


@pytest.mark.parametrize("unsafe", ['alice "quoted"', "a b", "alice;drop", "bob\\evil"])
def test_body_provider_rejects_unsafe_charset(unsafe: str) -> None:
    provider = BodyActorProvider()
    with pytest.raises(ActorResolutionError):
        provider.resolve(_request(), unsafe)


def test_body_provider_rejects_oversized_actor() -> None:
    provider = BodyActorProvider()
    with pytest.raises(ActorResolutionError):
        provider.resolve(_request(), "x" * 65)


def test_body_provider_strips_whitespace() -> None:
    provider = BodyActorProvider()
    assert provider.resolve(_request(), "  ops@nuotao.example  ") == "ops@nuotao.example"


TRUSTED_HEADER = "CF-Access-Jwt-Assertion"


def _configure_header_jwt(monkeypatch, private_pem: str) -> None:
    """Point the header provider at a preloaded ephemeral JWKS client."""
    settings = get_settings()
    monkeypatch.setattr(settings, "actor_provider", "header")
    monkeypatch.setattr(
        settings,
        "clerk_jwks_url",
        "https://staging.clerk.accounts.dev/.well-known/jwks.json",
    )
    monkeypatch.setattr(settings, "clerk_issuer", ISSUER)
    monkeypatch.setattr(settings, "clerk_audience", AUDIENCE)
    monkeypatch.setattr(settings, "jwt_clock_skew_seconds", 30)
    client = ClerkJwksClient.from_keys({KID: public_key_pem(private_pem)})
    monkeypatch.setattr("app.core.identity.get_jwks_client", lambda **kw: client)


# --------------------------------------------------------------------------- #
# Unit: JWT provider (M5.14 identity foundation)
# --------------------------------------------------------------------------- #


def test_header_provider_requires_jwt_token(monkeypatch) -> None:
    """No JWT -> authentication failure; there is NO body-actor fallback."""
    private_pem, _ = make_key_pair()
    _configure_header_jwt(monkeypatch, private_pem)
    provider = JwtActorProvider(TRUSTED_HEADER)
    with pytest.raises(JwtAuthenticationError):
        provider.resolve(_request(), "body-user")


def test_header_provider_valid_jwt_wins_over_body(monkeypatch) -> None:
    """A verified JWT resolves the actor; the body actor is ignored."""
    private_pem, _ = make_key_pair()
    _configure_header_jwt(monkeypatch, private_pem)
    token = mint_token(private_pem=private_pem, sub="user_jwt")
    provider = JwtActorProvider(TRUSTED_HEADER)
    request = _request({TRUSTED_HEADER: token, "X-Actor": "raw-header"})
    assert provider.resolve(request, "untrusted-body") == "user_jwt"


def test_header_provider_ignores_x_actor(monkeypatch) -> None:
    """A raw X-Actor header alone never authenticates."""
    private_pem, _ = make_key_pair()
    _configure_header_jwt(monkeypatch, private_pem)
    provider = JwtActorProvider(TRUSTED_HEADER)
    with pytest.raises(JwtAuthenticationError):
        provider.resolve(_request({"X-Actor": "ops@nuotao.example"}), "body-user")


def test_header_provider_rejects_reserved_actor(monkeypatch) -> None:
    """Agent/system identities cannot impersonate an operator via JWT."""
    private_pem, _ = make_key_pair()
    _configure_header_jwt(monkeypatch, private_pem)
    token = mint_token(private_pem=private_pem, sub="agent")
    provider = JwtActorProvider(TRUSTED_HEADER)
    with pytest.raises(JwtAuthenticationError):
        provider.resolve(_request({TRUSTED_HEADER: token}), "body-user")


# --------------------------------------------------------------------------- #
# Unit: provider configuration
# --------------------------------------------------------------------------- #


def test_get_actor_provider_follows_settings(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "actor_provider", "body")
    assert isinstance(get_actor_provider(), BodyActorProvider)
    monkeypatch.setattr(settings, "actor_provider", "header")
    provider = get_actor_provider()
    assert isinstance(provider, JwtActorProvider)
    assert provider.header_name == settings.trusted_identity_header


def test_resolve_actor_uses_configured_provider(monkeypatch) -> None:
    settings = get_settings()
    private_pem, _ = make_key_pair()
    _configure_header_jwt(monkeypatch, private_pem)
    token = mint_token(private_pem=private_pem, sub="sso-user")
    assert resolve_actor(_request({TRUSTED_HEADER: token}), "body-user") == "sso-user"
    monkeypatch.setattr(settings, "actor_provider", "body")
    assert resolve_actor(_request(), "body-user") == "body-user"


# --------------------------------------------------------------------------- #
# API level: reserved actor -> 400 (global handler), RBAC never bypassed
# --------------------------------------------------------------------------- #


async def _seed_and_intake(db_session, api_client) -> str:
    for rule in (
        RuleCreate(
            rule_id="PROD-GATE-001",
            name="Product cost data must be complete",
            category="PRODUCT",
            rule_type="hard",
            version="v1",
            status="active",
            when_conditions={"field": "cost.total_cost", "op": "gt", "value": 0},
            then_result={"passed_message": "cost ok", "failed_message": "cost missing"},
        ),
        RuleCreate(
            rule_id="PROD-GATE-002",
            name="Shipping within 40% of expected price",
            category="PRODUCT",
            rule_type="hard",
            version="v1",
            status="active",
            when_conditions={
                "field": "logistics.shipping_ratio",
                "op": "lte",
                "value": 0.4,
            },
            then_result={"passed_message": "ship ok", "failed_message": "ship too high"},
        ),
    ):
        await rule_engine.create_rule(db_session, workspace_id=WORKSPACE, data=rule)
    from app.agents.agent_seed import ensure_product_analyst_agent

    await ensure_product_analyst_agent(db_session, workspace_id=WORKSPACE)
    response = api_client.post(
        INTAKE_URL,
        json={
            "title": "Camping Headlamp Pro",
            "sku": "NTO-HEADLAMP-M58",
            "source_type": "1688",
            "source_url": "https://detail.1688.com/offer/555555555.html",
            "purchase_cost": "10.00",
            "domestic_shipping": "1.00",
            "first_leg_shipping": "2.00",
            "last_leg_shipping": "3.00",
            "weight_kg": "0.30",
            "target_market": "US",
            "currency": "USD",
        },
        headers=_headers(),
    )
    assert response.status_code == 201, response.text
    return response.json()["product"]["id"]


def _propose_decision(api_client, product_id: str) -> dict:
    response = api_client.post(DECISIONS_URL.format(product_id=product_id), headers=_headers())
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_api_reserved_actor_returns_400(db_session, api_client) -> None:
    """A reserved identity can never act: 400 from the global handler."""
    product_id = await _seed_and_intake(db_session, api_client)
    decision = _propose_decision(api_client, product_id)

    response = api_client.post(
        APPROVE_URL.format(decision_id=decision["id"]),
        json={"actor": "agent", "note": "attempt"},
        headers=_headers(),
    )
    assert response.status_code == 400, response.text
    assert response.json()["code"] == "ACTOR_RESOLUTION"

    rows = (await db_session.execute(select(ProductDecision))).scalars().all()
    assert rows[0].approval_status == "pending"


@pytest.mark.asyncio
async def test_api_header_provider_takes_actor_from_jwt(
    db_session, api_client, monkeypatch
) -> None:
    """Header provider: a verified JWT resolves the actor (body ignored)."""
    private_pem, _ = make_key_pair()
    _configure_header_jwt(monkeypatch, private_pem)
    token = mint_token(private_pem=private_pem, sub="ops@nuotao.example")
    product_id = await _seed_and_intake(db_session, api_client)
    decision = _propose_decision(api_client, product_id)

    response = api_client.post(
        APPROVE_URL.format(decision_id=decision["id"]),
        json={"actor": "untrusted-body-actor", "note": "approved via jwt"},
        headers={**_headers(), TRUSTED_HEADER: token},
    )
    assert response.status_code == 200, response.text
    assert response.json()["approval_status"] == "approved"

    rows = (await db_session.execute(select(ProductDecision))).scalars().all()
    assert rows[0].approval_status == "approved"


@pytest.mark.asyncio
async def test_api_header_provider_x_actor_rejected(db_session, api_client, monkeypatch) -> None:
    """A raw X-Actor header is never an identity source under header mode."""
    private_pem, _ = make_key_pair()
    _configure_header_jwt(monkeypatch, private_pem)
    product_id = await _seed_and_intake(db_session, api_client)
    decision = _propose_decision(api_client, product_id)

    response = api_client.post(
        APPROVE_URL.format(decision_id=decision["id"]),
        json={"actor": "ops@nuotao.example", "note": "attempt"},
        headers={**_headers(), "X-Actor": "ops@nuotao.example"},
    )
    assert response.status_code == 401, response.text

    rows = (await db_session.execute(select(ProductDecision))).scalars().all()
    assert rows[0].approval_status == "pending"


@pytest.mark.asyncio
async def test_api_header_provider_rbac_not_bypassed(db_session, api_client, monkeypatch) -> None:
    """Server-side RBAC still applies to the resolved JWT actor (403)."""
    private_pem, _ = make_key_pair()
    _configure_header_jwt(monkeypatch, private_pem)
    await approval_rbac.create_role(
        db_session,
        workspace_id=WORKSPACE,
        role_name="reviewer",
        permissions=["tool.approve"],  # NOT product.decision.approve
        actors=["reviewer@nuotao.example"],
        enabled=True,
        trace_id="test-m58",
    )
    product_id = await _seed_and_intake(db_session, api_client)
    decision = _propose_decision(api_client, product_id)

    response = api_client.post(
        APPROVE_URL.format(decision_id=decision["id"]),
        json={"actor": "reviewer@nuotao.example", "note": "no permission"},
        headers={
            **_headers(),
            TRUSTED_HEADER: mint_token(private_pem=private_pem, sub="reviewer@nuotao.example"),
        },
    )
    assert response.status_code == 403, response.text
