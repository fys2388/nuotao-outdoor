# 产品推送流程优化方案

> **文档编号**: OPT-PROD-001
> **版本**: 1.0
> **创建日期**: 2026-10-11
> **状态**: 待审核
> **负责人**: AI Agent

---

## 1. 问题背景

### 当前问题

当前产品推送到WooCommerce的流程存在**数据断裂**问题：

```
Product Master (数据不完整) 
    ↓
点击"推送" → 只同步部分字段到WC
    ↓
手动配置SEO (WP REST API)  ← 数据断开 ❌
    ↓
手动配置运费类别 (WC后台)  ← 数据断开 ❌
    ↓
运行质量评估脚本
```

### 缺失的字段

当前`build_wc_payload`函数**不包含**以下关键字段：

| 字段 | WC API Key | 说明 |
|------|------------|------|
| SEO Title | `_yoast_wpseo_title` | SEO标题 |
| Meta Description | `_yoast_wpseo_metadesc` | SEO描述 |
| Focus Keyword | `_yoast_wpseo_focuskw` | 核心关键词 |
| Noindex | `_yoast_wpseo_meta-robots-noindex` | 禁用索引 |
| 运费类别 | `shipping_class` | 运费类别 |
| 运费类别ID | `shipping_class_id` | 运费类别ID |

### 期望流程

```
Product Master (完整数据：SEO+运费类别+图片+文案)
    ↓
点击"推送" → 同步所有字段到WC
    ↓
前端系统与WC保持同步
    ↓
商品同步到B2C模块展示
```

---

## 2. 修改方案

### 2.1 扩展meta字段结构

在`Product.meta` JSON字段中添加SEO和运费类别信息：

```json
{
  "woocommerce_id": 2378,
  "woocommerce_slug": "ultra-light-aluminum-mini-folding-table",
  "seo": {
    "title": "Ultra-Light Aluminum Folding Table - Nuotao Outdoor | Camping Gear 2026",
    "description": "Ultra-light 1.2kg aluminum folding table for camping and picnics. One-second setup, 30kg capacity, compact 35x8cm folded size. Perfect outdoor gear by Nuotao.",
    "focus_keyword": "aluminum folding table",
    "noindex": false
  },
  "shipping_class": "outdoor-gear",
  "shipping_class_id": 359,
  "images": [
    {"id": 2379, "src": "https://..."},
    {"id": 2380, "src": "https://..."},
    {"id": 2381, "src": "https://..."}
  ]
}
```

### 2.2 修改`build_wc_payload`函数

**文件**: `backend/app/services/listing_gate.py`

**位置**: `build_wc_payload`函数（第629行）

**修改内容**: 添加SEO和运费类别字段

```python
def build_wc_payload(product: Any, prices: dict, en_copy: dict) -> dict:
    """Build a WooCommerce product payload from the approved English copy."""
    
    meta = getattr(product, "meta", None)
    meta = meta if isinstance(meta, dict) else {}
    
    # ... 现有代码 ...
    
    payload: dict[str, Any] = {
        "name": title,
        "sku": str(getattr(product, "sku", "") or ""),
        "type": "simple",
        "status": "publish" if getattr(product, "status", None) == "active" else "draft",
        "regular_price": str(round(regular, 2)) if regular else "0",
        "description": description,
        "short_description": short,
    }
    
    # ... 现有代码 ...
    
    # === 新增：SEO字段 ===
    seo = meta.get("seo", {})
    if seo.get("title"):
        payload["_yoast_wpseo_title"] = seo["title"]
    if seo.get("description"):
        payload["_yoast_wpseo_metadesc"] = seo["description"]
    if seo.get("focus_keyword"):
        payload["_yoast_wpseo_focuskw"] = seo["focus_keyword"]
    if seo.get("noindex") is not None:
        payload["_yoast_wpseo_meta-robots-noindex"] = "1" if seo["noindex"] else "0"
    
    # === 新增：运费类别 ===
    if meta.get("shipping_class"):
        payload["shipping_class"] = meta["shipping_class"]
    if meta.get("shipping_class_id"):
        payload["shipping_class_id"] = meta["shipping_class_id"]
    
    # ... 现有代码 ...
    
    return payload
```

