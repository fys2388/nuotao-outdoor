# B2C 电商事件追踪方案（GA4 Ecommerce）

> **D8-B 交付物** · GA4/GTM 现状审计 — 方案设计篇
> **日期**：2026-11-19
> **性质**：只读审计 + 方案设计，**未修改任何生产代码/配置**（Owner 未批准改配置）
> **范围**：B2C 商城 nuotaooutdoor.com（WordPress + WooCommerce）的 GA4 电商事件体系
> **关联文件**：`website-assets/nuotao-social-enhancements/includes/class-tracking.php`（B2C 追踪代码实际所在）

---

## 0. 执行摘要

B2C 商城当前通过 WP 插件 `nuotao-social-enhancements` 的 `class-tracking.php` 做三端打点（GA4 / Facebook Pixel / TikTok Pixel）。**已实现 3 个电商事件**（`view_item`、`add_to_cart`、`purchase`），但**结账漏斗中间环节完全无埋点**，且 GA4 与 Pixel 均为**无条件加载**（无 Cookie Consent、无 Consent Mode v2），存在 GDPR 合规风险（P0）。

本方案设计一套**完整的 B2C GA4 电商事件体系**（12 个标准事件），遵循 ChatGPT 硬性要求：唯一 `transaction_id` 防重复、金额/币种/商品 ID/数量准确、**绝不向 GA4 发送 PII**、WooCommerce 订单可与 GA4 购买事件对账。方案区分「补齐现有 WP 插件」与「新建」两类工作量，**全部实施需 Owner 批准后才执行**。

---

## 1. 现状基线（已读源码核实）

### 1.1 现有 GA4 事件（`class-tracking.php`）

| 事件 | 代码位置 | GA4 事件名 | 关键参数 | 状态 |
|---|---|---|---|---|
| 商品详情浏览 | `:146-205`，GA4 段 `:197` | `view_item` | `items`(id/name/price/quantity=1)、`value`、`currency` | ✅ 已有 |
| 加入购物车 | `:210-298`，GA4 段 `:285` | `add_to_cart` | `items`(id/name/price/quantity)、`value`(price×qty)、`currency` | ✅ 已有（经 PHP Session 中转，`wp_footer` 输出） |
| 购买 | `:303-372`，GA4 段 `:361` | `purchase` | `transaction_id`(=order_id `:362`)、`value`、`currency`、`items`、`tax`、`shipping` | ✅ 已有（挂 `woocommerce_thankyou`） |

FB Pixel（`:332` Purchase）与 TikTok Pixel（`:347` CompletePayment）同步打点。

### 1.2 关键结构性问题

- **GA4 注入无条件**：`inject_ga4()`（`:115-141`）直接 `gtag('config', ...)`，**无任何 consent 判断**，仅设置 `anonymize_ip: true`。GA4/Pixel 默认无条件加载。
- **GTM 未安装**：全站无 GTM 容器，追踪为**硬编码 PHP 注入**（`wp_head` 钩子，优先级 1/2/3）。
- **漏斗断层**：从 `add_to_cart` 直接跳到 `purchase`，中间 `view_cart → begin_checkout → add_shipping_info → add_payment_info` **零埋点**，无法定位结账流失。
- **列表/点击缺失**：无 `view_item_list`、`select_item`，无法分析品类/列表页转化。
- **无退款采集**：`refund` 完全缺失，GA4 收入无法与实际退款对冲。
- **无显式 `page_view` 业务埋点**：仅依赖 GA4 自动采集（ Enhanced Measurement），无自定义 `page_view`。

---

## 2. ChatGPT 硬性要求 → 设计约束（贯穿全方案）

