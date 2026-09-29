# Phase 3C: Decision Cockpit Data Sources

**Version:** 1.0  
**Date:** 2026-09-29  
**Phase:** 3C  
**Status:** Data Source Audit Complete

---

## 1. Product Facts

### Data Existence: ✅ EXISTS

### Model: `Product` (`products` table)

**Location:** `backend/app/models/product.py`

### Fields Available

| Field | Type | Description | Nullable |
|-------|------|-------------|----------|
| `id` | UUID | Product primary key | No |
| `sku` | String(64) | Stock Keeping Unit | No |
| `name` | String(255) | Product name | No |
| `description` | String(2000) | Product description | Yes |
| `category` | String(128) | Product category | Yes |
| `brand` | String(128) | Brand name | Yes |
| `brand_id` | UUID | Foreign key to brands | Yes |
| `status` | String(24) | Commerce status (draft/active/etc) | No |
| `candidate_status` | String(16) | Candidate lifecycle (candidate/approved/testing/winner/rejected) | Yes |
| `funnel_stage` | String(24) | V3 selection funnel stage | Yes |
| `reject_reasons` | JSON | V1-V12 veto reasons | No |
| `source` | String(32) | Product source (1688/MANUAL/CSV) | No |
| `source_url` | String(512) | Source URL | Yes |
| `tags` | JSON | Product tags | No |
| `attributes` | JSON | Product attributes | No |
| `meta` | JSON | Additional metadata | No |
| `weight_kg` | Numeric(8,3) | Weight in kg | Yes |
| `dimensions` | JSON | Dimensions | Yes |
| `target_market` | String(16) | Target market (US/EU/etc) | No |
| `mastered_at` | DateTime | Product Master creation timestamp | Yes |
| `mastered_by` | String(128) | Who approved Product Master | Yes |
| `mastered_trace_id` | String(64) | Trace ID for Product Master approval | Yes |
| `deleted_at` | DateTime | Soft delete timestamp | Yes |
| `workspace_id` | UUID | Workspace scope | No |
| `created_at` | DateTime | Creation timestamp | No |
| `updated_at` | DateTime | Last update timestamp | No |

### UNKNOWN Values

| Field | UNKNOWN Meaning | Handling |
|-------|-----------------|----------|
| `candidate_status` | Not a candidate product | Display as "N/A" |
| `funnel_stage` | Not in selection funnel | Display as "N/A" |
| `mastered_at` | Not yet Product Master | Display as "Not Mastered" |

### Traceability

- `id` - Primary key for joins
- `workspace_id` - Workspace scope
- `created_at` / `updated_at` - Timestamps
- `mastered_trace_id` - Trace ID for Product Master approval

### API Endpoint

- `GET /products/{id}` - Product detail
- `GET /products` - Product list

---

## 2. Market Analysis

### Data Existence: ✅ EXISTS

### Model: `ProductAnalysisRun` (`product_analysis_runs` table)

**Location:** `backend/app/models/product_intelligence.py`

### Fields Available

| Field | Type | Description | Nullable |
|-------|------|-------------|----------|
| `id` | UUID | Analysis run primary key | No |
| `product_id` | UUID | Foreign key to products | No |
| `market_size` | Decimal(12,2) | Market size in USD | Yes |
| `market_growth` | Decimal(5,2) | Market growth percentage | Yes |
| `competition_level` | String(16) | Competition level (low/medium/high) | Yes |
| `seasonality` | String(64) | Seasonality pattern | Yes |
| `target_customer` | JSON | Target customer profile | Yes |
| `ai_recommendation` | String(16) | AI recommendation (RECOMMEND/REVIEW/REJECT) | Yes |
| `confidence` | Decimal(4,3) | AI confidence (0-1) | Yes |
| `analysis_version` | String(16) | Analysis version (v1/v2/etc) | No |
| `trace_id` | String(64) | Trace ID for analysis run | Yes |
| `metadata_` | JSON | Additional analysis metadata | No |
| `created_at` | DateTime | Analysis creation timestamp | No |
| `workspace_id` | UUID | Workspace scope | No |

### UNKNOWN Values

| Field | UNKNOWN Meaning | Handling |
|-------|-----------------|----------|
| `market_size` | No market data available | Display as "UNKNOWN" |
| `market_growth` | No growth data | Display as "UNKNOWN" |
| `competition_level` | Not analyzed | Display as "UNKNOWN" |
| `ai_recommendation` | No AI analysis | Display as "No Analysis" |
| `confidence` | No confidence score | Display as "N/A" |

