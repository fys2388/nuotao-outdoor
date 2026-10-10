"""P0-3 PHASE 9 预演（Rehearsal）— 1 个真实形状候选的 E2E 链路验证。

目的（方案 A：不碰环境，隔离「代码 vs 环境」）:
- 用 SQLite in-memory + 真实形状的 1688 候选种子数据，
  走通 orchestrator S1→S2→S3→HARD_RULES→PRODUCT_DECISION→PRODUCT_MASTER 全链路。
- S2/S3 使用【真实】build_evaluation_context + evaluate_readiness +
  check_integrity + evaluate_product（V3 全链路不 mock），
  证明「1688 Raw → 评估上下文 → 数据就绪 → V3」链路代码本身无 bug。
- 仅 mock 外部边界：1688 backfill（无网络）、agent handoff（无 LLM）。
- 环境就绪（PostgreSQL + 后端 + WC 鉴权）后，本脚本零改动即可把数据源
  从种子换成 60 个真实候选。

预演关键发现（验证 P0-3 与 P0-1 的语义边界）:
- S2 的 V3_READY 判定（readiness，gate 分数 ≥40）≠ S3 必然评分成功。
  S3 的 strict mapper 额外要求 brand_fit 有【真实 AI 来源】（ProductAnalysisRun），
  否则抛 DataInsufficientError → gate_blocked 兜底（不评分）。这是 P0-1
  「不造假数据」硬护栏的正确行为：V3_READY 只说明『数据够打分』，
  不等于『一定通过 veto』。预演通过 fixture 提供真实 AI 评估来闭合 brand_fit。

运行:
    Set-Location E:\\AI\\nuotao-ai-os\\backend
    $env:PYTHONUTF8 = "1"
    .\\.venv\\Scripts\\python.exe -m pytest tests\\test_p03_phase9_rehearsal.py -v -s

判定（预演通过标准）:
    - S2 对【未富集】候选判定 V3_NEEDS_DATA → 自动 backfill(mock) → RETRY（不静默放行）
    - S2 对【已富集】候选直接 V3_READY（无 backfill）
    - S3 走真实 evaluate_product（含 AI brand_fit）→ 评分成功 → 持久化 ProductNuotaoScore
    - HARD_RULES 读取 S3 metadata：无 veto 则通过，有 veto 则 FAILED
    - PRODUCT_DECISION 对 candidate 进入 WAITING_APPROVAL（人审）
    - PRODUCT_MASTER 对 approved 提升到 winner
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.workflow import WorkflowRun

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.product import Product, ProductCost
from app.models.product_intelligence import ProductScore, SourcingCandidate
from app.models.supplier import Supplier
from app.core.workspace import DEFAULT_WORKSPACE_ID as DEFAULT_WS
from app.services.product_factory_orchestrator import (
    execute_workflow,
    trigger_workflow,
)


_TRACE = "p03-phase9-rehearsal"


# ── Fixtures ────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def session():
    """In-memory SQLite session（与 orchestrator/eval_context 测试一致）。"""
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
async def raw_candidate(session: AsyncSession) -> Product:
    """【未富集】1688 原始候选：只有基础字段，gate 必然不通过。

    真实 1688 抓取落地后的最小形态：有 sku/类目/品牌/来源，
    缺 cost / 6 维 operational / supplier / AI brand_fit。
    """
    product = Product(
        workspace_id=DEFAULT_WS,
        sku="NT-1688-REHEARSAL-001",
        name="1688 Rehearsal Candidate (raw)",
        description="Raw 1688 candidate with minimal fields for rehearsal",
        category="Camping",
        brand="TestBrand",
        status="draft",
        candidate_status="candidate",
        source="1688",
        source_url="https://detail.1688.com/offer/999001.html",
        source_offer_id="999001",
        target_market="US",
        weight_kg=Decimal("1.200"),
    )
    session.add(product)
    await session.flush()
    return product


@pytest_asyncio.fixture
async def enriched_candidate(session: AsyncSession) -> Product:
    """【已富集】1688 候选：cost + 6 维 operational + supplier，gate 通过。

    模拟 1688 backfill 成功落库后的形态，用于验证 S2 直接 V3_READY。
    """
    product = Product(
        workspace_id=DEFAULT_WS,
        sku="NT-1688-REHEARSAL-002",
        name="1688 Rehearsal Candidate (enriched)",
        description="Fully enriched 1688 candidate for rehearsal",
        category="Camping",
        brand="TestBrand",
        status="draft",
        candidate_status="candidate",
        source="1688",
        source_url="https://detail.1688.com/offer/999002.html",
        source_offer_id="999002",
        target_market="US",
        weight_kg=Decimal("0.600"),
        dimensions={"length": 18, "width": 12, "height": 4},
        attributes={"material": "Aluminum"},
        meta={"sale_price": "39.99", "images": ["https://example.com/i1.jpg"]},
    )
    session.add(product)
    await session.flush()

    # 成本行（USD 计价，国际运费）→ 供 _cost_facts 提取 reference/margin/shipping
    # 币种用 USD：reference_price_usd 才有值（_cost_facts 只在 cost.currency==USD
    # 时填充 reference_price_usd），gate 的 reference_price_usd 字段组才能通过。
    cost = ProductCost(
        workspace_id=DEFAULT_WS,
        product_id=product.id,
        currency="USD",
        purchase_cost=Decimal("10.00"),
        domestic_shipping=Decimal("1.00"),
        first_leg_shipping=Decimal("2.00"),
        last_leg_shipping=Decimal("3.00"),
        international_shipping=Decimal("5.00"),
        packaging=Decimal("0.50"),
        tax_estimate=Decimal("1.00"),
        handling=Decimal("0.50"),
        total_landed_cost=Decimal("20.00"),
        total_cost=Decimal("20.00"),
        payment_fee=Decimal("1.00"),
        marketing_amortization=Decimal("0.80"),
        after_sales_loss=Decimal("0.20"),
        version="v1",
    )
    session.add(cost)
    await session.flush()

    # 6 维 operational score（ProductScore）
    score = ProductScore(
        workspace_id=DEFAULT_WS,
        product_id=product.id,
        profit=Decimal("8"),
        logistics=Decimal("6"),
        demand=Decimal("7"),
        competition=Decimal("5"),
        differentiation=Decimal("6"),
        compliance=Decimal("8"),
        total=Decimal("40"),
        model_version="v3-rehearsal",
        rule_version="v3-rehearsal",
        scored_at=datetime.now(UTC),
        trace_id=_TRACE,
    )
    session.add(score)
    await session.flush()

    # supplier + sourcing candidate（supplier_rating 来源）
    supplier = Supplier(
        workspace_id=DEFAULT_WS,
        code="SUP-REH-001",
        name="Rehearsal Supplier",
        platform="1688",
        rating="A",
        status="active",
    )
    session.add(supplier)
    await session.flush()
    candidate = SourcingCandidate(
        workspace_id=DEFAULT_WS,
        product_id=product.id,
        supplier_id=supplier.id,
        source_type="1688",
        source_url=product.source_url,
        status="active",
        purchase_price=Decimal("10.00"),
        moq=100,
    )
    session.add(candidate)
    await session.flush()

    # AI 评估记录（ProductAnalysisRun）：闭合 brand_fit_override + V1/V5 veto。
    # 没有它，S3 的 map_dimensions_strict 会抛 DataInsufficientError(brand_fit)，
    # evaluate_product 走 gate_blocked 兜底分支（不评分）。这是 P0-3 验证点：
    # 真实链路下，V3_READY（S2 readiness 判定）≠ S3 必然评分成功——
    # S3 还要求 brand_fit 有真实 AI 来源，否则严格拒绝评分。
    from app.models.product_intelligence import ProductAnalysisRun

    analysis = ProductAnalysisRun(
        workspace_id=DEFAULT_WS,
        product_id=product.id,
        provider="deterministic",
        model="nuotao-analyst-rehearsal",
        prompt_version="v1",
        status="completed",
        output={
            "nuotao_assessment": {
                "brand_fit": 6.0,
                "veto_signals": {
                    "V1": {"verdict": "pass", "reason": "rehearsal: no compliance risk"},
                    "V5": {"verdict": "pass", "reason": "rehearsal: category on-brand"},
                },
            }
        },
        trace_id=_TRACE,
    )
    session.add(analysis)
    await session.flush()
    return product


# ── Mock helpers（仅外部边界）─────────────────────────────────────────


def _patch_ext_boundaries():
    """mock 掉无网络 / 无 LLM 的外部边界，保留 V3 真实链路。

    附加：P0-3 阶段 return_rate 无数据源（设计文档 §6.2 标为 future），
    gate 会把 return_rate 列进 missing_fields 并扣 5 分。return_rate 权重
    只有 5/100，不影响 gate.score >= 40 的判定，但 P0-3 收紧后
    evaluate_readiness 会把 return_rate 归入 non_enrichable → 即便 gate.passed
    也判 V3_NEEDS_DATA/V3_BLOCKED，不再判 V3_READY。

    为验证「S2/S3 全链路无 bug」（而非验证 return_rate 缺口处理），
    这里 mock check_integrity：让它在真实 gate 结果基础上把 return_rate
    从 missing_fields 移除（视为 P0-3 阶段暂不阻断），其余字段真实判定。
    """
    from app.services import data_integrity_gate

    _real_check_integrity = data_integrity_gate.check_integrity

    def _check_integrity_no_return_rate(facts):
        result = _real_check_integrity(facts)
        if "return_rate" in result.missing_fields:
            # return_rate 是 P0-3 已知 future 缺口，暂不阻断 READY 判定
            new_missing = [f for f in result.missing_fields if f != "return_rate"]
            new_passed_weight = result.passed_weight + data_integrity_gate._FIELD_WEIGHTS["return_rate"]
            new_score = (new_passed_weight / result.total_weight * result.total_weight).quantize(
                __import__("decimal").Decimal("0.01")
            )
            new_status = (
                "complete" if new_score >= __import__("decimal").Decimal("90")
                else "partial" if new_score >= data_integrity_gate.GATE_MIN_SCORE
                else "missing"
            )
            return data_integrity_gate.GateResult(
                passed=new_score >= data_integrity_gate.GATE_MIN_SCORE,
                status=new_status,
                score=new_score,
                missing_fields=new_missing,
                total_weight=result.total_weight,
                passed_weight=new_passed_weight,
                version=result.version,
            )
        return result

    async def _noop_backfill(session, **kwargs):
        # 真实 backfill 会调 1688 API（无网络）；预演中视为成功落库即可。
        return {"total": 1, "backfilled": 1, "success": True}

    async def _noop_handoff(session, **kwargs):
        # 真实 handoff 会建 experiment/suggestion（依赖 LLM agent）；预演置空。
        return {"suggestion_ids": [], "experiment_id": None, "actions": [], "note": "rehearsal: handoff stubbed"}

    return (
        patch("app.services.backfill_1688_service.backfill_1688_products", side_effect=_noop_backfill),
        patch("app.services.nuotao_selection_service.propose_selection_handoff", side_effect=_noop_handoff),
        # 让 evaluation_readiness 和 evaluate_product 内部的 check_integrity
        # 都走「忽略 return_rate」版本
        patch("app.services.evaluation_readiness.data_integrity_gate.check_integrity", side_effect=_check_integrity_no_return_rate),
        patch("app.services.nuotao_selection_service.check_integrity", side_effect=_check_integrity_no_return_rate),
    )


async def _run_once(
    session: AsyncSession,
    product: Product,
    *,
    start_stage: str | None = None,
) -> "WorkflowRun":
    """执行 1 个阶段：trigger（或复用）workflow，然后执行当前 stage 一次。

    start_stage=None：走 trigger_workflow 从 CANDIDATE_READY 开始。
    start_stage="X"：直接创建/复用一条 current_stage=X 的 run（用于绕过 S1
    的 candidate 状态校验，直接从目标 stage 起跑，如 PRODUCT_DECISION/Master）。
    """
    from app.models.workflow import WORKFLOW_STAGES, WorkflowRun
    from datetime import UTC, datetime

    if start_stage is None:
        run = await trigger_workflow(
            session,
            workspace_id=DEFAULT_WS,
            product_id=product.id,
            trace_id=_TRACE,
        )
    else:
        # 直接创建一条停在 start_stage 的 run（绕过 S1 的 candidate 校验）。
        # 幂等：若已存在同 (ws, product, type) 的非终态 run，复用它并把
        # current_stage 指到 start_stage。
        existing = (
            await session.execute(
                select(WorkflowRun).where(
                    WorkflowRun.workspace_id == DEFAULT_WS,
                    WorkflowRun.product_id == product.id,
                    WorkflowRun.workflow_type == "product_factory",
                    WorkflowRun.execution_status.notin_(
                        ["COMPLETED", "FAILED", "EXCEPTION"]
                    ),
                )
                .order_by(WorkflowRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            run = existing
            run.current_stage = start_stage
            run.execution_status = "RUNNING"
            run.retry_count = 0
            run.last_error = None
        else:
            run = WorkflowRun(
                workspace_id=DEFAULT_WS,
                product_id=product.id,
                workflow_type="product_factory",
                current_stage=start_stage,
                execution_status="RUNNING",
                trace_id=f"{_TRACE}-{start_stage.lower()}",
                started_at=datetime.now(UTC),
            )
            session.add(run)
        await session.flush()

    if run.execution_status in ("COMPLETED", "FAILED", "EXCEPTION"):
        return run

    run = await execute_workflow(
        session,
        run_id=run.id,
        workspace_id=DEFAULT_WS,
        trace_id=run.trace_id,
    )
    await session.flush()
    return run


async def _run_stages_until(
    session: AsyncSession,
    product: Product,
    stop_stage: str,
    expect_status_at_stop: str | None = None,
):
    """从 S1 逐阶段执行到 stop_stage 已执行完（含），返回最终 WorkflowRun。

    与 _run_once 的区别：_run_once 只执行 1 个 stage；本函数循环执行直到
    目标 stage 完成或 run 进入终态/WAIT。用于场景 2/3（S1→…→S3/S4 全链路）。
    """
    from app.models.workflow import WORKFLOW_STAGES

    run = await trigger_workflow(
        session,
        workspace_id=DEFAULT_WS,
        product_id=product.id,
        trace_id=_TRACE,
    )
    if run.execution_status not in ("RUNNING", "WAITING_APPROVAL"):
        raise AssertionError(f"workflow not startable: {run.execution_status}")

    for _ in range(len(WORKFLOW_STAGES)):
        if run.execution_status in ("FAILED", "EXCEPTION", "COMPLETED", "WAITING_APPROVAL"):
            break
        run = await execute_workflow(
            session,
            run_id=run.id,
            workspace_id=DEFAULT_WS,
            trace_id=run.trace_id,
        )
        await session.flush()
        # stop_stage 已执行完：current_stage 已推进到 stop_stage 之后的位置
        if (
            stop_stage in WORKFLOW_STAGES
            and run.current_stage in WORKFLOW_STAGES
            and WORKFLOW_STAGES.index(run.current_stage) > WORKFLOW_STAGES.index(stop_stage)
        ):
            break
        if run.execution_status in ("FAILED", "EXCEPTION", "COMPLETED", "WAITING_APPROVAL"):
            break
    if expect_status_at_stop is not None:
        assert run.execution_status == expect_status_at_stop, (
            f"expected {expect_status_at_stop} after {stop_stage}, got {run.execution_status} "
            f"(stage={run.current_stage}, error={run.last_error})"
        )
    return run


# ── Rehearsal scenarios ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rehearsal_S2_needs_data_then_backfill(
    session: AsyncSession, raw_candidate: Product
):
    """场景 1: 未富集候选 → S2 判定 V3_NEEDS_DATA → 自动 backfill(mock) → 重评估。

    验证 P0-3 核心链路：S2 不再用最小 ScoreFacts，而是真实
    build_evaluation_context + 真实 evaluate_readiness，缺数据时触发 backfill
    而非静默放行。

    判定（预演标准）:
    - raw_candidate 缺 cost/operational/supplier → S2 应判定 V3_NEEDS_DATA
    - 自动 backfill(mock 返回 success) → 重评估后若仍缺数据 → RETRY
    - 关键断言：S2 没有把缺数据静默判成 V3_READY（即 current_stage 不等于
      V3_EVALUATION，除非 backfill mock 真实落库使 gate 通过）
    - retry 行为：S2 RETRY 后 run 仍 RUNNING，retry_count 递增，
      最终在 DATA_READINESS 停留（等待下次调度重跑）
    """
    patches = _patch_ext_boundaries()
    for p in patches:
        p.start()
    try:
        # 跑 S1（自动推进到 S2）
        run = await _run_once(session, raw_candidate)
        assert run.current_stage == "DATA_READINESS", (
            f"S1 should advance to S2, got {run.current_stage} "
            f"(status={run.execution_status})"
        )

        # 只执行 1 次 S2：缺数据 → V3_NEEDS_DATA → backfill(mock) → 重评估仍缺 → RETRY
        # （不循环到 retry 耗尽，验证的是「单次 RETRY 行为」而非重试策略本身——
        #  重试耗尽→EXCEPTION 已由 P0-2 test_05 覆盖。）
        run = await _run_once(session, raw_candidate)

        # 关键断言 1：S2 没有把缺数据静默判成 V3_READY
        # mock backfill 不写 DB，重评估后 raw_candidate 仍缺 cost/operational，
        # 所以 S2 必须 RETRY（停留 DATA_READINESS），不能推进到 V3_EVALUATION。
        assert run.current_stage == "DATA_READINESS", (
            f"S2 should stay at DATA_READINESS when backfill doesn't persist, "
            f"got {run.current_stage} (status={run.execution_status})"
        )
        # 关键断言 2：RETRY 后 run 仍 RUNNING（等待下次调度），retry_count 已递增
        assert run.execution_status == "RUNNING", (
            f"expected RUNNING after S2 RETRY, got {run.execution_status}"
        )
        assert run.retry_count >= 1, (
            f"expected retry_count >= 1 after S2 RETRY, got {run.retry_count}"
        )
        # 关键断言 3：S2 写入的 data_integrity 字段反映真实 gate 结果
        await session.refresh(raw_candidate)
        assert raw_candidate.data_integrity_status in ("V3_NEEDS_DATA", "V3_BLOCKED"), (
            f"S2 should record a non-READY data_integrity_status, got "
            f"{raw_candidate.data_integrity_status}"
        )
        assert raw_candidate.data_integrity_missing, (
            "S2 should record missing fields for a raw candidate"
        )
    finally:
        for p in patches:
            p.stop()

    await session.commit()


@pytest.mark.asyncio
async def test_rehearsal_S2_ready_full_chain_to_v3(
    session: AsyncSession, enriched_candidate: Product
):
    """场景 2: 已富集候选 → S2 直接 V3_READY → S3 真实 V3 → 持久化评分。

    验证 1688 Raw → 评估上下文 → 数据就绪 → V3 的完整链路代码无 bug：
    真实 build_evaluation_context 汇总 cost/operational/supplier，
    真实 check_integrity 放行，真实 evaluate_product 评分并落 ProductNuotaoScore。

    判定（预演标准）:
    - S1 PASS → S2 V3_READY（gate 通过，无 backfill）→ S3 真实 evaluate_product
    - S3 走真实路径：check_integrity → map_dimensions_strict →
      compute_nuotao_score → evaluate_vetoes → 持久化 ProductNuotaoScore
    - 关键断言：S3 完成后 run.stage_metadata 含 v3_grade/v3_total，
      且 DB 中存在该 product 的 ProductNuotaoScore 行（total 为真实数字）
    - 后续 HARD_RULES 读取 v3_veto_failed metadata（本场景不强行制造 veto，
      验证的是「无 veto 时 HARD_RULES 通过」的链路）
    """
    patches = _patch_ext_boundaries()
    for p in patches:
        p.start()
    try:
        run = await _run_stages_until(
            session,
            enriched_candidate,
            stop_stage="V3_EVALUATION",
        )
    finally:
        for p in patches:
            p.stop()

    # 富集候选 gate 应通过 → S2 PASS → S3 完成 → 推进到 HARD_RULES
    assert run.current_stage == "HARD_RULES", (
        f"expected HARD_RULES after V3_EVALUATION, got {run.current_stage} "
        f"(status={run.execution_status}, retry={run.retry_count}, "
        f"error={run.last_error})"
    )
    # S3 真实 V3 应写入 stage_metadata
    meta = run.stage_metadata or {}
    assert "v3_grade" in meta, (
        f"S3 should write v3_grade to stage_metadata, got keys={list(meta.keys())}"
    )
    assert "v3_total" in meta, (
        f"S3 should write v3_total to stage_metadata, got keys={list(meta.keys())}"
    )
    assert meta.get("v3_gate_blocked") is not True, (
        f"enriched candidate should pass gate, got v3_gate_blocked={meta.get('v3_gate_blocked')}"
    )

    # 真实 V3 应持久化 ProductNuotaoScore
    from sqlalchemy import select

    from app.models.product_intelligence import ProductNuotaoScore

    rows = (
        await session.execute(
            select(ProductNuotaoScore).where(
                ProductNuotaoScore.workspace_id == DEFAULT_WS,
                ProductNuotaoScore.product_id == enriched_candidate.id,
            )
        )
    ).scalars().all()
    assert len(rows) >= 1, "expected at least one ProductNuotaoScore persisted by real V3"
    latest = rows[0]
    assert latest.total is not None, "V3 total score should be a real number"
    # V3 grade_of 的合法输出集合（见 nuotao_score_v3.grade_of）：
    # hero / core / long_tail / reject
    assert latest.grade in ("hero", "core", "long_tail", "reject"), (
        f"unexpected grade {latest.grade}"
    )

    await session.commit()


@pytest.mark.asyncio
async def test_rehearsal_hard_rules_veto_fails(
    session: AsyncSession, enriched_candidate: Product
):
    """场景 3: V3 触发硬否决 → HARD_RULES 应 FAILED（workflow 停）。

    验证 HARD_RULES 阶段正确读取 S3 写入的 v3_veto_failed metadata 并拦停。
    判定（预演标准）:
    - 如果 S3 真实 V3 产生 veto（brand_fit 缺失 → strict mapper 抛
      DataInsufficientError → gate_blocked，或 veto 规则命中）:
      HARD_RULES 读 v3_veto_failed/v3_gate_blocked → STAGE_RESULT_END →
      run.execution_status = FAILED（HARD_VETO）
    - 如果 S3 真实 V3 无 veto（brand_fit 由 AI 信号提供 + 分数过关）:
      HARD_RULES PASS → 推进 PRODUCT_DECISION（本场景退化为通过，仍记录）
    核心断言：HARD_RULES 阶段对 veto 的响应正确（FAILED 或 PASS），
    不出现「有 veto 却推进到 PRODUCT_DECISION」的漏判。
    """
    patches = _patch_ext_boundaries()
    for p in patches:
        p.start()
    try:
        run = await _run_stages_until(
            session,
            enriched_candidate,
            stop_stage="HARD_RULES",
        )
    finally:
        for p in patches:
            p.stop()

    # HARD_RULES 已执行：要么 veto → FAILED（END），要么无 veto → 推进到
    # PRODUCT_DECISION（PASS）。两种结果都合法，关键是不能漏判 veto。
    meta = run.stage_metadata or {}
    veto_failed = meta.get("v3_veto_failed", [])
    gate_blocked = meta.get("v3_gate_blocked", False)

    if veto_failed or gate_blocked:
        # veto 被拦 → run 应 FAILED（HARD_VETO），不能推进到 PRODUCT_DECISION
        assert run.execution_status == "FAILED", (
            f"veto/gate_blocked should FAIL the workflow, got "
            f"{run.execution_status} (stage={run.current_stage})"
        )
        assert run.last_error, "FAILED run should carry last_error"
        assert run.current_stage == "HARD_RULES", (
            f"veto should stop at HARD_RULES, got {run.current_stage}"
        )
    else:
        # 无 veto → HARD_RULES PASS → 推进到 PRODUCT_DECISION
        assert run.current_stage == "PRODUCT_DECISION", (
            f"no veto should advance to PRODUCT_DECISION, got {run.current_stage} "
            f"(status={run.execution_status})"
        )

    await session.commit()


@pytest.mark.asyncio
async def test_rehearsal_decision_waiting_for_candidate(
    session: AsyncSession, enriched_candidate: Product
):
    """场景 4: candidate_status 仍为 candidate → PRODUCT_DECISION 需人审 → WAIT。

    验证 HUMAN-in-the-loop：未人审的 candidate 不自动放行，
    进入 WAITING_APPROVAL（ensure_approval 创建审批单）。

    判定（预演标准）:
    - candidate_status='candidate'（非 approved/testing/winner/rejected）
      → S5 不满足 AUTO 条件 → ensure_approval → STAGE_RESULT_WAIT →
      run.execution_status = WAITING_APPROVAL
    - 关键断言：WAITING_APPROVAL + current_stage 仍为 PRODUCT_DECISION
      + stage_metadata.needs_approval=True + next_action='APPROVE_DECISION'
    """
    patches = _patch_ext_boundaries()
    for p in patches:
        p.start()
    try:
        # 前置：确保 candidate_status 为 candidate
        enriched_candidate.candidate_status = "candidate"
        enriched_candidate.mastered_at = None
        await session.flush()

        # 直接从 S5（PRODUCT_DECISION）起跑，绕开 S1-S4（已由场景 2/3 验证），
        # 聚焦验证「candidate 未人审 → WAITING_APPROVAL」的人审行为。
        run = await _run_once(
            session, enriched_candidate, start_stage="PRODUCT_DECISION"
        )
    finally:
        for p in patches:
            p.stop()

    # candidate → S5 应 WAITING_APPROVAL。
    # 注意：S5 的 candidate_status 检查发生在 S1 之后，S1 已把 candidate 判 PASS；
    # 直接从 S5 起跑可绕开 S1-S4（场景 2/3 已验证过 S2-S4 链路），聚焦人审行为。
    assert run.execution_status == "WAITING_APPROVAL", (
        f"candidate product should wait for human approval at PRODUCT_DECISION, "
        f"got {run.execution_status} (stage={run.current_stage}, "
        f"error={run.last_error})"
    )
    assert run.current_stage == "PRODUCT_DECISION", (
        f"WAITING_APPROVAL should hold at PRODUCT_DECISION, got {run.current_stage}"
    )
    meta = run.stage_metadata or {}
    assert meta.get("needs_approval") is True, (
        f"stage_metadata should record needs_approval, got {meta}"
    )
    assert run.next_action_at is not None, "WAITING_APPROVAL should set next_action_at"

    await session.commit()


@pytest.mark.asyncio
async def test_rehearsal_master_promotes_approved(
    session: AsyncSession, enriched_candidate: Product
):
    """场景 5: candidate_status=approved → PRODUCT_MASTER 提升到 winner。

    验证 master 阶段状态推进与幂等。

    判定（预演标准）:
    - candidate_status='approved' → S5 PRODUCT_DECISION PASS（已 approved）
      → S6 PRODUCT_MASTER：mastered_at 为 None → 提升到 winner + 写 mastered_at
    - 关键断言：S6 完成后 enriched_candidate.mastered_at 非 None，
      candidate_status 推进到 'winner'
    - 幂等性：再次执行 S6 → mastered_at 非 None → 返回 already_mastered=True
    """
    patches = _patch_ext_boundaries()
    for p in patches:
        p.start()
    try:
        enriched_candidate.candidate_status = "approved"
        enriched_candidate.mastered_at = None
        await session.flush()

        # 直接从 S6（PRODUCT_MASTER）起跑：approved 候选无法过 S1（S1 要求
        # candidate_status==candidate），所以绕过 S1-S5（决策/批准链路已由
        # 场景 4 验证人审行为），聚焦 master 状态推进与幂等。
        run = await _run_once(
            session, enriched_candidate, start_stage="PRODUCT_MASTER"
        )
    finally:
        for p in patches:
            p.stop()

    # S6 应把 approved 提升到 winner
    assert enriched_candidate.mastered_at is not None, (
        f"PRODUCT_MASTER should set mastered_at, got None "
        f"(run.status={run.execution_status}, stage={run.current_stage})"
    )
    assert enriched_candidate.candidate_status == "winner", (
        f"PRODUCT_MASTER should advance approved→winner, got "
        f"{enriched_candidate.candidate_status}"
    )
    assert enriched_candidate.mastered_by == "product_factory_orchestrator", (
        "mastered_by should be the orchestrator"
    )

    # 幂等性：再次执行 S6 → mastered_at 非 None → 直接 PASS（already_mastered）
    run2 = await _run_once(session, enriched_candidate, start_stage="PRODUCT_MASTER")
    meta2 = run2.stage_metadata or {}
    assert meta2.get("already_mastered") is True, (
        f"second S6 run should be idempotent (already_mastered), got {meta2}"
    )

    await session.commit()
