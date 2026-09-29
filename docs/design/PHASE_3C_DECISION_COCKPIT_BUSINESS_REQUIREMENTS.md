# Phase 3C: Product Decision Cockpit - Business Requirements

**Version:** 1.0  
**Date:** 2026-09-29  
**Phase:** 3C  
**Status:** Design

---

## 1. Problem Statement

### Current State (Phase 3B)
- Product Workbench shows lifecycle overview and today's tasks
- Users can see product counts by stage
- Users can filter tasks by stage and priority
- **But:** Users cannot answer the critical question: "Should I continue with this product?"

### Target State (Phase 3C)
- **30-second decision:** Boss opens a product, sees all relevant data, makes a decision in 30 seconds
- **Decision types:** Continue / Reject / Supplement Data / Approve
- **Evidence-based:** Every decision has supporting data and reasoning

### Success Metrics
- Time-to-decision: < 30 seconds for simple cases, < 5 minutes for complex cases
- Decision confidence: > 80% of decisions are confirmed without re-review
- Data completeness: < 10% of products require "Supplement Data" action

---

## 2. User Personas

### Primary: Product Manager / Boss
- **Goal:** Make fast, informed decisions on product viability
- **Pain points:**
  - Too much data scattered across systems
  - Unclear which metrics matter most
  - No clear decision framework
  - Fear of making wrong decisions without evidence
- **Needs:**
  - Single page with all decision-relevant data
  - Clear recommendation with reasoning
  - Quick action buttons (Continue/Reject/Approve)
  - Audit trail for decisions made

### Secondary: Operations Manager
- **Goal:** Understand product status and next actions
- **Pain points:**
  - Products stuck in certain stages
  - Unclear who is responsible for what
  - No visibility into blockers
- **Needs:**
  - Status overview
  - Task assignments
  - Blocker resolution

---

## 3. Core Decision Framework

### 3.1 The 30-Second Rule

When a user opens a product, they should be able to answer these questions in 30 seconds:

1. **Is this product viable?** (Yes/No/Maybe)
2. **Why?** (Top 3 reasons)
3. **What's the risk?** (High/Medium/Low)
4. **What should I do?** (Continue/Reject/Approve/Supplement Data)

### 3.2 Decision Types

| Decision | When to Use | Evidence Required |
|----------|-------------|-------------------|
| **Continue** | Product is viable, proceed to next stage | Positive AI score, passing hard rules, acceptable margin |
| **Reject** | Product is not viable, stop investment | Negative AI score, failing hard rules, poor margin |
| **Supplement Data** | Insufficient data to decide | Missing market data, incomplete cost data, unknown return rate |
| **Approve** | Product is ready for next major milestone | All checks passed, human review required |

### 3.3 Key Constraints (Non-Negotiable)

These constraints must be enforced in the UI and API:

| Constraint | Explanation | UI Enforcement |
|------------|-------------|----------------|
| **Candidate ≠ Product Master** | A candidate product cannot skip to Product Master | Blocked transition without approval |
| **Return Rate = UNKNOWN ≠ PASS** | Unknown return rate is not a pass condition | Show as "Data Missing", not "Pass" |
| **Hard Rule ≠ AI Score** | Hard rules are binary pass/fail; AI score is continuous | Separate sections, different visual treatment |
| **AI Recommendation ≠ Human Approval** | AI suggests; humans decide | Clear "AI suggests" vs "You decide" labels |
| **Listing Approved ≠ WooCommerce Published** | Approval is a decision; publishing is an action | Separate status indicators |

---

## 4. Information Architecture

