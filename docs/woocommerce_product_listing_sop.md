# WooCommerce 产品上架 SOP（商品上架标准作业流程）

> **版本**：v1.3 ｜ **更新日期**：2026-10-30 ｜ **适用范围**：1688 源产品 → WooCommerce 上架全流程
> **依据**：实际执行记录（充气床垫 NT-1054599709111 与加热睡袋垫 NT-986492089515 上架全流程）

---

## 1. 适用范围

本 SOP 定义从 **1688 源产品** 到 **WooCommerce 上架** 的完整标准作业流程，覆盖：

1. 1688 一键导入（AI OS 商品工作台）
2. 源产品参数提取
3. WooCommerce 产品创建（草稿）
4. 产品图片准备与上传
5. 产品参数完善（slug / 分类 / 描述 / 标签 / 变体 / 重量尺寸）
6. Rank Math SEO 优化
7. 质量验收（编辑页 + 展示页）
8. 发布（上架）

> ⚠️ **铁律（禁止跳过流程）**：严格按步骤 1→8 顺序执行，**禁止跳过任何步骤**。尤其步骤 1「1688 一键导入」必须先行（依赖 AI OS 登录态；未登录时先解决登录，不得跳步改用其它方式创建产品）。

---

## 2. 前置条件

| 项 | 说明 |
|---|---|
| 1688 源产品链接 | 已复制商品详情页 URL（如 `https://detail.1688.com/offer/{offer_id}.html`） |
| Nuotao AI OS 系统 | `https://admin.nuotaooutdoor.com`（浏览器已登录，商品工作台 `/products/pipeline`） |
| WooCommerce REST | consumer key / secret 可用（`.env`），TLS 1.2 强制 |
| WordPress 登录 | 浏览器已登录（产品编辑页可访问） |
| 图片素材 | 白底图 / 详情图已获取（1688 源或供应商提供） |
| 图片生成 | 如需英文电商图：ChatGPT 或等效工具 + 图片快照参数（prompt.md） |

---

## 3. 流程总览

```
1688 源产品链接
   │  ① AI OS 1688 一键导入（商品与AI选品 → 商品工作台 → 1688一键导入 → 输入链接 → 导入完成上架）
   ▼
源产品参数提取
   │  ② 参数提取（源链接 / SKU / 材质 / 尺寸 / 重量 / 颜色 / 包装）
   ▼
WooCommerce 产品创建（草稿）
   │  ③ POST /wp-json/wc/v3/products → 返回 wc_id
   ▼
图片准备与上传
   │  ④ 下载白底图 → 生成英文电商图 → WP media 上传 → 设为产品图/画廊
   ▼
产品参数完善
   │  ⑤ PUT /wp-json/wc/v3/products/{id}（slug / 分类 / 描述 / 标签 / 变体 / 重量尺寸）
   ▼
Rank Math SEO 优化
   │  ⑥ 浏览器：Focus Keyword / SEO Title / SEO Description → Save Draft
   ▼
质量验收
   │  ⑦ 编辑页 + 展示页（前台）核对
   ▼
发布（上架）
     ⑧ PUT /wp-json/wc/v3/products/{id}（status=publish）
```

---

## 4. 详细步骤

### 4.1 步骤 1：1688 一键导入（AI OS 商品工作台）

> **入口**：Nuotao AI OS 系统（`https://admin.nuotaooutdoor.com`）→ **商品与 AI 选品** → **商品工作台** → **1688 一键导入**。

**操作**：
0. **检查登录态**：打开 `/products/pipeline` 后看右上角；若显示「未登录」（导入会报 `Not authenticated`），点击右上角「未登录」按钮 → 点「登录管理账号」→ 输入用户名/密码（浏览器已保存，用户名 `admin`）→ 点「进入控制台」→ 确认右上角变为 `user admin` 后再继续。
1. 打开浏览器（已登录 AI OS），进入 **商品与 AI 选品 → 商品工作台**（`/products/pipeline`）。
2. 在 **「1688 一键导入」** 输入框粘贴 1688 源产品链接（`https://detail.1688.com/offer/{offer_id}.html`）。
3. 点击 **导入**；系统按 SKU 反查（`NT-<offer_id>`），存在则更新、不存在则新建。
4. **导入完成上架**：导入成功后选择「上架至 WooCommerce」，系统推送 `list_to_woocommerce`（存在即 PUT 更新，否则 POST 新建）。

