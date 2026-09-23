"""Tests for BUG #3: V3 一票否决后 candidate_status 应同步推进到 rejected。"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.nuotao_selection_service import evaluate_product

# 复用现有测试 fixture 里的 session/product 结构会太长；这里只用 mock 隔离关键路径。


@pytest.mark.asyncio
async def test_v3_veto_syncs_candidate_status_to_rejected() -> None:
    """当 veto['vetoed'] 为 True 且 candidate_status='approved'，应触发 update_candidate_status。"""
    # 构造最小桩数据，让 evaluate_product 走到 veto 分支并检查副作用
    product = _build_product(candidate_status="approved")
    session = AsyncMock()
    session.get = AsyncMock(return_value=product)
    session.flush = AsyncMock()

    workspace_id = uuid.uuid4()
    product_id = product.id

    with (
        patch("app.services.nuotao_selection_service._latest_operational_score", new=AsyncMock(return_value=None)),
        patch("app.services.nuotao_selection_service.latest_cost_for_product", new=AsyncMock(return_value=None)),
        patch("app.services.nuotao_selection_service._best_supplier_rating", new=AsyncMock(return_value="A")),
        patch("app.services.nuotao_selection_service._existing_hero_categories", new=AsyncMock(return_value=())),
        patch("app.services.nuotao_selection_service._latest_ai_assessment", new=AsyncMock(return_value=None)),
        patch("app.services.nuotao_selection_service._resolve_signals", return_value=_vetoable_signals()),
        patch("app.services.nuotao_selection_service.map_dimensions", return_value=(
            _zero_dimensions(),
            {},
        )),
        patch("app.services.nuotao_selection_service.compute_nuotao_score", return_value={
            "total": 30.0,
            "grade": "reject",
        }),
        patch("app.services.nuotao_selection_service.evaluate_vetoes", return_value={
            "vetoed": True,
            "failed": ["V1"],
            "pending": [],
            "findings": [_veto_finding("V1", "fail", "brand not fit")],
        }),
        patch("app.services.nuotao_selection_service.decide_funnel_stage", return_value="rejected"),
        patch("app.services.nuotao_selection_service.coverage_report", return_value={}),
        patch("app.services.nuotao_selection_service.propose_selection_handoff", new=AsyncMock(return_value={})),
        patch("app.services.nuotao_selection_service.update_candidate_status", new=AsyncMock()) as mock_update,
    ):
        await evaluate_product(session, product_id, workspace_id=workspace_id)

    mock_update.assert_awaited_once()
    kwargs = mock_update.await_args.kwargs
    assert kwargs["new_status"] == "rejected"
    assert kwargs["actor"] == "system:v3-veto"
    assert kwargs["product_id"] == product_id
    assert kwargs["workspace_id"] == workspace_id


@pytest.mark.asyncio
async def test_v3_pass_does_not_sync_candidate_status() -> None:
    """非 veto 情况下不应调用 update_candidate_status。"""
    product = _build_product(candidate_status="approved")
    session = AsyncMock()
    session.get = AsyncMock(return_value=product)
    session.flush = AsyncMock()

    workspace_id = uuid.uuid4()
    product_id = product.id

    with (
        patch("app.services.nuotao_selection_service._latest_operational_score", new=AsyncMock(return_value=None)),
        patch("app.services.nuotao_selection_service.latest_cost_for_product", new=AsyncMock(return_value=None)),
        patch("app.services.nuotao_selection_service._best_supplier_rating", new=AsyncMock(return_value="A")),
        patch("app.services.nuotao_selection_service._existing_hero_categories", new=AsyncMock(return_value=())),
        patch("app.services.nuotao_selection_service._latest_ai_assessment", new=AsyncMock(return_value=None)),
        patch("app.services.nuotao_selection_service._resolve_signals", return_value=_vetoable_signals()),
        patch("app.services.nuotao_selection_service.map_dimensions", return_value=(_zero_dimensions(), {})),
        patch("app.services.nuotao_selection_service.compute_nuotao_score", return_value={"total": 80.0, "grade": "pass"}),
        patch("app.services.nuotao_selection_service.evaluate_vetoes", return_value={
            "vetoed": False,
            "failed": [],
            "pending": [],
            "findings": [_veto_finding("V1", "pass", "ok")],
        }),
        patch("app.services.nuotao_selection_service.decide_funnel_stage", return_value="candidate"),
        patch("app.services.nuotao_selection_service.coverage_report", return_value={}),
        patch("app.services.nuotao_selection_service.propose_selection_handoff", new=AsyncMock(return_value={})),
        patch("app.services.nuotao_selection_service.update_candidate_status", new=AsyncMock()) as mock_update,
    ):
        await evaluate_product(session, product_id, workspace_id=workspace_id)

    mock_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_v3_veto_terminal_candidate_status_is_left_alone() -> None:
    """candidate_status='winner' 时即使 veto 也不该再推 rejected。"""
    product = _build_product(candidate_status="winner")
    session = AsyncMock()
    session.get = AsyncMock(return_value=product)
    session.flush = AsyncMock()

    workspace_id = uuid.uuid4()
    product_id = product.id

    with (
        patch("app.services.nuotao_selection_service._latest_operational_score", new=AsyncMock(return_value=None)),
        patch("app.services.nuotao_selection_service.latest_cost_for_product", new=AsyncMock(return_value=None)),
        patch("app.services.nuotao_selection_service._best_supplier_rating", new=AsyncMock(return_value="A")),
        patch("app.services.nuotao_selection_service._existing_hero_categories", new=AsyncMock(return_value=())),
        patch("app.services.nuotao_selection_service._latest_ai_assessment", new=AsyncMock(return_value=None)),
        patch("app.services.nuotao_selection_service._resolve_signals", return_value=_vetoable_signals()),
        patch("app.services.nuotao_selection_service.map_dimensions", return_value=(_zero_dimensions(), {})),
        patch("app.services.nuotao_selection_service.compute_nuotao_score", return_value={"total": 30.0, "grade": "reject"}),
        patch("app.services.nuotao_selection_service.evaluate_vetoes", return_value={
            "vetoed": True,
            "failed": ["V1"],
            "pending": [],
            "findings": [_veto_finding("V1", "fail", "brand not fit")],
        }),
        patch("app.services.nuotao_selection_service.decide_funnel_stage", return_value="rejected"),
        patch("app.services.nuotao_selection_service.coverage_report", return_value={}),
        patch("app.services.nuotao_selection_service.propose_selection_handoff", new=AsyncMock(return_value={})),
        patch("app.services.nuotao_selection_service.update_candidate_status", new=AsyncMock()) as mock_update,
    ):
        await evaluate_product(session, product_id, workspace_id=workspace_id)

    mock_update.assert_not_awaited()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

from decimal import Decimal  # noqa: E402

from app.models.product import Product  # noqa: E402
from app.services.nuotao_ai_signals import NormalizedAiSignals  # noqa: E402
from app.services.nuotao_veto import VetoFinding  # noqa: E402


def _veto_finding(rule_id: str, status: str, detail: str) -> VetoFinding:
    return VetoFinding(rule_id=rule_id, status=status, detail=detail)


def _zero_dimensions() -> dict[str, Decimal]:
    return {
        "value": Decimal("0"),
        "utility": Decimal("0"),
        "weight_packability": Decimal("0"),
        "durability": Decimal("0"),
        "brand_fit": Decimal("0"),
        "differentiation": Decimal("0"),
    }


def _vetoable_signals() -> NormalizedAiSignals:
    return NormalizedAiSignals()


def _build_product(candidate_status: str) -> Product:
    import uuid as _uuid
    from datetime import datetime, timezone

    pid = _uuid.uuid4()
    ws = _uuid.uuid4()
    now = datetime.now(timezone.utc)
    return Product(
        id=pid,
        workspace_id=ws,
        sku="TEST-SKU",
        name="test product",
        status="candidate",
        candidate_status=candidate_status,
        source="manual",
        tags=[],
        attributes={},
        meta={},
        reject_reasons=[],
        created_at=now,
        updated_at=now,
    )
