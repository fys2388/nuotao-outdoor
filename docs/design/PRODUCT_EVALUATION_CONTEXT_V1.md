# P0-3: PRODUCT EVALUATION CONTEXT + DATA ENRICHMENT

**Status:** DESIGN  
**Date:** 2026-10-04  
**Depends on:** P0-1 (Candidate Persistence), P0-2 (Product Factory Orchestrator)

---

## 1. ARCHITECTURE OVERVIEW

```
1688 Raw Product (ProductSource.raw_data)
    │
    ▼
ProductEvaluationContext (NEW: unified context builder)
    │
    ├──► Product Facts (Product.attributes, Product.meta)
    ├──► Cost & Landed Cost (ProductCost, cost_sync_service)
    ├──► Logistics Estimate (Product.dimensions, Product.weight_kg)
    ├──► Supplier Data (Supplier.rating, SourcingCandidate)
    ├──► Market Data (ProductScore, operational_score_v2)
    ├──► Competitor Data (existing_hero_categories)
    ├──► Material/Spec Analysis (Product.attributes)
    ├──► Creative Potential (Product.meta.images)
    └──► IP/Compliance Signals (ProductAnalysisRun.nuotao_assessment)
    │
    ▼
Data Readiness Matrix (V3_READY / V3_NEEDS_DATA / V3_BLOCKED)
    │
    ▼
V3.0 Evaluation (nuotao_selection_service.evaluate_product)
    │
    ├──► Score Dimensions (value, utility, weight_packability, durability, brand_fit, differentiation)
    ├──► V1-V12 Veto (evaluate_vetoes)
    └──► Funnel Stage (rejected / screened / test_candidate)
```

**Key principle:** No new data sources created. Every enrichment step reuses an existing service.

---

## 2. V3 SCORING DIMENSION FIELD REQUIREMENTS

### 2.1 Six Scoring Dimensions

| Dimension | Required Fields | Data Source | Derived Fields | UNKNOWN Behavior |
|---|---|---|---|---|
| **Value** | `operational.profit` (0-10), `margin_rate` (0-1) | ProductScore (M2.1 profit dim), ProductCost | margin_score = f(margin_rate); blend(profit, margin_score, 0.7) | Strict: profit MISSING → DataInsufficientError; margin missing → profit-only |
| **Utility** | `operational.demand` (0-10) | ProductScore (M2.1 demand dim) | direct: demand dim | Strict: MISSING → DataInsufficientError |
| **Weight & Packability** | `operational.logistics` (0-10), `weight_kg` | ProductScore (M2.1 logistics dim), Product.weight_kg | weight_score = f(weight_kg); blend(logistics, weight_score, 0.6) | Strict: logistics MISSING → error; weight missing → logistics-only |
| **Durability** | `operational.compliance` (0-10), `supplier_rating` (A/B/C/D) | ProductScore (M2.1 compliance dim), Supplier.rating | supplier_score = f(supplier_rating); blend(compliance, supplier_score, 0.5) | Strict: compliance MISSING → error; rating missing → compliance-only |
| **Brand Fit** | `brand_fit_override` (0-10) | ProductAnalysisRun → ai_signals.brand_fit | direct: brand_fit_override | Strict: MISSING → DataInsufficientError (no default!) |
| **Differentiation** | `operational.differentiation` (0-10), `operational.competition` (0-10) | ProductScore (M2.1 differentiation + competition dims) | blend(differentiation, competition, 0.6) | Strict: both MISSING → error |

### 2.2 V1-V12 Veto Rules

