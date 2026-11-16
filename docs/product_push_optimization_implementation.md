# 产品推送流程优化 - 实施总结

> **文档编号**: OPT-PROD-001-IMPL
> **版本**: 1.0
> **实施日期**: 2026-10-11
> **状态**: 已实施
> **负责人**: AI Agent

---

## 1. 修改概述

本次修改解决了产品推送到WooCommerce时**数据断裂**的问题，确保Product Master中的完整数据（SEO、运费类别、图片）能够同步到WC。

---

## 2. 已修改文件

### 2.1 `backend/app/services/listing_gate.py`

**修改内容**:

1. **添加图片处理函数**:
   - `is_wc_media_url(url: str) -> bool` - 检查URL是否是WC媒体库URL
   - `download_image_bytes(url: str, timeout: float) -> bytes | None` - 下载图片字节数据
   - `upload_to_wc_media(...)` - 上传图片到WC媒体库
   - `_get_wc_media_id(url: str, ...)` - 根据WC媒体URL获取媒体ID

2. **修改`build_wc_payload`函数**:
   - 添加SEO字段：`_yoast_wpseo_title`, `_yoast_wpseo_metadesc`, `_yoast_wpseo_focuskw`, `_yoast_wpseo_meta-robots-noindex`
   - 添加运费类别字段：`shipping_class`, `shipping_class_id`
   - 添加图片处理逻辑：检查是否已有WC媒体ID

3. **添加导入**:
   - `import httpx` - 异步HTTP客户端
   - `import requests` - 同步HTTP客户端（用于WC媒体上传）

### 2.2 `backend/app/api/v1/endpoints/listing_publish.py`

**修改内容**:

1. **添加本地图片收集函数**:
   - `_collect_local_generated_images(sku: str) -> list[dict]` - 从本地生成图片目录收集产品图片

2. **修改推送逻辑**（在`build_wc_payload`之前）:
   - 确保meta中包含SEO信息（从en_copy生成）
   - 确保meta中包含运费类别信息（默认值：outdoor-gear, 359）
   - 检查是否有图片需要处理（从本地收集）

3. **添加图片上传逻辑**（在`build_wc_payload`之后）:
   - 检查图片URL类型（WC媒体URL vs 本地路径）
   - 如果是本地路径，上传到WC媒体库
   - 更新payload中的图片为WC媒体ID

4. **添加导入**:
   - `import os`, `import glob` - 文件系统操作

---

## 3. 修改后的数据流

### 3.1 推送前

```
Product Master (meta字段)
├── seo: {title, description, focus_keyword, noindex}
├── shipping_class: "outdoor-gear"
├── shipping_class_id: 359
└── media: {images: [{src: url}, ...]}
```

### 3.2 推送时

```
1. 检查meta是否包含SEO信息
   └── 如果没有，从en_copy生成
2. 检查meta是否包含运费类别
   └── 如果没有，使用默认值
3. 检查meta是否包含图片
   └── 如果没有，从本地收集
4. 构建WC payload（包含SEO、运费类别、图片URL）
5. 处理图片上传
   ├── 如果是WC媒体URL → 获取媒体ID
   └── 如果是本地路径 → 上传到WC媒体库 → 获取媒体ID
6. 更新payload中的图片为WC媒体ID
7. 推送到WC
```

### 3.3 推送后

```
WooCommerce产品
├── name, sku, type, status
├── regular_price, sale_price
├── description, short_description
├── categories, brand
├── images: [{id: media_id, src: url}, ...]  ← WC媒体ID
├── weight, dimensions
├── manage_stock, stock_quantity, stock_status
├── attributes, tags
├── _yoast_wpseo_title
├── _yoast_wpseo_metadesc
├── _yoast_wpseo_focuskw
├── _yoast_wpseo_meta-robots-noindex
├── shipping_class
└── shipping_class_id
```

---

## 4. 验证步骤

### 4.1 语法检查

```bash
cd backend
python -m py_compile app/services/listing_gate.py
python -m py_compile app/api/v1/endpoints/listing_publish.py
```

✅ 语法检查通过

### 4.2 功能验证

1. **更新产品meta字段**:
   ```python
   meta = {
       "seo": {
           "title": "Ultra-Light Aluminum Folding Table - Nuotao Outdoor",
           "description": "Ultra-light 1.2kg aluminum folding table...",
           "focus_keyword": "aluminum folding table",
           "noindex": False,
       },
       "shipping_class": "outdoor-gear",
       "shipping_class_id": 359,
       "media": {
           "images": [
               {"src": "https://nuotaooutdoor.com/wp-content/uploads/2026/10/scene_001-1.png"},
               {"src": "https://nuotaooutdoor.com/wp-content/uploads/2026/10/camping_scene-1.png"},
               {"src": "https://nuotaooutdoor.com/wp-content/uploads/2026/10/back_view-1.png"},
           ]
       }
   }
   ```

2. **点击"推送"按钮**:
   - 检查WC产品是否包含SEO字段
   - 检查WC产品是否包含运费类别
   - 检查WC产品是否包含图片

3. **运行质量评估**:
   ```bash
   python scripts/wc_quality_assessment.py 2378
   ```

---

## 5. 预期效果

| 项目 | 修改前 | 修改后 |
|------|--------|--------|
| SEO字段 | ❌ 缺失 | ✅ 包含 |
| 运费类别 | ❌ 缺失 | ✅ 包含 |
| 图片 | ⚠️ 本地URL | ✅ WC媒体ID |
| 需要手动配置 | 是 | 否 |
| 质量分数 | 85/100 | ≥ 95/100 |

---

## 6. 下一步

1. ✅ 修改`listing_gate.py` - 完成
2. ✅ 修改`listing_publish.py` - 完成
3. ⏳ 修改`products.py` - CSV导入支持SEO和运费类别（可选）
4. ⏳ 修改`wc_quality_assessment.py` - 验证新字段（可选）
5. ⏳ 测试验证 - 推送产品并检查WC

---

**修改已完成，可以进行测试验证。**