| # | 硬性要求 | 本方案落地的设计约束 |
|---|---|---|
| H1 | `purchase` 必须用唯一 `transaction_id` 防刷新重复 | `transaction_id` = WooCommerce `order_id`（沿用 `:362`）；GA4 原生按 `transaction_id` 去重；**另加服务端一次性标记**（见 §4.3）双保险 |
| H2 | 金额、币种、商品 ID、数量准确 | `value`=订单实付总额（含税含运）；`currency`=订单币种（`get_currency()`）；`items[].id`=SKU 优先、回退 product_id（沿用 `:321`）；`quantity`=行项目数量 |
| H3 | 防止刷新页面导致重复 purchase | GA4 `transaction_id` 去重 + `order_meta` 写入 `_ga4_purchase_tracked` 标记，已标记则不再输出 purchase 脚本（需 Owner 批准） |
| H4 | 不得把测试事件算作真实收入 | 使用 **separate 测试 GA4 Property / 测试 stream** 或 GA4 DebugView；测试订单走独立 `transaction_id` 前缀（如 `TEST-`）并从正式报表过滤 |
| H5 | **不得将 PII 发送给 GA4** | GA4 事件**只发商品/金额/订单号**，禁止 `user_id`、email、name、address、phone；`transaction_id` 用 order_id（非 PII）；不调用 `gtag('set','user_data')` / User-ID |
| H6 | WooCommerce 订单数据与 GA4 购买事件可对账 | `transaction_id`=order_id 可一对一关联；`value`/`tax`/`shipping` 取自订单对象（`:315-316, :366-367`）；对账脚本按 `order_id` JOIN |

---

## 3. 完整事件清单（12 个 GA4 电商标准事件）

事件顺序 = 用户购物旅程。`items` 数组遵循 GA4 Ecommerce 规范：每项含 `item_id`（或 `item_name`）、`price`、`quantity`、`item_list_id`/`item_list_name`（列表类事件）、`item_category` 等。

> 命名说明：GA4 推荐用 `item_id`；现有代码用 `id`。为与 GA4 标准报表/对账兼容，**新建事件统一用 `item_id`**，现有 3 事件在补齐时同步迁移（需 Owner 批准，属破坏性变更需评估历史数据连续性）。

| # | 事件 | 触发时机 | 关键参数 | 现状 | 实施位置 | 类型 |
|---|---|---|---|---|---|---|
| E1 | `page_view` | 每次页面加载 | GA4 自动（Enhanced Measurement）+ 可选自定义 `page_type` | ⚠️ 仅自动采集 | WP 插件（可选增强） | 补齐 |
| E2 | `view_item_list` | 商品列表/分类/搜索结果页曝光 | `item_list_id`、`item_list_name`、`items[]` | ❌ 缺失 | WP 插件（WooCommerce archive 钩子） | 新建 |
| E3 | `select_item` | 用户点击列表中的商品 | `item_list_id`、`items[]`（单条） | ❌ 缺失 | WP 插件（列表项点击） | 新建 |
| E4 | `view_item` | 商品详情页曝光 | `items[]`、`value`、`currency` | ✅ 已有 `:197` | WP 插件 | 补齐（参数迁移 `item_id`） |
| E5 | `add_to_cart` | 加入购物车 | `items[]`、`value`(price×qty)、`currency` | ✅ 已有 `:285` | WP 插件 | 补齐 |
| E6 | `remove_from_cart` | 从购物车移除商品 | `items[]`、`value`、`currency` | ❌ 缺失 | WP 插件（AJAX 移除钩子） | 新建 |
| E7 | `view_cart` | 购物车页曝光 | `items[]`、`value`(小计)、`currency` | ❌ 缺失 | WP 插件（`woocommerce_cart` 页） | 新建 |
| E8 | `begin_checkout` | 进入结账第一步 | `items[]`、`value`、`currency`、`coupon` | ❌ 缺失 | WP 插件（`woocommerce_before_checkout_form`） | 新建 |
| E9 | `add_shipping_info` | 填写/选择配送方式后 | `items[]`、`value`、`currency`、`shipping_tier` | ❌ 缺失 | WP 插件（结账 shipping 段） | 新建 |
| E10 | `add_payment_info` | 选择/提交支付方式后 | `items[]`、`value`、`currency`、`payment_type` | ❌ 缺失 | WP 插件（结账 payment 段） | 新建 |
| E11 | `purchase` | 订单确认（thankyou 页） | `transaction_id`、`value`、`currency`、`items[]`、`tax`、`shipping`、`coupon` | ✅ 已有 `:361` | WP 插件 | 补齐（加去重标记） |
| E12 | `refund` | **仅真实退款发生时**（全/部分） | `transaction_id`、`value`、`currency`、`items[]`（部分退款） | ❌ 缺失 | WP 插件（`woocommerce_order_refunded`，**服务端**） | 新建 |