**要点**：
- 链接必须是 1688 商品详情页 URL（含 `offer/{offer_id}.html`），非搜索/列表页。
- **登录铁律**：1688 一键导入依赖 AI OS 登录态；右上角显示「未登录」时导入必失败（`Not authenticated`），必须先按操作 0 登录，禁止在未登录状态反复点导入。
- 一键导入依赖 `ALI1688_APP_KEY` 等 1688 开放平台凭据；若失败检查后端日志。
- 导入后回写本地 `meta.woocommerce_id`（`_remember_listed_product`），避免重复 POST 建新商品。

**错误处理（2026-01-15 实测）**：

#### ❌ 错误 1：未登录
- **现象**：点击导入后报 `Not authenticated`
- **原因**：未登录 AI OS 系统
- **解决**：按操作 0 登录后再导入

#### ❌ 错误 2：Scrapling 抓取失败
- **现象**：`1688 导入未完成 Scrapling failed and no hardcoded data for product {offer_id}`
- **原因**：1688 反爬虫机制导致 Scrapling 抓取失败
- **历史解决方案（已验证）**：**添加硬编码数据作为备选方案**

**硬编码数据解决方案步骤**：

1. **访问 1688 商品详情页**，获取以下信息：
   - 商品标题（中文 + 英文翻译）
   - 价格
   - 主图 URL（从页面 HTML 中提取 alicdn.com 图片链接）
   - SKU 列表（颜色/规格/库存）
   - 商品描述
   - 重量、尺寸
   - 属性（品牌、材质等）

2. **编辑硬编码数据文件**：`backend/app/services/scrape_1688.py`

3. **添加硬编码数据函数**（参考现有函数结构）：
   ```python
   def parse_1688_{product_name}_data() -> dict[str, Any]:
       """Return hardcoded data for {product_name} product ({offer_id})."""
       images = [
           "https://cbu01.alicdn.com/img/...",
           # 从 1688 页面提取的图片 URL
       ]
       sku_list = [
           {"skuName": "规格1", "name": "规格1", "price": "价格", "stock": 库存},
           # 所有 SKU 变体
       ]
       return {
           "source_url": "https://detail.1688.com/offer/{offer_id}.html",
           "source_id": "{offer_id}",
           "subject": "英文完整标题",
           "title": "英文简短标题",
           "price": "价格",
           "category_name": "中文类目",
           "images": images,
           "sku_list": sku_list,
           "description": "英文描述",
           "weight": "重量",
           "dimensions": "尺寸",
           "attributes": [
               {"name": "Brand", "value": "品牌"},
               # 其他属性
           ],
       }
   ```

4. **注册到 `_KNOWN_PRODUCTS` 字典**（在 `get_hardcoded_data` 函数中）：
   ```python
   _KNOWN_PRODUCTS: dict[str, dict[str, Any]] = {
       "844058953087": parse_1688_moon_chair_data(),
       "1054599709111": parse_1688_camping_pad_data(),
       # ... 其他已有产品
       "{offer_id}": parse_1688_{product_name}_data(),  # 新增
   }
   ```

5. **重启后端服务**：
   ```bash
   cd backend
   # 重启 uvicorn 或重新部署
   ```

6. **重新执行 1688 一键导入**

**已有硬编码产品列表**（`backend/app/services/scrape_1688.py`）：
- `844058953087` - Moon Chair（月亮椅）
- `1054599709111` - Camping Sleeping Pad（充气睡垫）
- `986492089515` - Heated Sleeping Pad（加热睡袋垫）
- `746435358585` - Ice Crampons（冰爪）
- `818076845448` - Tent Storage Bag（帐篷收纳袋）
- `964465929482` - Duka Headlamp（杜克头灯）

