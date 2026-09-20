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

### 第 2 轮：推送链路加固（2026-09-20 07:4x–08:1x UTC）

**最终闭环结果：后端链路全通，前端 UI 拿到真实 200，DB 与 WC 双向一致。**

| 时间 (UTC) | 事件 |
|---|---|
| 08:09:15 | 闸门 `needs_review` → HTTP 409（UI 弹「未通过 V3.0 选品闸门，需要人工复核」） |
| 08:09:15 | 点击「我已人工复核，强制放行」→ `POST .../push-woocommerce?force=true` |
| 08:10:01 | 后端写入 `listing_published_at` |
| 08:10:02 | nginx `200 550`；前端 toast「已推送：商品」 |

总耗时 47s（含 Cloudflare 抖动重试），前端 120s 超时内，不再出现假超时。

**最终一致状态（权威读回）**

| 项 | DB | WooCommerce 2106 |
|---|---|---|
| `woocommerce_id` | `2106` ✅（此前始终为 `None`） | — |
| `listing_published_by` | `listing_publish_gate` ✅ | — |
| `listing_published_price` | `15.8` ✅ | `regular_price: '15.8'` ✅ |
| `listing_published_at` | `2026-09-20T08:10:01Z` ✅ | — |
| 分类 | — | `Camping (id 223)` ✅（此前为 `Lighting`） |
| SKU | `NT-YUEYE-OUTDOO-09200123` | 同；`x-wp-total = 1`（**无重复**，幂等成立） |
| 长/短描述 | — | 1000 / 114 字符 ✅ |
| 标签 | — | 12 个 ✅ |
| 库存 | — | `instock` + `manage_stock` + 100 ✅ |

#### 本轮新增 bug 与修复

| 编号 | 问题 | 影响 | 修复 |
|---|---|---|---|
| BUG-05 | 前端「零售价」列对全部 27 行显示「缺失」，即使 `meta.sale_price` 存在 | 展示层误导，运营无法核对价格 | **未修**。取值链为 `meta.localizations.en.price` → `meta.price`，而真实价格在 `meta.sale_price`（字符串 `"15.80"`）。后端 `resolve_prices` 已正确读到，故不影响闸门与推送 |
| BUG-06 | Cloudflare 在 TLS 握手中途断开（`SSLEOFError(8, UNEXPECTED_EOF_WHILE_READING)`），单次窗口内 4/8 失败 | 推送随机假失败 | `_wc_call` 对 `ConnectionError`/`Timeout`/5xx 重试；4xx 立即抛出 |
| BUG-07 | 重试**非幂等**：WC 已提交后连接被撕断，重试撞 400 `product_invalid_sku` → 假失败，且 `woocommerce_id` 从未落库 | 重试反而造成长期假未同步 | `_find_wc_id_by_sku` 按 SKU 认领既有产品，把 create 降级为 update |
| BUG-08 | `categories: [{"name": "Camping"}]` 被 WC **静默忽略**，产品留在 `Uncategorized` | 分类 10 分全丢 | `_ensure_wc_category`：GET 列表解析 term id，不存在则 POST 创建，推送 `[{"id": N}]` |
| BUG-09 | `_TITLE_CATEGORY_RULES` 用子串匹配，`Lightweight` 含 `light` → Moon Chair 被分到 `Lighting` | 分类 10 分且语义错误 | 词边界正则 `\b(...)\b` + `light(?!weight\|\s+weight)` 负向前瞻（11/11 用例通过） |
| BUG-10 | 502 响应丢弃 WC 错误体，前端只看到"请求失败" | 无法定位根因 | `_wc_error_detail` 提取 `(status, body[:1000])`，502 detail 附 `woocommerce_status` / `woocommerce_error` / `attempts` / `submitted_payload` |
| BUG-11 | 前端 axios 默认 30s 超时 < 后端最坏 75s，后端已 200 但 UI 报「请求超时，请检查网络或后端服务状态」 | 用户看到假失败 | `ProductPublish.tsx` 推送调用显式 `{ method: 'POST', timeoutMs: 120000 }` |
| **BUG-12** | **`product.meta = meta` 对 JSON 列完全无效**：`flush()` 一条 UPDATE 都不发，`woocommerce_id` 每次推送都被静默丢弃 | **最严重**。整条推送链路看似成功、实则从不上报 WC id | 见下 |

