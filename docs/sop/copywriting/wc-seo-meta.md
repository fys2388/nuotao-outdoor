# WC SEO Meta Prompt

> **对应 SOP**：`wc-ai-content-sop-v1.0.md` Phase ⑤
> **WC 字段**：`meta_title`, `meta_description`, `slug`
> **语言**：英文

---

## 用途

SEO 元数据，直接影响 Google 搜索结果展示和自然搜索排名。

## 字段规格

| 字段 | 长度 | 用途 |
|---|---|---|
| `meta_title` | ≤ 60 字符 | Google Search 结果标题 |
| `meta_description` | ≤ 160 字符 + CTA | Google Search 结果描述 |
| `slug` | kebab-case，含核心 KW | URL 结构 |

---

## Prompt 模板

```markdown
# Role
You are an SEO specialist for DTC brands.

# Product Context
- Product: [PRODUCT]
- Core keyword: [CORE_KW]
- Secondary keywords: [KW1, KW2, KW3]
- Price: $[PRICE]
- Market: [TARGET MARKET]
- Brand: Nuotao Outdoor

# Hard Constraints
- meta_title ≤ 60 chars
- meta_description ≤ 160 chars + CTA
- slug: kebab-case, includes core keyword
- English (US)
- NO hype words (Best, No.1, Free, Guaranteed)
- NO Chinese
- Must be factual
- Character limits strictly enforced

# Output Format (strict JSON)
{
  "meta_title": "...",
  "meta_title_chars": 0,
  "meta_description": "...",
  "meta_description_chars": 0,
  "slug": "kebab-case-with-keyword",
  "primary_keyword": "...",
  "keyword_density_notes": "..."
}
```

---

## 示例

**输入**：
- Product: TPE Yoga Mat 6mm
- Core KW: "eco-friendly yoga mat"
- Secondary KW: "non-slip yoga mat", "tpe yoga mat", "alignment yoga mat"
- Price: $39.99
- Market: US

**输出**：
```json
{
  "meta_title": "Eco-Friendly Yoga Mat 6mm - Non-Slip TPE | Nuotao",
  "meta_title_chars": 51,
  "meta_description": "Premium 6mm TPE yoga mat with alignment lines. Non-slip, joint-friendly, SGS-certified. Free shipping & 30-day returns.",
  "meta_description_chars": 129,
  "slug": "eco-friendly-yoga-mat-6mm-non-slip-tpe",
  "primary_keyword": "eco-friendly yoga mat",
  "keyword_density_notes": "Core KW in title + description + slug; secondary KWs distributed in description"
}
```

---

## meta_title 公式

```
[Core Keyword] - [USP] | [Brand]
```

**示例**：
- `Eco-Friendly Yoga Mat 6mm - Non-Slip TPE | Nuotao`
- `Portable Folding Camp Chair - 45s Setup | Nuotao`
- `Headlamp 1000LM - 40h Battery | Nuotao`

---

## meta_description 公式

```
[Benefit-led hook]. [USP]. [Trust signal]. Shop [Product] today.
```

**示例**：
```
Premium 6mm TPE yoga mat with alignment lines. Non-slip, 
joint-friendly, SGS-certified. Free shipping & 30-day returns.
```

---

## slug 公式

```
kebab-case-[core-keyword]-[size]-[color]
```

**示例**：
- `eco-friendly-yoga-mat-6mm-non-slip-tpe`
- `portable-folding-camp-chair-45s-setup`
- `headlamp-1000lm-40h-battery-black`

---

## 验收 Checklist

- [ ] meta_title ≤ 60 字符
- [ ] meta_description ≤ 160 字符
- [ ] meta_description 包含 CTA
- [ ] slug 是 kebab-case
- [ ] slug 包含核心关键词
- [ ] 英文（US 拼写）
- [ ] 无禁词
- [ ] 无中文
- [ ] 核心关键词在 title + description + slug 中

---

## 版本记录

- v1.0 (2026-09-27)：初版
