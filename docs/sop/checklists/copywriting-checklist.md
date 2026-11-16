# 文案验收 Checklist

> **对应 SOP**：`wc-ai-content-sop-v1.0.md` Phase ⑤
> **对应闸口**：C3 文案审批（`status = approved`）
> **使用场景**：文案生成后必须过一遍

---

## 字段级验收

### 1. `name`（产品标题）

- [ ] 60-120 字符
- [ ] 包含品牌名（Nuotao）
- [ ] 包含核心关键词
- [ ] 包含 1 个关键特性
- [ ] 英文（US 拼写）
- [ ] 无禁词
- [ ] 无中文
- [ ] 无竞品品牌名
- [ ] 卖点与 1688 实际参数一致

### 2. `short_description`（短描述）

- [ ] 1-2 句话
- [ ] ≤ 160 字符
- [ ] 包含 1 个 USP
- [ ] 包含 1 个证明点（规格/认证/数据）
- [ ] 英文（US 拼写）
- [ ] 无禁词
- [ ] 无中文
- [ ] 卖点与 1688 实际参数一致

### 3. `description`（HTML 详情）

- [ ] 600-2500 词
- [ ] 7 个模块完整（Hero/Problem/Solution/Visual/Specs/Social/FAQ+CTA）
- [ ] HTML 结构完整（W3C 校验通过）
- [ ] 英文（US 拼写）
- [ ] 无禁词
- [ ] 无中文
- [ ] 卖点与 1688 实际参数一致
- [ ] 图片 alt 文本已填充
- [ ] 关键词密度 1.5-2.5%
- [ ] CTA 明确
- [ ] 符合 FTC/ASA/UK CMA

### 4. `meta_title` + `meta_description`

- [ ] meta_title ≤ 60 字符
- [ ] meta_description ≤ 160 字符
- [ ] meta_description 包含 CTA
- [ ] 核心关键词在 title + description 中
- [ ] 英文（US 拼写）
- [ ] 无禁词
- [ ] 无中文

### 5. `slug`（URL slug）

- [ ] kebab-case
- [ ] 包含核心关键词
- [ ] 无中文
- [ ] 无特殊字符（除 `-`）
- [ ] 长度合理（≤ 100 字符）

### 6. `tags`（标签）

- [ ] 5-10 个
- [ ] 英文
- [ ] 包含核心关键词
- [ ] 包含相关长尾词
- [ ] 无禁词
- [ ] 无中文

### 7. `categories`（分类）

- [ ] 已映射到 WC 真实 term id
- [ ] 中文分类名不直接使用
- [ ] 使用 `map_category_to_wc()` 函数

---

## 禁词检查

| 禁词 | 检查 |
|---|---|
| Best / No.1 / #1 | [ ] 无 |
| Free（无条件） | [ ] 无 |
| Guaranteed / Risk-Free | [ ] 无 |
| Perfect / Ultimate | [ ] 无 |
| Cure / Heal | [ ] 无 |
| Made in USA（如不是） | [ ] 无 |
| 中文 | [ ] 无 |

---

## 品牌口径检查

- [ ] 语气：direct, data-backed, no hype
- [ ] 调性：warm, professional
- [ ] 无夸大
- [ ] 无医疗宣称
- [ ] 无竞品提及
- [ ] 卖点与 1688 实际参数一致

---

## 文化敏感性检查（按市场）

### US
- [ ] 无冒犯性文化引用
- [ ] 无过度宗教元素
- [ ] 无过度政治元素

### EU
- [ ] GDPR 合规
- [ ] 无敏感民族/宗教元素
- [ ] 符合当地广告法规

### UK
- [ ] 英式拼写
- [ ] 无美式文化过度引用
- [ ] 符合 UK CMA

### UAE/SA
- [ ] 无过度露肤元素
- [ ] 无宗教敏感元素
- [ ] 符合伊斯兰文化规范

---

## HTML 有效性检查

- [ ] W3C 校验通过
- [ ] 标签正确闭合
- [ ] 无嵌套错误
- [ ] 无废弃标签
- [ ] 图片有 alt 文本
- [ ] 表格有 thead/tbody

---

## 通过后动作

1. 标记为 `pending_review`
2. 触发 L1 合规审核（`audit/compliance-audit-prompt.md`）
3. L1 verdict = PASS → 提交 L2 人工复核
4. L2 复核通过 → `status = approved`
5. 进入 Phase ⑥ 三层合规审核

---

## 版本记录

- v1.0 (2026-09-27)：初版
