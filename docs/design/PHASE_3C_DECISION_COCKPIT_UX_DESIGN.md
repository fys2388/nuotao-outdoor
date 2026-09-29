# Phase 3C: Product Decision Cockpit - UX Design

**Version:** 1.0  
**Date:** 2026-09-29  
**Phase:** 3C  
**Status:** Design

---

## 1. Design Principles

### 1.1 30-Second Rule

The user must be able to make a decision in 30 seconds for simple cases.

**Implications:**
- Most important data above the fold
- Clear visual hierarchy
- Minimal scrolling for decision
- Action buttons always visible

### 1.2 Evidence-Based Decisions

Every decision must have supporting evidence visible.

**Implications:**
- Show data sources for each metric
- Highlight data gaps
- Show AI reasoning
- Show rule evaluation results

### 1.3 Progressive Disclosure

Show summary first, details on demand.

**Implications:**
- Summary section at top
- Detailed tabs below
- Click to expand for more details
- No hidden data

### 1.4 Clear Decision Boundaries

Users must know when they can and cannot make decisions.

**Implications:**
- Show eligibility for each action
- Explain why an action is blocked
- Show next eligible action

---

## 2. Layout Structure

### 2.1 Header Section

```
┌─────────────────────────────────────────────────────────────────┐
│  ← Back to Workbench                                            │
│                                                                  │
│  Water Bottle 500ml                    [Candidate] [AI: 78/100] │
│  SKU: ABC-123                   Last Updated: 2026-09-29 10:00  │
│  Supplier: ABC Manufacturing      Created: 2026-09-01            │
└─────────────────────────────────────────────────────────────────┘
```

**Elements:**
- Back button (return to workbench)
- Product name (primary, large)
- Current status badge (color-coded)
- AI score badge (quick reference)
- SKU (secondary)
- Metadata (supplier, dates)

### 2.2 Decision Summary (Above the Fold)

