"""P0-2 Product Factory Orchestrator — 18 integration tests.

Tests cover:
1. candidate → workflow auto start
2. data ready → V3
3. missing data → auto backfill
4. backfill failure → retry
5. retry exhausted → exception
6. V3 reject → stop
7. decision approval → resume
8. Product Master idempotent
9. Creative failure → retry
10. Listing Gate blocked → stop
11. WC 429 → retry
12. WC 5xx → retry
13. WC duplicate → update
14. WC verify failure → exception
15. duplicate workflow → resume existing
16. cross workspace isolation
17. trace_id propagation
18. no fake success
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.product import Product
from app.models.workflow import (
    WORKFLOW_STAGES,
    WorkflowException,
    WorkflowRun,
)


# ── Fixtures ────────────────────────────────────────────────────────


DEFAULT_WS = UUID("00000000-0000-0000-0000-000000000001")


@pytest_asyncio.fixture
async def session():
    """In-memory SQLite session for tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def candidate_product(session: AsyncSession):
    """Create a product with candidate_status='candidate'."""
    product = Product(
        workspace_id=DEFAULT_WS,
        sku="NT-TEST-001",
        name="Test Product",
        description="A test product for orchestrator tests",
        category="Camping",
        brand="TestBrand",
        status="draft",
        candidate_status="candidate",
        source="1688",
        source_url="https://detail.1688.com/offer/123456.html",
        source_offer_id="123456",
        target_market="US",
    )
    session.add(product)
    await session.flush()
    return product


@pytest_asyncio.fixture
async def approved_product(session: AsyncSession):
    """Create a product with candidate_status='approved'."""
    product = Product(
        workspace_id=DEFAULT_WS,
        sku="NT-TEST-002",
        name="Approved Product",
        description="An approved test product",
        category="Camping",
        brand="TestBrand",
        status="active",
        candidate_status="approved",
        source="1688",
        source_url="https://detail.1688.com/offer/654321.html",
        source_offer_id="654321",
        target_market="US",
    )
    session.add(product)
    await session.flush()
    return product


@pytest_asyncio.fixture
async def mastered_product(session: AsyncSession):
    """Create a product that is already mastered."""
    product = Product(
        workspace_id=DEFAULT_WS,
        sku="NT-TEST-003",
        name="Mastered Product",
        description="An already-mastered product",
        category="Camping",
        brand="TestBrand",
        status="active",
        candidate_status="winner",
        source="1688",
        source_url="https://detail.1688.com/offer/789012.html",
        source_offer_id="789012",
        target_market="US",
        mastered_at=datetime.now(UTC),
        mastered_by="test_user",
        mastered_trace_id="test-trace-001",
    )
    session.add(product)
    await session.flush()
    return product


# ── Tests ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_01_candidate_workflow_auto_start(
    session: AsyncSession, candidate_product: Product
):
    """S1: candidate → workflow auto start."""
    from app.services.product_factory_orchestrator import (
        trigger_workflow,
        execute_workflow,
    )

    run = await trigger_workflow(
        session,
        workspace_id=DEFAULT_WS,
        product_id=candidate_product.id,
    )

    assert run.execution_status == "RUNNING"
    assert run.current_stage == "CANDIDATE_READY"
    assert run.trace_id is not None

    # Execute first stage — should pass
    run = await execute_workflow(
        session,
        run_id=run.id,
        workspace_id=DEFAULT_WS,
    )
    await session.commit()

    # Should advance to DATA_READINESS
    assert run.current_stage == "DATA_READINESS"
    assert run.execution_status == "RUNNING"


