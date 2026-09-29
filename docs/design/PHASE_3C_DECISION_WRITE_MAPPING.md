# Phase 3C-3: Decision Write Model — Service Mapping

> Phase: Phase 3C-3 — Decision Write Model
> Status: Design Complete, Ready for Implementation
> Based on: Existing services audit (product_intelligence, approval_service, approval_rbac, event_service)

---

## 1. Existing State Machines

### 1.1 Candidate Lifecycle (M5.13)

```
None → candidate → approved → testing → winner (terminal)
                ↘ rejected (terminal)
```

**Transitions defined in:** `_CANDIDATE_TRANSITIONS` in `product_intelligence.py`

```python
_CANDIDATE_TRANSITIONS: dict[str | None, set[str]] = {
    None: {"candidate"},
    "candidate": {"approved", "rejected"},
    "approved": {"testing", "rejected"},
    "testing": {"winner", "rejected"},
    "winner": set(),      # terminal
    "rejected": set(),    # terminal
}
```

**Precondition:** `candidate → approved` requires pricing (retail price + purchase cost) to be filled.

### 1.2 ProductDecision Approval

```
pending → approved (if decision == "test", advances product lifecycle)
      → rejected (sets candidate_status = "rejected")
```

**Functions:** `approve_decision()`, `reject_decision()` in `product_intelligence.py`

### 1.3 AgentApproval (M5.4)

```
pending → approved
      → rejected
```

**Approval types:** `PRODUCT_CANDIDATE`, `PRODUCT_DECISION`, `PRODUCT_EXPERIMENT`

### 1.4 Product Mastering

**Triggered by:** `candidate → approved` transition OR `ProductDecision` approval with `decision == "test"`

**Fields set:** `mastered_at`, `mastered_by`, `mastered_trace_id`

### 1.5 Listing Workflow

```
Product Master (candidate_status = approved) → Listing Job created → WC Draft generated → WC Published
```

**Separate from:** Product Decision (Listing Approval ≠ Product Approval)

---

## 2. Human Decision → Existing Service Mapping

| Human Decision | Existing Service | State Mutation | Resulting Stage |
|----------------|------------------|----------------|-----------------|
| **CONTINUE** | `update_candidate_status()` | Advances candidate lifecycle | Next legal stage |
| **REJECT** | `update_candidate_status()` | Sets `candidate_status = "rejected"` | Rejected (terminal) |
| **SUPPLEMENT_DATA** | `event_service.create_event()` | No state change, records data request | Same stage |
| **APPROVE** | `update_candidate_status()` or `approve_decision()` | Depends on current state | See below |

### 2.1 CONTINUE — Advance to Next Stage

**Semantics:** Continue the product evaluation flow to the next legal stage.

**Current State → Target State:**

| Current `candidate_status` | Target State | Service Call |
|----------------------------|--------------|--------------|
| `candidate` | `approved` | `update_candidate_status(new_status="approved")` |
| `approved` | `testing` | `update_candidate_status(new_status="testing")` |
| `testing` | `winner` | `update_candidate_status(new_status="winner")` |
| `winner` | — | DENY (terminal) |
| `rejected` | — | DENY (terminal) |

**Precondition checks:**
- `candidate → approved`: Must have pricing (retail price + purchase cost)
- `approved → testing`: No additional checks (already approved)
- `testing → winner`: No additional checks (already tested)

**Resulting Stage (User Stage):**
- `candidate → approved`: Pending Approval → Product Master
- `approved → testing`: Testing (new stage, maps to "Analysis" or "B2C Listing" depending on context)
- `testing → winner`: Winner (maps to "B2C Listing")

### 2.2 REJECT — Enter Rejected State

**Semantics:** Reject the product, enter the existing rejected flow.

**Service Call:** `update_candidate_status(new_status="rejected")`

**Record:**
- `actor`: from JWT
- `workspace`: from Workspace Authorization
- `reason`: from request body
- `timestamp`: `datetime.now(UTC)`
- `trace_id`: from request

**Resulting Stage:** Rejected (terminal, no further decisions allowed)

### 2.3 SUPPLEMENT_DATA — Request Data

**Semantics:** Request additional data without changing product state.

**Required fields:**
- `field`: which data is needed (e.g., "cost", "supplier", "market_evidence")
- `reason`: why the data is needed

