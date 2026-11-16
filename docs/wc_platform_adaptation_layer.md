# 平台适配层：Amazon SOP → Nuotao WooCommerce

> 版本：V1.0  
> 创建日期：2026-10-05  
> 用途：`docs/ai_image_generation_sop.md` 基于亚马逊方法论编写，本文档提供 Nuotao WooCommerce 平台适配映射。  
> 关系：SOP 原文 → 适配层 → 实际执行  
> 核心原则：**SOP 流程不变，只替换平台术语和交付格式。**

---

## 一、术语映射表

| SOP 原文（Amazon） | Nuotao WooCommerce 对应 | 说明 |
|---------------------|------------------------|------|
| 亚马逊 / Amazon | Nuotao WooCommerce | 平台名称 |
| 亚马逊主图 | WC 主图 (Main Image) | WooCommerce 产品主图 |
| 亚马逊附图 | WC 画廊图 (Gallery Images) | WooCommerce 产品画廊 |
| A+ Content | 产品描述 HTML (Description HTML) | WooCommerce 没有 A+，用 HTML 描述替代 |
| A+ 模块 | 描述模块 (Description Section) | 用 `<section>` 或 `<div>` 包装 |
| 亚马逊搜索结果页 | WC 分类页 / Google 搜索结果 | 流量入口 |
| 亚马逊买家 | WC 访客 / Google 搜索用户 | 目标用户 |
| Listing | 产品页面 (Product Page) | WooCommerce 术语 |
| 五点描述 (Bullet Points) | 产品描述 HTML 中的 `<ul>` 列表 | WC 用 HTML，无独立 bullet 字段 |
| 卖家后台 | WC 后台 (wp-admin) | 管理界面 |
| 亚马逊平台 | WooCommerce 平台 | 电商平台 |
| 亚马逊视觉工作流 | Nuotao 视觉工作流 | 工作流名称 |
| 亚马逊合规 | WooCommerce 合规 | 合规检查 |
| A+ 页面 | 产品描述页面 (Product Description) | WC 产品详情页 |
| A+ 设计规范 | WC 描述 HTML 设计规范 | 设计标准 |
| 亚马逊 Listing | WC 产品页面 | 术语映射 |
| 亚马逊 SEO | WC SEO (Yoast/Rank Math) | SEO 工具 |
| A+ Content 区域 | 产品描述区域 | 页面位置 |
| 亚马逊广告 | Google Ads / WC 推荐位 | 营销渠道 |
| 亚马逊 FBA | WC 自发货 / 海外仓 | 物流方式 |
| A+ 图文模块 | 描述图文模块 | 内容形式 |
| 亚马逊移动端 | WC 移动端 (Hugo/Boutique 主题) | 移动端适配 |
| A+ 手机端 | WC 描述 HTML 移动端 | 响应式设计 |

---

## 二、图片类型映射

### 2.1 主图 (Main Image)

| 维度 | Amazon | Nuotao WC | 差异说明 |
|------|--------|-----------|----------|
| 位置 | 搜索结果、广告位、商品列表 | 分类页、Google 搜索、直接链接 | WC 无搜索排名展示 |
| 比例 | 1:1 (正方形) | 1:1 或 4:3 (主题决定) | WC 主题灵活，建议 1:1 |
| 数量 | 主图 1 张 | 主图 1 张 (第 1 张画廊图) | 相同 |
| 白底要求 | 必须白底 | 建议白底 (非强制) | WC 无白底强制要求 |
| 尺寸 | 1600x1600+ | 1024x1024+ | WC 要求较低 |

**SOP Step 3.2 主图规划 → WC 适配**：

```yaml
main_image:
  quantity: 1
  aspect_ratio: "1:1"
  resolution: "1024x1024"
  background: "pure white (recommended)"
  content: "product only, no text or graphics"
  purpose: "WC category page + Google image search"
```

### 2.2 附图 (Gallery Images)

| 维度 | Amazon | Nuotao WC | 差异说明 |
|------|--------|-----------|----------|
| 位置 | Listing 详情页图片区 | 产品画廊 (Gallery) | WC 画廊支持拖拽排序 |
| 数量 | 5-7 张 (标准 6) | 5-11 张 (WC 画廊无上限) | WC 限制更少 |
| 比例 | 1:1 或 3:4 | 1:1 (推荐) | WC 主题通常 1:1 |
| 排序 | 手动排序 | 手动排序 (WP 后台拖拽) | 相同 |

**SOP Step 3.3 附图规划 → WC 适配**：

```yaml
gallery_images:
  quantity: "5-11"
  aspect_ratio: "1:1"
  resolution: "1024x1024"
  purpose: "WC product gallery, each image solves one buyer question"
  ordering:
    1: "real product photo (1688 original)"
    2-11: "I2I generated images (scenes, features, specs)"
```

### 2.3 A+ Content → 产品描述 HTML