| Rule | Name | Check Type | Required Fields | UNKNOWN Behavior |
|---|---|---|---|---|
| **V1** | IP Infringement | AI | ai_signals.veto_signals.V1 | PENDING (no AI) |
| **V2** | Regulatory Compliance | AI | ai_signals.veto_signals.V2 | PENDING (no AI) |
| **V3** | Safety Risk | AI/Hybrid | ai_signals.veto_signals.V3, compliance_failures | PENDING (no AI), FAIL if in compliance_failures |
| **V4** | Banned Category | Deterministic | category, banned_categories | FAIL if hit, PASS if configured & miss, PENDING if no config |
| **V5** | Brand Focus | Hybrid | category, off_brand_categories, ai_signals | FAIL if hit, PASS if configured & miss, PENDING if AI-only |
| **V6** | Low-Price Impulse | Deterministic | reference_price_usd | FAIL if < $5, PASS if >= $5, PENDING if None |
| **V7** | Hero Conflict | Deterministic | category, existing_hero_categories | FAIL if hit, PASS if no conflict |
| **V8** | Brand Fit Floor | Deterministic | dimensions.brand_fit | FAIL if < 5.0, PASS if >= 5.0 |
| **V9** | Logistics Feasibility | Deterministic | shipping_ratio | FAIL if > 0.40, PASS if <= 0.40, PENDING if None |
| **V10** | Margin Feasibility | Deterministic | margin_rate | FAIL if < 0.20, PASS if >= 0.20, PENDING if None |
| **V11** | Supplier Feasibility | Hybrid | supplier_rating | FAIL if D, PASS if A/B/C, PENDING if None |
| **V12** | Return Rate Risk | Hybrid | return_rate | FAIL if > 0.15, PASS if <= 0.15, PENDING if None |

### 2.3 Data Integrity Gate Field Weights

| Field Group | Weight | Status if Missing |
|---|---|---|
| operational_dimensions (6 dims) | 30 | missing_fields += "operational_dimensions" |
| margin_rate | 10 | missing_fields += "margin_rate" |
| shipping_ratio | 10 | missing_fields += "shipping_ratio" |
| reference_price_usd | 10 | missing_fields += "reference_price_usd" |
| weight_kg | 10 | missing_fields += "weight_kg" |
| supplier_rating | 10 | missing_fields += "supplier_rating" |
| brand_fit (AI override) | 10 | missing_fields += "brand_fit" |
| category | 5 | missing_fields += "category" |
| return_rate | 5 | missing_fields += "return_rate" |

**Gate thresholds:** score >= 40 → passed; >= 90 → "complete"; >= 40 → "partial"; < 40 → "missing"

---

## 3. RAW SOURCE CONTRACT (PHASE 2)

SOP-A (sourcing_service.create_product_candidate) already collects:

| Field | Stored In | Format |
|---|---|---|
| title | Product.name | string |
| description | Product.description | string |
| price / price_range | ProductSource.raw_data | dict |
| moq | ProductSource.raw_data | int |
| sku | Product.sku | string |
| attributes | Product.attributes | dict |
| material | Product.attributes.material | string |
| weight | Product.weight_kg | Decimal |
| dimensions | Product.dimensions | dict {length, width, height} |
| main_image / images | Product.meta.images | list[str] |
| supplier | SourcingCandidate.supplier_id | UUID → Supplier |
| category | Product.category | string |
| sale_quantity | ProductSource.raw_data | int |

**Existing services to reuse:**
- `sourcing_service.create_product_candidate` — 1688 candidate intake
- `product_source_identity.get_or_create_by_source` — dedup + source identity
- `backfill_1688_service.backfill_1688_products` — fill missing fields from 1688
- `cost_sync_service.sync_product_cost` — extract 1688 price → ProductCost

---

## 4. PRODUCT EVALUATION CONTEXT MODEL (PHASE 3)

### 4.1 Data Model