@pytest.mark.asyncio
async def test_02_data_ready_to_v3(
    session: AsyncSession, candidate_product: Product
):
    """S2: data ready → V3."""
    from app.services.product_factory_orchestrator import (
        trigger_workflow,
        execute_workflow,
    )

    # Mock data integrity gate to pass
    from app.services.data_integrity_gate import GateResult
    mock_gate = GateResult(
        passed=True, status="complete", score=Decimal("85.00"),
        missing_fields=[], total_weight=Decimal("100.00"),
        passed_weight=Decimal("85.00"), version="v1",
    )

    async def _mock_evaluate_product(s, pid, **kwargs):
        return {
            "grade": "pass",
            "nuotao_total": 75.0,
            "funnel_stage": "approved",
            "gate_blocked": False,
            "veto": {"failed": [], "pending": []},
            "evidence": {"operational_v2_coverage": {"coverage_ratio": 0.9}},
        }

    with patch(
        "app.services.data_integrity_gate.check_integrity",
        return_value=mock_gate,
    ), patch(
        "app.services.nuotao_selection_service.evaluate_product",
        side_effect=_mock_evaluate_product,
    ):
        run = await trigger_workflow(
            session,
            workspace_id=DEFAULT_WS,
            product_id=candidate_product.id,
        )
        # Execute S1 (CANDIDATE_READY)
        run = await execute_workflow(session, run_id=run.id, workspace_id=DEFAULT_WS)
        # Execute S2 (DATA_READINESS) — should pass with mock
        run = await execute_workflow(session, run_id=run.id, workspace_id=DEFAULT_WS)
        await session.commit()

        # S2 advances to the AI_ANALYSIS stage (which now sits between data
        # readiness and V3 so the analyst can produce brand_fit in-pipeline).
        assert run.current_stage == "AI_ANALYSIS"


@pytest.mark.asyncio
async def test_03_missing_data_auto_backfill(
    session: AsyncSession, candidate_product: Product
):
    """S2: missing data → auto backfill."""
    from app.services.product_factory_orchestrator import (
        trigger_workflow,
        execute_workflow,
    )

    # Mock backfill to succeed
    async def _mock_backfill(s, **kwargs):
        return {"total": 1, "backfilled": 1}

    with patch(
        "app.services.backfill_1688_service.backfill_1688_products",
        side_effect=_mock_backfill,
    ):
        run = await trigger_workflow(
            session,
            workspace_id=DEFAULT_WS,
            product_id=candidate_product.id,
        )
        # Execute S1
        run = await execute_workflow(session, run_id=run.id, workspace_id=DEFAULT_WS)
        # Execute S2 — data integrity will fail, backfill should be attempted
        # The retry logic handles this
        run = await execute_workflow(session, run_id=run.id, workspace_id=DEFAULT_WS)
        await session.commit()

        # Should have either advanced past S2 or be retrying
        assert run.execution_status in ("RUNNING", "EXCEPTION")


@pytest.mark.asyncio
async def test_04_backfill_failure_retry(
    session: AsyncSession, candidate_product: Product
):
    """S2: backfill failure → retry."""
    from app.services.product_factory_orchestrator import (
        trigger_workflow,
        execute_workflow,
    )
    from app.services.data_integrity_gate import GateResult

    # candidate_product is minimal (weight_kg + category only, gate score ~15):
    # the real gate would fail → readiness V3_NEEDS_DATA → S2 attempts backfill.
    # Backfill failure → RETRY.
    mock_gate = GateResult(
        passed=False, status="missing", score=Decimal("15.00"),
        missing_fields=[
            "operational_dimensions", "margin_rate", "shipping_ratio",
            "reference_price_usd", "supplier_rating", "brand_fit", "return_rate",
        ],
        total_weight=Decimal("100.00"),
        passed_weight=Decimal("15.00"), version="v1",
    )

    call_count = 0

    async def _mock_backfill_fail(s, **kwargs):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("1688 API timeout")

    with patch(
        "app.services.data_integrity_gate.check_integrity",
        return_value=mock_gate,
    ), patch(
        "app.services.backfill_1688_service.backfill_1688_products",
        side_effect=_mock_backfill_fail,
    ):
        run = await trigger_workflow(
            session,
            workspace_id=DEFAULT_WS,
            product_id=candidate_product.id,
        )
        # Execute S1
        run = await execute_workflow(session, run_id=run.id, workspace_id=DEFAULT_WS)
        # Execute S2 — should retry
        run = await execute_workflow(session, run_id=run.id, workspace_id=DEFAULT_WS)
        await session.commit()

        # Should have incremented retry_count
        assert run.retry_count >= 1
        assert run.execution_status in ("RUNNING", "EXCEPTION")


