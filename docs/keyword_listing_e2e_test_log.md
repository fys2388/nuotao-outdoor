# 关键词上架 E2E 测试记录（生产环境）

> 目标：在 `https://admin.nuotaooutdoor.com/dashboard` 前端系统内，测试"关键词上架"单个产品完整闭环。
> 记录过程中发现的 bug，先修再测，直到产品同步到 WooCommerce 端产品页达到 A++ 算闭环。
> 所有测试只在浏览器前端系统内进行。

## 测试环境

- 系统：Nuotao AI OS Production（admin 账号）
- 入口：`https://admin.nuotaooutdoor.com/dashboard` → 商品与 AI 选品 → 渠道与上架
- 目标产品：`Yueye Outdoor Moon Chair Foldable Portable Recliner...` SKU `NT-YUEYE-OUTDOO-09200123`
- WC 目标站：`https://nuotaooutdoor.com`

## 上架闭环定义（来自页面提示）

生成英文文案 → 人工审核批准 → 推送 WooCommerce → WC 端产品页 A++

后端强制校验：缺少已批准英文文案或无有效零售价时禁止推送。

## 初始状态快照（2026-09-20）

| 指标 | 值 |
|---|---|
| 草稿商品 | 27 |
| 待审 | 0 |
| 已发布 | 0 |
| WC 已同步 | 0 |

目标产品行状态：草稿 / 零售价缺失 / candidate / 英文文案缺失 / 未同步
"推送到 WC"按钮初始为 disabled（符合后端校验规则）。

## 上架流程（已阅读确认）

### 前端组件

生产前端 `渠道与上架` = `ProductPublish` 组件，数据源 `GET /api/v1/products?limit=200&offset=0`。

| 列 | 取值逻辑 |
|---|---|
| 零售价 | `meta.localizations.en.price` → `meta.price`；`Number.isFinite && > 0` 才显示，否则红标"缺失" |
| 候选状态 | `candidate_status`；空则橙标"未进入选品" |
| 英文文案 | `meta.localizations.en` 缺失→"缺失"；`status==="approved"`→"已批准"；否则"待审批" |
| WC同步 | `woocommerce_id`（顶层）或 `meta.woocommerce_id`；有→"已同步 #id" |

### 三步操作与 API

| 步骤 | 前端调用 | 说明 |
|---|---|---|
| 生成英文文案 | `N.generateProductCopy(productId)` | 提示"约 30-120 秒" |
| 审核并批准 | `N.approveProductLocalization(productId, "en")` | 弹 680 宽确认框展示英文标题/摘要/卖点 |
| 推送到 WC | `POST /api/v1/products/{id}/push-woocommerce`（可选 `?force=true`） | 先弹确认框，说明"先过 V3.0 选品闸门校验" |

### push-woocommerce 响应分支（生产实现）

| HTTP | 前端行为 |
|---|---|
| 2xx | `已推送：<name>`，刷新列表 |
| 409（未 force） | 弹"未通过 V3.0 选品闸门，需要人工复核"→"我已人工复核，强制放行"→ 重发 `?force=true` |
| 422 | 硬阻断，`V3.0 选品闸门阻断，禁止上架`（一票否决不可 force） |
| 其他 | 错误弹窗，含 traceId |

按钮可用性：`disabled = (copyStatus !== "approved")`；已有 `woocommerce_id` 则显示"已推送"且禁用。

### 本地仓库 vs 生产差异（重要）

- 本地仓库 `backend/app/api/v1/endpoints/products.py` 的 `push-woocommerce` **没有 V3.0 闸门**（直接 `push_product_to_woocommerce`）。
- 本地仓库无 `approve_product_localization` / V3.0 闸门 / `localizations.en` 文案存储实现。
- `git log HEAD..origin/main` 仅差 1 个 CI 提交，故生产代码含**未入库**变更，修复需以生产行为为准并补齐到仓库。