**注意事项**：
- ⚠️ 硬编码数据是临时方案，长期应修复 Scrapling 服务
- ⚠️ 所有数据必须来自真实 1688 页面，禁止编造
- ⚠️ 图片 URL 必须是可访问的 alicdn.com 链接
- ⚠️ SKU 列表必须完整（所有颜色/规格变体）

---

### 4.2 步骤 2：源产品参数提取

从 1688 源产品（`https://detail.1688.com/offer/{offer_id}.html`）提取真实参数：

| 参数 | 说明 | 示例（充气床垫） |
|---|---|---|
| offer_id | 1688 源商品 ID | `1054599709111` |
| SKU | `NT-<offer_id>`（红线） | `NT-1054599709111` |
| 品牌 | 供应商品牌 | nuotao |
| 材质 | 真实材质 | 40D Nylon TPU |
| 适用人数 | 1-2 人 | 1-2 人 |
| 尺寸 | Single/Double | Single / Double |
| 重量 | 净重（产品级取最大/打包规格） | Single 0.65kg / Double 1.4kg |
| 包装尺寸 | 收纳后尺寸 | Single 26×10×10cm / Double 33×14×14cm |
| 颜色数 | 全部颜色 | 13 色（8 单人 + 5 双人） |
| 充气方式 | 真实卖点 | 脚踩按压充气（免泵） |
| 功能 | 防水/防潮/便携 | 防潮防水、轻量便携 |

> ⚠️ **红线（无 AI 乱编）**：所有参数必须来自 1688 源链接 / 供应商快照；禁止编造材质、尺寸、重量、颜色等。图片快照参数（prompt.md）用于英文电商图与描述措辞，同样基于真实参数。

---

### 4.3 步骤 3：WooCommerce 产品创建（草稿）

```
POST https://nuotaooutdoor.com/wp-json/wc/v3/products
{
  "name": "<源产品名，或自然英文名>",
  "type": "variable",           // 多颜色/多尺寸 → variable
  "sku": "NT-<offer_id>",
  "status": "draft",            // 先草稿，质检通过后 publish
  "categories": [{"id": <cat_id>}],   // 真实分类
  "brand": "nuotao",
  "description": "...",
  "short_description": "...",
  "regular_price": "<美元价>",
  "images": [{"id": <media_id>}],
  "weight": "1.4",
  "dimensions": {"length":"33","width":"14","height":"14"}
}
```

- **status=draft** 先建草稿，待质检通过再 `publish`（防止未质检产品直接上线）。
- 返回 `id`（wc_id）与变体关系：变体需另行 POST `/products/{id}/variations`。

---

### 4.4 步骤 4：产品图片准备与上传

1. **白底图**：从 1688 源或供应商获取主图（白底 PNG/JPG）。
2. **英文电商图**：用图片快照参数（prompt.md，含产品名/卖点/材质/尺寸/颜色/场景）生成英文电商图（主图 + 卖点 + 细节 + 场景 + 尺寸规格，共 5 张）。

> ⚠️ **英文电商图必须在 ChatGPT 网页对话框生成**（不是 image_generate 服务不可用就跳过/降级用 1688 原图）。上次充气床垫/月亮椅/加热睡袋垫均用 ChatGPT 网页生成。

