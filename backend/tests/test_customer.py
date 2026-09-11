"""Tests for M3.3 Customer Intelligence Foundation.

Covers: profile CRUD + duplicate conflict, PII blocking, workspace isolation,
interaction/review append-only content, refund statistics and knowledge
retrieval - plus event emission for every write.
"""

from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.event import EventLog

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")


def _headers(workspace: UUID | None = None) -> dict:
    return {"X-Workspace-Id": str(workspace)} if workspace else {}


async def _event_types(db_session, workspace: UUID) -> set[str]:
    rows = (await db_session.execute(select(EventLog.event_type))).scalars().all()
    return set(rows)


def _profile_payload(ref: str, **overrides) -> dict:
    payload = {
        "customer_reference_id": ref,
        "country": "US",
        "language": "en",
        "segment": "new",
        "tags": ["campaign:summer"],
        "total_orders": 1,
        "total_revenue": "49.99",
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------- #
# 1. Customer profiles
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_profile_crud_and_duplicate_conflict(db_session, api_client) -> None:
    """Profiles round-trip; duplicate reference id returns 409."""
    created = api_client.post("/api/v1/customer-profiles", json=_profile_payload("wc-1001"))
    assert created.status_code == 201, created.text
    body = created.json()
    profile_id = UUID(body["id"])
    assert body["customer_reference_id"] == "wc-1001"
    assert "customer.profile_created" in await _event_types(db_session, WORKSPACE)

    duplicate = api_client.post("/api/v1/customer-profiles", json=_profile_payload("wc-1001"))
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["detail"]

    fetched = api_client.get(f"/api/v1/customer-profiles/{profile_id}")
    assert fetched.status_code == 200
    assert fetched.json()["segment"] == "new"

    updated = api_client.put(
        f"/api/v1/customer-profiles/{profile_id}",
        json={"segment": "repeat", "total_orders": 3},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["segment"] == "repeat"
    assert "customer.profile_updated" in await _event_types(db_session, WORKSPACE)

    deleted = api_client.delete(f"/api/v1/customer-profiles/{profile_id}")
    assert deleted.status_code == 204
    assert "customer.profile_deleted" in await _event_types(db_session, WORKSPACE)


@pytest.mark.asyncio
async def test_profile_workspace_isolation(db_session, api_client) -> None:
    """Profiles are invisible across workspaces."""
    assert (
        api_client.post("/api/v1/customer-profiles", json=_profile_payload("wc-iso-1")).status_code
        == 201
    )
    assert (
        api_client.post(
            "/api/v1/customer-profiles",
            json=_profile_payload("wc-iso-2"),
            headers=_headers(OTHER_WORKSPACE),
        ).status_code
        == 201
    )

    mine = api_client.get("/api/v1/customer-profiles").json()
    theirs = api_client.get("/api/v1/customer-profiles", headers=_headers(OTHER_WORKSPACE)).json()
    assert [row["customer_reference_id"] for row in mine] == ["wc-iso-1"]
    assert [row["customer_reference_id"] for row in theirs] == ["wc-iso-2"]

    # The same reference id is allowed in another workspace.
    assert (
        api_client.post(
            "/api/v1/customer-profiles",
            json=_profile_payload("wc-iso-1"),
            headers=_headers(OTHER_WORKSPACE),
        ).status_code
        == 201
    )


# --------------------------------------------------------------------------- #
# 2. PII restriction
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pii_blocked_in_metadata(db_session, api_client) -> None:
    """Free-form metadata containing PII keys is rejected."""
    response = api_client.post(
        "/api/v1/customer-interactions",
        json={
            "channel": "chat",
            "content": "How do I wash this?",
            "metadata": {"email": "user@example.com", "topic": "care"},
        },
    )
    assert response.status_code == 400
    assert "PII not allowed" in response.json()["detail"]

    # Non-PII metadata passes.
    ok = api_client.post(
        "/api/v1/customer-interactions",
        json={
            "channel": "chat",
            "content": "How do I wash this?",
            "metadata": {"topic": "care", "page": "product"},
        },
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["metadata"] == {"topic": "care", "page": "product"}


# --------------------------------------------------------------------------- #
# 3. Interactions (append-only content)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_interaction_crud_immutable_content(db_session, api_client) -> None:
    """Interaction content is immutable; classification is updatable."""
    profile_id = UUID(
        api_client.post("/api/v1/customer-profiles", json=_profile_payload("wc-int-1")).json()["id"]
    )
    created = api_client.post(
        "/api/v1/customer-interactions",
        json={
            "customer_id": str(profile_id),
            "channel": "email",
            "interaction_type": "question",
            "content": "Is it waterproof?",
            "sentiment": "neutral",
        },
    )
    assert created.status_code == 201, created.text
    interaction_id = UUID(created.json()["id"])
    assert "customer.interaction_created" in await _event_types(db_session, WORKSPACE)

    updated = api_client.put(
        f"/api/v1/customer-interactions/{interaction_id}",
        json={"sentiment": "positive", "metadata": {"topic": "waterproof"}},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["sentiment"] == "positive"
    assert updated.json()["content"] == "Is it waterproof?"
    assert updated.json()["metadata"] == {"topic": "waterproof"}
    assert "customer.interaction_updated" in await _event_types(db_session, WORKSPACE)

    filtered = api_client.get(
        f"/api/v1/customer-interactions?customer_id={profile_id}&channel=email"
    ).json()
    assert len(filtered) == 1

    deleted = api_client.delete(f"/api/v1/customer-interactions/{interaction_id}")
    assert deleted.status_code == 204
    assert "customer.interaction_deleted" in await _event_types(db_session, WORKSPACE)


# --------------------------------------------------------------------------- #
# 4. Reviews
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_review_crud(db_session, api_client) -> None:
    """Reviews round-trip with sentiment/issue classification."""
    created = api_client.post(
        "/api/v1/product-reviews",
        json={
            "platform": "amazon",
            "rating": 4,
            "content": "Comfortable but straps slip.",
            "sentiment": "neutral",
            "issue_type": "fit",
            "keywords": ["straps", "comfort"],
        },
    )
    assert created.status_code == 201, created.text
    review_id = UUID(created.json()["id"])
    assert "customer.review_created" in await _event_types(db_session, WORKSPACE)

    updated = api_client.put(
        f"/api/v1/product-reviews/{review_id}",
        json={"sentiment": "negative", "issue_type": "quality"},
    )
    assert updated.status_code == 200
    assert updated.json()["sentiment"] == "negative"
    assert updated.json()["content"] == "Comfortable but straps slip."

    negative = api_client.get("/api/v1/product-reviews?platform=amazon&sentiment=negative").json()
    assert len(negative) == 1

    deleted = api_client.delete(f"/api/v1/product-reviews/{review_id}")
    assert deleted.status_code == 204
    assert "customer.review_deleted" in await _event_types(db_session, WORKSPACE)


# --------------------------------------------------------------------------- #
# 5. Refund intelligence + statistics
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_refund_stats_by_category(db_session, api_client) -> None:
    """Refunds aggregate per category with case count and total amount."""
    for category, amount in (("quality", "19.99"), ("quality", "29.99"), ("size", "15.00")):
        response = api_client.post(
            "/api/v1/refund-cases",
            json={
                "reason": "Item arrived damaged.",
                "category": category,
                "amount": amount,
                "resolution": "refunded",
            },
        )
        assert response.status_code == 201, response.text
    assert "customer.refund_created" in await _event_types(db_session, WORKSPACE)

    stats = api_client.get("/api/v1/refund-cases/stats")
    assert stats.status_code == 200, stats.text
    by_category = {row["category"]: row for row in stats.json()}
    assert by_category["quality"]["case_count"] == 2
    assert by_category["quality"]["total_amount"] == "49.98"
    assert by_category["size"]["case_count"] == 1
    assert by_category["size"]["total_amount"] == "15.00"

    listed = api_client.get("/api/v1/refund-cases?category=quality&resolution=refunded").json()
    assert len(listed) == 2


@pytest.mark.asyncio
async def test_refund_unknown_order_404(db_session, api_client) -> None:
    """Refunds referencing an unknown order return 404."""
    missing = UUID("00000000-0000-0000-0000-00000000dead")
    response = api_client.post(
        "/api/v1/refund-cases",
        json={"order_id": str(missing), "reason": "x", "category": "other", "amount": "0.00"},
    )
    assert response.status_code == 404
    assert "order not found" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# 6. Customer knowledge memory
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_customer_knowledge_retrieval(db_session, api_client) -> None:
    """Knowledge entries are filterable by entry_type and category."""
    pain_point = {
        "entry_type": "pain_point",
        "category": "trekking-chair",
        "title": "Straps slip",
        "content": "Customers report straps slipping on rocky terrain.",
        "tags": ["straps"],
        "confidence": "0.9",
    }
    loyalty = {
        "entry_type": "loyalty_pattern",
        "category": "trekking-chair",
        "title": "Repeat buyers",
        "content": "Repeat buyers often upgrade within 90 days.",
        "tags": ["repeat"],
        "confidence": "0.7",
    }
    assert api_client.post("/api/v1/customer-knowledge-entries", json=pain_point).status_code == 201
    assert api_client.post("/api/v1/customer-knowledge-entries", json=loyalty).status_code == 201
    assert "customer.knowledge_created" in await _event_types(db_session, WORKSPACE)

    by_type = api_client.get("/api/v1/customer-knowledge-entries?entry_type=pain_point").json()
    assert len(by_type) == 1
    assert by_type[0]["title"] == "Straps slip"

    by_category = api_client.get(
        "/api/v1/customer-knowledge-entries?category=trekking-chair"
    ).json()
    assert len(by_category) == 2


@pytest.mark.asyncio
async def test_customer_knowledge_workspace_isolation(db_session, api_client) -> None:
    """Knowledge entries stay invisible across workspaces."""
    assert (
        api_client.post(
            "/api/v1/customer-knowledge-entries",
            json={
                "entry_type": "segment_pattern",
                "title": "US hikers",
                "content": "US customers prefer lightweight gear.",
                "confidence": "0.8",
            },
        ).status_code
        == 201
    )
    mine = api_client.get("/api/v1/customer-knowledge-entries").json()
    theirs = api_client.get(
        "/api/v1/customer-knowledge-entries", headers=_headers(OTHER_WORKSPACE)
    ).json()
    assert len(mine) == 1
    assert len(theirs) == 0