#### BUG-12 根因（实测定位，非推断）

`Product.meta` 映射为 `mapped_column(AI_JSON)`，而 `app/models/` 全目录**没有任何 `MutableDict` / `MutableList`**。

逐步排除，全部用真实产品行 + 可回滚测试键验证：

1. `source_url`（普通字符串列）ORM 写入 → **正常持久化** → 排除"数据库只读/副本"假设；
2. `p.meta = meta`（同对象）→ 不写入；`p.meta = dict(meta)`（新对象）→ 不写入；原地改 dict 不重赋值 → 不写入；
3. 挂 `before_cursor_execute` 事件监听：`await s.flush()` **只发出初始 SELECT，零 UPDATE** → 不是"发了但被回滚"，是 ORM 根本认为无变更；
4. `flag_modified(p, "meta")` → **写入成功**；bulk `update(Product).values(meta=...)` → **写入成功**。

结论：必须显式 `flag_modified(product, "meta")`。这是 SQLAlchemy 对非可追踪 JSON 列的官方用法。

> 附带发现（待查）：同样的 `product.meta = meta` 写法出现在
> `woocommerce_sync_service.py` 第 949 / 1152 / 1193 行。若同一行为在 legacy 同步链路也成立，
> 则**整个旧同步路径也从未持久化过 `woocommerce_id`**。本轮未逐一验证，登记为待查项，不据此改动生产代码。

#### 本轮部署

- 备份：`/opt/nuotao/backups/listing-gate-<stamp>/`（每次部署前逐个 `cp -a`）
- 新增/替换：`listing_gate.py`、`listing_publish.py`、`ProductPublish.tsx`（1 处，锚点唯一才替换）
- 校验：`compileall` → `systemctl restart nuotao-backend` → `/api/v1/readyz = 200`
  → 前端 `npm run build` → 部署 `/var/www/nuotao` → grep 确认三处改动均在线上
- 注：`/readyz` 在 404，正确健康端点是 `/api/v1/readyz`（首轮部署脚本误用，已修正认知）

## 诚实评分：65 / 100（B+），**未达到 A++**

```
[+] 10  标题
[+] 20  长描述        1000 字符
[+] 10  短描述
[ ] 15  主图          payload images=None
[+] 10  价格          '15.8'
[+] 10  分类          Camping (id 223)
[ ]  5  品牌          DB 无 brand 来源
[+]  5  SEO 标签      12 个
[ ] 10  可购买性      weight=None dimensions=None（管道实际下发值）
[ ]  5  属性          build_wc_payload 完全不产出 attributes
                   65 / 100
```

> **纠正上一轮的 75 分**：那 10 分可购买性来自我在诊断期对 WC 2106 手工 PUT 的
> `weight=0.900` / `dimensions`，**管道本身从未产出这些值**。分类当时还是错的 `Lighting`。

### A++ 缺口无法诚实补齐 —— 数据源头缺失，不是代码 bug

目标产品（`product_pipeline` 来源）在库内：

```
product.weight_kg = None      product.dimensions = None
product.tags      = []        product.attributes = {}
meta.images       = None      meta.brand = None
meta.source_id    = None      meta.source_url = None
```

`meta.source = "product_pipeline"`，但 `source_id` / `source_url` 均为 `None`，
即**没有 1688 源头链接可回抓**。`woocommerce_draft_payloads`、`creative_assets` 表 0 行。
WC 侧 `wp/v2/media` 用 WC key 认证返回 `invalid_username`，只能走 `images: [{"src": url}]`。

按 AGENTS.md「禁止凭感觉」，主图（15）、品牌（5）、可购性（10）、属性（5）
共 **35 分缺口不能靠编造数据补上**。这是数据管道上游断点，需产品侧决策。

### 遗留问题（需决策，不自行处置）

1. **WC 2106 携带诊断残留数据**：`weight='0.900'`、`dimensions={60×40×115}`、`stock_quantity=100`
   来自我诊断期的手工 PUT。管道 payload 实际下发 `weight=None / dimensions=None`，
   WC 因此保留旧值。这属于线上商品数据污染，需确认是清除还是保留。
