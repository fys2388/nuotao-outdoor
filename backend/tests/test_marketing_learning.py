"""Tests for M3.2 Marketing Learning Loop.

Covers: campaign evaluation + error classification, creative analysis audit,
marketing knowledge retrieval, growth context builder, calibration pattern
discovery + human approval protection and workspace isolation.
"""

from uuid import UUID

import pytest
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.event import EventLog
from sqlalchemy import select

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")


def _headers(workspace: UUID | None = None) -> dict:
    return {"X-Workspace-Id": str(workspace)} if workspace else {}


async def _event_types(db_session, workspace: UUID) -> set[str]:
    rows = (await db_session.execute(select(EventLog.event_type))).scalars().all()
    return set(rows)


def _campaign_payload(tag: str, **overrides) -> dict:
    payload = {
        "platform": "meta",
        "campaign_id": f"m32-{tag}",
        "name": f"Campaign {tag}",
        "budget": "100.00",
        "spend": "50.00",
        "impressions": 5000,
        "clicks": 200,
        "conversion": 10,
        "revenue": "120.00",
    }
    payload.update(overrides)
    return payload


def _creative_payload(tag: str, **overrides) -> dict:
    payload = {
        "platform": "meta",
        "asset_type": "video",
        "hook": f"Hook {tag}",
        "copy": f"Copy {tag}",
        "status": "active",
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------- #
# 1. Campaign evaluation + error classification
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_campaign_evaluation_success(db_session, api_client) -> None:
    """A matched prediction/decision is classified as success."""
    campaign_id = UUID(
        api_client.post("/api/v1/campaigns", json=_campaign_payload("eval-ok")).json()["id"]
    )
    response = api_client.post(
        "/api/v1/marketing-evaluations",
        json={
            "campaign_id": str(campaign_id),
            "prediction": {"decision": "scale", "roas": "2.0", "confidence": 0.8},
            "actual_result": {"decision": "scale", "roas": "2.5", "ctr": "0.04"},
            "human_rating": 4,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["prediction_result"] == "success"
    assert body["success_flag"] is True
    assert body["error_type"] is None
    assert body["confidence_bucket"] == "HIGH"
    assert body["confidence"] == "0.8"
    assert body["metric_snapshot"]["actual_roas"] == "2.5"
    assert "marketing.campaign_evaluation.recorded" in await _event_types(
        db_session, WORKSPACE
    )


@pytest.mark.asyncio
async def test_campaign_evaluation_failure_classification(db_session, api_client) -> None:
    """Failure modes are classified: decision_mismatch / metric_miss / other."""
    campaign_id = UUID(
        api_client.post("/api/v1/campaigns", json=_campaign_payload("eval-fail")).json()["id"]
    )

    mismatch = api_client.post(
        "/api/v1/marketing-evaluations",
        json={
            "campaign_id": str(campaign_id),
            "prediction": {"decision": "scale"},
            "actual_result": {"decision": "pause"},
        },
    )
    assert mismatch.status_code == 201
    assert mismatch.json()["prediction_result"] == "failure"
    assert mismatch.json()["error_type"] == "decision_mismatch"

    miss = api_client.post(
        "/api/v1/marketing-evaluations",
        json={
            "campaign_id": str(campaign_id),
            "prediction": {"roas": "3.0"},
            "actual_result": {"roas": "0.5"},
        },
    )
    assert miss.status_code == 201
    assert miss.json()["error_type"] == "metric_miss"

    other = api_client.post(
        "/api/v1/marketing-evaluations",
        json={
            "campaign_id": str(campaign_id),
            "prediction": {},
            "actual_result": {"success": False, "ctr": "0.001"},
        },
    )
    assert other.status_code == 201
    assert other.json()["prediction_result"] == "failure"
    assert other.json()["error_type"] == "other"


@pytest.mark.asyncio
async def test_campaign_evaluation_missing_campaign_404(db_session, api_client) -> None:
    """Evaluating an unknown campaign returns 404."""
    missing = UUID("00000000-0000-0000-0000-00000000dead")
    response = api_client.post(
        "/api/v1/marketing-evaluations",
        json={"campaign_id": str(missing), "prediction": {}, "actual_result": {}},
    )
    assert response.status_code == 404
    assert "campaign not found" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# 2. Creative intelligence audit
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_creative_analysis_run(db_session, api_client) -> None:
    """Creative analysis runs round-trip with input/output/result audit."""
    creative_id = UUID(
        api_client.post("/api/v1/creatives", json=_creative_payload("analysis")).json()["id"]
    )
    response = api_client.post(
        "/api/v1/creative-analysis-runs",
        json={
            "creative_id": str(creative_id),
            "input_snapshot": {"hook": "Lightest chair", "platform": "meta"},
            "analysis_output": {"strengths": ["clear hook"], "suggested_angle": "weight"},
            "performance_result": {"ctr": 0.03},
            "model_version": "creative-insight-v1",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["model_version"] == "creative-insight-v1"
    assert body["analysis_output"]["suggested_angle"] == "weight"
    assert "marketing.creative_analysis.recorded" in await _event_types(
        db_session, WORKSPACE
    )

    listed = api_client.get("/api/v1/creative-analysis-runs")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


# --------------------------------------------------------------------------- #
# 3. Marketing knowledge memory
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_marketing_knowledge_crud_filters(db_session, api_client) -> None:
    """Knowledge entries are filterable by entry_type and category."""
    creative_entry = {
        "entry_type": "creative_pattern",
        "category": "trekking-chair",
        "title": "Weight hook wins",
        "content": "Weight-focused hooks beat price hooks on CTR.",
        "tags": ["weight", "hook"],
        "source": "evaluation",
        "confidence": "0.85",
    }
    failure_entry = {
        "entry_type": "failure_pattern",
        "category": "trekking-chair",
        "title": "Price hook fails",
        "content": "Price hooks underperform for premium positioning.",
        "tags": ["price"],
        "source": "evaluation",
        "confidence": "0.70",
    }
    assert api_client.post(
        "/api/v1/marketing-knowledge-entries", json=creative_entry
    ).status_code == 201
    assert api_client.post(
        "/api/v1/marketing-knowledge-entries", json=failure_entry
    ).status_code == 201
    assert "marketing.knowledge.created" in await _event_types(db_session, WORKSPACE)

    by_type = api_client.get(
        "/api/v1/marketing-knowledge-entries?entry_type=creative_pattern"
    ).json()
    assert len(by_type) == 1
    assert by_type[0]["title"] == "Weight hook wins"

    by_category = api_client.get(
        "/api/v1/marketing-knowledge-entries?category=trekking-chair"
    ).json()
    assert len(by_category) == 2


# --------------------------------------------------------------------------- #
# 4. Growth context builder
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_growth_context_builder(db_session, api_client) -> None:
    """Context combines campaign + creatives/experiments/feedback/evaluations/knowledge."""
    campaign_id = UUID(
        api_client.post("/api/v1/campaigns", json=_campaign_payload("ctx")).json()["id"]
    )
    creative_id = UUID(
        api_client.post("/api/v1/creatives", json=_creative_payload("ctx")).json()["id"]
    )
    # Evaluation + knowledge linked to the campaign.
    assert (
        api_client.post(
            "/api/v1/marketing-evaluations",
            json={
                "campaign_id": str(campaign_id),
                "prediction": {"roas": "2.0"},
                "actual_result": {"roas": "2.2"},
            },
        ).status_code
        == 201
    )
    assert (
        api_client.post(
            "/api/v1/marketing-knowledge-entries",
            json={
                "campaign_id": str(campaign_id),
                "creative_id": str(creative_id),
                "entry_type": "copy_pattern",
                "title": "Short copy wins",
                "content": "Under 40 chars converts better.",
                "confidence": "0.6",
            },
        ).status_code
        == 201
    )

    context = api_client.get(f"/api/v1/marketing-context/{campaign_id}")
    assert context.status_code == 200, context.text
    body = context.json()
    assert body["campaign"]["campaign_id"] == "m32-ctx"
    assert len(body["evaluations"]) == 1
    assert len(body["knowledge"]) == 1
    assert body["knowledge"][0]["creative_id"] == str(creative_id)
    # Keys are all present; JSON-safe (no Decimal objects).
    for key in ("campaign", "creatives", "experiments", "feedback", "evaluations", "knowledge"):
        assert key in body

    missing = UUID("00000000-0000-0000-0000-00000000dead")
    assert api_client.get(f"/api/v1/marketing-context/{missing}").status_code == 404


# --------------------------------------------------------------------------- #
# 5. Calibration: patterns + approval protection
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_marketing_calibration_patterns_and_approval(db_session, api_client) -> None:
    """Calibration discovers patterns; approve/reject is human-only."""
    campaign_id = UUID(
        api_client.post("/api/v1/campaigns", json=_campaign_payload("cal")).json()["id"]
    )
    for prediction, actual in (
        ({"decision": "scale", "roas": "2.0"}, {"decision": "scale", "roas": "2.5"}),
        ({"decision": "scale", "roas": "2.0"}, {"decision": "pause", "roas": "0.8"}),
        ({"decision": "scale", "roas": "2.0"}, {"decision": "scale", "roas": "1.8"}),
    ):
        response = api_client.post(
            "/api/v1/marketing-evaluations",
            json={
                "campaign_id": str(campaign_id),
                "prediction": prediction,
                "actual_result": actual,
            },
        )
        assert response.status_code == 201

    created = api_client.post("/api/v1/marketing-calibration/runs")
    assert created.status_code == 201, created.text
    body = created.json()
    run_id = UUID(body["id"])
    assert body["status"] == "proposed"
    assert body["sample_size"] == 3
    assert body["successful_patterns"]["evaluation_success_count"] == 2
    assert body["failure_patterns"]["error_type_distribution"] == {"decision_mismatch": 1}
    assert "marketing.calibration_run_proposed" in await _event_types(db_session, WORKSPACE)

    # Approval is human-only and recorded (rules never auto-edited).
    approved = api_client.post(
        f"/api/v1/marketing-calibration/runs/{run_id}/approve",
        json={"actor": "owner@nuotao.example", "note": "ok"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_by"] == "owner@nuotao.example"
    assert "marketing.calibration_run_approved" in await _event_types(db_session, WORKSPACE)

    # Re-approving a non-proposed run fails.
    again = api_client.post(
        f"/api/v1/marketing-calibration/runs/{run_id}/approve",
        json={"actor": "owner@nuotao.example"},
    )
    assert again.status_code == 400
    assert "not proposed" in again.json()["detail"]


@pytest.mark.asyncio
async def test_marketing_calibration_reject(db_session, api_client) -> None:
    """Rejection records the decision and keeps the run rejected."""
    campaign_id = UUID(
        api_client.post("/api/v1/campaigns", json=_campaign_payload("cal-rej")).json()["id"]
    )
    assert (
        api_client.post(
            "/api/v1/marketing-evaluations",
            json={
                "campaign_id": str(campaign_id),
                "prediction": {"roas": "2.0"},
                "actual_result": {"roas": "2.5"},
            },
        ).status_code
        == 201
    )
    run_id = UUID(api_client.post("/api/v1/marketing-calibration/runs").json()["id"])
    rejected = api_client.post(
        f"/api/v1/marketing-calibration/runs/{run_id}/reject",
        json={"actor": "owner@nuotao.example", "note": "not now"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_marketing_calibration_requires_samples(db_session, api_client) -> None:
    """Calibration without enough evaluations returns 400."""
    response = api_client.post("/api/v1/marketing-calibration/runs")
    assert response.status_code == 400
    assert "not enough evaluations" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# 6. Workspace isolation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_marketing_learning_workspace_isolation(db_session, api_client) -> None:
    """Evaluations and knowledge stay invisible across workspaces."""
    campaign_id = UUID(
        api_client.post("/api/v1/campaigns", json=_campaign_payload("iso")).json()["id"]
    )
    assert (
        api_client.post(
            "/api/v1/marketing-evaluations",
            json={
                "campaign_id": str(campaign_id),
                "prediction": {"roas": "2.0"},
                "actual_result": {"roas": "2.5"},
            },
        ).status_code
        == 201
    )

    mine = api_client.get("/api/v1/marketing-evaluations").json()
    theirs = api_client.get(
        "/api/v1/marketing-evaluations", headers=_headers(OTHER_WORKSPACE)
    ).json()
    assert len(mine) == 1
    assert len(theirs) == 0

    # Cross-workspace context lookup returns 404 (campaign belongs elsewhere).
    assert (
        api_client.get(
            f"/api/v1/marketing-context/{campaign_id}", headers=_headers(OTHER_WORKSPACE)
        ).status_code
        == 404
    )
