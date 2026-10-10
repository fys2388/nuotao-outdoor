"""Tests for BUG #3: V3 一票否决后 candidate_status 应同步推进到 rejected。

P0-1 兼容性修复:
P0-1 在 evaluate_product 中插入了数据完整性 gate(check_integrity)。本测试的原
fixture 只有 supplier_rating='A',gate 计算分数 ≈10,必然被 gate 拦截在
map_dimensions_strict / update_candidate_status 之前,导致核心断言失败。

修复原则(业务语义不回退):
1. 保留真实 check_integrity,不绕过生产代码的完整性逻辑。
2. fixture 的 Product/operational facts 补齐到能通过 gate 的最小数据集
   (score 85+),使测试可靠进入 veto 分支。
3. mock 契约从 map_dimensions(旧宽松映射器)对齐到 map_dimensions_strict
   (P0-1 新调用点)。
4. 核心断言不变:update_candidate_status 被调用且 new_status='rejected'。
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.nuotao_selection_service import evaluate_product
from app.models.product_intelligence import ProductScore

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
        patch("app.services.nuotao_selection_service._latest_operational_score", new=AsyncMock(return_value=_full_operational_score())),
        patch("app.services.nuotao_selection_service.latest_cost_for_product", new=AsyncMock(return_value=None)),
        patch("app.services.nuotao_selection_service._best_supplier_rating", new=AsyncMock(return_value="A")),
        patch("app.services.nuotao_selection_service._existing_hero_categories", new=AsyncMock(return_value=())),
        patch("app.services.nuotao_selection_service._latest_ai_assessment", new=AsyncMock(return_value=None)),
        patch("app.services.nuotao_selection_service._resolve_signals", return_value=_vetoable_signals()),
        patch("app.services.nuotao_selection_service.map_dimensions_strict", return_value=(
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
        patch("app.services.nuotao_selection_service._latest_operational_score", new=AsyncMock(return_value=_full_operational_score())),
        patch("app.services.nuotao_selection_service.latest_cost_for_product", new=AsyncMock(return_value=None)),
        patch("app.services.nuotao_selection_service._best_supplier_rating", new=AsyncMock(return_value="A")),
        patch("app.services.nuotao_selection_service._existing_hero_categories", new=AsyncMock(return_value=())),
        patch("app.services.nuotao_selection_service._latest_ai_assessment", new=AsyncMock(return_value=None)),
        patch("app.services.nuotao_selection_service._resolve_signals", return_value=_vetoable_signals()),
        patch("app.services.nuotao_selection_service.map_dimensions_strict", return_value=(_zero_dimensions(), {})),
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
        patch("app.services.nuotao_selection_service._latest_operational_score", new=AsyncMock(return_value=_full_operational_score())),
        patch("app.services.nuotao_selection_service.latest_cost_for_product", new=AsyncMock(return_value=None)),
        patch("app.services.nuotao_selection_service._best_supplier_rating", new=AsyncMock(return_value="A")),
        patch("app.services.nuotao_selection_service._existing_hero_categories", new=AsyncMock(return_value=())),
        patch("app.services.nuotao_selection_service._latest_ai_assessment", new=AsyncMock(return_value=None)),
        patch("app.services.nuotao_selection_service._resolve_signals", return_value=_vetoable_signals()),
        patch("app.services.nuotao_selection_service.map_dimensions_strict", return_value=(_zero_dimensions(), {})),
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
    # P0-1 严格映射器(map_dimensions_strict)没有 brand_fit 覆盖时,会显式抛
    # DataInsufficientError(['brand_fit'])——而不是像旧宽松映射器那样静默用
    # NEUTRAL=5.0 兜底。Brand Fit 没有结构化数据源,只能由 AI 评估提供;
    # 因此 veto 场景下测试 fixture 让 AI 信号携带 brand_fit。
    return NormalizedAiSignals(brand_fit=Decimal("6.0"))


def _full_operational_score() -> "ProductScore":
    """返回 6 维全有的 ProductScore,让真实 check_integrity gate 通过。

    P0-1 在 evaluate_product 中插入数据完整性 gate;旧 fixture 的 operational
    为空(gate 分数 ≈35,<40),流程在 gate 处提前 gate_blocked 返回,根本
    到不了 update_candidate_status。补齐 operational 6 维(权重 30)使 gate
    通过(分数 65+),而 map_dimensions_strict 仍被 mock,不影响 veto 路径
    核心断言。
    """
    from app.models.product_intelligence import ProductScore

    return ProductScore(
        product_id=uuid.uuid4(),
        profit=Decimal("7"),
        logistics=Decimal("6"),
        demand=Decimal("8"),
        competition=Decimal("5"),
        differentiation=Decimal("6"),
        compliance=Decimal("7"),
        total=Decimal("40"),
        model_version="v3-test",
        rule_version="v3-test",
    )


def _build_product(candidate_status: str) -> Product:
    """构造能通过 P0-1 数据完整性 gate(score 85+)的 Product。

    gate 9 个字段组加权到 100:operational_dimensions(30)+margin_rate(10)
    +shipping_ratio(10)+reference_price_usd(10)+weight_kg(10)+
    supplier_rating(10)+brand_fit(10)+category(5)+return_rate(5)。
    只补齐到 ≥40(实际 85)即可让真实 check_integrity 放行;brand_fit 由
    AI 信号路径提供(见 _vetoable_signals),不伪造结构化数据。
    """
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
        # ── gate 最小通过数据集 ──
        category="Camping",              # category (5)
        weight_kg=Decimal("1.5"),        # weight_kg (10)
        meta={                           # 供 _cost_facts 提取 reference_price_usd (10)
            "sale_price": "25.0",
        },
        tags=[],
        attributes={},
        reject_reasons=[],
        created_at=now,
        updated_at=now,
    )

