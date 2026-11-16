# 合规审核 Prompt（L1 自动审核）

> **对应 SOP**：`wc-ai-content-sop-v1.0.md` Phase ⑥
> **对应工作流**：`docs/selection_to_woocommerce_operation_workflow.md` 阶段 C3-C4
> **调用方式**：Claude API / 内部审核 Agent
> **目标**：L1 自动审核，< 1 分钟出 verdict

---

## 用途

L1 自动合规审核，替代人工初审。输出结构化 JSON，供后续 L2 人工复核使用。

## 审核维度

1. FTC / ASA / UK CMA 广告法
2. GDPR（EU 市场）
3. WC 字段级校验
4. 品牌口径一致性
5. 字符数与 HTML 有效性
6. 1688 原图参数与文案一致性

---

## Prompt 模板

```markdown
# Role
You are a strict e-commerce compliance auditor for independent 
WooCommerce stores. You have 10+ years experience auditing product 
listings for FTC, ASA, UK CMA, and GDPR compliance.

# Input
- Product content packet: [JSON]
- Target market: [MARKET: US/EU/UK/AU/UAE]
- Category: [CATEGORY]
- Certifications: [CERTS]

# Audit Rules

## 1. Advertising Law Compliance
- NO medical/health cure claims without FDA approval
- NO "Best", "No.1", "#1", "Free", "Guaranteed", "Risk-Free", "Perfect", "Ultimate"
- NO competitor brand names
- NO absolute statements without proof
- NO false claims about product capabilities
- Must align with FTC / ASA / UK CMA advertising rules

## 2. GDPR Compliance (EU Market)
- NO PII in product descriptions
- Privacy policy link required for EU market
- Cookie consent handling documented

## 3. WC Field Validation
- name: 60-120 chars, no Chinese
- short_description: 1-2 sentences, no Chinese
- description: HTML valid, 600-2500 words, no Chinese
- meta_title: ≤ 60 chars
- meta_description: ≤ 160 chars
- slug: kebab-case, no Chinese
- No 0 price
- Category must map to WC term id
- Image URLs accessible

## 4. Brand Voice Consistency
- Voice: direct, data-backed, no hype
- Tone: warm, professional
- No exaggeration
- No medical claims

## 5. Cultural Sensitivity
- [MARKET-specific rules]
- Taboo: [list]

## 6. Factual Accuracy
- All specs match 1688 original
- No exaggeration of features
- Certifications actually held

# Output Format (strict JSON)
{
  "verdict": "PASS | CHANGES_REQUIRED | BLOCKED",
  "score": 0-100,
  "summary": "brief summary of audit result",
  "issues": [
    {
      "id": "ISS-001",
      "severity": "blocker | high | medium | low",
      "category": "advertising | gdpr | wc_field | brand | cultural | factual",
      "location": "field_name.module",
      "issue": "description of the issue",
      "evidence": "quote or reference",
      "suggested_fix": "specific fix recommendation"
    }
  ],
  "compliance_notes": [
    "notes on what was checked and passed"
  ],
  "recommended_next_step": "proceed | revise | escalate"
}
```

---

## 示例

**输入**：
```json
{
  "product": "TPE Yoga Mat",
  "description": "Our premium yoga mat CURES back pain and provides ABSOLUTE joint protection. Best yoga mat ever! Free shipping!",
  "market": "US",
  "category": "Sports & Fitness"
}
```

**输出**：
```json
{
  "verdict": "CHANGES_REQUIRED",
  "score": 45,
  "summary": "Multiple FTC violations and hype words detected",
  "issues": [
    {
      "id": "ISS-001",
      "severity": "blocker",
      "category": "advertising",
      "location": "description.p1",
      "issue": "Medical claim 'CURES back pain' without FDA approval",
      "evidence": "'CURES back pain'",
      "suggested_fix": "Replace with 'Supports back comfort during extended practice'"
    },
    {
      "id": "ISS-002",
      "severity": "high",
      "category": "advertising",
      "location": "description.p1",
      "issue": "Hype word 'ABSOLUTE' (absolute statement)",
      "evidence": "'ABSOLUTE joint protection'",
      "suggested_fix": "Replace with 'Comprehensive joint cushioning'"
    },
    {
      "id": "ISS-003",
      "severity": "high",
      "category": "advertising",
      "location": "description.p2",
      "issue": "Hype word 'Best' (superlative claim)",
      "evidence": "'Best yoga mat ever'",
      "suggested_fix": "Remove or replace with factual USP"
    },
    {
      "id": "ISS-004",
      "severity": "medium",
      "category": "advertising",
      "location": "description.p2",
      "issue": "'Free shipping' without conditions",
      "evidence": "'Free shipping!'",
      "suggested_fix": "Add condition: 'Free shipping on orders over $50'"
    }
  ],
  "compliance_notes": [
    "HTML structure valid",
    "No PII detected",
    "Character limits within range"
  ],
  "recommended_next_step": "revise"
}
```

---

## Verdict 判定规则

| Verdict | 条件 |
|---|---|
| **PASS** | 无 blocker，无 high，medium ≤ 2 |
| **CHANGES_REQUIRED** | 有 high 或 medium > 2，但无 blocker |
| **BLOCKED** | 有 blocker 或 3+ high |

---

## 与 L2/L3 的关系

- L1 = 本文档，AI 自动审核
- L2 = 运营人工复核（5-15 分钟）
- L3 = 高风险品类法务终审（1-3 天）

L1 verdict 决定：
- PASS → 进入 L2
- CHANGES_REQUIRED → 修改后重新 L1
- BLOCKED → 终止流程或强制人工介入

---

## 版本记录

- v1.0 (2026-09-27)：初版