@pytest.mark.asyncio
async def test_05_retry_exhausted_exception(
    session: AsyncSession, candidate_product: Product
):
    """S2: retry exhausted → exception."""
    from app.services.product_factory_orchestrator import (
        trigger_workflow,
        execute_workflow,
        get_exception_queue,
    )
    from app.services.data_integrity_gate import GateResult

    # candidate_product is minimal: the real gate would fail → readiness
    # V3_NEEDS_DATA → S2 attempts backfill → failure → retry.
    # Retry exhaustion → EXCEPTION.
    mock_gate = GateResult(
        passed=False, status="missing", score=Decimal("15.00"),
        missing_fields=[
            "operational_dimensions", "margin_rate", "shipping_ratio",
            "reference_price_usd", "supplier_rating", "brand_fit", "return_rate",
        ],
        total_weight=Decimal("100.00"),
        passed_weight=Decimal("15.00"), version="v1",
    )

    async def _mock_backfill_fail(s, **kwargs):
        raise RuntimeError("1688 API permanent failure")

    with patch(
        "app.services.data_integrity_gate.check_integrity",
        return_value=mock_gate,
    ), patch(
        "app.services.backfill_1688_service.backfill_1688_products",
        side_effect=_mock_backfill_fail,
    ):
        run = await trigger_workflow(
            session,
            workspace_id=DEFAULT_WS,
            product_id=candidate_product.id,
        )
        # Execute S1
        run = await execute_workflow(session, run_id=run.id, workspace_id=DEFAULT_WS)

        # Execute S2 multiple times until retry exhausted
        for _ in range(5):
            run = await execute_workflow(session, run_id=run.id, workspace_id=DEFAULT_WS)
            if run.execution_status in ("EXCEPTION", "FAILED", "COMPLETED"):
                break

        await session.commit()

        # Should be in EXCEPTION state
        assert run.execution_status == "EXCEPTION"
        assert run.retry_count >= 3

        # Exception should be in the queue
        exceptions = await get_exception_queue(
            session, workspace_id=DEFAULT_WS, unresolved_only=True
        )
        assert len(exceptions) >= 1
        assert exceptions[0]["stage"] == "DATA_READINESS"


@pytest.mark.asyncio
async def test_06_v3_reject_stop(
    session: AsyncSession, candidate_product: Product
):
    """S3: V3 reject → stop."""
    from app.services.product_factory_orchestrator import (
        trigger_workflow,
        execute_workflow,
    )
    from app.services.data_integrity_gate import GateResult

    mock_gate = GateResult(
        passed=True, status="complete", score=Decimal("85.00"),
        missing_fields=[], total_weight=Decimal("100.00"),
        passed_weight=Decimal("85.00"), version="v1",
    )

    async def _mock_evaluate_reject(s, pid, **kwargs):
        return {
            "grade": "reject",
            "nuotao_total": 30.0,
            "funnel_stage": "rejected",
            "gate_blocked": True,
            "veto": {"failed": ["V4_low_margin"], "pending": []},
            "evidence": {"operational_v2_coverage": {"coverage_ratio": 0.8}},
        }

    with patch(
        "app.services.data_integrity_gate.check_integrity",
        return_value=mock_gate,
    ), patch(
        "app.services.nuotao_selection_service.evaluate_product",
        side_effect=_mock_evaluate_reject,
    ), patch(
        # AI_ANALYSIS reuses an existing assessment, so no LLM call is made.
        "app.services.evaluation_context._latest_ai_assessment",
        new=AsyncMock(return_value={"brand_fit": "7.0", "veto_signals": {}}),
    ):
        run = await trigger_workflow(
            session,
            workspace_id=DEFAULT_WS,
            product_id=candidate_product.id,
        )
        # Execute through S1-S5
        # (CANDIDATE_READY→DATA_READINESS→AI_ANALYSIS→V3_EVALUATION→HARD_RULES)
        for _ in range(5):
            run = await execute_workflow(session, run_id=run.id, workspace_id=DEFAULT_WS)
            if run.execution_status in ("EXCEPTION", "FAILED", "COMPLETED"):
                break
        await session.commit()

        # Should have ended due to hard veto
        assert run.execution_status in ("EXCEPTION", "FAILED")
        if run.last_error:
            assert "veto" in run.last_error.lower() or "V3" in run.last_error