```python
@dataclass
class ProductEvaluationContext:
    """Unified evaluation context for V3.0 scoring."""
    product_id: UUID
    workspace_id: UUID
    trace_id: str

    # Product facts
    product_facts: dict[str, Any]      # {value, source, confidence, updated_at}

    # Cost & landed cost
    cost: dict[str, Any] | None        # {purchase_cost, shipping, total_landed_cost, ...}
    margin_rate: Decimal | None
    shipping_ratio: Decimal | None
    reference_price_usd: Decimal | None

    # Physical
    weight_kg: Decimal | None
    dimensions: dict[str, Any] | None

    # Supplier
    supplier_rating: str | None        # A/B/C/D

    # Market (operational)
    operational: dict[str, Decimal]    # {profit, logistics, demand, competition, differentiation, compliance}

    # Brand
    brand_fit_override: Decimal | None # AI/rulebook

    # Compliance / IP
    ai_veto_signals: dict[str, AiVerdict] | None  # V1-V3, V5
    compliance_failures: tuple[str, ...] = ()

    # Category
    category: str | None
    banned_categories: tuple[str, ...] = ()
    off_brand_categories: tuple[str, ...] = ()
    existing_hero_categories: tuple[str, ...] = ()

    # Return rate
    return_rate: Decimal | None

    # Metadata
    context_version: str = "v1"
    enriched_at: datetime | None = None
```

### 4.2 UNKNOWN Semantics

- `None` = field not available, explicitly unknown
- `Decimal("0")` = zero value (valid, e.g. zero cost)
- `""` or `[]` = empty but present (valid, e.g. no tags)
- Missing key = field not collected (never use this pattern)

---

## 5. DATA ENRICHMENT PIPELINE (PHASE 4)

### 5.1 Enrichment Steps (all reuse existing services)

```
Step 1: Product Facts
  Source: Product.attributes, Product.meta, ProductSource.raw_data
  Service: (direct DB read — no external call)

Step 2: Cost / Landed Cost
  Source: ProductCost table
  Service: product_cost_service.latest_cost_for_product()
  Fallback: cost_sync_service.sync_product_cost() if no ProductCost exists

Step 3: Logistics Estimate
  Source: Product.weight_kg, Product.dimensions
  Service: (direct DB read)
  Derived: shipping_ratio = international_shipping / sale_price

Step 4: Supplier Data
  Source: Supplier.rating via SourcingCandidate
  Service: nuotao_selection_service._best_supplier_rating()

Step 5: Market Data
  Source: ProductScore (M2.1 operational score)
  Service: nuotao_selection_service._latest_operational_score()

Step 6: Competitor Data
  Source: Existing Hero products (Product.funnel_stage='hero' or candidate_status='winner')
  Service: nuotao_selection_service._existing_hero_categories()

Step 7: Material/Spec Analysis
  Source: Product.attributes (material, specification, etc.)
  Service: (direct DB read)

Step 8: Creative Potential
  Source: Product.meta.images, Product.description
  Service: (direct DB read)

Step 9: IP/Compliance Signals
  Source: ProductAnalysisRun.output.nuotao_assessment
  Service: nuotao_selection_service._latest_ai_assessment()
  Normalizer: nuotao_ai_signals.normalize_ai_assessment()
```

### 5.2 Enrichment Function

```python
async def build_evaluation_context(
    session: AsyncSession,
    product_id: UUID,
    *,
    workspace_id: UUID,
    trace_id: str,
) -> ProductEvaluationContext:
    """Build unified evaluation context by reusing existing services."""
    ...
```

---

## 6. READINESS MATRIX (PHASE 5)

### 6.1 Readiness States

| State | Condition | Action |
|---|---|---|
| **V3_READY** | data_integrity_gate passes (score >= 40) | Auto V3 evaluation |
| **V3_NEEDS_DATA** | Gate fails but missing fields can be auto-enriched | Attempt enrichment, retry up to 3x |
| **V3_BLOCKED** | Gate fails and missing fields cannot be enriched | Exception Queue |

### 6.2 Auto-Enrichable Fields

| Field | Auto-Enrichable? | Source | Max Retries |
|---|---|---|---|
| operational_dimensions | Yes (if ProductScore exists) | _latest_operational_score | 1 |
| margin_rate | Yes (if ProductCost exists) | product_cost_service | 1 |
| shipping_ratio | Yes (if ProductCost exists) | product_cost_service | 1 |
| reference_price_usd | Yes (from Product.meta or ProductCost) | product_cost_service | 1 |
| weight_kg | Yes (from backfill_1688) | backfill_1688_service | 3 |
| supplier_rating | Yes (if SourcingCandidate exists) | _best_supplier_rating | 1 |
| brand_fit | No (requires AI assessment) | ProductAnalysisRun | 0 |
| category | Yes (from Product.category or backfill) | backfill_1688_service | 3 |
| return_rate | No (requires historical data) | (future) | 0 |

