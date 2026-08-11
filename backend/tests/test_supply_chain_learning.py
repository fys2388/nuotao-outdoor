"""Tests for M4.2 Supply Chain Learning Loop.

Covers: supplier/logistics prediction accuracy, deterministic pattern
extraction, calibration approval protection, extended knowledge entry types,
workspace isolation and event audit.
"""

from uuid import UUID

import pytest
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.event import EventLog
from app.models.supplier import Supplier
from app.models.supply_chain import ShipmentRecord, SupplierProfile
from sqlalchemy import select

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")


def _headers(workspace: UUID | None = None) -> dict:
    return {"X-Workspace-Id": str(workspace)} if workspace else {}


async def _event_types(db_session) -> set[str]:
    rows = (await db_session.execute(select(EventLog.event_type))).scalars().all()
    return set(rows)


async def _seed_supplier(db_session, workspace: UUID = WORKSPACE, code: str = "1688-learn") -> UUID:
    supplier = Supplier(workspace_id=workspace, code=code, name=f"Supplier {code}")
    db_session.add(supplier)
    await db_session.flush()
    return supplier.id


async def _seed_profile(
    db_session,
    supplier_id: UUID,
    *,
    workspace: UUID = WORKSPACE,
    quality_score: str = "88.5",
    on_time_rate: str = "92.0",
    defect_rate: str = "1.5",
    risk_level: str = "low",
) -> UUID:
    profile = SupplierProfile(
        workspace_id=workspace,
        supplier_id=supplier_id,
        quality_score=quality_score,
        on_time_rate=on_time_rate,
        defect_rate=defect_rate,
        risk_level=risk_level,
    )
    db_session.add(profile)
    await db_session.flush()
    return profile.id


async def _seed_shipment(db_session, workspace: UUID = WORKSPACE) -> UUID:
    shipment = ShipmentRecord(
        workspace_id=workspace,
        carrier="Cainiao",
        origin="Yiwu, China",
        destination="Los Angeles, US",
        status="delivered",
    )
    db_session.add(shipment)
    await db_session.flush()
    return shipment.id