**Service Call:** `event_service.create_event(event_type="product.decision.supplement_data_requested")`

**No state change:** Product remains in current stage.

**Resulting Stage:** Same as before

### 2.4 APPROVE — Human Decision = APPROVED

**Semantics:** Human has reviewed and approved the product for the next milestone.

**Ambiguity:** "APPROVE" could mean:
1. Approve a pending `ProductDecision` (calls `approve_decision()`)
2. Approve a pending `AgentApproval` (calls `approval_service.approve()`)
3. Advance candidate to `approved` state (calls `update_candidate_status()`)

**Resolution based on current state:**

| Current State | APPROVE Meaning | Service Call |
|---------------|-----------------|--------------|
| `candidate` | Approve candidate → Product Master | `update_candidate_status(new_status="approved")` |
| `approved` | Approve for testing | `update_candidate_status(new_status="testing")` |
| `testing` | Approve for winner | `update_candidate_status(new_status="winner")` |
| `winner` | DENY (already terminal) | — |
| `rejected` | DENY (already terminal) | — |
| Pending `ProductDecision` | Approve decision | `approve_decision(decision_id=...)` |
| Pending `AgentApproval` | Approve approval | `approval_service.approve(...)` |

**Critical distinction:**
- `APPROVE` ≠ `WooCommerce Publish`
- `APPROVE` ≠ `Create Listing`
- `APPROVE` → `Product Master Created` (only when `candidate → approved`)

---

## 3. Permission Model

### 3.1 Existing Permissions

**From `approval_rbac.py`:**

| Approval Type | Permission Prefix | Actions |
|---------------|-------------------|---------|
| `PRODUCT_DECISION` | `product.decision` | `approve`, `reject` |
| `PRODUCT_CANDIDATE` | `product.candidate` | `approve`, `reject` |
| `PRODUCT_EXPERIMENT` | `product.experiment` | `approve`, `reject` |

### 3.2 Decision Permissions

| Decision | Required Permission | Notes |
|----------|---------------------|-------|
| **CONTINUE** | `product.candidate.approve` | Same as approve candidate |
| **REJECT** | `product.candidate.reject` | Same as reject candidate |
| **SUPPLEMENT_DATA** | None (any authenticated user) | Low-risk action, no state change |
| **APPROVE** | `product.candidate.approve` OR `product.decision.approve` | Depends on current state |

### 3.3 Permission Gaps

| Gap | Description | Resolution |
|-----|-------------|------------|
| `SUPPLEMENT_DATA` permission | No specific permission defined | Any authenticated user can request data (low risk) |
| `CONTINUE` vs `APPROVE` distinction | Both advance lifecycle | Use `CONTINUE` for explicit advancement, `APPROVE` for approval semantics |

---

## 4. Idempotency

### 4.1 Existing Mechanism

**From:** `b2b_finance.py`, `refund.py`, `customer_privacy.py`, etc.

**Pattern:**
- Unique constraint on `(workspace_id, idempotency_key)` or `(workspace_id, entity_id, idempotency_key)`
- First request creates the record
- Subsequent requests with same key return the existing record

### 4.2 Decision Idempotency

**Approach:** Use `EventLog` as the idempotency store.

**Logic:**
1. Generate `idempotency_key` if not provided (from request hash)
2. Check `EventLog` for existing decision event with same key
3. If exists: return stable result (no mutation)
4. If not: proceed with mutation, create event with `idempotency_key` in payload

**Duplicate detection:**
- Same `idempotency_key` → return existing result
- Same decision type + same state → return current state (idempotent)
- Different decision + same `idempotency_key` → return error (key already used for different decision)

### 4.3 Idempotency Key Generation

**Priority:**
1. Client-provided `idempotency_key`
2. Hash of `(workspace_id, product_id, decision, actor, reason)`

**Format:** `decision-{product_id}-{decision}-{timestamp}`

---

## 5. Audit / Event Logging

### 5.1 Event Types

| Decision | Event Type | Entity Type | Payload |
|----------|------------|-------------|---------|
| **CONTINUE** | `product.decision.continue` | `product` | `{decision, reason, from_status, to_status, actor, idempotency_key}` |
| **REJECT** | `product.decision.reject` | `product` | `{decision, reason, from_status, to_status, actor, idempotency_key}` |
| **SUPPLEMENT_DATA** | `product.decision.supplement_data_requested` | `product` | `{decision, reason, supplement_fields, actor, idempotency_key}` |
| **APPROVE** | `product.decision.approve` | `product` | `{decision, reason, from_status, to_status, actor, idempotency_key}` |