**ChatGPT 网页生成方法（加热睡袋垫 986492089515 实测）**：
1. 浏览器打开 `chatgpt.com`，进入**上次的「根据1688图片设计转化英文电商图片」对话**（沿用既有对话，不新建）。
2. **先发图片 URL 列表**（1688 主图 alicdn URL，5 张；来自 `scrape_1688.py` 兜底 `parse_1688_heating_sleeping_pad_data()` 的 `images` 字段）。
3. **再发 prompt.md 完整模板**（图片生成指令，5 张套图 + 锁定外观铁律）。
4. **复制粘贴 5 张不同的原图**（区分重复：先算感知哈希，相似度 ≥65% 视为重复，只留代表；如 01/04/05/06/07）进对话框（PowerShell `Clipboard.SetImage` + `bsk press Ctrl+V`，逐张）→ 发送。
5. 等 ChatGPT 用 PIL 基于**真实照片**处理（**禁止重新绘制商品本体**，只做抠图/背景/排版），生成 `01-main-image.png` 等 5 张 1600×1600。
6. 若供应商图出现**参数冲突**（如 30 Heating Zones vs 6 Heating Panels），ChatGPT 会采用**供应商详情图可证实**的（6 Panels）并提示确认；**以供应商资料为准**，避免臆测。
7. **下载**：ChatGPT 回复的「下载完整 ZIP 压缩包」→ 浏览器下载到本地（如 `D:\桌面文件夹\独立站\外贸\`），解压取 5 张 PNG。
3. **上传**：`POST /wp-json/wp/v2/media`（WordPress media，附 Authorization Basic base64(应用密码)），取得 media_id（本次 2758-2762）。
4. **设置**：`PUT /products/{id}` 设 `images[0]`（主图）+ `images[1..n]`（画廊）（本次产品 2743 已替换为 v2 英文电商图）。

---

### 4.5 步骤 5：产品参数完善

`PUT /wp-json/wc/v3/products/{id}` 更新：

| 字段 | 说明 | 本 SOP 要求 |
|---|---|---|
| `slug` | 固定链接 | 小写连字符英文（如 `foot-press-inflatable-sleeping-pad`） |
| `categories` | 产品分类 | 至少 1 个真实分类（如 `Sleeping Gear & Mattress` + `Sleeping Pads`） |
| `description` | 长描述 | ≥ 500 词；含目录（可选）+ 关键特性 + 规格表 + 使用场景 + 护理 + 包含物 |
| `tags` | 标签 | **英文**（如 camping / hiking / outdoor / inflatable sleeping pad / foot press inflation）；禁止中文标签 |
| `weight` | 重量 | 产品级取双人打包重量（kg） |
| `dimensions` | 尺寸 | 产品级取双人打包尺寸（cm） |
| `variations` | 变体 | 每颜色/尺寸 1 个变体，含对应重量/尺寸/价格 |
| `stock` | 库存 | 真实库存（如 53185） |

> ⚠️ **标签必须英文**：WC 前台标签显示中文会严重影响英文站点质量。

---

### 4.6 步骤 6：Rank Math SEO 优化

> ⚠️ **关键**：Rank Math 的 Focus Keyword / SEO Title / SEO Description 经 **WC REST API 不可写**（POST 接受但忽略 / 400）。**正确方法**：WP REST（`wp/v2`）可写 `_web` 后缀键（`_rank_math_focus_keyphrase` / `_rank_math_title_web` / `_rank_math_description_web`），但 **Rank Math 分析读无 `_web` 键**（`rank_math_focus_keyword` 等，仅浏览器可写）。**必须**通过产品编辑页浏览器操作（Edit Snippet 对话框 + Focus Keyword 字段 + Save Draft + reload 让 Rank Math 重新分析）。

**操作步骤（加热睡袋垫 986492089515 实测）**：
1. **Focus Keyword**（浏览器）：打开产品编辑页 → `rankMathEditor.focusKeywordField.props.updateKeywords("<核心词>")`（浏览器 console）→ Save Draft → reload。这会写入 Rank Math 分析用的焦点词键，Rank Math 识别后 Basic SEO 从 10/100 → 69/100 且 All Good。
2. **SEO Title**（浏览器 Edit Snippet）：点「Edit Snippet」→ `#rank-math-editor-title` 填 `<核心词> - <情感词> <数字> <卖点>`（如 `Heated Sleeping Bag Liner - Warm 3-Temp USB Camping Pad`，≤60 字符，含情感词 Warm + 数字 3-Temp）→ 点「Close」→ Save Draft。
3. **SEO Description**（浏览器 Edit Snippet）：`#rank-math-editor-description` 填 `<核心词> + 卖点`（≤160 字符）→ Close → Save Draft。
4. **`_web` 键兜底**（WP REST）：`PUT /wp-json/wp/v2/product/{id}` 的 `meta` 写 `_rank_math_focus_keyphrase` / `_rank_math_title_web` / `_rank_math_description_web`（前端 title/description 实际渲染用；Save Draft 会覆盖，**发布后重写一次**）。
5. **内容**：焦点词出现 ≥ 5 次（密度 ≥ 0.5%），首段含焦点词（空格分隔），含 DoFollow 外链 + 内链。
6. **每次修改后点 `#save-post`（Save Draft）+ reload** 保存，Rank Math 才会重新分析。

