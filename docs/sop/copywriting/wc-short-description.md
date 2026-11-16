# WC 短描述 Prompt

> **对应 SOP**：`wc-ai-content-sop-v1.0.md` Phase ⑤
> **WC 字段**：`short_description`
> **长度**：1-2 句话，≤ 160 字符
> **语言**：英文

---

## 用途

WooCommerce 产品短描述。显示在产品列表页、搜索结果、社交分享预览。这是买家对产品的第一印象。

## 公式（PAS 结构压缩版）

```
[SOLUTION + KEY USP]. Perfect for [USE CASE] - [SPEC PROOF].
```

---

## Prompt 模板

```markdown
# Role
Senior DTC copywriter for Nuotao Outdoor.

# Product Context
- Product: [PRODUCT]
- 1688 specs: [SPEC YAML]
- Brand voice: direct, data-backed, no hype
- Market: [TARGET MARKET]

# Hard Constraints
- 1-2 sentences, ≤ 160 characters
- English (US)
- MUST include: 1 USP + 1 proof point
- NO hype words (Best, #1, Perfect, Ultimate)
- NO competitor mentions
- NO false claims
- NO Chinese

# Output Format (strict JSON)
{
  "short_description": "...",
  "character_count": 0,
  "usp": "the single USP highlighted",
  "proof_point": "the factual proof included"
}
```

---

## 示例

**输入**：
- Product: TPE Yoga Mat 6mm
- Specs: Non-slip, SGS certified, alignment lines
- Price: $39.99
- Market: US

**输出**：
```json
{
  "short_description": "Premium 6mm TPE yoga mat with alignment lines - joint-friendly cushioning for daily practice. SGS-certified eco-friendly material.",
  "character_count": 137,
  "usp": "alignment lines + joint-friendly cushioning",
  "proof_point": "SGS-certified, 6mm TPE"
}
```

---

## 验收 Checklist

- [ ] 1-2 句话
- [ ] ≤ 160 字符
- [ ] 包含 1 个 USP
- [ ] 包含 1 个证明点（规格/认证/数据）
- [ ] 英文
- [ ] 无禁词
- [ ] 无中文
- [ ] 卖点与 1688 实际参数一致

---

## 版本记录

- v1.0 (2026-09-27)：初版