# --------------------------------------------------------------------------- #
# 1. Supplier evaluation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_supplier_evaluation_success(db_session, api_client) -> None:
    """A matched supplier prediction/decision is classified as success."""
    supplier_id = await _seed_supplier(db_session)
    response = api_client.post(
        "/api/v1/supplier-evaluations",
        json={
            "supplier_id": str(supplier_id),
            "prediction": {"decision": "approve", "confidence": 0.8},
            "actual_result": {"decision": "approve", "success": True},
            "human_rating": 5,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["prediction_result"] == "success"
    assert body["success_flag"] is True
    assert body["error_type"] is None
    assert body["confidence_bucket"] == "HIGH"
    assert body["accuracy"]["decision_match"] is True
    assert "supply.supplier_evaluation_recorded" in await _event_types(db_session)


@pytest.mark.asyncio
async def test_supplier_evaluation_failure_classification(db_session, api_client) -> None:
    """Decision mismatch is classified as failure with error_type."""
    supplier_id = await _seed_supplier(db_session)
    response = api_client.post(
        "/api/v1/supplier-evaluations",
        json={
            "supplier_id": str(supplier_id),
            "prediction": {"decision": "approve", "confidence": 0.8},
            "actual_result": {"decision": "reject"},
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["prediction_result"] == "failure"
    assert body["success_flag"] is False
    assert body["error_type"] == "decision_mismatch"


@pytest.mark.asyncio
async def test_supplier_evaluation_missing_supplier_404(db_session, api_client) -> None:
    """Evaluating an unknown supplier returns 404."""
    missing = UUID("00000000-0000-0000-0000-00000000dead")
    response = api_client.post(
        "/api/v1/supplier-evaluations",
        json={"supplier_id": str(missing), "prediction": {}, "actual_result": {}},
    )
    assert response.status_code == 404
    assert "supplier not found" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# 2. Logistics evaluation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_logistics_evaluation_delay_failure(db_session, api_client) -> None:
    """A delayed delivery prediction mismatch is recorded with delay reason."""
    shipment_id = await _seed_shipment(db_session)
    response = api_client.post(
        "/api/v1/logistics-evaluations",
        json={
            "shipment_id": str(shipment_id),
            "prediction": {"decision": "on_time", "confidence": 0.7, "delivery_time_days": 10},
            "actual_result": {"decision": "delayed", "delayed": True, "delay_days": 5},
            "delay_reason": "customs hold",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["prediction_result"] == "failure"
    assert body["error_type"] == "decision_mismatch"
    assert body["delay_reason"] == "customs hold"
    assert body["carrier"] == "Cainiao"
    assert body["route"] == "Yiwu, China -> Los Angeles, US"
    assert "supply.logistics_evaluation_recorded" in await _event_types(db_session)


@pytest.mark.asyncio
async def test_logistics_evaluation_missing_shipment_404(db_session, api_client) -> None:
    """Evaluating an unknown shipment returns 404."""
    missing = UUID("00000000-0000-0000-0000-00000000dead")
    response = api_client.post(
        "/api/v1/logistics-evaluations",
        json={"shipment_id": str(missing), "prediction": {}, "actual_result": {}},
    )
    assert response.status_code == 404
    assert "shipment not found" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# 3. Pattern mining
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_supplier_pattern_extraction(db_session, api_client) -> None:
    """Quality/risk patterns aggregate deterministically from profiles+evaluations."""
    supplier_id = await _seed_supplier(db_session)
    await _seed_profile(
        db_session, supplier_id, quality_score="90", defect_rate="1", on_time_rate="95"
    )
    await _seed_profile(
        db_session,
        await _seed_supplier(db_session, code="1688-learn-2"),
        quality_score="80",
        defect_rate="2",
        on_time_rate="90",
        risk_level="high",
    )
    api_client.post(
        "/api/v1/supplier-evaluations",
        json={
            "supplier_id": str(supplier_id),
            "prediction": {"decision": "approve"},
            "actual_result": {"decision": "reject"},
        },
    )

    quality = api_client.post(
        "/api/v1/supplier-pattern-runs", json={"pattern_type": "quality_pattern"}
    )
    assert quality.status_code == 201, quality.text
    quality_body = quality.json()
    assert quality_body["output_pattern"]["avg_quality_score"] == "85.00"
    assert quality_body["output_pattern"]["avg_defect_rate"] == "1.50"

    risk = api_client.post("/api/v1/supplier-pattern-runs", json={"pattern_type": "risk_pattern"})
    assert risk.status_code == 201, risk.text
    risk_body = risk.json()
    assert risk_body["output_pattern"]["failure_rate"] == "1.0000"
    assert risk_body["output_pattern"]["risk_level_distribution"]["high"] == 1
    assert "supply.supplier_pattern_run_completed" in await _event_types(db_session)


@pytest.mark.asyncio
async def test_logistics_pattern_extraction(db_session, api_client) -> None:
    """Delay/country patterns aggregate deterministically from evaluations."""
    shipment_id = await _seed_shipment(db_session)
    for reason in ("customs hold", "customs hold", "weather"):
        api_client.post(
            "/api/v1/logistics-evaluations",
            json={
                "shipment_id": str(shipment_id),
                "prediction": {"decision": "on_time"},
                "actual_result": {"decision": "delayed"},
                "delay_reason": reason,
            },
        )

    delay = api_client.post(
        "/api/v1/logistics-pattern-runs", json={"pattern_type": "delay_pattern"}
    )
    assert delay.status_code == 201, delay.text
    delay_body = delay.json()
    assert delay_body["output_pattern"]["failure_evaluation_count"] == 3
    assert delay_body["output_pattern"]["top_delay_reason"] == "customs hold"
    assert delay_body["output_pattern"]["delay_reason_distribution"]["weather"] == 1

    country = api_client.post(
        "/api/v1/logistics-pattern-runs", json={"pattern_type": "country_pattern"}
    )
    assert country.status_code == 201, country.text
    country_body = country.json()
    assert country_body["output_pattern"]["countries"]["US"]["count"] == 3
    assert "supply.logistics_pattern_run_completed" in await _event_types(db_session)


# --------------------------------------------------------------------------- #
# 4. Calibration (human approval only)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_calibration_requires_evaluations(db_session, api_client) -> None:
    """Calibration without evaluations is rejected."""
    response = api_client.post("/api/v1/supply-chain-calibration/runs")
    assert response.status_code == 400
    assert "not enough evaluations" in response.json()["detail"]


@pytest.mark.asyncio
async def test_calibration_approval_protection(db_session, api_client) -> None:
    """A proposal must be human-approved exactly once."""
    supplier_id = await _seed_supplier(db_session)
    shipment_id = await _seed_shipment(db_session)
    api_client.post(
        "/api/v1/supplier-evaluations",
        json={
            "supplier_id": str(supplier_id),
            "prediction": {"decision": "approve"},
            "actual_result": {"decision": "approve"},
        },
    )
    api_client.post(
        "/api/v1/logistics-evaluations",
        json={
            "shipment_id": str(shipment_id),
            "prediction": {"decision": "on_time"},
            "actual_result": {"decision": "delayed"},
        },
    )

    created = api_client.post("/api/v1/supply-chain-calibration/runs")
    assert created.status_code == 201, created.text
    run = created.json()
    assert run["status"] == "proposed"
    assert run["metrics"]["supplier_failure_count"] == 0
    assert run["metrics"]["logistics_failure_count"] == 1
    assert "supply.calibration_run_proposed" in await _event_types(db_session)

    approved = api_client.post(
        f"/api/v1/supply-chain-calibration/runs/{run['id']}/approve",
        json={"actor": "owner@nuotao.example", "note": "ok"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_by"] == "owner@nuotao.example"
    assert approved.json()["approved_at"] is not None
    assert "supply.calibration_run_approved" in await _event_types(db_session)

    again = api_client.post(
        f"/api/v1/supply-chain-calibration/runs/{run['id']}/approve",
        json={"actor": "owner@nuotao.example"},
    )
    assert again.status_code == 400
    assert "not proposed" in again.json()["detail"]


@pytest.mark.asyncio
async def test_calibration_reject_flow(db_session, api_client) -> None:
    """Human rejection records the decision without pattern changes."""
    supplier_id = await _seed_supplier(db_session)
    api_client.post(
        "/api/v1/supplier-evaluations",
        json={
            "supplier_id": str(supplier_id),
            "prediction": {"decision": "approve"},
            "actual_result": {"decision": "approve"},
        },
    )
    run_id = api_client.post("/api/v1/supply-chain-calibration/runs").json()["id"]
    rejected = api_client.post(
        f"/api/v1/supply-chain-calibration/runs/{run_id}/reject",
        json={"actor": "owner@nuotao.example", "note": "not now"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert "supply.calibration_run_rejected" in await _event_types(db_session)


# --------------------------------------------------------------------------- #
# 5. Knowledge extension + workspace isolation + event audit
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_knowledge_new_entry_types(db_session, api_client) -> None:
    """M4.2 knowledge entry types are accepted by the knowledge API."""
    supplier_id = await _seed_supplier(db_session)
    for entry_type, title in (
        ("supplier_success_pattern", "Reliable factory"),
        ("supplier_failure_pattern", "Defect spike"),
        ("logistics_success_pattern", "Fast lane"),
        ("logistics_failure_pattern", "Customs delays"),
        ("season_pattern", "Q4 peak"),
        ("country_pattern", "US customs"),
    ):
        response = api_client.post(
            "/api/v1/supply-chain-knowledge-entries",
            json={
                "supplier_id": str(supplier_id),
                "entry_type": entry_type,
                "title": title,
                "content": f"{title} learning entry.",
                "confidence": 0.8,
            },
        )
        assert response.status_code == 201, response.text
    assert "supply.knowledge_created" in await _event_types(db_session)


@pytest.mark.asyncio
async def test_workspace_isolation(db_session, api_client) -> None:
    """Evaluations, pattern runs and calibrations are workspace-scoped."""
    supplier_id = await _seed_supplier(db_session, workspace=WORKSPACE)
    shipment_id = await _seed_shipment(db_session, workspace=WORKSPACE)
    api_client.post(
        "/api/v1/supplier-evaluations",
        json={
            "supplier_id": str(supplier_id),
            "prediction": {"decision": "approve"},
            "actual_result": {"decision": "approve"},
        },
    )
    api_client.post(
        "/api/v1/logistics-evaluations",
        json={
            "shipment_id": str(shipment_id),
            "prediction": {"decision": "on_time"},
            "actual_result": {"decision": "delayed"},
        },
    )
    api_client.post("/api/v1/supplier-pattern-runs", json={"pattern_type": "quality_pattern"})
    api_client.post("/api/v1/supply-chain-calibration/runs")

    assert (
        api_client.get("/api/v1/supplier-evaluations", headers=_headers(OTHER_WORKSPACE)).json()
        == []
    )
    assert (
        api_client.get("/api/v1/logistics-evaluations", headers=_headers(OTHER_WORKSPACE)).json()
        == []
    )
    assert (
        api_client.get("/api/v1/supplier-pattern-runs", headers=_headers(OTHER_WORKSPACE)).json()
        == []
    )
    assert (
        api_client.get(
            "/api/v1/supply-chain-calibration/runs", headers=_headers(OTHER_WORKSPACE)
        ).json()
        == []
    )


@pytest.mark.asyncio
async def test_event_audit_has_trace_id(db_session, api_client) -> None:
    """Learning-loop writes land in event_log with trace_id."""
    supplier_id = await _seed_supplier(db_session)
    api_client.post(
        "/api/v1/supplier-evaluations",
        json={
            "supplier_id": str(supplier_id),
            "prediction": {"decision": "approve"},
            "actual_result": {"decision": "approve"},
        },
    )
    rows = (
        (
            await db_session.execute(
                select(EventLog).where(EventLog.event_type == "supply.supplier_evaluation_recorded")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].workspace_id == WORKSPACE
    assert rows[0].entity_type == "supplier"
    assert rows[0].trace_id is not None