### Traceability

- `trace_id` - Full traceability for analysis run
- `analysis_version` - Version of analysis algorithm
- `created_at` - When analysis was run

### API Endpoint

- `GET /products/{id}/analysis` - Latest analysis
- `GET /products/{id}/analysis/history` - Analysis history

---

## 3. AI Score (Nuotao Score)

### Data Existence: ✅ EXISTS

### Model: `ProductNuotaoScore` (`product_nuotao_scores` table)

**Location:** `backend/app/models/product_intelligence.py`

### Fields Available

| Field | Type | Description | Nullable |
|-------|------|-------------|----------|
| `id` | UUID | Score primary key | No |
| `product_id` | UUID | Foreign key to products | No |
| `grade` | String(16) | Grade (hero/core/long_tail/reject) | No |
| `score` | Decimal(5,2) | Score (0-100) | No |
| `veto_rules` | JSON | List of veto rule IDs | No |
| `score_components` | JSON | Breakdown of score components | No |
| `trace_id` | String(64) | Trace ID for scoring | Yes |
| `created_at` | DateTime | Score creation timestamp | No |
| `workspace_id` | UUID | Workspace scope | No |

### UNKNOWN Values

| Field | UNKNOWN Meaning | Handling |
|-------|-----------------|----------|
| `score` | 0 means not scored | Display as "Not Scored" if 0 |
| `grade` | Always has value | N/A |
| `veto_rules` | Empty list = no vetos | Display as "No Vetos" |

### Traceability

- `trace_id` - Full traceability for scoring run
- `score_components` - Breakdown shows which factors affected score
- `created_at` - When score was calculated

### API Endpoint

- `GET /products/{id}/score` - Latest score
- `GET /products/{id}/score/history` - Score history

---

## 4. Cost / Landed Cost

### Data Existence: ✅ EXISTS

### Model: `ProductCost` (`product_cost` table)

**Location:** `backend/app/models/product.py`

### Fields Available

| Field | Type | Description | Nullable |
|-------|------|-------------|----------|
| `id` | UUID | Cost record primary key | No |
| `product_id` | UUID | Foreign key to products | Yes |
| `currency` | String(8) | Currency (USD/CNY/etc) | No |
| `purchase_cost` | Numeric(12,2) | Supplier purchase cost | No |
| `domestic_shipping` | Numeric(12,2) | Domestic shipping cost | No |
| `first_leg_shipping` | Numeric(12,2) | First leg (port to port) shipping | No |
| `last_leg_shipping` | Numeric(12,2) | Last leg (port to warehouse) shipping | No |
| `international_shipping` | Numeric(12,2) | International shipping (authoritative) | No |
| `packaging` | Numeric(12,2) | Packaging cost | No |
| `tax_estimate` | Numeric(12,2) | Tax estimate | No |
| `handling` | Numeric(12,2) | Handling fees | No |
| `total_landed_cost` | Numeric(12,2) | Total landed cost | No |
| `version` | String(16) | Cost model version | No |
| `payment_fee` | Numeric(12,2) | Payment processing fee | No |
| `marketing_amortization` | Numeric(12,2) | Marketing cost amortization | No |
| `after_sales_loss` | Numeric(12,2) | Estimated after-sales loss | No |
| `total_cost` | Numeric(12,2) | Legacy total cost | No |
| `valid_from` | DateTime | When cost became valid | No |
| `notes` | JSON | Additional notes | No |
| `created_at` | DateTime | Creation timestamp | No |
| `updated_at` | DateTime | Last update timestamp | No |
| `workspace_id` | UUID | Workspace scope | No |

### UNKNOWN Values

| Field | UNKNOWN Meaning | Handling |
|-------|-----------------|----------|
| `product_id` | Cost not linked to product | Display as "Orphaned Cost" |
| `purchase_cost` | 0 = not set | Display as "0.00" or "UNKNOWN" |
| `total_landed_cost` | 0 = not calculated | Display as "Not Calculated" |
| `version` | Always has value | N/A |

### Calculated Fields

| Field | Formula | Notes |
|-------|---------|-------|
| `margin_percent` | `(retail_price - total_landed_cost) / retail_price * 100` | Retail price from Product or WooCommerce |
| `freight_share` | `international_shipping / total_landed_cost * 100` | Percentage of landed cost |

