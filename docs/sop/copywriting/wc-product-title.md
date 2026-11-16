# WC 产品标题 Prompt

> **对应 SOP**：`wc-ai-content-sop-v1.0.md` Phase ⑤
> **WC 字段**：`name`
> **长度**：60-120 字符
> **语言**：英文（US 优先）
> **对应审批闸口**：C3（文案审批，`status = approved`）

---

## 用途

WooCommerce 产品标题。这是产品页的核心 SEO 入口，也是 Google Search 结果展示的标题。

## 公式

```
[Brand] + [Core Keyword] + [Key Feature] + [Material/Spec] +
[Use Case] + [Size/Color] + [Target]
```

---

## Prompt 模板（Claude / GPT）

```markdown
# Role
You are a senior cross-border e-commerce copywriter with 10+ years 
experience on DTC brands. You write for Nuotao Outdoor, selling 
to [TARGET MARKET: US/EU/UK/AU].

# Product Context
- 1688 Source: [URL]
- Real product specs: [spec YAML]
- Brand voice: direct, data-backed, no hype
- Price point: $[PRICE]

# Hard Constraints
- 60-120 characters
- English (US)
- NO "Best", "No.1", "Free", "Guaranteed", "Risk-Free"
- NO competitor brand names
- Must include: brand + core keyword + 1 key feature
- Must be factual (no false claims)

# Output Format (strict JSON)
{
  "name": "...",
  "character_count": 0,
  "keywords_used": ["keyword1", "keyword2"],
  "notes": "any compliance notes"
}
```

---

## 示例

**输入**：
- Product: 折叠露营椅
- Brand: Nuotao
- Core Feature: 45 秒快速折叠
- Material: 600D 牛津布
- Weight: 1.2kg
- Price: $49.99
- Market: US

**输出**：
```json
{
  "name": "Nuotao Portable Folding Camp Chair 45-Second Setup 600D Oxford 1.2kg Lightweight",
  "character_count": 82,
  "keywords_used": ["folding camp chair", "portable camping chair", "lightweight outdoor"],
  "notes": "All facts verified from 1688 spec"
}
```

---

## 禁词清单

| 禁词 | 原因 |
|---|---|
| Best / No.1 / #1 | FTC 违规 |
| Free | 需要明确条件 |
| Guaranteed / Risk-Free | FTC 违规 |
| Perfect / Ultimate | 绝对化用语 |
| Cure / Heal | 医疗宣称 |
| Free Shipping（无条件下） | 必须有条件 |
| Made in USA（如不是） | 产地虚假 |

---

## 验收 Checklist

- [ ] 60-120 字符
- [ ] 包含品牌名（Nuotao）
- [ ] 包含核心关键词
- [ ] 包含 1 个关键特性
- [ ] 英文（US 拼写）
- [ ] 无禁词
- [ ] 无中文
- [ ] 无竞品品牌名
- [ ] 卖点与 1688 实际参数一致

---

## 版本记录

- v1.0 (2026-09-27)：初版