2. **`product.status = draft`** → payload `status='draft'` → WC 产品为 `draft`，
   **前台商店不可见**。若要"上架"需将产品状态推进为 `active`（涉及 M5.13 状态机与审批，未擅自改动）。
3. **BUG-05**（前端零售价列全显示「缺失」）未修，属展示层。
4. **legacy `woocommerce_sync_service.py` 三处 `product.meta = meta`** 未验证、未改动。
5. **INFO 级日志在线上不可见**：服务日志级别为 WARNING，本轮"Adopting existing product" /
   "Linked WooCommerce product" 等关键动作 INFO 行全部被过滤，直接导致 BUG-07/BUG-12 排查多绕数轮。
   建议线上后端日志级别调到 INFO（配置项，非代码）。

## 第 3 轮：上游数据管道断点定位（2026-09-20 08:4x UTC）

> 决策：①先修上游管道 ②清除 WC 残留 ③保持 draft。

### BUG-13：管道算出的媒体/分类数据从不落库（已修复并上线）

`product_pipeline_service.py` 内部链路：

| 函数 | 产出 |
|---|---|
| `_fetch_1688_product` | `name / category / price / weight / dimensions / images[:10] / source_url / source_id` |
| `_generate_listing_data` | `images`（1688 原图 + AI 生图）、`main_images`、`tags`、`categories` |
| `run_v3_gate` | **只取了 `sku / name / description / weight_kg`，其余全部丢弃** |

`listing_data` 仅作为 `steps_result["listing_data"]` 返回给调用方，**从未写入产品行**。
`build_wc_payload` 对 `images / attributes / brand / weight / dimensions` 的条件式映射其实早已写对，
只是上游永远给不出数据。

**全量普查（28 行）**：`have images=0 / tags=0 / attributes=0 / brand=0 / weight_kg=0 / dimensions=0`。
**A++ 缺口是系统性的，不是单个产品的问题。**

**修复（已部署，备份 `listing-gate-20260920T084121Z`）**

1. `listing_gate.py` 新增 4 个纯函数：`normalise_listing_images` / `normalise_listing_tags`
   / `parse_dimensions` / `collect_attributes`，全部返回空而非编造；
   `parse_dimensions` 对 `60*40*115`、`60 x 40 x 115`、`60,40,115 cm`、`尺寸 60*40*115` 均正确解析，
   不足 3 个数值一律返回 `None`。
2. `run_v3_gate` 锚点补丁（落在 626–666 行）：把 `listing_data.main_images`、`listing_data.tags`、
   `collect_attributes(product_info)`、`parse_dimensions(product_info.dimensions)` 写入产品行，
   并对每个 JSON 列调用 `flag_modified`（沿用第 2 轮已在线上验证的模式）。
3. `build_wc_payload` 属性映射放开单值属性：原 `len(value) > 1` 会丢弃全部非变体属性，
   即使命中属性也是 0。现 `1 <= len(options) <= 10`，属性总数封顶 8，图片封顶 10。

**验证**：readyz 200、模块导入通过、`chair → Camping`、`lantern → Lighting`（第 2 轮修复未回退）；
单值属性与图片进入 payload 均为 `True`。

### BUG-12 结论修正

第 2 轮判定"`product.meta = meta` 静默丢写、必须 `flag_modified`"。第 3 轮用同一产品行复测：
在标准 `async with async_session_factory()` 会话中，`tags / attributes / dimensions / meta`
**四种写法（原地改 / 新对象 / `flag_modified` / bulk update）全部持久化成功**。
真正失效的是我测试脚本里 `s = async_session_factory()` + 手动 `s.close()` 的会话生命周期。

结论：`flag_modified` 不是通用必需项，但在第 2 轮的端点路径上确实是让 `woocommerce_id` 落库的那一步，
且防御性无害。**线上代码保持 `flag_modified` 不动。**

### BUG-14：A++ 缺口的真正根因 —— 1688 开放平台凭据 ACL 失效（需人工处理）

对一条带 `source_url` 的产品跑**生产环境的真实抓取**（无 LLM 调用、不写任何产品行）：