## Bug 记录

### BUG-01（Blocker）push-woocommerce 假成功：HTTP 200 但产品未创建、未写回 woocommerce_id

- **位置**：`POST /api/v1/products/{id}/push-woocommerce`（渠道与上架 → 推送到 WC）
- **产品**：Yueye Outdoor Moon Chair，id `f865672b-2d98-4233-90cc-03b97aa743f6`，SKU `NT-YUEYE-OUTDOO-09200123`
- **前置状态**：status=draft、零售价缺失（红标）、candidate_status=candidate、英文文案已批准
- **实测结果**：
  | 检查项 | 期望 | 实际 |
  |---|---|---|
  | HTTP 状态 | 4xx 闸门阻断（零售价缺失） | `200` |
  | 前端提示 | 闸门拦截 | 显示"已推送"，无异常 |
  | WC 已同步计数 | 0→1 | 仍为 `0` |
  | WC同步列 | `已同步 #id` | 仍 `未同步` |
  | 操作按钮 | `已推送`（禁用） | 仍 `推送到 WC`（可重复点击） |
  | WC 前台搜索 | 产品页可见 | `It seems we can't find what you're looking for.` |
- **影响**：违反页面自身声明的"后端强制校验：无有效零售价时禁止推送，不会以 0 元价格创建无法购买的商品"；操作员会误判上架成功；重试无限重复。
- **待定位**：响应体（是否 `success:false` 且前端未校验）、WC 端是否创建了 draft 产品。
- **状态**：⬜ 定位中

### BUG-02（Medium）AI 生成的英文文案缺少卖点（bullet points）

- **位置**：`POST /api/v1/products/{id}/generate-copy`
- **实测**：审批弹窗只渲染"英文标题 + 摘要"两行，无"卖点"区块。前端逻辑为 `n.bullets && n.bullets.length > 0` 才渲染，说明返回的 `bullets` 为空数组。
- **影响**：文案质量不完整；WooCommerce 前台缺少 bullet points，转化率受损。生成提示要求 5-6 条 bullet。
- **状态**：⬜ 待确认根因（LLM 未返回 vs 字段映射丢失）

### BUG-03（Medium）后端强制校验声明与实现不一致（闸门形同虚设）

- **位置**：渠道与上架页顶部 Alert
- **实测**：零售价"缺失" + 候选状态仅 `candidate`（未经 winner/approved 流程）+ 无六维 Nuotao Score，仍可通过推送。
- **说明**：本地仓库 `products.py` 的 `push-woocommerce` 完全没有 V3.0 闸门；生产环境也未拦截。前端确认弹窗宣称"会先过 V3.0 选品闸门校验""触发一票否决的商品会被硬阻断"。
### BUG-04（Architecture）渠道上架无准入闸门：数据裸入 products 表即可推 WC

**用户提问**：「产品相关数据都没完整怎么会触发去推送 WC？」→ 证实为设计断链。

- **取证 1**：`商品工作台` 页面工作流进度区显示「暂无数据 / 请在左侧输入商品信息并点击'一键运行'」。
  → 27 个草稿产品**从未经过工作台 7 步**（input → analysis → main_image → prompt → listing_data → v3_gate → listing），没有 AI 分析、无主图、无生图 Prompt、无 listing_data、无 v3_gate 结论、无成本快照。
- **取证 2**：`渠道与上架` 直接 `GET /api/v1/products?limit=200` 全量拉取，前端仅对 `status==='draft'` 过滤，**无任何完整性校验**。
- **取证 3**：推送到 WC 的实际前置条件只有 1 个 —— `copyStatus === "approved"`（按钮 disabled 逻辑）。
  而文案 approved 可被一键达成：生成（LLM 自动）→ 批准（仅一个确认弹窗，无需看零售价/成本/分析）。