### 5.2 Failed Decisions

| Failure Type | Event Type | Payload |
|--------------|------------|---------|
| Invalid state transition | `product.decision.failed` | `{decision, reason, error, actor, idempotency_key}` |
| Permission denied | `product.decision.failed` | `{decision, reason, error, actor, idempotency_key}` |
| Precondition not met | `product.decision.failed` | `{decision, reason, error, actor, idempotency_key}` |

---

## 6. State Validation

### 6.1 Pre-Decision Checks

| Check | Description | Error Code |
|-------|-------------|------------|
| Product exists | Product must exist in workspace | 404 |
| Not terminal | Product must not be in terminal state (winner/rejected) | 400 |
| Allowed transition | Target state must be in `_CANDIDATE_TRANSITIONS` | 400 |
| Pricing required | `candidate → approved` requires pricing | 400 |
| Hard rules pass | No `RULE_FAIL` blockers (unless override mechanism exists) | 400 |
| Permission | Actor must have required permission | 403 |

### 6.2 Hard Rule Enforcement

**Rule FAIL → APPROVE/CONTINUE:**
- Default: DENY
- Exception: Only if existing override mechanism is used (none found in current code)

**Rule UNKNOWN:**
- Cannot auto-PASS
- Returns `SUPPLEMENT_DATA` or `REVIEW_REQUIRED`

---

## 7. API Contract

### 7.1 Request Schema

```python
class ProductDecisionRequest(BaseModel):
    decision: Literal["CONTINUE", "REJECT", "SUPPLEMENT_DATA", "APPROVE"]
    reason: str | None = Field(default=None, max_length=500)
    supplement_fields: list[str] | None = None  # Required for SUPPLEMENT_DATA
    idempotency_key: str | None = Field(default=None, max_length=128)
```

### 7.2 Response Schema

```python
class ProductDecisionResult(BaseModel):
    success: bool
    decision: str
    previous_status: str | None
    current_status: str | None
    stage: str
    reason: str | None
    next_action: str
    blockers: list[DecisionBlocker]
    idempotency_key: str
    trace_id: str | None
    timestamp: datetime
```

### 7.3 Error Response

```python
class ProductDecisionError(BaseModel):
    success: bool = False
    decision: str
    error: str
    reason: str | None
    current_status: str | None
    idempotency_key: str | None
    trace_id: str | None
```

---

## 8. Implementation Notes

### 8.1 Do NOT

- ❌ Create new state machine
- ❌ Copy state transition logic into `decision_service.py`
- ❌ Auto-create Product Master on APPROVE (let existing service handle it)
- ❌ Auto-create Listing on APPROVE
- ❌ Auto-sync WooCommerce on APPROVE
- ❌ Allow `force=true` bypass
- ❌ Accept body `actor` (use JWT)
- ❌ Accept `X-Workspace-ID` as identity

### 8.2 DO

- ✅ Call existing `update_candidate_status()` for lifecycle changes
- ✅ Call existing `approve_decision()` for decision approvals
- ✅ Call existing `event_service.create_event()` for audit
- ✅ Use existing `approval_rbac.check_approval_permission()` for permissions
- ✅ Use existing `EventLog` for idempotency
- ✅ Return `SUPPLEMENT_DATA` when data is missing
- ✅ DENY when Hard Rules FAIL (no override mechanism exists)

---

## 9. File Index

### Modified Files

- `backend/app/schemas/product_intelligence.py` — Add `ProductDecisionRequest`, `ProductDecisionResult`
- `backend/app/services/decision_service.py` — Add `apply_product_decision()` function
- `backend/app/api/v1/endpoints/product_intelligence.py` — Add `POST /decision` endpoint
- `backend/tests/test_decision_write_model.py` — New test file
- `docs/design/PRODUCT_AI_SELECTION_API_CONTRACT.md` — Update API contract

### New Files

- `docs/design/PHASE_3C_DECISION_WRITE_MAPPING.md` — This document

---

*Last Updated: 2026-09-29*