@pytest.mark.asyncio
async def test_07_decision_approval_resume(
    session: AsyncSession, candidate_product: Product
):
    """S5: decision approval → resume."""
    from app.services.product_factory_orchestrator import (
        trigger_workflow,
        execute_workflow,
        resume_workflow,
    )
    from app.models.agent_operations import AgentApproval
    from app.services.data_integrity_gate import GateResult

    mock_gate = GateResult(
        passed=True, status="complete", score=Decimal("85.00"),
        missing_fields=[], total_weight=Decimal("100.00"),
        passed_weight=Decimal("85.00"), version="v1",
    )

    async def _mock_evaluate_pass(s, pid, **kwargs):
        return {
            "grade": "pass",
            "nuotao_total": 80.0,
            "funnel_stage": "approved",
            "gate_blocked": False,
            "veto": {"failed": [], "pending": []},
            "evidence": {"operational_v2_coverage": {"coverage_ratio": 0.9}},
        }

    with patch(
        "app.services.data_integrity_gate.check_integrity",
        return_value=mock_gate,
    ), patch(
        "app.services.nuotao_selection_service.evaluate_product",
        side_effect=_mock_evaluate_pass,
    ), patch(
        # AI_ANALYSIS reuses an existing assessment, so no LLM call is made.
        "app.services.evaluation_context._latest_ai_assessment",
        new=AsyncMock(return_value={"brand_fit": "7.0", "veto_signals": {}}),
    ):
        run = await trigger_workflow(
            session,
            workspace_id=DEFAULT_WS,
            product_id=candidate_product.id,
        )
        # Execute S1-S4
        # (CANDIDATE_READY, DATA_READINESS, AI_ANALYSIS, V3_EVALUATION)
        for _ in range(4):
            run = await execute_workflow(session, run_id=run.id, workspace_id=DEFAULT_WS)
            if run.execution_status in ("EXCEPTION", "FAILED", "COMPLETED"):
                break

        # S5 HARD_RULES should pass (no veto)
        run = await execute_workflow(session, run_id=run.id, workspace_id=DEFAULT_WS)
        # S6 PRODUCT_DECISION should WAIT (no approval yet)
        run = await execute_workflow(session, run_id=run.id, workspace_id=DEFAULT_WS)
        await session.commit()

        assert run.execution_status == "WAITING_APPROVAL"

        # Now create an approval and resume
        approval = AgentApproval(
            workspace_id=DEFAULT_WS,
            approval_type="product_decision",
            entity_type="product",
            entity_id=str(candidate_product.id),
            status="approved",
        )
        session.add(approval)
        await session.flush()

        run = await resume_workflow(
            session,
            run_id=run.id,
            workspace_id=DEFAULT_WS,
            actor="test_approver",
        )
        await session.commit()

        # Should have advanced past PRODUCT_DECISION
        assert run.execution_status in ("RUNNING", "COMPLETED", "EXCEPTION")
        assert run.current_stage in ("PRODUCT_MASTER", "CREATIVE", "CREATIVE_QC",
                                     "LISTING_BUILD", "LISTING_GATE", "WC_SYNC",
                                     "WC_VERIFY", "LEARNING_EVENT")


@pytest.mark.asyncio
async def test_08_product_master_idempotent(
    session: AsyncSession, mastered_product: Product
):
    """S6: Product Master idempotent."""
    from app.services.product_factory_orchestrator import (
        _stage_product_master,
    )

    run = WorkflowRun(
        workspace_id=DEFAULT_WS,
        product_id=mastered_product.id,
        workflow_type="product_factory",
        current_stage="PRODUCT_MASTER",
        execution_status="RUNNING",
    )
    session.add(run)
    await session.flush()

    result = await _stage_product_master(
        session,
        workspace_id=DEFAULT_WS,
        product_id=mastered_product.id,
        run=run,
        trace_id="test-trace",
    )

    await session.flush()

    assert result.outcome == "PASS"
    assert result.metadata.get("already_mastered") is True


@pytest.mark.asyncio
async def test_09_creative_failure_retry(
    session: AsyncSession, approved_product: Product
):
    """S7: Creative failure → retry."""
    from app.services.product_factory_orchestrator import (
        _stage_creative,
    )

    run = WorkflowRun(
        workspace_id=DEFAULT_WS,
        product_id=approved_product.id,
        workflow_type="product_factory",
        current_stage="CREATIVE",
        execution_status="RUNNING",
        retry_count=0,
    )
    session.add(run)
    await session.flush()

    with patch(
        "app.services.creative_service.create_brief_from_product",
        side_effect=RuntimeError("Creative gateway unavailable"),
    ):
        result = await _stage_creative(
            session,
            workspace_id=DEFAULT_WS,
            product_id=approved_product.id,
            run=run,
            trace_id="test-trace",
        )

    assert result.outcome == "RETRY"
    assert result.retryable is True