| 维度 | Amazon A+ | Nuotao WC | 差异说明 |
|------|-----------|-----------|----------|
| 名称 | A+ Content | Product Description (HTML) | WC 用 HTML 描述 |
| 格式 | 模块化 (A+ modules) | HTML `<section>` 包装 | 需要 HTML 编码 |
| 宽度 | 固定模块宽度 | 主题决定 (通常 720-1200px) | 需要响应式设计 |
| 高度 | 各模块独立 | 连续滚动 | WC 描述是一个长页面 |
| 限制 | A+ 模块类型有限制 | 无限制 (HTML) | WC 更灵活 |
| 手机端 | 独立手机端 A+ | 响应式 HTML (媒体查询) | WC 用 CSS 响应式 |

**SOP Step 3.4-3.5 A+ 规划 → WC 适配**：

```yaml
wc_description_html:
  format: "HTML5"
  structure:
    - section: "hero"
      width: "100%"
      content: "hero image + product name + tagline"
    - section: "features"
      width: "100%"
      content: "feature grid (2-3 columns on desktop, 1 column on mobile)"
    - section: "specs"
      width: "100%"
      content: "specification table"
    - section: "gallery"
      width: "100%"
      content: "image gallery with captions"
    - section: "trust"
      width: "100%"
      content: "reviews, certifications, warranty"
  responsive:
    desktop: ">768px"
    tablet: "768px-480px"
    mobile: "<480px"
  typography:
    heading: "24-36px, bold"
    subheading: "18-24px"
    body: "14-16px"
    caption: "12-14px"
```

---

## 三、图片生成策略映射

### 3.1 SOP Step 5 生图策略 → WC 适配

| SOP 图片类型 | Amazon 用途 | WC 用途 | 生图策略 |
|-------------|-------------|---------|----------|
| 主图 | 搜索页 CTR | 分类页 + Google 图片搜索 CTR | I2I (1688 原图 → 白底高清) |
| 附图 1-6 | 转化 (CVR) | WC 画廊图 (转化) | I2I (场景/功能/细节) |
| A+ 模块 1-7 | 信任 (Brand) | WC 描述 HTML 图文模块 (信任) | I2I + HTML 包装 |
| A+ 手机端 1-7 | 移动端信任 | WC 描述 HTML 响应式 | 同一套图，CSS 适配 |

### 3.2 WC 描述 HTML 模板

```html
<!-- WC 产品描述 HTML 模板 -->
<div class="nuotao-product-description">
  <!-- Hero Section -->
  <section class="hero">
    <img src="{{hero_image_url}}" alt="{{product_name}}" style="width:100%">
    <h1>{{product_name}}</h1>
    <p class="tagline">{{tagline}}</p>
  </section>
  
  <!-- Features Section -->
  <section class="features">
    <h2>Why You'll Love It</h2>
    <div class="feature-grid">
      <div class="feature">
        <img src="{{feature_1_image}}" alt="{{feature_1_title}}">
        <h3>{{feature_1_title}}</h3>
        <p>{{feature_1_description}}</p>
      </div>
      <!-- repeat for each feature -->
    </div>
  </section>
  
  <!-- Specs Section -->
  <section class="specs">
    <h2>Specifications</h2>
    <table>
      <tr><td>Weight</td><td>{{weight_kg}} kg</td></tr>
      <tr><td>Dimensions</td><td>{{dimensions}}</td></tr>
      <tr><td>Material</td><td>{{material}}</td></tr>
      <!-- more specs -->
    </table>
  </section>
  
  <!-- Gallery Section -->
  <section class="gallery">
    <h2>In Detail</h2>
    <div class="image-gallery">
      <img src="{{gallery_1}}" alt="{{caption_1}}">
      <img src="{{gallery_2}}" alt="{{caption_2}}">
      <!-- more gallery images -->
    </div>
  </section>
  
  <!-- Trust Section -->
  <section class="trust">
    <h2>Trusted by {{customer_count}}+ Outdoor Enthusiasts</h2>
    <p>{{warranty_text}}</p>
  </section>
</div>
```

---

## 四、WC 描述 HTML 设计规范

### 4.1 桌面端 (>768px)

| 元素 | 建议 |
|------|------|
| 容器宽度 | 720-1200px (主题决定) |
| 图片宽度 | 100% (响应式) |
| 特征网格 | 2-3 列 |
| 标题字号 | 24-36px |
| 正文字号 | 14-16px |
| 行高 | 1.6-1.8 |
| 段间距 | 24-48px |

### 4.2 移动端 (<480px)

| 元素 | 建议 |
|------|------|
| 容器宽度 | 100% |
| 图片宽度 | 100% |
| 特征网格 | 1 列 |
| 标题字号 | 18-24px |
| 正文字号 | 14-16px (不缩小) |
| 段间距 | 16-32px |
| 按钮高度 | 44px+ (触控友好) |

### 4.3 CSS 媒体查询模板

```css
.nuotao-product-description {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 20px;
}
.feature-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
}
@media (max-width: 768px) {
  .feature-grid {
    grid-template-columns: 1fr;
  }
}
```

---

## 五、WC 图片上传流程

### 5.1 图片→WC 管线