### Traceability

- `version` - Cost model version
- `valid_from` - When cost became valid
- `created_at` / `updated_at` - Timestamps

### API Endpoint

- `GET /products/{id}/cost` - Current cost
- `GET /products/{id}/cost/history` - Cost history

---

## 5. Supply Chain

### Data Existence: ✅ EXISTS

### Models

| Model | Table | Location |
|-------|-------|----------|
| `Supplier` | `suppliers` | `backend/app/models/supplier.py` |
| `SupplierProfile` | `supplier_profiles` | `backend/app/models/supply_chain.py` |
| `ProductSource` | `product_sources` | `backend/app/models/product_intelligence.py` |

### Supplier Fields

| Field | Type | Description | Nullable |
|-------|------|-------------|----------|
| `id` | UUID | Supplier primary key | No |
| `code` | String(64) | Supplier code | No |
| `name` | String(255) | Supplier name | No |
| `platform` | String(32) | Platform (1688/etc) | No |
| `shop_url` | String(512) | Shop URL | Yes |
| `rating` | String(8) | Supplier rating (A/B/C/D) | No |
| `status` | String(16) | Supplier status (active/inactive) | No |
| `contact` | JSON | Contact information | No |
| `created_at` | DateTime | Creation timestamp | No |
| `updated_at` | DateTime | Last update timestamp | No |
| `workspace_id` | UUID | Workspace scope | No |

### ProductSource Fields

| Field | Type | Description | Nullable |
|-------|------|-------------|----------|
| `id` | UUID | Source primary key | No |
| `product_id` | UUID | Foreign key to products | Yes |
| `source_type` | String(16) | Source type (1688/MANUAL/CSV) | No |
| `source_url` | String(512) | Source URL | Yes |
| `supplier_id` | UUID | Foreign key to suppliers | Yes |
| `supplier_code` | String(64) | Supplier code | Yes |
| `captured_at` | DateTime | When source was captured | No |
| `raw_data` | JSON | Raw source data | No |
| `trace_id` | String(64) | Trace ID for sourcing | Yes |
| `workspace_id` | UUID | Workspace scope | No |

### UNKNOWN Values

| Field | UNKNOWN Meaning | Handling |
|-------|-----------------|----------|
| `supplier_id` | No supplier linked | Display as "Unknown Supplier" |
| `rating` | Always has value | N/A |
| `lead_time` | Not in model | Display as "Not Set" |
| `moq` | Not in model | Display as "Not Set" |

### Missing Fields (Need to Add)

| Field | Description | Proposed Location |
|-------|-------------|-------------------|
| `lead_time_days` | Supplier lead time in days | `SupplierProfile` or `ProductSource` |
| `moq` | Minimum Order Quantity | `SupplierProfile` or `ProductSource` |
| `qc_rate` | Quality Control pass rate | `SupplierProfile` |
| `order_history` | Historical orders with this supplier | New model or `EventLog` |

### Traceability

- `trace_id` - Full traceability for sourcing
- `supplier_id` - Links to supplier record
- `captured_at` - When source was captured

### API Endpoint

- `GET /suppliers/{id}` - Supplier detail
- `GET /products/{id}/sources` - Product sources
- `GET /products/{id}/supplier` - Product supplier

---

## 6. Hard Rules

### Data Existence: ✅ EXISTS

### Models

| Model | Table | Location |
|-------|-------|----------|
| `Rule` | `rules` | `backend/app/models/rule.py` |
| `RuleExecutionLog` | `rule_execution_logs` | `backend/app/models/rule.py` |

### Rule Fields

| Field | Type | Description | Nullable |
|-------|------|-------------|----------|
| `id` | UUID | Rule primary key | No |
| `rule_id` | String(64) | Rule identifier | No |
| `name` | String(255) | Rule name | No |
| `category` | String(64) | Rule category | No |
| `rule_type` | String(16) | Rule type (hard/soft) | No |
| `version` | String(16) | Rule version | No |
| `status` | String(16) | Rule status (draft/active/inactive) | No |
| `effective_from` | DateTime | When rule became effective | Yes |
| `effective_to` | DateTime | When rule expires | Yes |
| `scope` | JSON | Rule scope | No |
| `when_conditions` | JSON | Rule conditions | No |
| `then_result` | JSON | Rule result | No |
| `params` | JSON | Rule parameters | No |
| `approval_level` | String(8) | Approval level (L0/L1/L2/L3) | No |
| `owner` | String(128) | Rule owner | Yes |
| `created_at` | DateTime | Creation timestamp | No |
| `updated_at` | DateTime | Last update timestamp | No |
| `workspace_id` | UUID | Workspace scope | No |