### 2.3 更新推送逻辑

**文件**: `backend/app/api/v1/endpoints/listing_publish.py`

**位置**: `push_product_to_woocommerce_gated`函数（第357行）

**修改内容**: 确保推送时包含SEO、运费类别和图片字段

```python
# 在推送前，确保meta中包含SEO、运费类别和图片信息
meta = product.meta if isinstance(product.meta, dict) else {}

# 如果meta中没有SEO信息，从en_copy中生成
if "seo" not in meta and en_copy:
    meta["seo"] = {
        "title": en_copy.get("title", ""),
        "description": en_copy.get("short_description", ""),
        "focus_keyword": en_copy.get("seo_keywords", [""])[0] if en_copy.get("seo_keywords") else "",
        "noindex": False,
    }

# 如果meta中没有运费类别信息，使用默认值
if "shipping_class" not in meta:
    meta["shipping_class"] = "outdoor-gear"
if "shipping_class_id" not in meta:
    meta["shipping_class_id"] = 359

# === 新增：图片处理 ===
# 如果meta中没有图片信息，尝试从本地生成图片目录收集
if "images" not in meta and "media" not in meta:
    generated_images = collect_local_generated_images(product.sku)
    if generated_images:
        meta["media"] = {"images": generated_images}

product.meta = meta
flag_modified(product, "meta")
```

### 2.4 图片上传逻辑

**文件**: `backend/app/services/listing_gate.py`

**新增函数**: `upload_images_to_wc`

```python
async def upload_images_to_wc(
    image_urls: list[str],
    product_sku: str,
    wc_auth: tuple[str, str],
    wc_headers: dict[str, str],
    budget: "_PushBudget",
) -> list[dict[str, Any]]:
    """上传本地图片到WC媒体库，返回WC媒体ID列表。
    
    处理流程：
    1. 检查图片URL是否已经是WC媒体库URL
    2. 如果是本地URL或外部URL，上传到WC媒体库
    3. 返回WC媒体ID列表，用于更新产品图片数组
    """
    wc_media_ids = []
    
    for url in image_urls:
        # 检查是否已经是WC媒体库URL
        if is_wc_media_url(url):
            # 获取WC媒体ID
            media_id = _get_wc_media_id(url, wc_auth, wc_headers, budget)
            if media_id:
                wc_media_ids.append({"id": media_id, "src": url})
            continue
        
        # 下载本地图片
        image_bytes = await download_image(url)
        if not image_bytes:
            continue
        
        # 上传到WC媒体库
        media_id = await upload_to_wc_media(
            image_bytes=image_bytes,
            filename=url.split("/")[-1],
            title=f"{product_sku} - Product Image",
            auth=wc_auth,
            headers=wc_headers,
            budget=budget,
        )
        
        if media_id:
            wc_media_ids.append({"id": media_id, "src": url})
    
    return wc_media_ids


def is_wc_media_url(url: str) -> bool:
    """检查URL是否是WC媒体库URL。"""
    return url.startswith("https://nuotaooutdoor.com/wp-content/uploads/")


async def download_image(url: str) -> bytes | None:
    """从URL下载图片。"""
    if url.startswith("http://") or url.startswith("https://"):
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30.0)
            if response.status_code == 200:
                return response.content
    return None


async def upload_to_wc_media(
    image_bytes: bytes,
    filename: str,
    title: str,
    auth: tuple[str, str],
    headers: dict[str, str],
    budget: "_PushBudget",
) -> int | None:
    """上传图片到WC媒体库，返回媒体ID。"""
    base = _wc_base_url()
    url = f"{base}/wp-json/wp/v2/media"
    
    # 构建multipart/form-data请求
    files = {"file": (filename, image_bytes, "image/png")}
    data = {"title": title}
    
    try:
        response = requests.post(
            url,
            auth=auth,
            headers={k: v for k, v in headers.items() if k != "Content-Type"},
            files=files,
            data=data,
            timeout=60,
        )
        response.raise_for_status()
        result = response.json()
        return result.get("id")
    except Exception as e:
        logger.error(f"Failed to upload image to WC media: {e}")
        return None


def _get_wc_media_id(
    url: str,
    auth: tuple[str, str],
    headers: dict[str, str],
    budget: "_PushBudget",
) -> int | None:
    """根据WC媒体URL获取媒体ID。"""
    base = _wc_base_url()
    search_url = f"{base}/wp-json/wp/v2/media"
    params = {"source_url": url}
    
    try:
        response = requests.get(
            search_url,
            auth=auth,
            headers=headers,
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        results = response.json()
        if results:
            return results[0].get("id")
    except Exception as e:
        logger.error(f"Failed to get WC media id: {e}")
    return None
```