### 4.1 Decision Cockpit Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Product Decision Cockpit                    [Product Name]     │
│  SKU: ABC-123                      Status: [Candidate▼]        │
│  Created: 2026-09-01               Last Updated: 2026-09-29     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  DECISION SUMMARY (30-Second View)                       │  │
│  │                                                          │  │
│  │  AI Score: 78/100  ████████░░  [Continue Recommended]   │  │
│  │  Hard Rules: 4/5 PASS  ⚠️ 1 FAIL (Return Rate Unknown)  │  │
│  │  Margin: 45%  ✅  (Target: 40%)                         │  │
│  │  Risk Level: MEDIUM                                     │  │
│  │                                                          │  │
│  │  ┌─────────────┬──────────┬──────────┬────────────────┐  │  │
│  │  │ CONTINUE    │ REJECT   │ SUPPLEMENT│ APPROVE        │  │  │
│  │  │ [Primary]   │ [Danger] │ [Warning] │ [Success]     │  │  │
│  │  └─────────────┴──────────┴──────────┴────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│  TABS: [Facts] [Analysis] [Cost] [Supply] [Rules] [History]   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─── FACTS TAB ──────────────────────────────────────────┐    │
│  │  Product: Water Bottle 500ml                            │    │
│  │  Category: Outdoor Hydration                            │    │
│  │  Price: ¥89.00                                          │    │
│  │  Weight: 250g                                           │    │
│  │  Origin: Zhejiang, CN                                   │    │
│  │  Supplier: ABC Manufacturing                            │    │
│  │  Lead Time: 15 days                                     │    │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─── ANALYSIS TAB ───────────────────────────────────────┐    │
│  │  Market Size: ¥1.2B/year  │ Growth: 12% YoY            │    │
│  │  Competition: Medium      │ Seasonality: Summer Peak    │    │
│  │  Target Customer: 25-45, Urban, Outdoor Enthusiasts     │    │
│  │  AI Recommendation: STRONG CONTINUE                     │    │
│  │  Confidence: 85%                                        │    │
│  │  Top Reasons:                                           │    │
│  │    1. High demand growth (+15% YoY)                    │    │
│  │    2. Low competition in 500ml segment                 │    │
│  │    3. Strong margin potential (45%)                    │    │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─── COST TAB ───────────────────────────────────────────┐    │
│  │  Unit Cost: ¥28.00 (Supplier: ABC Manufacturing)        │    │
│  │  Landed Cost: ¥35.00                                    │    │
│  │    - Shipping: ¥5.00                                    │    │
│  │    - Duties: ¥2.00                                      │    │
│  │    - Fees: ¥1.00                                        │    │
│  │  Retail Price: ¥89.00                                   │    │
│  │  Gross Margin: 60%  │ Net Margin: 45%                  │    │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─── SUPPLY TAB ─────────────────────────────────────────┐    │
│  │  Supplier: ABC Manufacturing                            │    │
│  │  Rating: 4.5/5.0  │ Orders: 12                          │    │
│  │  Lead Time: 15 days  │ MOQ: 100                         │    │
│  │  QC Rate: 98%                                             │    │
│  │  ⚠️ Risk: Seasonal capacity constraints                 │    │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─── RULES TAB ──────────────────────────────────────────┐    │
│  │  Hard Rules (Binary Pass/Fail):                         │    │
│  │  ✅ Price >= ¥50.00                                     │    │
│  │  ✅ Margin >= 40%                                       │    │
│  │  ✅ Lead Time <= 30 days                                │    │
│  │  ⚠️ Return Rate = UNKNOWN (Data Missing)               │    │
│  │  ✅ Compliance = PASSED                                 │    │
│  │                                                          │    │
│  │  AI Score (Continuous 0-100):                           │    │
│  │  78/100  ████████░░                                     │    │
│  │  Factors:                                               │    │
│  │    + Market growth (+20)                                │    │
│  │    + Margin potential (+18)                             │    │
│  │    - Competition (-8)                                   │    │
│  │    - Return rate unknown (-12)                          │    │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─── HISTORY TAB ────────────────────────────────────────┐    │
│  │  2026-09-29: Created as Candidate                       │    │
│  │  2026-09-28: AI Analysis completed (Score: 78)         │    │
│  │  2026-09-27: Product imported from 1688                │    │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Data Sections

| Section | Data Source | Update Frequency | Decision Impact |
|---------|-------------|------------------|-----------------|
| **Product Facts** | Product model, supplier data | Real-time | Foundation for all analysis |
| **Market Analysis** | AI analysis service, market data | Daily | Viability assessment |
| **AI Recommendation** | AI scoring engine | Per analysis run | Primary decision input |
| **Cost / Landed Cost** | Cost service, supplier quotes | Per quote update | Margin calculation |
| **Margin** | Calculated from cost + price | Real-time | Profitability check |
| **Supply Chain** | Supplier model, order history | Real-time | Risk assessment |
| **Hard Rules** | Rule engine | Per evaluation | Binary pass/fail gate |
| **Risks** | Aggregated from all sections | Real-time | Decision modifier |
| **Approval** | Approval workflow | Per approval action | Human decision record |
| **Next Action** | Lifecycle engine | Per state change | Guided workflow |