```
success : False
error   : 'gw.APIACLDecline: AppKey is not allowed(acl)
           （开放平台：gw.APIACLDecline: AppKey is not allowed(acl)）'
data_source : 1688_open_api
stderr:  1688 product detail failed: gw.APIACLDecline: AppKey is not allowed(acl)
```

**1688 Open API 的 AppKey 已失去 ACL 授权**，抓取返回 `success=False`、无 `product_info`。
这就是全部 28 个产品都没有图片/属性/重量/品牌的根本原因，**不是代码 bug，无法从代码侧修复**，
需在 1688 开放平台后台为当前 AppKey 重新申请/开通商品详情接口 ACL 权限。

同时发现：**18 条"有 source_url"的产品全部指向同一个 1688 offer `771641344658`**
（`NT-QINGYE-OUTDOO-09181748`、`NT-HIGH-MOON-09181750`、`NT-HIGH-MOON-09181827`、
`NT-WILDFU-MOON-09191408` 等），属重复建档，需另开清理任务。

### 未解决：WC 残留无法用合法路径清除

`weight='0.900'`、`dimensions={60×40×115}` 两次尝试清除均失败：

| 尝试 | 结果 |
|---|---|
| 顶层 `{"weight":"","length":"","width":"","height":""}` | 200，但值未变（且嵌套结构写错） |
| 嵌套空串 `{"dimensions":{"length":"","width":"","height":""}}` | 200，值未变 |
| 嵌套 null | **400** `rest_invalid_type: dimensions[length] is not of type string` |

WooCommerce REST v3 中空字符串语义是「不修改」，null 被类型校验拒绝——
**无法通过 PUT 清空 `weight` / `dimensions`**。而 AGENTS.md §1.4 明令「禁止直接改其数据库」。
残留只能保留（已在评分中剔除，不计入 10 分可购性），或删除后重建产品（会丢 permalink 与 term 关联，未获授权）。

### 当前诚实状态

- 同步链路闭环：**完成**。DB ↔ WC ↔ UI 三环一致（前端「WC 已同步」0 → 1，目标行「已同步 #2106」「已推送」）。
- A++：**65 / 100（B+），未达到**。缺口 35 分（主图 15 + 可购性 10 + 品牌 5 + 属性 5）。
- 阻塞项：BUG-14（1688 AppKey ACL）——外部凭据问题，需人工到 1688 开放平台处理。
- BUG-13 修复已上线，**一旦 1688 权限恢复并重跑管道，图片/属性/重量将自动落库**，无需再改代码。

## 第 4 轮：牛顿链路定位与上游解锁（2026-09-20 10:0x UTC）

> 用户纠偏：1688 官方 API 根本不可用，牛顿才是唯一通道。据此重新定位。

### BUG-14 结论修正

第 3 轮把根因归为「1688 AppKey ACL 失效」。实际 `_fetch_1688_product`（1391 行）逻辑是：

```
Step 2: 优先使用牛顿 Agent 读取商品（1688 官方 API 权限不足）
        → 牛顿失败才降级到开放 API
```

即**开放 API 是兜底、且本就无权限，ACL 被拒是设计预期**。真正失败的是牛顿。
归因修正：**根因是牛顿超时，属代码缺陷，可修**。

### BUG-15：牛顿超时窗口过短（已修复上线）

实测同一商品真实抓取：

```
extract_1688_product(max_wait=90)  → elapsed 53s   success=True
extract_1688_product(max_wait=300) → elapsed 114s  success=True
```

`max_wait=90` 而真实耗时可达 114s → **必然误报超时**，即第 3 轮观察到的
`Newton product extraction timed out`。已改为 `max_wait=300`，保留超时后 `kill_task` 清理。
积分配额 5000，`qwen3.6-plus` 为合法默认模型（`isDefault: true`）。

### BUG-16：属性表被硬编码为空（已修复上线）

`_normalize_extracted_product` 原为 `"attributes": []`，牛顿 prompt 也未索取，
因此 `product_info["attributes"]` 恒为 `[]`，weight / dimensions / materials 全部落空。
已改为原样透传 `data.get("attributes")`。

### BUG-17：转换层不携带属性表（已修复上线）