### 3.1 事件详解与设计要点

#### E1 `page_view`
- **触发**：GA4 Enhanced Measurement 自动采集为主。可选在 WP 插件对关键模板（product / cart / checkout / thankyou）补一个带 `page_type` 的自定义 `page_view`，便于漏斗分桶。
- **PII 约束**：不发送 URL 中的用户名、邮箱参数；GA4 默认可能采集页面路径，需在 GA4 后台做 PII 过滤策略（属配置项，需 Owner 批准）。

#### E2 `view_item_list`（新建）
- **触发**：WooCommerce 商品归档页 / 分类页 / 搜索结果页，列表渲染完成后，一次性发送可见商品（建议分批，避免单事件 items 过长）。
- **参数**：
  - `item_list_id`：如 `category_camping_tents`、`search_results`
  - `item_list_name`：如 "Camping Tents"
  - `items[]`：`[{item_id, item_name, price, item_category}]`，`quantity` 可省略或为 1
- **价值**：与 E3 配合计算列表 → 详情的点击率（`select_item / view_item_list`）。

#### E3 `select_item`（新建）
- **触发**：用户点击列表中某个商品卡（进入详情页前）。
- **参数**：`item_list_id`、`items[]`（被点单条）。
- **实现**：在列表项 `<a>` 上绑前端点击事件（dataLayer push 或 gtag），需 JS；纯 PHP 服务端难以精确捕获点击，建议前端 dataLayer 方案（若未来引入 GTM 则改由 GTM tag 触发）。

#### E4 `view_item`（补齐现有 `:197`）
- **现状**：已实现，参数用 `id/name/price/quantity`。
- **补齐点**：① 参数键迁移到 `item_id`；② `value` 确认 = 商品单价×1（当前 `:199` = `get_price()` 单价，正确）；③ 确认 `currency` 用站点币种（当前 `get_woocommerce_currency()`，单币种场景正确；多币种需改为所选币种）。

#### E5 `add_to_cart`（补齐现有 `:285`）
- **现状**：已实现，经 PHP Session → `wp_footer` 输出。`value`=price×qty（`:292`）正确。
- **补齐点**：① 参数键迁移 `item_id`；② **AJAX 加购场景**：当前依赖 `wp_footer` + Session，若主题为 AJAX 加购（不整页刷新）可能漏发或重复，需评估改为 JS 端 `added_to_cart` 事件监听；③ `session_start()` 手动调用（`:224`）需确认与 WP session 兼容、无副作用。

#### E6 `remove_from_cart`（新建）
- **触发**：购物车页/迷你购物车点击移除。
- **参数**：`items[]`（被移除项）、`value`（被移除金额）、`currency`。
- **实现**：WooCommerce 移除走 AJAX（`wc-ajax=remove_from_cart`），需前端 JS 监听或 `woocommerce_removed_coupon` 类钩子；建议前端 dataLayer。

#### E7 `view_cart`（新建）
- **触发**：`/cart/` 页（`is_cart()`）加载。
- **参数**：`items[]`（购物车全部商品）、`value`=购物车小计、`currency`。
- **实现**：挂 `woocommerce_before_cart` / `template_redirect`，服务端可拿到 `WC()->cart`。

#### E8 `begin_checkout`（新建）— **漏斗关键**
- **触发**：进入结账页（`is_checkout()` 且非 order-received）。
- **参数**：`items[]`、`value`、`currency`、`coupon`（若有）。
- **价值**：`begin_checkout → purchase` 转化率 = 核心结账流失指标。

#### E9 `add_shipping_info`（新建）
- **触发**：用户完成配送方式选择/更新。
- **参数**：新增 `shipping_tier`（如 `standard` / `express` / `dhl`）；其余同 E8。
- **实现**：结账页配送段 change 事件，前端 JS 捕获（服务端难精确）。

