"""M5.8 actor resolution extension point tests (AUTHENTICATION_GAP).

The approval/audit actor is currently declared in the request body
(staging-safe default provider). Server-side RBAC is never bypassed; the
resolved actor must still pass the workspace role/permission checks. A
``header`` provider is the future SSO/JWT seam.

Covers: body provider validation, reserved identities, header provider
precedence + fallback, provider configuration and API-level guarantees
(reserved actor -> 400, header actor source, RBAC not bypassed).
"""

import pytest
from app.core.actor import (
    ActorResolutionError,
    BodyActorProvider,
    HeaderActorProvider,
    get_actor_provider,
    resolve_actor,
)
from app.core.config import get_settings
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.product_intelligence import ProductDecision
from app.schemas.rule import RuleCreate
from app.services import approval_rbac, rule_engine
from fastapi import Request
from sqlalchemy import select
from starlette.datastructures import Headers, QueryParams

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


# --------------------------------------------------------------------------- #
# Unit: header provider (SSO/JWT seam)
# --------------------------------------------------------------------------- #


def test_header_provider_prefers_header_over_body() -> None:
    provider = HeaderActorProvider("X-Actor")
    request = _request({"X-Actor": "sso-user@nuotao.example"})
    assert provider.resolve(request, "body-user") == "sso-user@nuotao.example"


def test_header_provider_falls_back_to_body() -> None:
    provider = HeaderActorProvider("X-Actor")
    assert provider.resolve(_request(), "body-user") == "body-user"


def test_header_provider_rejects_invalid_header() -> None:
    provider = HeaderActorProvider("X-Actor")
    with pytest.raises(ActorResolutionError):
        provider.resolve(_request({"X-Actor": "not allowed"}), "body-user")


def test_header_provider_rejects_reserved_header() -> None:
    provider = HeaderActorProvider("X-Actor")
    with pytest.raises(ActorResolutionError):
        provider.resolve(_request({"X-Actor": "agent"}), "body-user")


# --------------------------------------------------------------------------- #
# Unit: provider configuration
# --------------------------------------------------------------------------- #


def test_get_actor_provider_follows_settings(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "actor_provider", "body")
    assert isinstance(get_actor_provider(), BodyActorProvider)
    monkeypatch.setattr(settings, "actor_provider", "header")
    provider = get_actor_provider()
    assert isinstance(provider, HeaderActorProvider)
    assert provider.header_name == settings.actor_header_name


def test_resolve_actor_uses_configured_provider(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "actor_provider", "header")
    request = _request({"X-Actor": "sso-user@nuotao.example"})
    assert resolve_actor(request, "body-user") == "sso-user@nuotao.example"
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
async def test_api_header_provider_takes_actor_from_header(
    db_session, api_client, monkeypatch
) -> None:
    """Header provider: the SSO header wins over the (ignored) body actor."""
    settings = get_settings()
    monkeypatch.setattr(settings, "actor_provider", "header")
    product_id = await _seed_and_intake(db_session, api_client)
    decision = _propose_decision(api_client, product_id)

    response = api_client.post(
        APPROVE_URL.format(decision_id=decision["id"]),
        json={"actor": "untrusted-body-actor", "note": "approved via header"},
        headers={**_headers(), "X-Actor": "ops@nuotao.example"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["approval_status"] == "approved"

    rows = (await db_session.execute(select(ProductDecision))).scalars().all()
    assert rows[0].approval_status == "approved"


@pytest.mark.asyncio
async def test_api_header_provider_rbac_not_bypassed(db_session, api_client, monkeypatch) -> None:
    """Server-side RBAC still applies to the resolved header actor (403)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "actor_provider", "header")
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
        headers={**_headers(), "X-Actor": "reviewer@nuotao.example"},
    )
    assert response.status_code == 403, response.text