```
SOP Step 5: 生成图片
    ↓
Step 5.5: 图片下载 (Agnes URL → 本地)
    ↓
Step 5.6: 图片上传到 WC Media Library
    ↓
Step 5.7: 获取 WC media_id
    ↓
Step 5.8: 更新产品 images 数组
    ↓
Step 5.9: WC GET=200 验证
```

### 5.2 WC Media 上传 API

```python
# WC Media 上传 (multipart/form-data)
POST /wp-json/wc/v3/media
Authorization: Basic ck_xxx:cs_xxx

Files:
  file: [binary image data]

Response:
{
  "id": 12345,
  "src": "https://nuotaooutdoor.com/wp-content/uploads/...",
  "alt": "description",
  "caption": "caption"
}
```

### 5.3 产品图片更新 API

```python
# WC 产品图片更新
PUT /wp-json/wc/v3/products/{product_id}
Authorization: Basic ck_xxx:cs_xxx

Body:
{
  "images": [
    {"id": 12345, "alt": "main image"},
    {"id": 12346, "alt": "feature image"},
    {"id": 12347, "alt": "scene image"}
  ]
}
```

---

## 六、WC 产品字段映射 (SOP → WC)

| SOP 概念 | WC 字段 | 数据类型 | API 字段 |
|----------|---------|----------|----------|
| 产品名称 | Name | string | `name` |
| 产品 SKU | SKU | string | `sku` |
| 产品描述 | Description | HTML string | `description` |
| 短描述 | Short Description | HTML string | `short_description` |
| 主图 | Main Image | media_id | `images[0].id` |
| 画廊图 | Gallery Images | media_id[] | `images[1:].id` |
| 价格 | Regular Price | decimal | `regular_price` |
| 促销价 | Sale Price | decimal | `sale_price` |
| 库存 | Stock | integer | `stock_quantity` |
| 重量 | Weight | decimal (kg) | `weight` |
| 尺寸 | Dimensions | L×W×H (cm) | `dimensions.length/width/height` |
| 分类 | Categories | term_id[] | `categories[].id` |
| 标签 | Tags | term_id[] | `tags[].id` |
| 属性 | Attributes | name+options | `attributes[].name/options` |
| 品牌 | Brand | text/meta | `meta_data[]` 或 ACAS plugin |
| 型号 | Model | text/meta | `meta_data[]` |
| 运费模板 | Shipping Class | term_id | `shipping_class_id` |
| 推荐位 | Featured | boolean | `featured` |

---

## 七、WC SEO 适配

| SOP 概念 | WC 对应 | 说明 |
|----------|---------|------|
| 亚马逊 SEO | Yoast SEO / Rank Math | WP 插件 |
| 亚马逊关键词 | WC Meta Title / Meta Description | Yoast 插件字段 |
| 亚马逊 Schema | Yoast Schema (Product Schema) | JSON-LD |
| 亚马逊图片 alt | WC 图片 alt text | WC Media Library |
| 亚马逊产品摘要 | WC Short Description | 155 字符以内 |
| 亚马逊类目 | WC Product Category | WC 后台分类 |
| 亚马逊品牌 | WC Brand (ACAS 插件) | 品牌插件 |

---

## 八、WC 主题适配

| 主题类型 | 描述宽度 | 图片比例 | A+ 等价物 |
|----------|----------|----------|-----------|
| Twenty Twenty-Four | 720px | 1:1 | 描述 HTML 居中 |
| Storefront | 720px | 1:1 | 描述 HTML 居中 |
| Astra + Elementor | 主题决定 | 主题决定 | Elementor 编辑 |
| Hugo (户外主题) | 960px | 16:9 | 宽屏描述 |
| WooCommerce MyStore | 720px | 1:1 | 描述 HTML 居中 |

**建议**：统一使用 1:1 比例图片 + 响应式 HTML 描述，兼容所有主题。

---

## 九、执行检查清单

### 9.1 WC 产品上架前检查

- [ ] 主图：白底、1:1、产品居中、无文字水印
- [ ] 画廊图：5-11 张、1:1、每张解决一个问题
- [ ] 描述 HTML：响应式、桌面 3 列 / 移动 1 列
- [ ] 描述 HTML：包含规格表、功能列表、信任背书
- [ ] 标题：SEO 优化 (关键词前置)
- [ ] 短描述：155 字符以内
- [ ] 分类：正确映射到 WC 分类树
- [ ] 标签：5-10 个相关标签
- [ ] 属性：材质、尺寸、颜色等
- [ ] 品牌：ACAS 插件或 meta_data
- [ ] 型号：meta_data 或属性
- [ ] 重量：真实值 (非估算)
- [ ] 尺寸：真实值 (非估算)
- [ ] 运费模板：已设置 (需 WP Admin)
- [ ] 推荐位：featured = true (如需)
- [ ] WC GET=200：API 验证通过
- [ ] 公开页面 HTTP 200：浏览器验证通过

---

## 十、版本历史

| 版本 | 日期 | 变更 | 作者 |
|------|------|------|------|
| V1.0 | 2026-10-05 | 首版：Amazon→WC 术语映射、图片策略、描述 HTML 模板、WC API 映射 | marketing_manager |