`convert_1688_to_pipeline_input` 解析了属性表（派生 materials/dimensions/weight），
但 return dict 未包含 `attributes`，`collect_attributes` 永远读不到。已补 `"attributes": attributes`。

### 增强 prompt 实测（离线验证，符合 §3.4 先评测再上线）

加入 `"attributes": [{name, value}]` 并要求完整搬运「商品属性 / 产品参数」表格后，
同一商品实测（208s，22 条属性）：

```
{"name": "重量(g)",        "value": "1800"}
{"name": "规格(长*宽*高)",  "value": "47cm*47cm*90cm"}
{"name": "包装长(cm)",      "value": "92"}        ← 另含宽/高 = 16/16
{"name": "材质",           "value": "牛津布,碳钢"}
{"name": "品牌",           "value": "怡佳文嫣"}
{"name": "颜色",           "value": "高靠背绿色,高靠背白色,..."}
{"name": "产地",           "value": "河北廊坊"}
```

附带收益：`description` 由标题变为真描述（"600D牛津布耐磨抗撕…承重240斤"），
`category` 拿到 `户外/露营/折叠椅`，`images` 由 1 张增至 5 张。

### BUG-18：重量单位被读错一千倍（已修复上线）

`convert_1688_to_pipeline_input` 只取属性值、不读属性名里的单位。
`{"name": "重量(g)", "value": "1800"}` → `_parse_weight_kg("1800")` → **1800 kg**，
实际应为 1.8 kg。按公斤计费时运费误差可达三个数量级。已改为把单位一并带给解析器：

```python
unit_match = re.search(r"[(（]([^)）]{1,6})[)）]", attr_name_raw)
weight = f"{attr.get('value', '')} {unit_match.group(1).strip() if unit_match else ''}".strip()
```

单测 7 例全过：`1800 g→1.800`、`500g→0.500`、`0.5kg→0.5`、`1.2千克→1.2`、
`2公斤→2`、`1800→1800`、`3 lbs→3`（未知单位保持原行为）。

### BUG-19：尺寸取了产品规格而非包装箱（已修复上线）

1688 同时给产品规格（47×47×90）与包装尺寸（92×16×16）。运费按**外包装**计费，
取产品规格使体积重虚高约 20 倍。已改为优先 `包装长/宽/高`，缺省才退回 `规格/尺寸`。

### 部署纪律修正

第 4b 轮补丁脚本在锚点未命中时 `sys.exit(1)`，但部署脚本未检查子脚本退出码，
导致「prompt 已改、重量未改」却报告成功。第 4c 轮起改用 `PATCH_OK` 哨兵断言，
未见即回滚。

### 行为验证（合成真实属性表，全部通过）

```
weight raw     : '1800 g' -> kg = 1.800                    ✅
dimensions     : '92*16*16'（包装箱，非产品规格）          ✅
parse_dimensions: {length:92.0, width:16.0, height:16.0}   ✅
attributes     : 9 entries                                  ✅
materials      : ['牛津布,碳钢']                            ✅
category       : 户外/露营/折叠椅                           ✅
```

### 已部署（备份 `listing-gate-20260920T100037Z` / `T100642Z` / `T101100Z`）

- `newton_agent_service.py`：`max_wait` 90→300、attributes 透传、prompt 索取属性表
- `product_pipeline_service.py`：attributes 保留、重量单位修正、包装尺寸优先

每轮均 COMPILE_OK + 单测通过 + readyz 200。

### 单位统一与遗留

按用户指令统一到 kg：`_parse_weight_kg` 输出 kg，payload 直接下发该值。
**未完成**：WC 店铺级 `weight_unit` / `dimension_unit` 不在 `/wc/v3/settings` 内
（实测该端点仅 36 项且无任何单位字段），需 WP 用户权限读取，而现有 key 仅能访问
`wc/v3/*`。故 WC 后台「设置 → 常规 → 计量单位」需人工确认为 kg / cm，否则数值仍会被误读。

### 明确不做

- **不自动写 `product.brand`**：1688 同时返回 `有可授权的自有品牌: 否`，
  品牌名「怡佳文嫣」无授权依据，按 §3.1「Agent 是提议者不是执行者」留给人工。
- **不编造**：数据源无字段时按 §1.2 留空。