> ⚠️ **踩坑**：`bsk evaluate` 传含空格/引号的 JS 会被 PowerShell/bsk 拆参。**可靠方式**：用 node `child_process.spawnSync("bsk", ["evaluate","--session",sess,"--json", js], {encoding:"utf8"})`（JS 经 `ConvertTo-Json` 转义后写入 node 脚本文件执行）。

**SEO 评分目标**：
- Basic SEO：All Good（焦点词在标题/描述/URL/内容/首段 10%）
- Title Readability：All Good（情感词 + 数字）
- Content Readability：内容字数 ≥ 500
- 剩余「错误」若为插件/Pro 建议（Content AI 需 Pro、TOC 需插件）→ 非内容错误，可接受。

---

### 4.7 步骤 7：质量验收（编辑页 + 展示页）

**A. 产品编辑页核对**：

| 项 | 检查点 |
|---|---|
| 状态 | draft（发布前） |
| 名称 | 自然英文名（非 1688 营销名，如 `Foot-Press Inflatable Sleeping Pad 40D Nylon TPU Camping Air Mattress (Single / Double)`） |
| 固定链接 | `/product/<slug>/` |
| 描述 | ≥ 500 词，无乱编 |
| 标签 | 英文 |
| SKU / 库存 | `NT-<offer_id>` / 真实库存 |
| SEO | Basic SEO + Title Readability All Good |

**B. 产品展示页（前台）核对**：
- H1 = 产品名；面包屑同步
- 图片（主图 + 画廊）正常显示
- 价格区间、变体可选、Add to cart
- 描述完整、标签英文、SKU、分类、信任徽章

**C. noindex 检查**：`_rank_math_robots_noindex_web` 应为 `False`（可索引）。若为 `True`（draft 自动 noindex），发布后需在 Rank Math Advanced 页签关闭 noindex。

---

### 4.8 步骤 8：发布（上架）

```
PUT https://nuotaooutdoor.com/wp-json/wc/v3/products/{id}
{ "status": "publish" }
```

- 质检通过后发布（status=publish）。
- 发布后再次核对前台 URL（`/product/<slug>/`）正常渲染。
- 确认 `_rank_math_robots_noindex_web = False`（可索引）。

---

## 5. 关键错误与规避（实际踩坑）

