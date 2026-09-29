# Phase 3C Task Registry

## P1-DEV-001: Vite Proxy ECONNREFUSED

**Priority:** P1 (High)  
**Status:** OPEN  
**Created:** 2026-09-29  
**Source:** Phase 3B Acceptance

### Description

Vite dev server proxy returns `ECONNREFUSED` when forwarding `/api` requests to backend.

**Environment:**
- Vite: 5.4.21
- Node.js: 24.9.0
- Backend: FastAPI on port 8011

**Current Workaround:**
- Frontend configured to call backend directly via `VITE_API_BASE=http://127.0.0.1:8011/api/v1`
- Bypasses Vite proxy entirely

**Root Cause (Suspected):**
- Vite 5.4.21 incompatible with Node.js 24.9.0
- Possible HTTP/1.1 vs HTTP/2 issue in `http-proxy` package

**Acceptance Criteria:**
- [ ] Vite proxy forwards `/api` requests to backend correctly
- [ ] Frontend can use relative API paths (`/api/v1/...`)
- [ ] No need for `VITE_API_BASE` env var in development
- [ ] Browser network tab shows requests going through `localhost:3000/api/...`

**Testing:**
```bash
# Start backend
cd backend && python -m uvicorn app.main:app --port 8011

# Start frontend
cd frontend && npx vite

# Test proxy
curl -v http://localhost:3000/api/v1/healthz
# Should return: {"status":"ok"}
```

**Estimate:** 2-4 hours

---

## P2-TEST-001: Alert Scheduler Test Failures

**Priority:** P2 (Medium)  
**Status:** OPEN  
**Created:** 2026-09-29  
**Source:** Phase 3B Test Baseline

### Description

3 tests in `tests/test_alert_scheduler.py` fail consistently:

1. `test_start_stop_lifecycle` - `AssertionError: assert (None is not None)`
2. `test_loop_tick_calls_run_once` - `assert 0 >= 2`
3. `test_tick_exception_does_not_kill_loop` - `assert 0 >= 2`

**Root Cause:**
- Alert scheduler's `enabled` flag defaults to `False` in test configuration
- `scheduler.start()` logs "alert scheduler disabled - not starting"
- `scheduler._task` remains `None`, so tick loop never runs

**Acceptance Criteria:**
- [ ] All 3 alert scheduler tests pass
- [ ] Full test suite: 893/893 passed
- [ ] Alert scheduler can be enabled/disabled in test fixtures

**Suggested Fix:**
```python
# In test fixtures, enable the scheduler
@pytest.fixture
def alert_scheduler_config():
    return {
        "alert_scheduler_enabled": True,
        "alert_scheduler_interval_seconds": 1,
    }
```

**Estimate:** 1-2 hours

---

## Phase 3C Tasks

*(To be defined in Phase 3C design phase)*

### P3C-CORE: Product Decision Cockpit

**Goal:** Boss opens a product, 30 seconds to decide "Continue / Reject / Supplement Data / Approve"

**Key Questions:**
1. Is this product worth continuing?
2. Why?
3. What are the risks?
4. What decision should be made?

**Data Flow:**
```
Product Facts
   ↓
Market Analysis
   ↓
AI Recommendation
   ↓
Cost / Landed Cost
   ↓
Margin
   ↓
Supply Chain
   ↓
Hard Rules
   ↓
Risks
   ↓
Approval
   ↓
Next Action
```

**Key Constraints:**
- Candidate ≠ Product Master
- Return Rate = UNKNOWN ≠ PASS
- Hard Rule ≠ AI Score
- AI Recommendation ≠ Human Approval
- Listing Approved ≠ WooCommerce Published

**Design Deliverables:**
- [ ] Business requirements document
- [ ] Information architecture
- [ ] Interaction design
- [ ] Data contract (API)
- [ ] UX mockups

---

*Last Updated: 2026-09-29*
