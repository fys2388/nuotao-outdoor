# WC 字段契约（Content Packet Schema）

> **对应 SOP**：`wc-ai-content-sop-v1.0.md` Phase ⑦
> **对应代码**：`backend/app/services/woocommerce_sync_service.py` · `push_product_to_woocommerce`
> **对应 skill**：`wc-product-upload`
> **对应文档**：`docs/selection_to_woocommerce_operation_workflow.md`

---

## 用途

定义 `product_content_packet.json` 的完整结构，对齐 WC REST API v3 字段契约。

---

## 完整结构

```json
{
  "product_id": "uuid-local-db",
  "source": {
    "url": "https://detail.1688.com/offer/XXXXX.html",
    "supplier": "supplier name"
  },
  "target": {
    "market": "US",
    "store_id": "wc-prod-01",
    "currency": "USD"
  },
  "wc_product": {
    "name": "...",
    "type": "simple",
    "status": "publish",
    "sku": "...",
    "regular_price": "...",
    "sale_price": "...",
    "description": "...",
    "short_description": "...",
    "categories": [...],
    "tags": [...],
    "attributes": [...],
    "weight": "...",
    "dimensions": {...},
    "stock_quantity": 0,
    "manage_stock": true,
    "stock_status": "...",
    "images": [...],
    "meta_title": "...",
    "meta_description": "...",
    "slug": "..."
  },
  "audit": {
    "gate_result": {...},
    "l1_verdict": "...",
    "l2_reviewer": "...",
    "l2_verified_at": "...",
    "compliance_notes": [...]
  }
}
```

---

## 字段详细说明

### P0 必填字段（缺失会导致功能异常）

| 字段 | WC API Key | 类型 | 说明 |
|---|---|---|---|
| 名称 | `name` | string | 60-120 字符，英文 |
| SKU | `sku` | string | 库存单位编码，唯一 |
| 类型 | `type` | string | 固定 `"simple"` |
| 状态 | `status` | string | `"publish"` / `"draft"` |
| 描述 | `description` | HTML string | 600-2500 词，7 模块 |
| 短描述 | `short_description` | string | 1-2 句话，≤ 160 字符 |
| 价格 | `regular_price` / `price` | string | USD，> 0，禁止 0 元 |
| 库存管理 | `manage_stock` | bool | 默认 True |
| 库存数量 | `stock_quantity` | int | ≥ 0 |
| 库存状态 | `stock_status` | string | `"instock"` / `"outofstock"` / `"onbackorder"` |
| 重量 | `weight` | string | kg |
| 尺寸 | `dimensions` | object | `{length, width, height}` cm |

### P1 推荐字段

| 字段 | WC API Key | 类型 | 说明 |
|---|---|---|---|
| 分类 | `categories` | array | 映射到 WC 真实 term id |
| 标签 | `tags` | array | 5-10 个 |
| 属性 | `attributes` | array | 变体属性 |
| 图片 | `images` | array | `[{src: url}]` 格式，11 张 |
| 促销价 | `sale_price` | string | < regular_price |
| 品牌 | `brand` | string | 需映射到 WC brand term id |
| SEO 标题 | `meta_title` | string | ≤ 60 字符 |
| SEO 描述 | `meta_description` | string | ≤ 160 字符 |
| Slug | `slug` | string | kebab-case |

---

## 本地模型字段映射

对应 `backend/app/models/product.py`：

```python
product.name          → wc_product["name"]
product.sku           → wc_product["sku"]
product.description   → wc_product["description"]
product.category      → wc_product["categories"]  # map_category_to_wc()
product.brand         → wc_product["brand"]       # brand 映射表
product.tags          → wc_product["tags"]        # list → [{name: t}]
product.attributes    → wc_product["attributes"]  # dict → [{name, options, visible}]
product.weight_kg     → wc_product["weight"]      # Numeric(8,3) → str
product.dimensions    → wc_product["dimensions"]  # JSON {length,width,height}
product.meta["price"] → wc_product["regular_price"] / ["price"]
product.meta["sale_price"] → wc_product["sale_price"]
product.meta["stock_quantity"] → wc_product["stock_quantity"]
product.meta["manage_stock"] → wc_product["manage_stock"]
product.meta["stock_status"] → wc_product["stock_status"]
product.meta["images"] → wc_product["images"]     # 图片 URL 列表
```

---