#### E10 `add_payment_info`（新建）
- **触发**：用户选择/提交支付方式。
- **参数**：新增 `payment_type`（如 `stripe` / `paypal` / `credit_card`）；其余同 E8。
- **实现**：结账页支付段 change / place_order 前事件，前端 JS。
- **PII 约束**：`payment_type` 只发**支付方式类别**，**绝不发送卡号、卡类型明细、账单地址**。

#### E11 `purchase`（补齐现有 `:361`）
- **现状**：已实现，`transaction_id`=order_id（`:362`），`value/tax/shipping` 取自订单（`:363-367`），结构良好。
- **补齐点（满足 H1/H3）**：
  - **去重**：GA4 原生按 `transaction_id` 去重（同 session）；**另加服务端标记**：`woocommerce_thankyou` 输出前检查 `order_meta('_ga4_purchase_tracked')`，已标记则跳过输出，未标记则输出并写标记。防止跨 session 刷新重复。
  - **参数迁移**：`items[]` 键迁移 `item_id`。
  - **coupon**：可补 `coupon` 参数（`$order->get_coupon_codes()`）。
  - **币种**：`$order->get_currency()`（`:316`）已正确（订单级币种，优于站点默认）。

#### E12 `refund`（新建）— **服务端采集，仅真实退款**
- **触发**：WooCommerce 后台真实执行退款（`woocommerce_order_refunded` 钩子）。
- **参数**：`transaction_id`（原 order_id）、`value`（退款额）、`currency`、全退时可不带 `items`、部分退时带 `items[]`（被退商品）。
- **关键**：**只在真实退款动作发生时触发**，不是按订单状态推测；服务端 `wp_remote_post` 发送（Measurement Protocol）或经 GTM server 端，避免依赖浏览器（退款发生在后台，用户不一定再访问站点）。
- **价值**：GA4 收入能与实际退款对冲，得到净收入，避免 ROAS 虚高。

---

## 4. 发现问题清单（5 要素表）

| ID | 发现 | 当前状态 | 证据 | 风险等级 | 建议方案 | 需 Owner 批准 |
|---|---|---|---|---|---|---|
| F1 | 结账漏斗中间事件全缺失（E7-E10） | `view_cart`/`begin_checkout`/`add_shipping_info`/`add_payment_info` 零埋点 | `class-tracking.php` 仅 3 个钩子（`:31-33`）；无 checkout 相关钩子 | **P1** | 按 §3 补建 E7-E10，还原完整漏斗，定位结账流失 | **是**（改生产追踪代码） |
| F2 | 列表/点击事件缺失（E2-E3） | 无法分析列表→详情转化 | 无 archive/list 相关代码 | P1 | 补建 `view_item_list`/`select_item` | **是** |
| F3 | 无退款采集（E12） | GA4 收入无法对冲退款 | 无 refund 代码 | P1 | 服务端 `woocommerce_order_refunded` 触发 `refund` | **是** |
| F4 | purchase 刷新重复风险 | 仅靠 GA4 原生 `transaction_id` 去重（同 session），无服务端标记 | `track_purchase` `:303-372` 无去重标记逻辑 | P1 | 加 `order_meta('_ga4_purchase_tracked')` 服务端一次性标记（H1/H3） | **是** |
| F5 | GA4/Pixel 无条件加载，无 Consent Mode v2 | `inject_ga4` `:115-141` 直接 config，无 consent 判断；无 Cookie Banner | 源码 `:131-137`；线上 HTML 无 consent | **P0（GDPR）** | 实施 Google Consent Mode v2 + Cookie Banner（CMP）；GA4 默认 denied，获同意后 granted（详见 B2B/B2C 架构报告） | **是**（P0 合规，优先） |
| F6 | 参数键 `id` 与 GA4 标准 `item_id` 不一致 | 现有 3 事件用 `id/name/price` | `:158-161, :287-290, :321-324` | P2 | 迁移到 `item_id` 以兼容 GA4 标准报表与对账；需评估历史数据连续性 | **是**（破坏性） |
| F7 | 无显式 `page_view` 业务埋点 | 仅 GA4 Enhanced Measurement 自动采集 | 无自定义 page_view | P2 | 可选：关键模板补 `page_type` 自定义 page_view | **是**（可选） |
| F8 | AJAX 加购可能漏发/重复 | `add_to_cart` 经 Session→`wp_footer`，依赖整页刷新 | `:223-235, :240-298` | P2 | 评估改为前端 `added_to_cart` 事件监听 | **是** |
| F9 | GTM 未安装，硬编码注入 | 全站无 GTM 容器 | 线上 HTML 无 gtm.js；追踪全在 PHP | P2 | 评估引入 GTM 统一管理 tag（与 F5 Consent 联动），或保持 PHP 注入但加 consent 层 | **是**（架构决策） |
| F10 | 多币种场景 `view_item`/`add_to_cart` 币种 | 用 `get_woocommerce_currency()`（站点默认）而非所选币种 | `:173, :187, :200, :253` | P2 | 若启用多币种（美国/德国/欧盟），改为用户所选币种；`purchase` 已用订单币种（正确） | **是** |