### 2.5 更新`build_wc_payload`函数中的图片处理

**文件**: `backend/app/services/listing_gate.py`

**位置**: `build_wc_payload`函数（第684行）

**修改内容**: 使用WC媒体ID而不是URL

```python
# 现有代码
images = collect_listing_images(meta)
if images:
    payload["images"] = images[:_MAX_IMAGES]

# === 修改为 ===
# 收集图片URL
image_urls = []
for img in collect_listing_images(meta):
    url = img.get("src", "")
    if url:
        image_urls.append(url)

# 如果meta中已经有WC媒体ID，直接使用
wc_media_ids = meta.get("wc_media_ids", [])
if wc_media_ids:
    payload["images"] = wc_media_ids[:_MAX_IMAGES]
else:
    # 否则使用URL，WC API会自动处理
    if image_urls:
        payload["images"] = image_urls[:_MAX_IMAGES]
```

### 2.4 更新CSV导入逻辑

**文件**: `backend/app/api/v1/endpoints/products.py`

**位置**: CSV导入端点

**修改内容**: 支持导入SEO和运费类别字段

```python
# CSV列扩展
CSV_COLUMNS = [
    "sku", "name", "description", "category", "brand", "tags", "attributes", 
    "source_url", "supplier_code",
    # 新增列
    "seo_title", "seo_description", "seo_focus_keyword", "seo_noindex",
    "shipping_class", "shipping_class_id"
]

# 导入时解析SEO和运费类别
def parse_csv_row(row: dict) -> dict:
    meta = {}
    
    # SEO字段
    if row.get("seo_title") or row.get("seo_description") or row.get("seo_focus_keyword"):
        meta["seo"] = {
            "title": row.get("seo_title", ""),
            "description": row.get("seo_description", ""),
            "focus_keyword": row.get("seo_focus_keyword", ""),
            "noindex": row.get("seo_noindex", "false").lower() == "true",
        }
    
    # 运费类别字段
    if row.get("shipping_class"):
        meta["shipping_class"] = row["shipping_class"]
    if row.get("shipping_class_id"):
        meta["shipping_class_id"] = int(row["shipping_class_id"])
    
    return {"meta": meta}
```

---

## 3. 实施步骤

### 步骤1: 修改`build_wc_payload`函数

**文件**: `backend/app/services/listing_gate.py`

**操作**: 添加SEO和运费类别字段到payload

### 步骤2: 更新推送逻辑

**文件**: `backend/app/api/v1/endpoints/listing_publish.py`

**操作**: 在推送前确保meta中包含SEO和运费类别信息

### 步骤3: 更新CSV导入逻辑

**文件**: `backend/app/api/v1/endpoints/products.py`

**操作**: 支持导入SEO和运费类别字段

### 步骤4: 测试