## JSON Schema（简化版）

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "NuotaoProductContentPacket",
  "type": "object",
  "required": ["product_id", "source", "target", "wc_product", "audit"],
  "properties": {
    "product_id": {
      "type": "string",
      "description": "Local database UUID"
    },
    "source": {
      "type": "object",
      "required": ["url"],
      "properties": {
        "url": {"type": "string", "format": "uri"},
        "supplier": {"type": "string"}
      }
    },
    "target": {
      "type": "object",
      "required": ["market", "store_id", "currency"],
      "properties": {
        "market": {"type": "string", "enum": ["US", "UK", "DE", "FR", "AU", "UAE", "SA"]},
        "store_id": {"type": "string"},
        "currency": {"type": "string", "enum": ["USD", "GBP", "EUR", "AUD", "AED", "SAR"]}
      }
    },
    "wc_product": {
      "type": "object",
      "required": ["name", "sku", "type", "status", "description", "short_description", "regular_price", "weight", "dimensions", "manage_stock", "stock_status"],
      "properties": {
        "name": {"type": "string", "minLength": 60, "maxLength": 120},
        "type": {"type": "string", "const": "simple"},
        "status": {"type": "string", "enum": ["publish", "draft", "pending"]},
        "sku": {"type": "string", "minLength": 1},
        "regular_price": {"type": "string", "pattern": "^\\d+\\.\\d{2}$"},
        "sale_price": {"type": "string", "pattern": "^\\d+\\.\\d{2}$"},
        "description": {"type": "string", "minLength": 600},
        "short_description": {"type": "string", "maxLength": 160},
        "categories": {"type": "array", "items": {"type": "object", "required": ["id"]}},
        "tags": {"type": "array", "items": {"type": "object", "required": ["name"]}},
        "attributes": {"type": "array"},
        "weight": {"type": "string"},
        "dimensions": {
          "type": "object",
          "required": ["length", "width", "height"],
          "properties": {
            "length": {"type": "string"},
            "width": {"type": "string"},
            "height": {"type": "string"}
          }
        },
        "stock_quantity": {"type": "integer", "minimum": 0},
        "manage_stock": {"type": "boolean", "default": true},
        "stock_status": {"type": "string", "enum": ["instock", "outofstock", "onbackorder"]},
        "images": {"type": "array", "minItems": 11},
        "meta_title": {"type": "string", "maxLength": 60},
        "meta_description": {"type": "string", "maxLength": 160},
        "slug": {"type": "string", "pattern": "^[a-z0-9-]+$"}
      }
    },
    "audit": {
      "type": "object",
      "required": ["gate_result", "l1_verdict"],
      "properties": {
        "gate_result": {
          "type": "object",
          "properties": {
            "blocked": {"type": "boolean"},
            "force_required": {"type": "boolean"},
            "reasons": {"type": "array", "items": {"type": "string"}}
          }
        },
        "l1_verdict": {"type": "string", "enum": ["PASS", "CHANGES_REQUIRED", "BLOCKED"]},
        "l2_reviewer": {"type": "string"},
        "l2_verified_at": {"type": "string", "format": "date-time"},
        "compliance_notes": {"type": "array", "items": {"type": "string"}}
      }
    }
  }
}
```

---

## 6 道拦截（对齐 `listing_gate.py`）

```python
# 1. 价格拦截
if price is None or price <= 0:
    BLOCK

# 2. 中文拦截
if has_cjk(description) and not has_approved_english(localization):
    BLOCK

# 3. 分类映射
wc_product["categories"] = map_category_to_wc(title, category)

# 4. V3.0 选品闸门
gate = await check_product_push_gate(db, product_id, workspace_id, force)
if gate.get("blocked"): BLOCK
if gate.get("force_required"): REQUIRE_MANUAL_APPROVAL

# 5. 图片 URL 可访问性
for img in images:
    if HEAD(img.src).status != 200: BLOCK

# 6. HTML 有效性
if not html_validate(description): BLOCK
```

---

## 推送后 Mapping

```python
# 推送成功后，保存 Mapping
product.meta["woocommerce_id"] = wc_product_id
product.meta["last_synced_at"] = datetime.now()
```

**⚠️ 已知风险**（见 `docs/selection_to_woocommerce_operation_workflow.md` §5 差异 6）：
- JSON 字段无数据库唯一约束
- 重复/孤儿映射隐患
- 建议加唯一约束或定期清理

---

## 版本记录

- v1.0 (2026-09-27)：初版，对齐 `wc-product-upload` skill 和 `woocommerce_sync_service.py`