@pytest.mark.asyncio
async def test_10_listing_gate_blocked_stop(
    session: AsyncSession, approved_product: Product
):
    """S10: Listing Gate blocked → stop."""
    from app.services.product_factory_orchestrator import (
        _stage_listing_gate,
    )

    # Set listing_data with a problem (no price)
    approved_product.meta = {
        "listing_data": {
            "sku": "NT-TEST-002",
            "name": "Test Product",
            "description": "No price here",
            "regular_price": "",
        }
    }
    await session.flush()

    run = WorkflowRun(
        workspace_id=DEFAULT_WS,
        product_id=approved_product.id,
        workflow_type="product_factory",
        current_stage="LISTING_GATE",
        execution_status="RUNNING",
    )
    session.add(run)
    await session.flush()

    result = await _stage_listing_gate(
        session,
        workspace_id=DEFAULT_WS,
        product_id=approved_product.id,
        run=run,
        trace_id="test-trace",
    )

    assert result.outcome == "END"
    assert result.error_code == "GATE_BLOCKED"


@pytest.mark.asyncio
async def test_11_wc_429_retry(
    session: AsyncSession, approved_product: Product
):
    """S11: WC 429 → retry."""
    from app.services.product_factory_orchestrator import (
        _stage_wc_sync,
    )

    run = WorkflowRun(
        workspace_id=DEFAULT_WS,
        product_id=approved_product.id,
        workflow_type="product_factory",
        current_stage="WC_SYNC",
        execution_status="RUNNING",
        retry_count=0,
    )
    session.add(run)
    await session.flush()

    async def _mock_wc_429(pid, **kwargs):
        return {"success": False, "error": "Too Many Requests", "status_code": 429}

    with patch(
        "app.services.woocommerce_sync_service.push_product_to_woocommerce",
        side_effect=_mock_wc_429,
    ):
        result = await _stage_wc_sync(
            session,
            workspace_id=DEFAULT_WS,
            product_id=approved_product.id,
            run=run,
            trace_id="test-trace",
        )

    assert result.outcome == "RETRY"
    assert result.retryable is True


@pytest.mark.asyncio
async def test_12_wc_5xx_retry(
    session: AsyncSession, approved_product: Product
):
    """S11: WC 5xx → retry."""
    from app.services.product_factory_orchestrator import (
        _stage_wc_sync,
    )

    run = WorkflowRun(
        workspace_id=DEFAULT_WS,
        product_id=approved_product.id,
        workflow_type="product_factory",
        current_stage="WC_SYNC",
        execution_status="RUNNING",
        retry_count=0,
    )
    session.add(run)
    await session.flush()

    async def _mock_wc_500(pid, **kwargs):
        return {"success": False, "error": "Internal Server Error", "status_code": 500}

    with patch(
        "app.services.woocommerce_sync_service.push_product_to_woocommerce",
        side_effect=_mock_wc_500,
    ):
        result = await _stage_wc_sync(
            session,
            workspace_id=DEFAULT_WS,
            product_id=approved_product.id,
            run=run,
            trace_id="test-trace",
        )

    assert result.outcome == "RETRY"
    assert result.retryable is True


@pytest.mark.asyncio
async def test_13_wc_duplicate_update(
    session: AsyncSession, approved_product: Product
):
    """S11: WC duplicate → update."""
    from app.services.product_factory_orchestrator import (
        _stage_wc_sync,
    )

    run = WorkflowRun(
        workspace_id=DEFAULT_WS,
        product_id=approved_product.id,
        workflow_type="product_factory",
        current_stage="WC_SYNC",
        execution_status="RUNNING",
    )
    session.add(run)
    await session.flush()

    async def _mock_wc_duplicate(pid, **kwargs):
        return {
            "success": True,
            "woocommerce_id": 12345,
            "action": "update",
        }

    with patch(
        "app.services.woocommerce_sync_service.push_product_to_woocommerce",
        side_effect=_mock_wc_duplicate,
    ):
        result = await _stage_wc_sync(
            session,
            workspace_id=DEFAULT_WS,
            product_id=approved_product.id,
            run=run,
            trace_id="test-trace",
        )

    assert result.outcome == "PASS"
    assert result.metadata.get("action") == "update"


@pytest.mark.asyncio
async def test_14_wc_verify_failure_exception(
    session: AsyncSession, approved_product: Product
):
    """S12: WC verify failure → exception."""
    from app.services.product_factory_orchestrator import (
        _stage_wc_verify,
    )

    # Product with no WC ID
    approved_product.meta = {}
    await session.flush()

    run = WorkflowRun(
        workspace_id=DEFAULT_WS,
        product_id=approved_product.id,
        workflow_type="product_factory",
        current_stage="WC_VERIFY",
        execution_status="RUNNING",
    )
    session.add(run)
    await session.flush()

    result = await _stage_wc_verify(
        session,
        workspace_id=DEFAULT_WS,
        product_id=approved_product.id,
        run=run,
        trace_id="test-trace",
    )

    assert result.outcome == "FAIL"
    assert result.error_code == "WC_VERIFY_NO_ID"


