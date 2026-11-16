# 推送前 Checklist（6 道拦截）

> **对应 SOP**：`wc-ai-content-sop-v1.0.md` Phase ⑦
> **对应代码**：`backend/app/services/listing_gate.py`（当前在 hotfix-listing-gate/ 目录）
> **对应工作流**：`docs/selection_to_woocommerce_operation_workflow.md` 阶段 D2

---

## 用途

在推送到 WooCommerce 之前，执行 6 道拦截检查。任一阻断项未通过 → 终止推送。

## 6 道拦截

### 拦截 1：价格拦截（BUG-27）

**规则**：`regular_price ≤ 0` → BLOCK

```python
if price is None or price <= 0:
    return {
        "success": False,
        "action": "blocked",
        "error": "缺少有效零售价，禁止以 0 元价格推送到 WooCommerce"
    }
```

**Checklist**：
- [ ] `regular_price > 0`
- [ ] `sale_price`（如有）< `regular_price`
- [ ] 价格与定价模型一致
- [ ] 价格符合目标市场定位

---

### 拦截 2：中文拦截

**规则**：`has_cjk(description) and not has_approved_english(localization)` → BLOCK

```python
if has_cjk(description) and not has_approved_english(localization):
    return {
        "success": False,
        "action": "blocked",
        "error": "缺少已审核的英文商品文案"
    }
```

**Checklist**：
- [ ] `name` 无中文
- [ ] `short_description` 无中文
- [ ] `description` 无中文
- [ ] `meta_title` 无中文
- [ ] `meta_description` 无中文
- [ ] `slug` 无中文
- [ ] 已通过 `has_cjk()` 检查
- [ ] 英文文案已通过审批（`status = approved`）

---

### 拦截 3：分类映射

**规则**：中文名直接推 → WC 建成 "Uncategorized"，必须映射

```python
wc_product["categories"] = map_category_to_wc(title, category)
```

**Checklist**：
- [ ] 分类已映射到 WC term id
- [ ] 使用 `map_category_to_wc()` 函数
- [ ] 分类名英文
- [ ] 分类在 WC 中存在

---

### 拦截 4：V3.0 选品闸门

**规则**：`check_product_push_gate()` 结果

```python
gate = await check_product_push_gate(db, product_id, workspace_id, force)
if gate.get("blocked"):
    raise HTTPException(422, "V3.0 选品闸门阻断")
if gate.get("force_required"):
    raise HTTPException(409, "需人工复核确认后放行")
```

**Checklist**：
- [ ] V3.0 选品闸门通过
- [ ] 毛利率 ≥ 35%
- [ ] 认证合规（如有）
- [ ] 品牌授权（如有）
- [ ] 品类黑名单检查通过
- [ ] 目标市场已选
- [ ] 闸口①选品决策已放行

---

### 拦截 5：图片 URL 可访问性

**规则**：任一图片 URL 不可访问 → BLOCK

```python
for img in images:
    if HEAD(img.src).status != 200:
        return {
            "success": False,
            "action": "blocked",
            "error": f"图片不可访问: {img.src}"
        }
```

**Checklist**：
- [ ] 所有图片 URL 可访问（HTTP 200）
- [ ] 所有图片已通过闸口④图片审批
- [ ] 图片分辨率达标
- [ ] 图片文件大小 ≤ 500KB
- [ ] 图片格式为 JPG/WebP

---

### 拦截 6：HTML 有效性

**规则**：HTML 无效 → BLOCK

```python
if not html_validate(description):
    return {
        "success": False,
        "action": "blocked",
        "error": "description HTML 无效"
    }
```

**Checklist**：
- [ ] W3C 校验通过
- [ ] 标签正确闭合
- [ ] 无嵌套错误
- [ ] 图片有 alt 文本
- [ ] 表格有 thead/tbody

---

## 整体推送前 Checklist

### 字段完整性

- [ ] `name` 已填
- [ ] `sku` 已填（唯一）
- [ ] `type = "simple"`
- [ ] `status = "publish" | "draft"`
- [ ] `description` 已填
- [ ] `short_description` 已填
- [ ] `regular_price` > 0
- [ ] `weight` 已填
- [ ] `dimensions` 已填
- [ ] `stock_quantity` ≥ 0
- [ ] `manage_stock = true`
- [ ] `stock_status` 已填
- [ ] `categories` 已映射
- [ ] `tags` 已填
- [ ] `images` 已填
- [ ] `meta_title` 已填
- [ ] `meta_description` 已填
- [ ] `slug` 已填

### 审批状态

- [ ] 闸口①选品决策已放行
- [ ] 闸口③文案审批已放行（`status = approved`）
- [ ] 闸口④图片审批已放行
- [ ] L1 合规审核 PASS
- [ ] L2 人工复核通过（如需）
- [ ] L3 法务终审通过（高风险品类）

### 6 道拦截

- [ ] 拦截 1：价格拦截通过
- [ ] 拦截 2：中文拦截通过
- [ ] 拦截 3：分类映射通过
- [ ] 拦截 4：V3.0 选品闸门通过
- [ ] 拦截 5：图片 URL 可访问性通过
- [ ] 拦截 6：HTML 有效性通过

### 闸口②上架确认

- [ ] `POST /product-pipeline/confirm-list` 待执行

---

## 通过后动作

1. 触发 `POST /product-pipeline/confirm-list`
2. 闸口②人工确认上架
3. 触发 `push_product_to_woocommerce`
4. 回读验证
5. 写入 `ai_agent_runs` 表

---

## 版本记录

- v1.0 (2026-09-27)：初版