| # | 错误 | 规避 |
|---|---|---|
| 1 | WC REST 写 Rank Math meta 400（`_rank_math_robots_noindex_web=""`、实际键 `rank_math_focus_keyword` 等） | Rank Math 字段仅经浏览器（Edit Snippet + Focus Keyword + Save Draft）可写 |
| 2 | `text=...` 选择器报 DOM Error（bsk 不支持） | 用 `bsk_inspect observe`（maxDepth≥8）找按钮 ref 后点击 |
| 3 | "Focus Keyword appears in first 10%" 报错 | 首段焦点词用空格分隔（`foot press inflatable sleeping pad`，非连字符） |
| 4 | 关键词密度过低 + 缺外链/内链 | 焦点词出现 ≥ 5 次 + DoFollow 外链 + 内链 |
| 5 | "Your title doesn't contain a word"（情感词） | SEO 标题加情感词 + 数字（如 `Easy 1-2 Person`） |
| 6 | "You don't seem to be using a TOC plugin" | 手动 HTML 目录不被 Rank Math 识别（需 TOC 插件）；属插件建议，非内容错误 |
| 7 | 间歇性"基础连接已经关闭" | TLS 1.2 强制 + 重试（GET 加 `?_cb=<random>` 绕缓存；PUT 不加） |
| 8 | 产品名过长（1688 营销名） | 改用自然英文名（基于真实参数，如 `Foot-Press Inflatable Sleeping Pad 40D Nylon TPU Camping Air Mattress (Single / Double)`） |
| 9 | 标签显示中文 | 必须英文标签（camping / hiking / outdoor 等） |
| 10 | pwsh 不支持 `??`；`$i:` 被当驱动器 | 用 `${i}:`；避免空合并 |
| 11 | 1688 一键导入依赖 `ALI1688_APP_KEY` | 后端日志检查凭据；导入后回写 `meta.woocommerce_id` 防重复 |
| 12 | Rank Math 焦点词经浏览器 Tagify 输入后 Save Draft 丢失（`rank_math_focus_keyword` 无 `_web` 键空） | 用 `rankMathEditor.focusKeywordField.props.updateKeywords("<词>")`（console）→ Save Draft → reload；Rank Math 识别焦点词（Basic SEO 10/100 → 69/100 All Good） |
| 13 | `bsk evaluate` 传含空格/引号 JS 被 PowerShell/bsk 拆参 | 用 node `spawnSync("bsk", ["evaluate",..., js])`，JS 经 `ConvertTo-Json` 转义写入 node 脚本文件执行 |
| 14 | `ConvertTo-Json` 长 HTML 序列化成嵌套对象 + UTF-8 BOM 导致 WP `rest_invalid_json` | 手动构造 JSON（转义 `\` `"` `\n`）+ UTF8 no-BOM 写文件 + curl `--data-binary @file` |
| 15 | Save Draft 覆盖 WP REST 写的 `_web` 键（Rank Math React 空状态提交） | 先浏览器 Edit Snippet + Save Draft 保存焦点词/标题/描述，再 WP REST 写 `_web` 键；发布后重写 `_web` 键确保前端 SEO 正确 |
| 16 | Rank Math「Add Focus Keyword to SEO title」等 5 错误（焦点词未识别） | 原因 = `rank_math_focus_keyword`（无 `_web`）空；用 #12 的 `updateKeywords` 修复 |

---

## 6. 验收清单（上架前）

- [ ] 1688 一键导入成功（AI OS 商品工作台，`NT-<offer_id>` 已入列）
- [ ] 产品参数与 1688 源一致（无 AI 乱编）
- [ ] slug / 分类 / 描述 / 标签 / 变体 / 重量尺寸正确
- [ ] 图片（主图 + 画廊）已设置
- [ ] Rank Math：Basic SEO All Good、Title Readability All Good
- [ ] 编辑页 + 展示页质量合格
- [ ] noindex 关闭（可索引）
- [ ] status=publish（上架完毕）

---

## 7. 修订记录

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.4 | 2026-10-30 | 步骤 4 补充英文电商图 **ChatGPT 网页生成方法**（沿用过对话、图片 URL 列表 + prompt.md、复制粘贴 5 张不同原图、PIL 基于真实照片不重绘、参数冲突以供应商为准、ZIP 下载到本地）；错误表补充图片重复/下载踩坑 |
| v1.3 | 2026-10-30 | 实测加热睡袋垫 NT-986492089515 上架；步骤 6 补充 Rank Math 正确方法（`updateKeywords` + WP REST `_web` 键兜底）；错误表新增 #12-#16 |
| v1.2 | 2026-10-29 | 新增「禁止跳过流程」铁律（严格按步骤 1→8 顺序，禁止跳过任何步骤；步骤 1 须 AI OS 登录） |
| v1.1 | 2026-10-29 | 新增步骤 1「1688 一键导入（AI OS 商品工作台）」；流程重排为 8 步；补充 `ALI1688_APP_KEY` 踩坑 |
| v1.0 | 2026-10-29 | 初版：依据充气床垫 NT-1054599709111 上架全流程（top1–top4）沉淀 |