- **结论**：设计的 ②AI分析 → ③工作台7步 → ④V3.0闸门 → ⑤候选审批 与 ⑦渠道上架之间**没有准入连接**。`candidate_status` 停留在 `candidate`（状态机要求 `winner → approved` 才可上架）被完全绕过。
- **影响**：27 个商品全部可在数据缺失状态下直接上架，页面声明的"后端强制校验"完全失效。
- **状态**：⬜ 待修复



## 根因链（BUG-01 已定位）

通过浏览器读取 `GET /api/v1/products?limit=1` 拿到产品完整 meta：

```json
"meta": {
  "source": "product_pipeline", "source_id": null,
  "sale_price": "15.80",          // ← 促销价
  "source_price": "7.9",          // ← 1688 采购价
  "source_url": null,
  "localizations": { "en": { "status": "approved",
    "title": "...", "description": "...",
    "seo_keywords": [12 个], "bullet_points": [6 条] } }
}
```

**无 `meta.price`、无 `meta.regular_price`、无 `woocommerce_id`。**

### 完整因果链

1. 选品 pipeline 落库时价格写入 `meta.sale_price` / `meta.source_price`，**未写 `meta.price` / `meta.regular_price`**。
2. 前端零售价读取逻辑：`meta.localizations.en.price → meta.price` → 两个都不存在 → 红标「缺失」。
3. `push-woocommerce` 无闸门 → 放行。
4. `push_product_to_woocommerce` 构建 WC payload：`regular_price` 空、`price` 空、仅 `sale_price=15.80`。
5. WooCommerce REST API 拒绝（sale price 必须低于 regular price / 缺 price）→ `raise_for_status()` 抛异常。
6. 异常被 catch，返回 `{"success": false, "error": ...}` **但 HTTP 仍为 200**。
7. 前端 `A()` 只判断 HTTP status，不校验 `success` 字段 → 误报「已推送」。
8. `woocommerce_id` 未写回 → 列表仍「未同步」，WC 已同步计数仍 0，WC 前台搜不到。

### 由此拆出的修复项

| ID | 缺陷 | 修复方向 |
|---|---|---|
| FIX-1 | 价格字段命名断层（写 `sale_price` / 读 `price`·`regular_price`） | 推送时把 `meta.sale_price` 映射为 WC `regular_price`；或统一落库字段名 |
| FIX-2 | push 失败仍返回 HTTP 200 | `success=false` 时抛 4xx（422 闸门 / 502 WC 调用失败） |
| FIX-3 | 前端不校验 `success` 字段 | `A()` 中检查 `s.success`，false 时走错误分支 |
| FIX-4 | 无准入闸门（零售价/candidate_status） | 实现 V3.0 闸门校验：零售价必须 > 0，否则 422 |
| FIX-5 | 前端读 `n.bullets`，后端写 `bullet_points` | 字段名统一为 `bullet_points`（数据实际有 6 条，仅显示层丢失） |

## 补充修复项（对照 `wc-product-upload` 字段规范发现）

对照仓库内 WooCommerce 产品上传字段规范复核现有 payload 后，发现原实现（`push_product_to_woocommerce`）
生成的 WC 商品是**空壳**，即使价格修好、成功创建，前台页也远达不到 A++：

| ID | 缺陷 | 规范依据 | 修复 |
|---|---|---|---|
| FIX-6 | payload 缺 `type: "simple"` | P0 必填 | 显式写入 |
| FIX-7 | payload 缺 `weight` / `dimensions` | P0，用于运费计算 | 读 `product.weight_kg` / `product.dimensions` |
| FIX-8 | payload 缺 `manage_stock` / `stock_quantity` / `stock_status` | P0 | 从 `meta` 读，缺省 `instock` + 100 |
| FIX-9 | payload 缺 `brand` / `attributes` | P1 推荐 | `brand` 非中文才写；`attributes` 仅多值项（单值非变体） |
| FIX-10 | payload 缺 `images` | P1，前台主图 | 读 `meta.images` → `[{"src": url}]` |
| FIX-11 | 中文分类名直接推送 → WC 建为 Uncategorized | 规范要求映射 term | 内置中文→英文分类映射表 |
| FIX-12 | 无中文文案拦截 | 规范：无已审核英文文案 + 含 CJK → blocked | 含 CJK 且无已批准英文本地化 → **422 硬阻断**（不可 force 覆盖） |
| FIX-13 | `candidate_status` 完全未参与上架准入 | M5.13 状态机 | `NULL`=已落地电商产品（放行）；非 `approved` → 409 |
| FIX-14 | 无文案质量下限 | 前台完整度 | 已批准英文描述 < 600 字符 → 409（thin_copy） |

