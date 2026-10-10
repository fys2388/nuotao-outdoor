"""Selection workflow state schemas for the LangGraph DAG.

Defines the Pydantic models that carry state through the LangGraph StateGraph.
Each node reads from and writes to this state, making the workflow auditable
and testable.

Aligns with:
- docs/nuotao_product_score_v3.0.md (V3.0 Nuotao Score + V1-V12 veto)
- docs/product_selection_logic_v2.0.md (11-dimension operational score)
- AGENTS.md (data-driven, no hardcoded business logic)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ── V3.0 funnel stages ──────────────────────────────────────────────
FunnelStage = Literal[
    "recalled",  # 100: sourced candidates
    "screened",  # 60: passed compliance/commercial veto
    "deep_candidate",  # 20: operational score reached deep bar
    "test_candidate",  # 8: Nuotao Score + brand-fit veto passed
    "testing",  # 3: small-batch live test
    "hero",  # 1-2: Hero review approved
    "rejected",  # vetoed / failed at any stage
]

WorkflowStatus = Literal[
    "running",
    "completed",
    "failed",
    "waiting_approval",
]

DecisionType = Literal["test", "hold", "reject"]


# ── Market data snapshot ────────────────────────────────────────────
class MarketDataSnapshot(BaseModel):
    """Collected market intelligence for one candidate product."""

    google_trends_score: float = Field(
        ge=0, le=10, description="Google Trends search heat (0-10)"
    )
    google_trends_direction: Literal["rising", "stable", "declining"] = "stable"
    amazon_bsr_rank: int | None = Field(
        None, description="Amazon Best Sellers Rank (lower = better)"
    )
    amazon_review_count: int | None = Field(
        None, ge=0, description="Number of reviews for the product listing"
    )
    amazon_competition_level: Literal["low", "medium", "high"] | None = None
    tiktok_hashtag_views: int | None = Field(
        None, ge=0, description="TikTok hashtag views for related tags"
    )
    seasonality_score: float = Field(
        ge=0, le=10, description="Seasonality fitness (0-10)"
    )
    collected_at: str = Field(..., description="ISO 8601 timestamp")
    data_sources: list[str] = Field(
        default_factory=list, description="Data sources used"
    )


# ── Veto check result ───────────────────────────────────────────────
class VetoCheckResult(BaseModel):
    """Result of one veto rule check (V1-V12)."""

    rule_id: str = Field(..., description="V1-V12")
    rule_name: str
    category: Literal["compliance", "brand", "commercial"]
    check_type: Literal["deterministic", "ai", "hybrid"]
    verdict: Literal["pass", "fail", "uncertain"]
    reason: str = Field(..., description="One-line explanation grounded in data")
    evidence: dict[str, Any] = Field(default_factory=dict)


# ── Operational score (V2.0, 11 dimensions) ─────────────────────────
class OperationalScore(BaseModel):
    """11-dimension V2.0 operational scorecard."""

    supplier_quality: float = Field(ge=0, le=100, description="供应商资质")
    sales_validation: float = Field(ge=0, le=100, description="销量验证")
    margin_rate: float = Field(ge=0, le=100, description="全成本利润率")
    product_quality: float = Field(ge=0, le=100, description="产品质量")
    logistics_support: float = Field(ge=0, le=100, description="物流支持")
    differentiation: float = Field(ge=0, le=100, description="差异化空间")
    market_heat: float = Field(ge=0, le=100, description="市场热度")
    amazon_competition: float = Field(ge=0, le=100, description="亚马逊竞争度")
    seasonality: float = Field(ge=0, le=100, description="季节性适配")
    ai_image_difficulty: float = Field(ge=0, le=100, description="AI生图难度")
    compliance_risk: float = Field(ge=0, le=100, description="合规与侵权风险")
    total: float = Field(ge=0, le=100, description="加权总分")


# ── Nuotao Score dimensions (V3.0, 6 dimensions) ────────────────────
class NuotaoScoreDimensions(BaseModel):
    """6-dimension V3.0 Nuotao Score (0-10 each)."""

    value: float = Field(ge=0, le=10, description="性价比")
    utility: float = Field(ge=0, le=10, description="实用性")
    weight_packability: float = Field(ge=0, le=10, description="轻量便携")
    durability: float = Field(ge=0, le=10, description="耐用性")
    brand_fit: float = Field(ge=0, le=10, description="品牌契合")
    differentiation: float = Field(ge=0, le=10, description="差异化")


# ── Selection workflow state (LangGraph StateGraph) ─────────────────
class SelectionWorkflowState(BaseModel):
    """LangGraph state carrying data through the selection DAG.

    Nodes mutate this state in-place (LangGraph convention). The state
    is serialized to JSONB for persistence and audit.
    """

    # Input
    workspace_id: str
    product_id: str
    product_name: str | None = None
    category: str | None = None
    target_market: str = "US"

    # Stage tracking
    current_stage: FunnelStage = "recalled"

    # Market data (populated by market_data_collection node)
    market_data: MarketDataSnapshot | None = None

    # Category configuration (loaded from strategy_versions by pipeline)
    category_config: dict[str, Any] | None = None

    # Operational scorecard weights (loaded from strategy_versions by pipeline)
    operational_weights: dict[str, float] | None = None

    # Scoring
    operational_score: OperationalScore | None = None
    nuotao_score_total: float | None = Field(
        None, ge=0, le=100, description="V3.0 Nuotao Score total (0-100)"
    )
    nuotao_dimensions: NuotaoScoreDimensions | None = None
    nuotao_grade: str | None = Field(
        None, description="hero / core / long_tail / reject"
    )

    # Veto checks
    veto_results: list[VetoCheckResult] = Field(default_factory=list)
    veto_passed: bool | None = None

    # Decision
    recommended_decision: DecisionType | None = None
    recommended_price: Decimal | None = None
    confidence: Decimal | None = Field(None, ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    # Workflow metadata
    trace_id: str | None = None
    run_id: str | None = None
    error: str | None = None
    status: WorkflowStatus = "running"


# ── API request/response models ─────────────────────────────────────
class SelectionWorkflowTriggerRequest(BaseModel):
    """Request body for triggering a selection workflow run."""

    product_id: str = Field(..., description="Product UUID")
    workspace_id: str | None = Field(
        None, description="Workspace UUID (defaults to DEFAULT_WORKSPACE_ID)"
    )
    target_market: str = Field("US", description="Target market code")
    dry_run: bool = Field(
        False, description="If true, validate the chain without writing to DB"
    )
    include_market_data: bool = Field(
        True, description="If true, attempt to collect market data"
    )


class SelectionWorkflowRunOut(BaseModel):
    """Output model for a selection workflow run."""

    run_id: str
    product_id: str
    workspace_id: str
    status: WorkflowStatus
    current_stage: FunnelStage
    recommended_decision: DecisionType | None = None
    nuotao_score_total: float | None = None
    nuotao_grade: str | None = None
    veto_passed: bool | None = None
    confidence: Decimal | None = None
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    trace_id: str | None = None
    error: str | None = None
    created_at: str | None = None
    completed_at: str | None = None