---

## 5. 实施工作量分类

### 5.1 补齐现有 WP 插件（改造 `class-tracking.php`）
- E4 `view_item`：参数迁移 `item_id`（F6）
- E5 `add_to_cart`：参数迁移 + AJAX 场景加固（F6/F8）
- E11 `purchase`：加服务端去重标记（F4）+ 参数迁移 + coupon（F6）
- E1 `page_view`：可选增强（F7）

### 5.2 新建（在 `class-tracking.php` 或新建专用 ecommerce-tracking 模块）
- E2 `view_item_list`、E3 `select_item`（F2）
- E6 `remove_from_cart`、E7 `view_cart`、E8 `begin_checkout`、E9 `add_shipping_info`、E10 `add_payment_info`（F1）
- E12 `refund`（F3，服务端）

### 5.3 前置依赖（需先决）
- **F5 Consent（P0）**：所有事件采集应在 Consent Mode v2 框架下进行，**建议先落地 Consent，再补事件**，避免补完事件仍不合规。
- **F9 GTM 决策**：决定 tag 管理方式（GTM vs PHP 注入），影响 E2/E3/E6/E9/E10 等前端事件的实现载体。

---

## 6. 对账方案（满足 H6）

1. **关联键**：`transaction_id` = WooCommerce `order_id`，可一对一。
2. **金额口径**：GA4 `purchase.value` = `order.get_total()`（实付，含税含运，`:315, :363`）；对账时 WooCommerce 侧用 `order_total`（同一口径）。
3. **对账方法**：导出 WooCommerce 订单（order_id, order_total, currency, date）与 GA4 `purchase` 事件（transaction_id, value, currency, date）按 `order_id=transaction_id` JOIN，核对金额差异；差异通常来自：退款（需 E12）、币种、时区、GA4 采样。
4. **净收入**：引入 E12 `refund` 后，GA4 收入 − refund = 净收入，方可用于 ROAS。
5. **PII 边界**：对账仅在内部（WooCommerce/DB/GA4 导出）按 order_id 进行，**GA4 侧不含 PII**，符合 H5。

---

## 7. 结论

- B2C GA4 电商**已有基础**（3 个核心事件，purchase 结构较完整，含 transaction_id/tax/shipping），但**漏斗断层严重**（结账中间 4 事件 + 列表 2 事件 + 退款全缺失），无法支撑转化优化与真实 ROAS。
- **最紧迫**是 F5（P0，GDPR Consent），建议在任何事件补齐前先落地 Consent Mode v2。
- 本方案为**设计文档**，所有改造（补齐/新建/去重/参数迁移）**均需 Owner 批准后**在下一阶段实施；本阶段**未修改任何生产代码或配置**。
- 建议实施顺序：① Consent Mode v2（P0）→ ② purchase 去重 + 对账打通（P1）→ ③ 结账漏斗 E7-E10（P1）→ ④ 列表/点击 E2-E3 + refund E12（P1）→ ⑤ 参数迁移/多币种/GTM 决策（P2）。

---

*本文档为 D8-B 方案设计交付物，仅作规划用途，未改动任何生产配置。实施需 Owner 显式批准。*