### RuleExecutionLog Fields

| Field | Type | Description | Nullable |
|-------|------|-------------|----------|
| `id` | BigInt | Log primary key | No |
| `rule_id` | String(64) | Rule identifier | No |
| `rule_version` | String(16) | Rule version | No |
| `context` | JSON | Evaluation context | No |
| `result` | JSON | Evaluation result | No |
| `trace_id` | String(64) | Trace ID for evaluation | Yes |
| `created_at` | DateTime | When rule was evaluated | No |
| `workspace_id` | UUID | Workspace scope | No |

### UNKNOWN Values

| Field | UNKNOWN Meaning | Handling |
|-------|-----------------|----------|
| `status` | Not active | Display as "Inactive" |
| `effective_from` | Not yet effective | Display as "Not Effective" |
| `effective_to` | Never expires | Display as "Indefinite" |

### Rule Result Format

```json
{
  "passed": true,
  "rule_id": "margin_threshold",
  "rule_version": "v1",
  "value": 45.0,
  "threshold": 40.0,
  "message": "Margin 45% >= 40%",
  "trace_id": "abc123"
}
```

### Traceability

- `rule_id` + `rule_version` - Unique rule identification
- `trace_id` - Full traceability for evaluation
- `created_at` - When rule was evaluated

### API Endpoint

- `GET /rules` - List all rules
- `GET /rules/{rule_id}` - Rule detail
- `GET /products/{id}/rules` - Product rule evaluations
- `GET /products/{id}/rule-results` - Product rule results

---

## 7. Approval

### Data Existence: ✅ EXISTS

### Model: `AgentApproval` (`agent_approvals` table)

**Location:** `backend/app/models/agent_operations.py`

### Fields Available

| Field | Type | Description | Nullable |
|-------|------|-------------|----------|
| `id` | UUID | Approval primary key | No |
| `approval_type` | String(32) | Approval type (PRODUCT_CANDIDATE/RECOMMENDATION/etc) | No |
| `status` | String(16) | Approval status (pending/approved/rejected/expired) | No |
| `business_scope` | String(8) | Business scope (B2C/B2B/SHARED) | No |
| `entity_type` | String(64) | Entity type (product/etc) | No |
| `entity_id` | String(64) | Entity ID | No |
| `target_task_id` | UUID | Target task ID | Yes |
| `agent_id` | UUID | Agent ID | Yes |
| `actor` | String(64) | Who approved/rejected | Yes |
| `action` | String(16) | Action taken (approve/reject) | Yes |
| `note` | String(500) | Approval note/reason | Yes |
| `metadata_` | JSON | Additional metadata | No |
| `decided_at` | DateTime | When decision was made | Yes |
| `sla_warning_at` | DateTime | SLA warning time | Yes |
| `expires_at` | DateTime | Expiration time | Yes |
| `trace_id` | String(64) | Trace ID for approval | Yes |
| `created_at` | DateTime | Creation timestamp | No |
| `updated_at` | DateTime | Last update timestamp | No |
| `workspace_id` | UUID | Workspace scope | No |

### UNKNOWN Values

| Field | UNKNOWN Meaning | Handling |
|-------|-----------------|----------|
| `actor` | Not decided yet | Display as "Pending" |
| `action` | Not decided yet | Display as "Pending" |
| `note` | No note provided | Display as "No Note" |
| `decided_at` | Not decided yet | Display as "Pending" |

### Approval Types for Products

| Approval Type | Description |
|---------------|-------------|
| `PRODUCT_CANDIDATE` | Product candidate approval |
| `PRODUCT_MASTER` | Product Master creation approval |
| `LISTING` | Listing approval |

### Traceability

- `trace_id` - Full traceability for approval chain
- `actor` - Who made the decision
- `decided_at` - When decision was made
- `note` - Reason for decision

### API Endpoint

- `GET /approvals` - List approvals
- `GET /approvals/{id}` - Approval detail
- `POST /approvals/{id}/approve` - Approve
- `POST /approvals/{id}/reject` - Reject
- `GET /products/{id}/approvals` - Product approvals

