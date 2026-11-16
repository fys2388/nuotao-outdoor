# WC 完整 HTML 描述 Prompt

> **对应 SOP**：`wc-ai-content-sop-v1.0.md` Phase ⑤
> **WC 字段**：`description`
> **长度**：600-2500 词
> **格式**：HTML（含 `<h2>/<h3>/<p>/<ul>/<img>`）
> **语言**：英文

---

## 用途

WooCommerce 产品详细描述，是产品页的主体内容。这是 SEO 和内容转化率的核心。

## 7 模块结构

| 模块 | 内容 | 字数 |
|---|---|---|
| 1. Hero | 产品名 + 一句话承诺 | 100-150 词 |
| 2. Problem | 痛点描述 | 100 词 |
| 3. Solution | 我们的解法（卖点列表） | 200-300 词 |
| 4. Visual Proof | 图片网格 | - |
| 5. Specs | 规格表 | 50 词 |
| 6. Social Proof | 信任背书 | 150 词 |
| 7. FAQ + CTA | 常见问题 + 行动号召 | 200 词 |

---

## Prompt 模板

```markdown
# Role
You are a senior direct-to-consumer copywriter for Nuotao Outdoor.
You write for [TARGET MARKET] with a direct, data-backed, no-hype voice.

# Product Context
- 1688 Source: [URL]
- Real product specs: [SPEC YAML]
- Brand voice: direct, warm, data-backed, no hype
- Buyer persona: [PERSONA YAML]
- Price point: $[PRICE]
- Top competitors: [3 brand names]
- Certifications: [SGS/CE/etc]

# Hard Constraints
- Target language: English (US)
- Total words: 600-2500
- HTML structure required (h2/h3/p/ul/table/img)
- NO medical/health cure claims
- NO "Best", "No.1", "Free", "Guaranteed", "Risk-Free", "Perfect"
- NO competitor brand names
- NO Chinese characters
- Must be HTML-valid (W3C)
- Must align with FTC / ASA / UK CMA advertising rules
- All facts must match 1688 spec (no exaggeration)

# Output Format (strict JSON)
{
  "description_html": "<h2>...</h2><p>...</p>...",
  "word_count": 0,
  "modules": {
    "hero": "100-150 words",
    "problem": "100 words",
    "solution": "200-300 words",
    "visual_proof": "image grid",
    "specs": "table",
    "social_proof": "150 words",
    "faq_cta": "200 words"
  },
  "compliance_notes": ["..."]
}
```

---

## HTML 模板参考

```html
<!-- Module 1: Hero -->
<h2>[Product Name] - [One-line promise]</h2>
<p>[Story hook: who it's for, what problem it solves]</p>

<!-- Module 2: The Problem -->
<h2>Meet the Problem We Fixed</h2>
<p>[Agitate pain points with specifics]</p>

<!-- Module 3: Our Solution -->
<h2>Why [Product] is Different</h2>
<ul>
  <li><strong>[USP 1]:</strong> [Benefit + spec]</li>
  <li><strong>[USP 2]:</strong> [Benefit + spec]</li>
  <li><strong>[USP 3]:</strong> [Benefit + spec]</li>
</ul>

<!-- Module 4: Visual Proof -->
<div class="product-images">
  <img src="..." alt="..." />
</div>

<!-- Module 5: Specs -->
<h2>Product Specifications</h2>
<table>
  <tr><td>Material</td><td>[VALUE]</td></tr>
  <tr><td>Dimensions</td><td>[VALUE]</td></tr>
  <tr><td>Certification</td><td>[VALUE]</td></tr>
</table>

<!-- Module 6: Social Proof -->
<h2>Trusted by [N] customers</h2>
<p>[Testimonials / ratings / certifications]</p>

<!-- Module 7: FAQ + CTA -->
<h2>Frequently Asked Questions</h2>
<details><summary>Q1</summary><p>A1</p></details>

<div class="cta-block">
  <h3>Ready to elevate your [USE CASE]?</h3>
  <button>Add to Cart</button>
  <p>Free shipping · 30-day returns · 2-year warranty</p>
</div>
```

---

## 验收 Checklist

- [ ] 600-2500 词
- [ ] 7 个模块完整
- [ ] HTML 结构完整（W3C 校验通过）
- [ ] 英文（US 拼写）
- [ ] 无禁词
- [ ] 无中文
- [ ] 卖点与 1688 实际参数一致
- [ ] 图片 alt 文本已填充
- [ ] 关键词密度 1.5-2.5%
- [ ] CTA 明确
- [ ] 符合 FTC/ASA/UK CMA

---

## 版本记录

- v1.0 (2026-09-27)：初版
