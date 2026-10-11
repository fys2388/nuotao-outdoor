# 系统问题修复记录 - 2026-10-11

## 概述

本文档记录了产品上架闭环检查中发现的4个系统问题及其修复方案。

---

## 问题1: 货币转换缺失

### 问题描述
成本快照的 currency 为 "CNY" 时，系统不会自动转换为 USD，导致闸门检查失败。

**原因**: `pricing_policy.py` 中的 `landed_cost_or_estimate` 函数直接使用 `cost_row.total_landed_cost`，没有考虑货币转换。

### 修复方案

**文件**: `backend/app/services/pricing_policy.py`

**修改内容**: 在 `landed_cost_or_estimate` 函数中添加货币转换逻辑

```python
def landed_cost_or_estimate(purchase_usd, cost_row=None) -> tuple[Decimal | None, str]:
    if cost_row is not None:
        currency = str(getattr(cost_row, "currency", "USD") or "USD").upper()
        landed = _money_amount(getattr(cost_row, "total_landed_cost", None))
        purchase = _money_amount(getattr(cost_row, "purchase_cost", None))
        
        # Convert CNY to USD if needed
        if currency == "CNY" and landed is not None:
            landed = to_usd(landed, "CNY")
        if currency == "CNY" and purchase is not None:
            purchase = to_usd(purchase, "CNY")
        
        if landed and landed > 0 and purchase and purchase > 0:
            return landed, "measured"
    return estimate_landed_cost(purchase_usd), "estimated"
```

### 验证方法
1. 创建成本快照，currency="CNY"
2. 调用 gate-preview 端点
3. 确认不再返回 negative_margin 错误

---

## 问题2: Funnel Stage 不可更新

### 问题描述
`funnel_stage` 字段无法通过 `/full-update` API 更新。

**原因**: `ProductFullUpdateRequest` schema 中没有 `funnel_stage` 字段，`full_update_product` 函数也没有处理该字段。

### 修复方案

**文件**: `backend/app/api/v1/endpoints/product_intelligence.py`

**修改1**: 在 `ProductFullUpdateRequest` 中添加 `funnel_stage` 字段

```python
class ProductFullUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    brand: str | None = None
    price: str | None = None
    status: str | None = None
    funnel_stage: str | None = None  # 新增
    weight_kg: float | None = None
    dimensions: dict[str, Any] | None = None
    tags: list[str] | None = None
    images: list[dict[str, str]] | None = None
    meta: dict[str, Any] | None = None
```

**修改2**: 在 `full_update_product` 函数中处理 `funnel_stage`

```python
if body.funnel_stage is not None:
    product.funnel_stage = body.funnel_stage
    updated_fields.append("funnel_stage")
```

### 验证方法
```bash
PATCH /api/v1/products/{id}/full-update
Body: {"funnel_stage": "published"}
```

确认响应中 `updated_fields` 包含 "funnel_stage"。

---

## 问题3: WordPress Meta 字段不保存

### 问题描述
通过 WordPress REST API 更新的 `_rank_math_*` meta 字段不生效。

**原因**: WordPress REST API 默认不暴露 meta 字段（安全限制）。除非在 WordPress 中注册这些字段为 `show_in_rest`，否则无法通过 API 更新。

### 修复方案

**方案A（推荐）**: 使用 excerpt 作为 fallback

Rank Math 默认使用 excerpt 作为 meta description。通过更新 excerpt 可以间接设置 meta description。

**方案B**: 在 WordPress 中注册 meta 字段

需要创建 WordPress 插件或 mu-plugin，注册 `_rank_math_*` 字段为 `show_in_rest`。

```php
// wp-content/mu-plugins/register-seo-meta.php
add_action('init', function() {
    $fields = [
        '_rank_math_title_web',
        '_rank_math_description_web',
        '_rank_math_focus_keyphrase',
        '_rank_math_robots_noindex_web',
    ];
    
    foreach ($fields as $field) {
        register_post_meta('product', $field, [
            'show_in_rest' => true,
            'single' => true,
            'type' => 'string',
        ]);
    }
});
```

### 当前实现

已在新的 SEO 端点中实现了方案A（使用 excerpt 作为 fallback）。

---

## 问题4: SEO 端点缺失

### 问题描述
Nuotao AI OS 没有管理 Rank Math SEO 设置的端点。

### 修复方案

**文件**: `backend/app/api/v1/endpoints/seo.py`

**新增端点**: `POST /api/v1/seo/wordpress/update`

```python
class WordPressSEOUpdateRequest(BaseModel):
    post_id: int  # WordPress 文章/产品 ID
    seo_title: str | None  # SEO 标题
    meta_description: str | None  # Meta 描述
    focus_keyword: str | None  # 焦点关键词
    noindex: bool = False  # 是否禁用索引
    excerpt: str | None  # 文章摘要（fallback）

@router.post("/wordpress/update")
async def update_wordpress_seo(request: WordPressSEOUpdateRequest):
    # 通过 WordPress REST API 更新 SEO 设置
    ...
```

**需要配置的环境变量**:
- `WP_USERNAME`: WordPress 用户名或邮箱
- `WP_APP_PASSWORD`: WordPress 应用密码
- `WP_SITE_URL`: WordPress 站点 URL

### 验证方法
```bash
POST /api/v1/seo/wordpress/update
Body: {
    "post_id": 2372,
    "seo_title": "Product Title",
    "meta_description": "Product description...",
    "focus_keyword": "focus keyword",
    "noindex": false,
    "excerpt": "Product excerpt..."
}
```

---

## 部署步骤

1. **提交代码变更**
   ```bash
   git add backend/app/services/pricing_policy.py
   git add backend/app/api/v1/endpoints/product_intelligence.py
   git add backend/app/api/v1/endpoints/seo.py
   git commit -m "fix: 修复产品上架闭环的4个系统问题"
   git push
   ```

2. **部署到生产环境**
   ```bash
   # 在服务器上拉取最新代码
   cd /path/to/nuotao-ai-os
   git pull
   
   # 重启后端服务
   systemctl restart nuotao-backend
   # 或使用 Docker
   docker-compose restart backend
   ```

3. **验证修复**
   ```bash
   # 测试1: 货币转换
   # 创建 CNY 成本快照，检查 gate-preview 是否通过
   
   # 测试2: funnel_stage 更新
   curl -X PATCH https://admin.nuotaooutdoor.com/api/v1/products/{id}/full-update \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"funnel_stage": "published"}'
   
   # 测试3: SEO 端点
   curl -X POST https://admin.nuotaooutdoor.com/api/v1/seo/wordpress/update \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"post_id": 2372, "seo_title": "Test Title", "meta_description": "Test Description"}'
   ```

---

## 后续优化建议

1. **自动货币转换**: 在创建成本快照时，如果 currency 是 CNY，自动转换为 USD 存储
2. **WordPress Meta 注册**: 部署 mu-plugin 注册 Rank Math meta 字段，启用完整的 SEO 设置同步
3. **SEO 自动化**: 在推送产品到 WooCommerce 时，自动调用 SEO 端点配置 Rank Math 设置
4. **Funnel Stage 自动化**: 当产品状态变为 "published" 时，自动更新 funnel_stage

---

## 附录: 代码变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `backend/app/services/pricing_policy.py` | 修改 | 添加 CNY 到 USD 货币转换 |
| `backend/app/api/v1/endpoints/product_intelligence.py` | 修改 | 添加 funnel_stage 字段支持 |
| `backend/app/api/v1/endpoints/seo.py` | 修改 | 添加 WordPress SEO 更新端点 |