```
┌─────────────────────────────────────────────────────────────────┐
│  DECISION SUMMARY                                               │
│                                                                  │
│  ┌──────────────┬──────────────┬──────────────┬──────────────┐  │
│  │ AI SCORE     │ HARD RULES   │ MARGIN       │ RISK LEVEL   │  │
│  │ 78/100       │ 4/5 PASS     │ 45%          │ MEDIUM       │  │
│  │ ████████░░   │ ⚠️ 1 FAIL    │ ✅ Good      │ ⚠️ Moderate  │  │
│  └──────────────┴──────────────┴──────────────┴──────────────┘  │
│                                                                  │
│  AI RECOMMENDS: CONTINUE                                        │
│  Reasoning: Strong margin (45%), good market growth (12%)       │
│                                                                  │
│  ┌──────────┬──────────┬──────────────┬──────────┐             │
│  │ CONTINUE │ REJECT   │ SUPPLEMENT   │ APPROVE  │             │
│  │ [Blue]   │ [Red]    │ [Orange]     │ [Green]  │             │
│  └──────────┴──────────┴──────────────┴──────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

**Elements:**
- 4 key metrics (AI Score, Hard Rules, Margin, Risk Level)
- Each metric with visual indicator (progress bar, icon, color)
- AI recommendation with reasoning
- 4 action buttons (always visible)

### 2.3 Tab Navigation

```
┌─────────────────────────────────────────────────────────────────┐
│  [Facts] [Analysis] [Cost] [Supply] [Rules] [History]          │
└─────────────────────────────────────────────────────────────────┘
```

**Tabs:**
- **Facts:** Product basic information
- **Analysis:** Market analysis and AI reasoning
- **Cost:** Unit cost, landed cost, margin
- **Supply:** Supplier information and risks
- **Rules:** Hard rules evaluation and AI score breakdown
- **History:** Decision and status change history

### 2.4 Content Area

Each tab shows detailed information relevant to that section.

**Design patterns:**
- Cards for grouped information
- Tables for structured data
- Progress bars for scores
- Badges for status indicators
- Color coding for pass/fail/warning

---

## 3. Color System

### 3.1 Status Colors

| Status | Color | Usage |
|--------|-------|-------|
| **Success** | Green (#52c41a) | Pass, Continue, Approved |
| **Warning** | Orange (#faad14) | Data Missing, Supplement |
| **Danger** | Red (#f5222d) | Fail, Reject, Risk High |
| **Info** | Blue (#1890ff) | Active, Current |
| **Neutral** | Gray (#8c8c8c) | Inactive, Historical |

### 3.2 Risk Level Colors

| Risk Level | Color | Indicator |
|------------|-------|-----------|
| **Low** | Green | ✅ |
| **Medium** | Orange | ⚠️ |
| **High** | Red | ❌ |

### 3.3 Decision Button Colors

| Button | Color | Hover | Active |
|--------|-------|-------|--------|
| **Continue** | Blue (#1890ff) | #40a9ff | #096dd9 |
| **Reject** | Red (#f5222d) | #ff4d4f | #cf1322 |
| **Supplement** | Orange (#faad14) | #ffc53d | #d48806 |
| **Approve** | Green (#52c41a) | #73d13d | #389e0d |

---

## 4. Typography

### 4.1 Font Sizes

| Element | Size | Weight |
|---------|------|--------|
| Product Name | 24px | 600 |
| Section Headers | 18px | 600 |
| Metric Values | 20px | 600 |
| Body Text | 14px | 400 |
| Labels | 12px | 400 |
| Badges | 12px | 500 |

### 4.2 Line Height

- Body text: 1.5
- Headers: 1.3
- Labels: 1.2

---

## 5. Iconography

### 5.1 Key Icons

| Icon | Usage |
|------|-------|
| 📊 | AI Score |
| ✅ | Hard Rule Pass |
| ❌ | Hard Rule Fail |
| ⚠️ | Warning / Data Missing |
| 📈 | Growth / Positive |
| 📉 | Decline / Negative |
| ⏱️ | Lead Time |
| 💰 | Cost / Margin |
| 🏭 | Supplier |
| 📦 | Product |
| 📋 | History |
| ⚖️ | Decision |

---

## 6. Interaction Patterns

### 6.1 Loading States

| State | UI | Duration |
|-------|-----|----------|
| **Initial Load** | Skeleton loader | < 2s |
| **Tab Switch** | Content fade | < 500ms |
| **Decision Submit** | Button loading spinner | < 3s |
| **API Error** | Error message + retry | N/A |

### 6.2 Empty States

| Section | Empty State | Action |
|---------|-------------|--------|
| **Analysis** | "No analysis available" | [Run Analysis] |
| **Cost** | "No cost data" | [Add Cost] |
| **Supply** | "No supplier data" | [Add Supplier] |
| **History** | "No history" | - |

### 6.3 Decision Modal

When user clicks an action button:

```
┌─────────────────────────────────────────┐
│  Confirm Decision                       │
│                                         │
│  You are about to: CONTINUE             │
│                                         │
│  Reasoning: * (required)                │
│  ┌───────────────────────────────────┐  │
│  │ [Text area]                       │  │
│  └───────────────────────────────────┘  │
│                                         │
│  Evidence captured:                     │
│  • AI Score: 78/100                     │
│  • Margin: 45%                          │
│  • Hard Rules: 4/5 PASS                 │
│  • Risk Level: Medium                   │
│                                         │
│  Next Action: Create Product Master     │
│                                         │
│         [Cancel]    [Confirm Decision]   │
└─────────────────────────────────────────┘
```

---

## 7. Accessibility

### 7.1 Color Contrast

| Element | Foreground | Background | Contrast Ratio |
|---------|------------|------------|----------------|
| Body Text | #000000 | #ffffff | 21:1 |
| Links | #1890ff | #ffffff | 3.6:1 |
| Success Badge | #ffffff | #52c41a | 3.2:1 |
| Danger Badge | #ffffff | #f5222d | 3.4:1 |

### 7.2 Keyboard Navigation

| Key | Action |
|-----|--------|
| Tab | Navigate between elements |
| Enter | Activate focused element |
| Esc | Close modal |
| Arrow Keys | Navigate tabs |

### 7.3 Screen Reader Support

- ARIA labels for all icons
- ARIA roles for tabs and tab panels
- Live region for decision confirmation
- Alt text for all images

---

## 8. Responsive Design

### 8.1 Breakpoints

| Breakpoint | Width | Layout |
|------------|-------|--------|
| **Desktop** | > 1200px | Full layout, all sections |
| **Tablet** | 768-1200px | Stacked sections, 2-column metrics |
| **Mobile** | < 768px | Single column, collapsible sections |

### 8.2 Mobile Adaptations

- Decision summary: 2x2 grid instead of 1x4
- Tabs: Horizontal scroll
- Action buttons: Full-width, stacked
- Modals: Full-screen

---

## 9. Animation & Transitions

### 9.1 Timing

| Transition | Duration | Easing |
|------------|----------|--------|
| Tab switch | 200ms | ease-in-out |
| Button hover | 100ms | ease |
| Modal open | 200ms | cubic-bezier(0.34, 1.56, 0.64, 1) |
| Loading spinner | 1s | linear (infinite) |

### 9.2 Reduced Motion

Respect `prefers-reduced-motion`:
- Disable all animations
- Instant transitions
- No loading spinner (use text indicator)

---

## 10. Component Library

### 10.1 Required Components

| Component | Usage |
|-----------|-------|
| Card | Group related information |
| Badge | Status indicators |
| Button | Action buttons |
| Progress | AI score visualization |
| Tabs | Section navigation |
| Table | Structured data |
| Modal | Decision confirmation |
| Alert | Warnings and errors |
| Skeleton | Loading states |
| Tooltip | Additional context |

---

## 11. Error States

### 11.1 API Error

```
┌─────────────────────────────────────────┐
│  ⚠️ Failed to Load Data                 │
│                                         │
│  Error: Network error                   │
│                                         │
│  [Retry]                                │
└─────────────────────────────────────────┘
```

### 11.2 Permission Error

```
┌─────────────────────────────────────────┐
│  🔒 Access Denied                       │
│                                         │
│  You need permission to view this       │
│  product. Contact your admin.           │
│                                         │
│  [Back to Workbench]                    │
└─────────────────────────────────────────┘
```

### 11.3 Data Missing

```
┌─────────────────────────────────────────┐
│  📊 Data Missing                        │
│                                         │
│  Market analysis not available.         │
│  This affects AI score accuracy.        │
│                                         │
│  [Run Analysis]                         │
└─────────────────────────────────────────┘
```

---

## 12. Success States

### 12.1 Decision Recorded

```
┌─────────────────────────────────────────┐
│  ✅ Decision Recorded                   │
│                                         │
│  Product: Water Bottle 500ml            │
│  Decision: Continue                     │
│  Reasoning: Strong margin, good market  │
│                                         │
│  Next Step: Create Product Master       │
│                                         │
│  [View History]    [Close]              │
└─────────────────────────────────────────┘
```

---

## 13. Design Checklist

- [ ] 30-second decision rule met
- [ ] All key metrics visible above the fold
- [ ] Action buttons always visible
- [ ] Color contrast meets WCAG AA
- [ ] Keyboard navigation works
- [ ] Screen reader support added
- [ ] Mobile responsive
- [ ] Loading states defined
- [ ] Empty states defined
- [ ] Error states defined
- [ ] Success states defined
- [ ] Animations respect reduced motion
- [ ] Decision modal captures reasoning
- [ ] Evidence shown in decision modal

---

## 14. Mockup Wireframe

```
┌─────────────────────────────────────────────────────────────────┐
│  ← Back to Workbench                                            │
│                                                                  │
│  Water Bottle 500ml                    [Candidate] [AI: 78/100] │
│  SKU: ABC-123                   Last Updated: 2026-09-29 10:00  │
├─────────────────────────────────────────────────────────────────┤
│  DECISION SUMMARY                                               │
│                                                                  │
│  ┌──────────┬──────────┬──────────┬──────────┐                 │
│  │ 📊 78/100│ ✅ 4/5  │ 💰 45%  │ ⚠️ MEDIUM│                 │
│  │ AI Score │ Rules   │ Margin  │ Risk     │                 │
│  └──────────┴──────────┴──────────┴──────────┘                 │
│                                                                  │
│  AI RECOMMENDS: CONTINUE                                        │
│  Reasoning: Strong margin (45%), good market growth (12%)       │
│                                                                  │
│  [CONTINUE]  [REJECT]  [SUPPLEMENT DATA]  [APPROVE]            │
├─────────────────────────────────────────────────────────────────┤
│  [Facts] [Analysis] [Cost] [Supply] [Rules] [History]         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─── FACTS ──────────────────────────────────────────────┐   │
│  │  Product: Water Bottle 500ml                            │   │
│  │  Category: Outdoor Hydration                            │   │
│  │  Price: ¥89.00                                          │   │
│  │  Weight: 250g                                           │   │
│  │  Origin: Zhejiang, CN                                   │   │
│  │  Supplier: ABC Manufacturing                            │   │
│  │  Lead Time: 15 days                                     │   │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

*Document Owner: UX Designer*  
*Last Updated: 2026-09-29*