### 闸门分级设计（最终实现）

| 级别 | HTTP | 可否 `?force=true` 覆盖 | 触发条件 |
|---|---|---|---|
| blocked | 422 | ❌ 不可 | `missing_sku`、`cjk_without_localization` |
| needs_review | 409 | ✅ 可（人工复核后放行） | `missing_price`、`unapproved_copy`、`unapproved_candidate`、`cjk_in_approved_copy`、`thin_copy` |
| passed | 200 | — | 全部通过 |

设计取舍：`missing_price` 归为 409 而非 422 —— 规范写的是"禁止以 0 元推送"，
但闸门语义是"需人工复核确认后放行"，符合 AGENTS.md「AI 是提议者不是执行者」。
真正的不可覆盖项只有 SKU 缺失（无渠道映射）与中文文案直推（合规红线）。

## A++ 定义（WC 前台产品页内容完整度评分）

| 维度 | 权重 | 满分标准 |
|---|---|---|
| 标题 | 10 | 英文标题存在、含核心关键词 |
| 长描述 | 20 | ≥ 600 字符，HTML 结构 |
| 短描述/卖点 | 10 | short_description + 卖点列表 |
| 主图 | 15 | ≥ 1 张有效主图 |
| 价格 | 10 | regular_price > 0，USD |
| 分类 | 10 | 非 Uncategorized |
| 品牌 | 5 | brand 已填 |
| SEO/标签 | 5 | tags/seo_keywords |
| 可购买性 | 10 | instock + 运费字段（weight/dimensions） |
| 属性 | 5 | 关键属性存在 |

映射：≥90 = A++，80-89 = A+，70-79 = A，60-69 = B+，<60 = B。
**图片是最大单项权重（15 分）**：27 个草稿产品未经过工作台「主图」步骤，
`meta.images` 预计为空 —— 这是 A++ 的主要风险点，需在测试中确认。

## 修复实现说明

采用**零覆盖精确补丁**（不 rsync、不全量替换任何生产文件），因为生产 checkout 含
未入库的服务器端代码（localizations 端点等），全量部署会使其 404：

1. **新增** `backend/app/services/listing_gate.py` —— 闸门 + 价格修复 + payload 构建
2. **新增** `backend/app/api/v1/endpoints/listing_publish.py` —— 带闸门的推送端点
3. **锚点插入** `backend/app/api/v1/router.py` —— 在 `products.router` **之前**注册
   同 `/products` prefix 的新 router，只覆盖 `POST /{id}/push-woocommerce` 一个路径，
   生产环境专属的 localizations/approve 端点保持原样
4. **锚点替换** `frontend/src/pages/ProductPublish.tsx` —— `.bullets` → `.bullet_points`
5. 全部改动先备份到 `/opt/nuotao/backups/listing-gate-<stamp>/`，锚点不匹配即中止

部署 workflow：`.github/workflows/hotfix-listing-gate.yml`（分支 `hotfix/listing-gate`）。
完整部署日志同时写入 `/var/www/nuotao/deploy-listing-gate.log`，
可通过 `https://admin.nuotaooutdoor.com/deploy-listing-gate.log` 在浏览器中读取。

## 步骤记录

（测试过程中追加）
