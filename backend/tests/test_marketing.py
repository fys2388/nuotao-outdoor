"""Tests for M3.1 Marketing Intelligence Foundation.

Covers: ROI / derived metric math, campaign CRUD + event emission, workspace
data isolation, creative CRUD, feedback query filtering and the experiment
lifecycle (proposed -> active -> completed) with A/B calibration.
"""

from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.event import EventLog
from app.services import marketing

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")


def _headers(workspace: UUID | None = None) -> dict:
    return {"X-Workspace-Id": str(workspace)} if workspace else {}


async def _event_types(db_session, workspace: UUID) -> set[str]:
    rows = (await db_session.execute(select(EventLog.event_type))).scalars().all()
    return set(rows)


# --------------------------------------------------------------------------- #
# 1. Derived metrics and ROI
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_roi_calculation() -> None:
    """ROI is (revenue - spend) / spend; None when spend is zero."""
    assert marketing.calculate_roi(Decimal("150.00"), Decimal("100.00")) == Decimal("0.5")
    assert marketing.calculate_roi(Decimal("80.00"), Decimal("100.00")) == Decimal("-0.2")
    assert marketing.calculate_roi(Decimal("100.00"), Decimal("0")) is None


@pytest.mark.asyncio
async def test_derive_metrics() -> None:
    """CTR/CPC/ROAS are derived deterministically; explicit values win."""
    ctr, cpc, roas = marketing.derive_metrics(
        spend=Decimal("100.00"),
        impressions=10000,
        clicks=500,
        revenue=Decimal("250.00"),
    )
    assert ctr == Decimal("0.05")
    assert cpc == Decimal("0.2")
    assert roas == Decimal("2.5")

    # Explicit values take precedence.
    ctr2, cpc2, roas2 = marketing.derive_metrics(
        spend=Decimal("100.00"),
        impressions=0,
        clicks=0,
        revenue=Decimal("0"),
        ctr=Decimal("0.01"),
        cpc=Decimal("1.5"),
        roas=Decimal("3.0"),
    )
    assert (ctr2, cpc2, roas2) == (Decimal("0.01"), Decimal("1.5"), Decimal("3.0"))

    # Zero clicks / impressions -> None (no division by zero).
    ctr3, cpc3, roas3 = marketing.derive_metrics(
        spend=Decimal("0"), impressions=0, clicks=0, revenue=Decimal("0")
    )
    assert (ctr3, cpc3, roas3) == (None, None, None)