---

## 5. Interaction Design

### 5.1 Decision Flow

```
┌─────────────┐
│ Open Product │
└──────┬──────┘
       ↓
┌─────────────┐
│ View Summary │ ← 30-second decision view
└──────┬──────┘
       ↓
┌─────────────┐
│ Decide:      │
│ Continue?    │
│ Reject?      │
│ Supplement?  │
│ Approve?     │
└──────┬──────┘
       ↓
┌─────────────┐
│ Execute:     │
│ Transition   │
│ or           │
│ Request Data │
└──────┬──────┘
       ↓
┌─────────────┐
│ Record:      │
│ Decision +   │
│ Reasoning    │
└─────────────┘
```

### 5.2 Action Buttons

| Button | Color | When Available | Action |
|--------|-------|----------------|--------|
| **Continue** | Primary (Blue) | Always | Move to next stage |
| **Reject** | Danger (Red) | Always | Move to rejected stage |
| **Supplement Data** | Warning (Orange) | When data missing | Create data task |
| **Approve** | Success (Green) | When eligible | Approve for next milestone |

### 5.3 Evidence Requirements

Each decision must capture:

| Field | Required | Example |
|-------|----------|---------|
| Decision | Yes | "Continue" |
| Reasoning | Yes | "Strong margin, good market growth" |
| Evidence Sources | Yes | ["AI Score: 78", "Margin: 45%", "Rules: 4/5 PASS"] |
| Approver | Yes | "admin" |
| Timestamp | Yes | "2026-09-29T10:00:00Z" |
| Next Action | Yes | "Create Product Master" |

---

## 6. API Contract (Draft)

### 6.1 GET /products/{id}/decision

Returns all data needed for the decision cockpit:

```json
{
  "product_id": "uuid",
  "sku": "ABC-123",
  "name": "Water Bottle 500ml",
  "status": "candidate",
  "created_at": "2026-09-01T00:00:00Z",
  "updated_at": "2026-09-29T10:00:00Z",
  
  "decision_summary": {
    "ai_score": 78,
    "ai_recommendation": "continue",
    "hard_rules_pass": 4,
    "hard_rules_total": 5,
    "hard_rules_failures": ["return_rate_unknown"],
    "margin_percent": 45,
    "risk_level": "medium",
    "recommended_action": "continue"
  },
  
  "facts": { ... },
  "analysis": { ... },
  "cost": { ... },
  "supply": { ... },
  "rules": { ... },
  "history": [ ... ]
}
```

### 6.2 POST /products/{id}/decision

Records a decision:

```json
{
  "decision": "continue",
  "reasoning": "Strong margin, good market growth",
  "evidence_sources": ["ai_score:78", "margin:45%", "rules:4/5"],
  "next_action": "create_product_master"
}
```

---

## 7. Acceptance Criteria

### Phase 3C Design Complete When:

- [ ] Business requirements documented (this document)
- [ ] Information architecture defined
- [ ] Interaction design defined
- [ ] API contract drafted
- [ ] Key constraints identified and documented
- [ ] Decision framework defined
- [ ] Success metrics defined

### Phase 3C Implementation Complete When:

- [ ] Decision Cockpit page implemented
- [ ] All 6 tabs functional
- [ ] Decision buttons functional
- [ ] Decision history recorded
- [ ] Evidence captured for all decisions
- [ ] Key constraints enforced
- [ ] Browser acceptance passed
- [ ] No mock data

---

## 8. Open Questions

1. **Data Sources:** Which existing services provide market analysis data?
2. **AI Scoring:** What's the current AI scoring algorithm and data requirements?
3. **Cost Data:** How is landed cost calculated? What's the data source?
4. **Hard Rules:** What are the current hard rules defined in the system?
5. **Approval Workflow:** What's the current approval process for products?

---

## 9. Next Steps

1. Review this document with stakeholders
2. Identify data sources for each section
3. Define API endpoints in detail
4. Create UX mockups
5. Begin implementation (Phase 3C DEV)

---

*Document Owner: Product Manager*  
*Last Updated: 2026-09-29*