1. 更新产品NT-610901081609的meta字段
2. 点击"推送"按钮
3. 验证WC中是否包含SEO和运费类别字段
4. 运行质量评估脚本，验证分数

---

## 4. 风险与注意事项

### 4.1 数据兼容性

- **向后兼容**: 旧产品没有SEO和运费类别信息时，使用默认值
- **向前兼容**: 新产品可以包含SEO和运费类别信息

### 4.2 WC API限制

- **SEO字段**: WC API支持直接更新Yoast SEO字段
- **运费类别**: WC API支持直接更新shipping_class字段
- **运费类别ID**: 需要确保shipping_class_id在WC中存在

### 4.3 性能影响

- **数据量**: meta字段增加约200-500字节
- **推送时间**: 增加约100-200ms（API调用）

---

## 5. 验证标准

### 5.1 功能验证

- [ ] 推送后WC产品包含SEO Title
- [ ] 推送后WC产品包含Meta Description
- [ ] 推送后WC产品包含Focus Keyword
- [ ] 推送后WC产品包含Noindex设置
- [ ] 推送后WC产品包含Shipping Class
- [ ] 推送后WC产品包含Shipping Class ID

### 5.2 质量验证

- [ ] 质量评估分数 ≥ 95/100
- [ ] 无需手动配置SEO字段
- [ ] 无需手动配置运费类别

### 5.3 数据一致性

- [ ] Product Master与WC数据一致
- [ ] 前端系统与B2C模块数据同步

---

## 6. 预期效果

### 修改前

| 项目 | 状态 |
|------|------|
| 推送后SEO字段 | ❌ 缺失 |
| 推送后运费类别 | ❌ 缺失 |
| 需要手动配置SEO | 是 |
| 需要手动配置运费类别 | 是 |
| 质量分数 | 85/100 |

### 修改后

| 项目 | 状态 |
|------|------|
| 推送后SEO字段 | ✅ 包含 |
| 推送后运费类别 | ✅ 包含 |
| 需要手动配置SEO | 否 |
| 需要手动配置运费类别 | 否 |
| 质量分数 | ≥ 95/100 |

---

## 7. 文件修改清单

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `backend/app/services/listing_gate.py` | 修改 | 添加SEO、运费类别字段；新增图片上传函数 |
| `backend/app/api/v1/endpoints/listing_publish.py` | 修改 | 更新推送逻辑，包含图片处理 |
| `backend/app/api/v1/endpoints/products.py` | 修改 | 更新CSV导入逻辑 |
| `backend/scripts/wc_quality_assessment.py` | 修改 | 验证SEO、运费类别、图片字段 |

---

## 8. 图片推送流程

### 8.1 当前问题

```
Product Master (本地图片URL)
    ↓
点击"推送" → 图片URL无效（本地路径）
    ↓
WC中无图片 ❌
```

### 8.2 修改后的流程

```
Product Master (本地图片URL)
    ↓
点击"推送" → 检测图片URL
    ↓
如果是本地URL → 上传到WC媒体库 → 获取WC媒体ID
    ↓
如果是WC媒体URL → 直接使用WC媒体ID
    ↓
更新产品图片数组
    ↓
WC中显示图片 ✅
```

### 8.3 图片处理逻辑

```python
# 1. 收集Product Master中的图片URL
image_urls = collect_listing_images(meta)

# 2. 检查每个图片URL
for url in image_urls:
    if is_wc_media_url(url):
        # 已经是WC媒体URL，获取ID
        media_id = _get_wc_media_id(url)
    else:
        # 本地URL，上传到WC媒体库
        media_id = upload_to_wc_media(url)

# 3. 更新产品图片数组
payload["images"] = [{"id": media_id, "src": url}]
```

---

## 9. 下一步

1. **审核方案**: 请审核上述修改方案
2. **确认实施**: 确认后开始实施修改
3. **测试验证**: 实施后进行功能测试
4. **更新文档**: 更新SOP文档

---

**请审核此方案，确认后我将开始实施修改。**