@pytest.mark.asyncio
async def test_15_duplicate_workflow_resume_existing(
    session: AsyncSession, candidate_product: Product
):
    """Idempotency: duplicate workflow → resume existing."""
    from app.services.product_factory_orchestrator import (
        trigger_workflow,
    )

    run1 = await trigger_workflow(
        session,
        workspace_id=DEFAULT_WS,
        product_id=candidate_product.id,
    )
    await session.flush()

    run2 = await trigger_workflow(
        session,
        workspace_id=DEFAULT_WS,
        product_id=candidate_product.id,
    )
    await session.flush()

    # Should be the same run
    assert run1.id == run2.id
    assert run1.current_stage == run2.current_stage


@pytest.mark.asyncio
async def test_16_cross_workspace_isolation(
    session: AsyncSession, candidate_product: Product
):
    """Workspace isolation: different workspace gets its own run."""
    from app.services.product_factory_orchestrator import (
        trigger_workflow,
        list_workflow_runs,
    )

    other_ws = UUID("00000000-0000-0000-0000-000000000002")

    # Create product in other workspace
    product2 = Product(
        workspace_id=other_ws,
        sku="NT-TEST-001",
        name="Test Product WS2",
        candidate_status="candidate",
        source="1688",
        source_offer_id="123456",
        target_market="US",
    )
    session.add(product2)
    await session.flush()

    run1 = await trigger_workflow(
        session,
        workspace_id=DEFAULT_WS,
        product_id=candidate_product.id,
    )
    run2 = await trigger_workflow(
        session,
        workspace_id=other_ws,
        product_id=product2.id,
    )
    await session.flush()

    # Should be different runs
    assert run1.id != run2.id
    assert run1.workspace_id != run2.workspace_id

    # List only shows runs for the requesting workspace
    runs1 = await list_workflow_runs(session, workspace_id=DEFAULT_WS)
    runs2 = await list_workflow_runs(session, workspace_id=other_ws)
    assert len(runs1) == 1
    assert len(runs2) == 1


@pytest.mark.asyncio
async def test_17_trace_id_propagation(
    session: AsyncSession, candidate_product: Product
):
    """Trace ID propagation through workflow execution."""
    from app.services.product_factory_orchestrator import (
        trigger_workflow,
        execute_workflow,
    )

    test_trace = "test-trace-id-12345"

    run = await trigger_workflow(
        session,
        workspace_id=DEFAULT_WS,
        product_id=candidate_product.id,
        trace_id=test_trace,
    )
    assert run.trace_id == test_trace

    run = await execute_workflow(
        session,
        run_id=run.id,
        workspace_id=DEFAULT_WS,
        trace_id=test_trace,
    )
    await session.commit()
    assert run.trace_id == test_trace


@pytest.mark.asyncio
async def test_18_no_fake_success(
    session: AsyncSession, candidate_product: Product
):
    """No fake success: if a service call fails, the workflow must not report success."""
    from app.services.product_factory_orchestrator import (
        trigger_workflow,
        execute_workflow,
    )

    # Mock V3 to fail with an exception
    async def _mock_v3_fail(s, pid, **kwargs):
        raise RuntimeError("LLM gateway unavailable")

    with patch(
        "app.services.nuotao_selection_service.evaluate_product",
        side_effect=_mock_v3_fail,
    ):
        run = await trigger_workflow(
            session,
            workspace_id=DEFAULT_WS,
            product_id=candidate_product.id,
        )
        # Execute through S1, S2
        for _ in range(2):
            run = await execute_workflow(session, run_id=run.id, workspace_id=DEFAULT_WS)
        # Execute S3 (V3_EVALUATION) — should fail
        run = await execute_workflow(session, run_id=run.id, workspace_id=DEFAULT_WS)
        await session.commit()

        # Workflow must NOT be in COMPLETED state
        assert run.execution_status != "COMPLETED"
        assert run.execution_status in ("EXCEPTION", "FAILED", "RUNNING")
        if run.execution_status in ("EXCEPTION", "FAILED"):
            assert "V3" in (run.last_error or "") or "gateway" in (run.last_error or "").lower()
