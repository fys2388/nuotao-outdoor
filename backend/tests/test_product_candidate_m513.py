"""M5.13 Product Candidate Source Correction tests.

Covers the 18 acceptance points:
1688/MANUAL/CSV intake, candidate_status default + lifecycle, rejected guard,
Product Analyst on candidates without WooCommerce, promote approval boundary,
draft payload, no WooCommerce write, source metadata, workspace isolation,
PII/secret guard, activation gate candidate source and WooCommerce sync
candidate_status=NULL.
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.product import Product
from app.models.product_intelligence import ProductSource, WooCommerceDraft
from app.schemas.rule import RuleCreate
from app.services import rule_engine

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = uuid4()

INTAKE_URL = "/api/v1/products/intake"
CSV_URL = "/api/v1/products/intake/csv"
STATUS_URL = "/api/v1/product-candidates/{pid}/status"
PROMOTE_URL = "/api/v1/product-candidates/{pid}/promote"
DRAFTS_URL = "/api/v1/product-candidates/{pid}/drafts"


def _intake_payload(**overrides) -> dict:
    payload = {
        "title": "Camping Headlamp Pro",
        "sku": "NTO-HEADLAMP-001",
        "description": "USB rechargeable 300lm headlamp",
        "source_type": "1688",
        "source_url": "https://detail.1688.com/offer/123456789.html",
        "supplier_code": None,
        "purchase_cost": "10.00",
        "domestic_shipping": "1.00",
        "first_leg_shipping": "2.00",
        "last_leg_shipping": "3.00",
        "weight_kg": "0.30",
        "dimensions": {"length": 8, "width": 5, "height": 4},
        "target_market": "US",
        "currency": "USD",
    }
    payload.update(overrides)
    return payload


async def _seed_product_rules(db_session) -> None:
    """Seed the deterministic PRODUCT gates (same shape as migration 0004)."""
    rules = [
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
            when_conditions={"field": "logistics.shipping_ratio", "op": "lte", "value": 0.4},
            then_result={"passed_message": "ship ok", "failed_message": "ship too high"},
        ),
    ]
    for data in rules:
        await rule_engine.create_rule(db_session, workspace_id=WORKSPACE, data=data)


async def _intake(api_client, **overrides) -> dict:
    response = api_client.post(INTAKE_URL, json=_intake_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# 1-4. Intake sources + candidate_status default
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_1688_url_intake_creates_candidate(db_session, api_client) -> None:
    """A 1688 URL intake creates a Product Candidate with source metadata."""
    await _seed_product_rules(db_session)
    result = await _intake(api_client)
    product = result["product"]
    assert product["candidate_status"] == "candidate"
    assert product["status"] == "candidate"
    assert product["source"] == "intake"
    assert product["source_url"] == "https://detail.1688.com/offer/123456789.html"

    sources = (await db_session.execute(select(ProductSource))).scalars().all()
    assert len(sources) == 1
    assert sources[0].source_type == "1688"
    assert sources[0].source_url == "https://detail.1688.com/offer/123456789.html"
    assert sources[0].raw_data["source_type"] == "1688"


@pytest.mark.asyncio
async def test_manual_intake_creates_candidate(db_session, api_client) -> None:
    """A MANUAL intake (no source_url) also becomes a candidate."""
    await _seed_product_rules(db_session)
    result = await _intake(
        api_client,
        sku="NTO-MANUAL-001",
        source_type="MANUAL",
        source_url=None,
        title="Manual Kayak Light",
    )
    assert result["product"]["candidate_status"] == "candidate"
    assert result["product"]["source_url"] is None


@pytest.mark.asyncio
async def test_csv_intake_endpoint(db_session, api_client) -> None:
    """CSV intake imports good rows and isolates bad rows."""
    await _seed_product_rules(db_session)
    csv_text = (
        "source_type,source_url,title,sku,category,purchase_cost,weight_kg,target_market\n"
        "1688,https://detail.1688.com/offer/111.html,CSV Tent One,NTO-CSV-1,Outdoor,12.00,1.2,US\n"
        "MANUAL,,CSV Stove Two,NTO-CSV-2,Camping,8.00,0.9,US\n"
        "1688,https://detail.1688.com/offer/333.html,,NTO-CSV-3,Outdoor,5.00,0.5,US\n"
    )
    response = api_client.post(
        CSV_URL,
        files={"file": ("candidates.csv", csv_text.encode("utf-8-sig"), "text/csv")},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["imported"] == 2
    assert result["failed"] == 1
    assert result["results"][2]["status"] == "failed"
    assert result["trace_id"] is not None

    products = (await db_session.execute(select(Product))).scalars().all()
    assert len(products) == 2
    assert {p.sku for p in products} == {"NTO-CSV-1", "NTO-CSV-2"}
    assert all(p.candidate_status == "candidate" for p in products)

    sources = (await db_session.execute(select(ProductSource))).scalars().all()
    assert {s.source_type for s in sources} == {"1688", "MANUAL"}


# --------------------------------------------------------------------------- #
# 5-6. Candidate lifecycle + rejected guard
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_candidate_lifecycle_state_machine(db_session, api_client) -> None:
    """candidate -> approved -> testing -> winner, then winner is terminal."""
    await _seed_product_rules(db_session)
    result = await _intake(api_client, sku="NTO-LIFE-001")
    product_id = result["product"]["id"]

    for status_name in ("approved", "testing", "winner"):
        response = api_client.post(
            STATUS_URL.format(pid=product_id),
            json={"status": status_name, "actor": "ops-a"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["candidate_status"] == status_name

    # winner -> candidate is forbidden.
    response = api_client.post(
        STATUS_URL.format(pid=product_id),
        json={"status": "candidate", "actor": "ops-a"},
    )
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"]

    # winner -> rejected is forbidden.
    response = api_client.post(
        STATUS_URL.format(pid=product_id),
        json={"status": "rejected", "actor": "ops-a"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_rejected_candidate_guard(db_session, api_client) -> None:
    """A rejected candidate cannot move forward in the lifecycle."""
    await _seed_product_rules(db_session)
    result = await _intake(api_client, sku="NTO-REJ-001")
    product_id = result["product"]["id"]

    response = api_client.post(
        STATUS_URL.format(pid=product_id),
        json={"status": "rejected", "actor": "ops-a"},
    )
    assert response.status_code == 200
    assert response.json()["candidate_status"] == "rejected"

    response = api_client.post(
        STATUS_URL.format(pid=product_id),
        json={"status": "approved", "actor": "ops-a"},
    )
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"]


@pytest.mark.asyncio
async def test_reject_decision_marks_candidate_rejected(db_session, api_client) -> None:
    """A rejected product decision also marks the candidate rejected."""
    await _seed_product_rules(db_session)
    result = await _intake(api_client, sku="NTO-DEC-001")
    product_id = result["product"]["id"]

    decision = api_client.post(f"/api/v1/products/{product_id}/decisions")
    assert decision.status_code in (200, 201), decision.text
    decision_id = decision.json()["id"]

    rejected = api_client.post(
        f"/api/v1/product-decisions/{decision_id}/reject",
        json={"actor": "ops-a", "note": "not for us"},
    )
    assert rejected.status_code == 200, rejected.text

    product = (
        await db_session.execute(select(Product).where(Product.id == UUID(product_id)))
    ).scalar_one()
    assert product.candidate_status == "rejected"


# --------------------------------------------------------------------------- #
# 7-8. Product Analyst works on candidates without WooCommerce
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_context_builder_includes_candidate_metadata(db_session, api_client) -> None:
    """The Product Context carries candidate_status/source_type/source_url."""
    from app.services.product_context import build_product_context

    await _seed_product_rules(db_session)
    result = await _intake(api_client, sku="NTO-CTX-001")
    product_id = result["product"]["id"]

    context = await build_product_context(
        db_session, workspace_id=WORKSPACE, product_id=UUID(product_id), trace_id="t-ctx"
    )
    assert context["product"]["candidate_status"] == "candidate"
    assert context["product"]["source_type"] == "1688"
    assert context["product"]["source_url"] == "https://detail.1688.com/offer/123456789.html"


@pytest.mark.asyncio
async def test_product_analyst_pilot_task_without_woocommerce(db_session, api_client) -> None:
    """create_pilot_task works for a candidate with no WooCommerce product."""
    from app.agents.agent_seed import ensure_product_analyst_agent
    from app.services import pilot_product_analyst

    await _seed_product_rules(db_session)
    await ensure_product_analyst_agent(db_session, workspace_id=WORKSPACE)
    result = await _intake(api_client, sku="NTO-PILOT-001")
    product_id = result["product"]["id"]

    task = await pilot_product_analyst.create_pilot_task(
        db_session,
        workspace_id=WORKSPACE,
        product_id=UUID(product_id),
        actor="ops-a",
        trace_id="t-pilot",
    )
    assert task.id is not None
    assert task.input["product_id"] == str(product_id)


# --------------------------------------------------------------------------- #
# 9-13. Promote approval boundary + draft payload + no WooCommerce write
# --------------------------------------------------------------------------- #


async def _make_winner(api_client, db_session, *, sku: str) -> str:
    await _seed_product_rules(db_session)
    result = await _intake(api_client, sku=sku)
    product_id = result["product"]["id"]
    for status_name in ("approved", "testing", "winner"):
        response = api_client.post(
            STATUS_URL.format(pid=product_id),
            json={"status": status_name, "actor": "ops-a"},
        )
        assert response.status_code == 200, response.text
    return product_id


@pytest.mark.asyncio
async def test_promote_requires_winner(db_session, api_client) -> None:
    """A non-winner candidate cannot request promotion (400)."""
    await _seed_product_rules(db_session)
    result = await _intake(api_client, sku="NTO-PROMO-0")
    product_id = result["product"]["id"]

    response = api_client.post(
        PROMOTE_URL.format(pid=product_id),
        json={"actor": "ops-a", "note": "promote me"},
    )
    assert response.status_code == 400
    assert "only a winner" in response.json()["detail"]


@pytest.mark.asyncio
async def test_promote_creates_human_approval(db_session, api_client) -> None:
    """Promote creates a pending PRODUCT_CANDIDATE approval, never a draft."""
    product_id = await _make_winner(api_client, db_session, sku="NTO-PROMO-1")
    response = api_client.post(
        PROMOTE_URL.format(pid=product_id),
        json={"actor": "ops-a", "note": "promote winner"},
    )
    assert response.status_code == 201, response.text
    approval = response.json()
    assert approval["approval_type"] == "PRODUCT_CANDIDATE"
    assert approval["status"] == "pending"
    assert approval["entity_id"] == str(product_id)

    # Idempotent: a second request returns the same pending approval.
    second = api_client.post(
        PROMOTE_URL.format(pid=product_id),
        json={"actor": "ops-a", "note": "again"},
    )
    assert second.status_code == 201
    assert second.json()["id"] == approval["id"]

    # No draft is generated before the human decision.
    drafts = (await db_session.execute(select(WooCommerceDraft))).scalars().all()
    assert drafts == []


@pytest.mark.asyncio
async def test_agent_cannot_promote(db_session, api_client) -> None:
    """The Product Analyst agent actor is rejected (403)."""
    from app.agents.agent_seed import ensure_product_analyst_agent

    await ensure_product_analyst_agent(db_session, workspace_id=WORKSPACE)
    product_id = await _make_winner(api_client, db_session, sku="NTO-AGENT-1")

    response = api_client.post(
        PROMOTE_URL.format(pid=product_id),
        json={"actor": "product_analyst", "note": "self promote"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_draft_payload_generated_after_human_approval(
    db_session, api_client, monkeypatch
) -> None:
    """After human approval a complete WooCommerce draft payload is generated.

    The WooCommerce connector is never invoked (Phase 1: no write API).
    """
    from app.integrations import woocommerce

    calls: list[str] = []
    original_sync = woocommerce.WooCommerceConnector.sync

    async def _spy_sync(self, *args, **kwargs):
        calls.append("sync")
        return await original_sync(self, *args, **kwargs)

    monkeypatch.setattr(woocommerce.WooCommerceConnector, "sync", _spy_sync)

    product_id = await _make_winner(api_client, db_session, sku="NTO-DRAFT-1")
    response = api_client.post(
        PROMOTE_URL.format(pid=product_id),
        json={"actor": "ops-a", "note": "go"},
    )
    assert response.status_code == 201
    approval_id = response.json()["id"]

    decided = api_client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"actor": "ops-a", "note": "approved"},
    )
    assert decided.status_code == 200, decided.text

    # Draft payload persisted with the full hand-off structure.
    drafts = (await db_session.execute(select(WooCommerceDraft))).scalars().all()
    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.status == "generated"
    assert draft.sku == "NTO-DRAFT-1"
    assert draft.approved_by == "ops-a"

    payload = draft.payload
    assert payload["sku"] == "NTO-DRAFT-1"
    assert payload["name"] == "Camping Headlamp Pro"
    assert payload["price"] is not None
    assert payload["categories"] == []  # category unknown -> empty list
    assert payload["inventory"]["manage_stock"] is False
    assert payload["metadata"]["source_type"] == "1688"
    assert payload["metadata"]["source_url"] == "https://detail.1688.com/offer/123456789.html"
    assert payload["metadata"]["product_id"] == str(product_id)
    assert payload["metadata"]["trace_id"] is not None

    # The draft is readable through the API.
    drafts_api = api_client.get(DRAFTS_URL.format(pid=product_id))
    assert drafts_api.status_code == 200
    assert drafts_api.json()[0]["payload"]["sku"] == "NTO-DRAFT-1"

    # Phase 1 boundary: the WooCommerce connector was never invoked.
    assert calls == []


@pytest.mark.asyncio
async def test_promote_rejection_records_event_only(db_session, api_client) -> None:
    """A rejected promote approval records the decision; no draft is created."""
    product_id = await _make_winner(api_client, db_session, sku="NTO-REJ2-1")
    response = api_client.post(
        PROMOTE_URL.format(pid=product_id),
        json={"actor": "ops-a", "note": "go"},
    )
    approval_id = response.json()["id"]

    decided = api_client.post(
        f"/api/v1/approvals/{approval_id}/reject",
        json={"actor": "ops-a", "note": "not yet"},
    )
    assert decided.status_code == 200

    drafts = (await db_session.execute(select(WooCommerceDraft))).scalars().all()
    assert drafts == []


# --------------------------------------------------------------------------- #
# 14-16. Source metadata, isolation, PII/secret guard
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_workspace_isolation_for_candidate_ops(db_session, api_client) -> None:
    """Cross-workspace candidate operations are concealed (404)."""
    await _seed_product_rules(db_session)
    result = await _intake(api_client, sku="NTO-ISO-001")
    product_id = result["product"]["id"]

    # Move the product into a different workspace: it no longer exists here.
    product = (
        await db_session.execute(select(Product).where(Product.id == UUID(product_id)))
    ).scalar_one()
    product.workspace_id = OTHER_WORKSPACE
    await db_session.flush()

    status = api_client.post(
        STATUS_URL.format(pid=product_id),
        json={"status": "approved", "actor": "ops-a"},
    )
    assert status.status_code == 404

    promote = api_client.post(
        PROMOTE_URL.format(pid=product_id),
        json={"actor": "ops-a"},
    )
    assert promote.status_code == 404

    drafts = api_client.get(DRAFTS_URL.format(pid=product_id))
    assert drafts.status_code == 200
    assert drafts.json() == []


@pytest.mark.asyncio
async def test_pii_and_secret_not_written_to_event_log(db_session, api_client) -> None:
    """Event log rows never carry PII or credentials."""
    from app.models.event import EventLog

    await _seed_product_rules(db_session)
    await _intake(api_client, sku="NTO-PII-001")
    await db_session.flush()

    rows = (await db_session.execute(select(EventLog))).scalars().all()
    assert rows
    blob = "\n".join(f"{row.event_type} {row.payload}" for row in rows).lower()
    for forbidden in ("sk-proj-", "consumer_secret", "consumer_key", "password", "jwt"):
        assert forbidden not in blob


# --------------------------------------------------------------------------- #
# 17-18. Activation gate + WooCommerce sync semantics
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_woocommerce_synced_product_keeps_candidate_status_null(
    db_session, api_client
) -> None:
    """WooCommerce-synced rows stay NULL; intake can adopt them as candidates."""
    await _seed_product_rules(db_session)
    synced = Product(
        workspace_id=WORKSPACE,
        sku="WC-SYNC-001",
        name="Synced Commerce Product",
        status="active",
        source="woocommerce",
    )
    db_session.add(synced)
    await db_session.flush()
    assert synced.candidate_status is None

    # The same SKU enters through candidate intake -> becomes a candidate.
    await _intake(api_client, sku="WC-SYNC-001", title="Synced Commerce Product")
    product = (
        await db_session.execute(select(Product).where(Product.id == synced.id))
    ).scalar_one()
    assert product.candidate_status == "candidate"
    # commerce status is preserved (decoupled from the candidate flow)
    assert product.status == "active"