### 6.3 Non-Auto-Enrichable Fields

- **brand_fit**: Requires Product Analyst AI run. Until P2 AI assessment is available, this is always PENDING.
- **return_rate**: Requires historical return data. Currently always PENDING.

---

## 7. ORCHESTRATOR INTEGRATION (PHASE 6)

### 7.1 Stage Flow

```
Candidate Ready (S1)
    │
    ▼
Data Enrichment (S2 — NEW)
    │  ├── Auto-enrich missing fields
    │  ├── Backfill from 1688 (max 3 retries)
    │  └── Build ProductEvaluationContext
    ▼
Data Readiness (S3 — existing DATA_READINESS)
    │  ├── data_integrity_gate.check_integrity()
    │  ├── V3_READY → auto V3
    │  ├── V3_NEEDS_DATA → loop back to S2
    │  └── V3_BLOCKED → Exception Queue
    ▼
V3 Evaluation (S4 — existing V3_EVALUATION)
    │  ├── nuotao_selection_service.evaluate_product()
    │  └── Persist ProductNuotaoScore
    ▼
Hard Rules (S5 — existing HARD_RULES)
    │  ├── evaluate_vetoes()
    │  └── Veto? → rejected
    ▼
Product Decision (S6 — existing PRODUCT_DECISION)
```

### 7.2 Exception Queue

When enrichment fails after 3 retries:
```python
{
    "error_code": "ENRICHMENT_FAILED",
    "missing_fields": [...],
    "next_actions": [...],
    "source": "data_enrichment",
    "retry_count": 3,
}
```

---

## 8. COST MODEL (PHASE 7)

### 8.1 Landed Cost Components

```
Landed Cost =
    purchase_cost
  + domestic_shipping
  + international_shipping  (or first_leg + last_leg fallback)
  + packaging
  + tax_estimate
  + handling
```

### 8.2 Effective Landed Cost

The V3 evaluation uses `cost.total_landed_cost` (effective landed cost) for margin calculation:

```python
margin_rate = (revenue - total_landed_cost - payment_fee - marketing - refund) / revenue
```

**Rule:** V3 must consume `ProductCost.total_landed_cost`, never a manually copied value.

### 8.3 Cost Enrichment

If no `ProductCost` exists:
1. Try `cost_sync_service.sync_product_cost()` — extract from 1688 source data
2. If still missing, mark `margin_rate` and `shipping_ratio` as None (PENDING for V9/V10)

---

## 9. STOP RULES

- **Do NOT** modify V3 scoring algorithm (nuotao_score_mapper, nuotao_score_v3, nuotao_veto)
- **Do NOT** modify Hard Rules (data_integrity_gate, decision rules)
- **Do NOT** create Product Master, Creative, Listing, or WC Publish
- **Do NOT** use fake data or mock success
- **Do NOT** treat UNKNOWN as 0, 50, or PASS
- **Do NOT** create a second 1688 parser

---

## 10. IMPLEMENTATION PLAN

| Phase | Deliverable | Files |
|---|---|---|
| 1 | Audit report | docs/audits/P0_3_V3_FIELD_AUDIT.md |
| 2 | Confirm raw source contract | (no new code — existing services) |
| 3 | ProductEvaluationContext model | app/services/evaluation_context.py |
| 4 | Data enrichment pipeline | app/services/evaluation_context.py |
| 5 | Readiness matrix | app/services/evaluation_readiness.py |
| 6 | Orchestrator integration | app/services/product_factory_orchestrator.py (S2 handler) |
| 7 | Cost model integration | (existing — cost_sync_service reuse) |
| 8 | Tests | tests/test_evaluation_context.py |
| 9 | Real test with 60 candidates | (requires env — see P0-2.5 STOP) |