---

## 8. Lifecycle / Audit

### Data Existence: ✅ EXISTS

### Models

| Model | Table | Location |
|-------|-------|----------|
| `EventLog` | `event_log` | `backend/app/models/event.py` |
| `Product.mastered_at` | `products` | `backend/app/models/product.py` |
| `Product.mastered_by` | `products` | `backend/app/models/product.py` |
| `Product.mastered_trace_id` | `products` | `backend/app/models/product.py` |

### EventLog Fields

| Field | Type | Description | Nullable |
|-------|------|-------------|----------|
| `id` | BigInt | Event primary key | No |
| `event_type` | String(128) | Event type | No |
| `entity_type` | String(64) | Entity type | No |
| `entity_id` | String(64) | Entity ID | No |
| `payload` | JSON | Event payload | No |
| `trace_id` | String(64) | Trace ID | Yes |
| `created_at` | DateTime | When event occurred | No |
| `workspace_id` | UUID | Workspace scope | No |

### Product Lifecycle Events

| Event Type | Description |
|------------|-------------|
| `product.created` | Product created |
| `product.candidate_status_changed` | Candidate status changed |
| `product.mastered` | Product Master created |
| `product.analysis_run` | AI analysis run |
| `product.score_calculated` | Nuotao Score calculated |
| `product.cost_updated` | Cost updated |
| `product.rule_evaluated` | Rules evaluated |
| `product.approval_created` | Approval created |
| `product.approval_decided` | Approval decided |
| `product.listing_created` | Listing job created |
| `product.listing_pushed` | Listing pushed to WC |

### UNKNOWN Values

| Field | UNKNOWN Meaning | Handling |
|-------|-----------------|----------|
| `trace_id` | No trace available | Display as "No Trace" |
| `payload` | Empty payload | Display as "No Details" |

### Traceability

- `trace_id` - Full traceability across all events
- `entity_type` + `entity_id` - Links events to products
- `created_at` - When event occurred

### API Endpoint

- `GET /events` - List events
- `GET /events/{id}` - Event detail
- `GET /products/{id}/events` - Product events
- `GET /products/{id}/timeline` - Product timeline

---

## 9. WooCommerce / Listing

### Data Existence: ✅ EXISTS

### Models

| Model | Table | Location |
|-------|-------|----------|
| `WooCommerceDraft` | `woocommerce_draft_payloads` | `backend/app/models/product_intelligence.py` |
| `ListingJob` | `listing_jobs` | `backend/app/models/listing_job.py` |

### WooCommerceDraft Fields

| Field | Type | Description | Nullable |
|-------|------|-------------|----------|
| `id` | UUID | Draft primary key | No |
| `product_id` | UUID | Foreign key to products | No |
| `sku` | String(64) | Product SKU | No |
| `name` | String(255) | Product name | No |
| `payload` | JSON | WooCommerce payload | No |
| `status` | String(24) | Draft status (generated/pushed/synced) | No |
| `created_by` | String(64) | Who created draft | Yes |
| `approved_by` | String(64) | Who approved draft | Yes |
| `approved_at` | DateTime | When approved | Yes |
| `trace_id` | String(64) | Trace ID | Yes |
| `created_at` | DateTime | Creation timestamp | No |
| `updated_at` | DateTime | Last update timestamp | No |
| `workspace_id` | UUID | Workspace scope | No |

### ListingJob Fields

| Field | Type | Description | Nullable |
|-------|------|-------------|----------|
| `id` | UUID | Job primary key | No |
| `product_id` | UUID | Foreign key to products | No |
| `sku` | String(64) | Product SKU | No |
| `name` | String(255) | Product name | No |
| `payload` | JSON | WC payload snapshot | No |
| `status` | String(16) | Job status (pending/approved/processing/rejected/published/failed) | No |
| `note` | Text | Notes/review comments | Yes |
| `reject_reasons` | JSON | Rejection reasons | No |
| `submitted_by` | String(128) | Who submitted | No |
| `reviewed_by` | String(128) | Who reviewed | Yes |
| `submitted_at` | DateTime | When submitted | No |
| `reviewed_at` | DateTime | When reviewed | Yes |
| `pushed_at` | DateTime | When pushed to WC | Yes |
| `published_at` | DateTime | When published | Yes |
| `retry_count` | Integer | Retry count | No |
| `wc_product_id` | Integer | WooCommerce product ID | Yes |
| `created_at` | DateTime | Creation timestamp | No |
| `updated_at` | DateTime | Last update timestamp | No |
| `workspace_id` | UUID | Workspace scope | No |