# --------------------------------------------------------------------------- #
# 2. Campaigns CRUD + events
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_campaign_crud_and_events(db_session, api_client) -> None:
    """Campaigns are created/read/updated/deleted with derived ROI + events."""
    payload = {
        "platform": "meta",
        "campaign_id": "camp-001",
        "name": "US DTC launch",
        "budget": "500.00",
        "spend": "100.00",
        "impressions": 10000,
        "clicks": 400,
        "conversion": 20,
        "revenue": "240.00",
    }
    created = api_client.post("/api/v1/campaigns", json=payload)
    assert created.status_code == 201, created.text
    body = created.json()
    campaign_id = UUID(body["id"])
    assert body["ctr"] == "0.04"
    assert body["roi"] == "1.4"
    assert body["roas"] == "2.4"

    events = await _event_types(db_session, WORKSPACE)
    assert "campaign.created" in events

    listed = api_client.get("/api/v1/campaigns", headers=_headers())
    assert listed.status_code == 200
    assert any(item["id"] == str(campaign_id) for item in listed.json())

    fetched = api_client.get(f"/api/v1/campaigns/{campaign_id}")
    assert fetched.status_code == 200
    assert fetched.json()["campaign_id"] == "camp-001"

    updated = api_client.put(
        f"/api/v1/campaigns/{campaign_id}",
        json={"spend": "200.00", "revenue": "600.00"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["roi"] == "2"
    assert "campaign.updated" in await _event_types(db_session, WORKSPACE)

    deleted = api_client.delete(f"/api/v1/campaigns/{campaign_id}")
    assert deleted.status_code == 204
    assert "campaign.deleted" in await _event_types(db_session, WORKSPACE)


@pytest.mark.asyncio
async def test_campaign_duplicate_conflict(db_session, api_client) -> None:
    """The same (workspace, platform, campaign_id) returns 409."""
    payload = {"platform": "google", "campaign_id": "dup-001", "budget": "10.00"}
    assert api_client.post("/api/v1/campaigns", json=payload).status_code == 201
    conflict = api_client.post("/api/v1/campaigns", json=payload)
    assert conflict.status_code == 409
    assert "already exists" in conflict.json()["detail"]


# --------------------------------------------------------------------------- #
# 3. Workspace data isolation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_workspace_data_isolation(db_session, api_client) -> None:
    """Rows are invisible across workspaces."""
    payload = {
        "platform": "meta",
        "campaign_id": "iso-001",
        "name": "WS A campaign",
        "budget": "10.00",
    }
    assert api_client.post("/api/v1/campaigns", json=payload).status_code == 201
    assert (
        api_client.post(
            "/api/v1/campaigns",
            json={**payload, "campaign_id": "iso-002"},
            headers=_headers(OTHER_WORKSPACE),
        ).status_code
        == 201
    )

    mine = api_client.get("/api/v1/campaigns", headers=_headers())
    others = api_client.get("/api/v1/campaigns", headers=_headers(OTHER_WORKSPACE))
    assert [row["campaign_id"] for row in mine.json()] == ["iso-001"]
    assert [row["campaign_id"] for row in others.json()] == ["iso-002"]

    # Same external campaign id is allowed in a different workspace.
    assert (
        api_client.post(
            "/api/v1/campaigns",
            json={"platform": "meta", "campaign_id": "iso-001", "budget": "1.00"},
            headers=_headers(OTHER_WORKSPACE),
        ).status_code
        == 201
    )


# --------------------------------------------------------------------------- #
# 4. Creatives
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_creative_crud_and_events(db_session, api_client) -> None:
    """Creatives round-trip with structured positioning fields + events."""
    payload = {
        "platform": "meta",
        "asset_type": "video",
        "hook": "Lightest trekking chair",
        "angle": "weight saving",
        "copy": "Carry less. Hike further.",
        "performance_snapshot": {"ctr": 0.03},
        "status": "active",
    }
    created = api_client.post("/api/v1/creatives", json=payload)
    assert created.status_code == 201, created.text
    creative_id = UUID(created.json()["id"])
    assert "creative.created" in await _event_types(db_session, WORKSPACE)

    listed = api_client.get("/api/v1/creatives")
    assert listed.status_code == 200
    assert any(item["id"] == str(creative_id) for item in listed.json())

    updated = api_client.put(f"/api/v1/creatives/{creative_id}", json={"status": "archived"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "archived"
    assert "creative.updated" in await _event_types(db_session, WORKSPACE)

    deleted = api_client.delete(f"/api/v1/creatives/{creative_id}")
    assert deleted.status_code == 204
    assert "creative.deleted" in await _event_types(db_session, WORKSPACE)


# --------------------------------------------------------------------------- #
# 5. Customer feedback
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_feedback_crud_filters(db_session, api_client) -> None:
    """Feedback is append-only and filterable by sentiment/source."""
    positive = {
        "source": "review",
        "content": "Great quality for the price.",
        "sentiment": "positive",
        "rating": 5,
    }
    negative = {
        "source": "support",
        "content": "Straps broke after one trip.",
        "sentiment": "negative",
        "issue_type": "quality",
        "rating": 2,
    }
    assert api_client.post("/api/v1/feedback", json=positive).status_code == 201
    assert api_client.post("/api/v1/feedback", json=negative).status_code == 201
    assert "feedback.created" in await _event_types(db_session, WORKSPACE)

    all_rows = api_client.get("/api/v1/feedback").json()
    assert len(all_rows) == 2

    positive_rows = api_client.get("/api/v1/feedback?sentiment=positive").json()
    assert len(positive_rows) == 1
    assert positive_rows[0]["content"] == positive["content"]

    source_rows = api_client.get("/api/v1/feedback?source=support").json()
    assert len(source_rows) == 1
    assert source_rows[0]["issue_type"] == "quality"

    # Content is immutable on update (classification may change).
    row_id = UUID(positive_rows[0]["id"])
    updated = api_client.put(
        f"/api/v1/feedback/{row_id}",
        json={"sentiment": "neutral", "metadata": {"source_order": "x"}},
    )
    assert updated.status_code == 200
    assert updated.json()["content"] == positive["content"]
    assert updated.json()["sentiment"] == "neutral"
    assert "feedback.updated" in await _event_types(db_session, WORKSPACE)


# --------------------------------------------------------------------------- #
# 6. Marketing experiments lifecycle
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_experiment_lifecycle_and_calibration(db_session, api_client) -> None:
    """proposed -> active -> completed with A/B calibration deltas + events."""
    proposed = api_client.post(
        "/api/v1/marketing-experiments",
        json={
            "name": "Hook A/B",
            "hypothesis": "Weight-focused hook outperforms price hook",
            "variant_a": {"hook": "lightest"},
            "variant_b": {"hook": "cheapest"},
        },
    )
    assert proposed.status_code == 201, proposed.text
    experiment_id = UUID(proposed.json()["id"])
    assert proposed.json()["status"] == "proposed"
    assert "marketing_experiment.proposed" in await _event_types(db_session, WORKSPACE)

    started = api_client.post(
        f"/api/v1/marketing-experiments/{experiment_id}/start",
        json={
            "variant_a": {"ctr": 0.02},
            "variant_b": {"ctr": 0.04},
            "started_at": "2026-08-01T00:00:00Z",
        },
    )
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "active"
    assert "marketing_experiment.started" in await _event_types(db_session, WORKSPACE)

    completed = api_client.post(
        f"/api/v1/marketing-experiments/{experiment_id}/complete",
        json={
            "variant_a_result": {"ctr": 0.02, "roas": 1.8},
            "variant_b_result": {"ctr": 0.04, "roas": 2.4},
            "winner": "variant_b",
            "notes": "B wins on both metrics",
        },
    )
    assert completed.status_code == 200, completed.text
    body = completed.json()
    assert body["status"] == "completed"
    assert body["calibration"]["deltas"] == {"ctr": "0.02", "roas": "0.6"}
    assert body["calibration"]["keys"] == ["ctr", "roas"]
    assert "marketing_experiment.completed" in await _event_types(db_session, WORKSPACE)

    # Lifecycle guards: proposed cannot be completed; active cannot restart.
    guard = api_client.post("/api/v1/marketing-experiments", json={"hypothesis": "guard"})
    assert guard.status_code == 201
    guard_id = UUID(guard.json()["id"])
    guard_complete = api_client.post(
        f"/api/v1/marketing-experiments/{guard_id}/complete",
        json={"variant_a_result": {}, "variant_b_result": {}},
    )
    assert guard_complete.status_code == 400
    assert "not active" in guard_complete.json()["detail"]

    restart = api_client.post(f"/api/v1/marketing-experiments/{experiment_id}/start", json={})
    assert restart.status_code == 400
    assert "not proposed" in restart.json()["detail"]


@pytest.mark.asyncio
async def test_experiment_missing_returns_404(db_session, api_client) -> None:
    """Unknown experiment ids map to 404."""
    missing = UUID("00000000-0000-0000-0000-00000000dead")
    assert (
        api_client.post(f"/api/v1/marketing-experiments/{missing}/start", json={}).status_code
        == 404
    )