### UNKNOWN Values

| Field | UNKNOWN Meaning | Handling |
|-------|-----------------|----------|
| `wc_product_id` | Not yet published | Display as "Not Published" |
| `approved_by` | Not approved yet | Display as "Pending" |
| `published_at` | Not published yet | Display as "Not Published" |

### Listing Status Flow

```
pending → approved → processing → published
    ↓          ↓
rejected    failed → retry → processing
```

### Traceability

- `trace_id` - Full traceability for WC operations
- `wc_product_id` - Links to actual WC product
- `submitted_at` / `reviewed_at` / `published_at` - Timeline

### API Endpoint

- `GET /listing-jobs` - List listing jobs
- `GET /listing-jobs/{id}` - Listing job detail
- `GET /products/{id}/listing` - Product listing job
- `GET /products/{id}/woocommerce` - Product WC draft

---

## 10. Data Gap Analysis

### Missing Data for Decision Cockpit

| Data Point | Current Source | Gap | Proposed Solution |
|------------|----------------|-----|-------------------|
| **Return Rate** | None | Not in any model | Add to `ProductAnalysisRun` or new `ProductMetrics` model |
| **Lead Time** | None | Not in any model | Add to `SupplierProfile` |
| **MOQ** | None | Not in any model | Add to `SupplierProfile` |
| **QC Rate** | None | Not in any model | Add to `SupplierProfile` |
| **Retail Price** | Partial | In `Product.attributes` or WooCommerce | Standardize in `Product` model |
| **Order History** | None | Not in any model | Use `EventLog` or new `ProductOrders` model |
| **Compliance Status** | Partial | In `ProductAnalysisRun.metadata_` | Standardize in `Product` model |

### Recommended Additions

**1. Product Metrics (New Model)**

```python
class ProductMetrics(Base, TimestampMixin, WorkspaceMixin):
    """Product performance metrics (append-only)."""
    
    __tablename__ = "product_metrics"
    
    id: Mapped[UUID]
    product_id: Mapped[UUID]
    metric_type: Mapped[str]  # return_rate, order_count, revenue, etc.
    value: Mapped[Decimal]
    period_start: Mapped[DateTime]
    period_end: Mapped[DateTime]
    source: Mapped[str]  # woo, manual, calculated
    trace_id: Mapped[str | None]
```

**2. Supplier Profile Enhancements**

```python
class SupplierProfile(Base, TimestampMixin, WorkspaceMixin):
    """Enhanced supplier profile."""
    
    __tablename__ = "supplier_profiles"
    
    # Existing fields...
    lead_time_days: Mapped[int | None]
    moq: Mapped[int | None]
    qc_rate: Mapped[Decimal | None]
    price_competitiveness: Mapped[str]  # high/medium/low
```

---

## 11. Summary

### Data Availability Summary

| Data Category | Available | Complete | Traceable | Notes |
|---------------|-----------|----------|-----------|-------|
| **Product Facts** | ✅ | ✅ | ✅ | Complete in Product model |
| **Market Analysis** | ✅ | ⚠️ | ✅ | Missing return_rate, compliance |
| **AI Score** | ✅ | ✅ | ✅ | Complete in ProductNuotaoScore |
| **Cost / Landed Cost** | ✅ | ✅ | ✅ | Complete in ProductCost |
| **Supply Chain** | ✅ | ⚠️ | ⚠️ | Missing lead_time, moq, qc_rate |
| **Hard Rules** | ✅ | ✅ | ✅ | Complete in Rule/RuleExecutionLog |
| **Approval** | ✅ | ✅ | ✅ | Complete in AgentApproval |
| **Lifecycle / Audit** | ✅ | ✅ | ✅ | Complete in EventLog |
| **WooCommerce** | ✅ | ✅ | ✅ | Complete in WooCommerceDraft/ListingJob |

### Recommended Actions

1. **Phase 3C Implementation** - Use existing models for Decision Read Model
2. **Phase 3D Enhancement** - Add missing fields (return_rate, lead_time, moq, qc_rate)
3. **No New Models** - Reuse existing models for Decision Cockpit

---

*Document Owner: Data Architect*  
*Last Updated: 2026-09-29*
