# WOOCOMMERCE_API_CONNECTIVITY_AUDIT.md — WooCommerce API 连接审计（D8-A2）

> **Nuotao AI OS · V2.1 · 任务 D8-A2（P0）· 交付物 1/6**
> 执行角色：DSH 技术负责人 · 审核人：ChatGPT · Owner：项目负责人
> 执行日期：2026-11-19
> 授权状态：OWNER APPROVED

---

## 0. 执行摘要

D8-A2 由一个疑似生产故障触发：AI OS 后端调 WooCommerce REST API 返回 **HTTP 401 "Consumer Secret Invalid"**，ChatGPT 据此下达"修复 WooCommerce API 连接"任务。

经生产环境**多次复测与精确诊断**，得出结论：

> **WooCommerce consumer key/secret 完全有效，AI OS ↔ WooCommerce API 连接正常，无需修复。**
> 触发本任务的那次 401 是**一次性偶发误报**（同一凭证复测 3+ 次全部 200）。

本报告如实记录诊断过程、证据与结论，并澄清 D8-A2 的真实范围。

---

## 1. 诊断背景

| 项 | 内容 |
|---|---|
| 触发现象 | AI OS 后端调 `GET /wp-json/wc/v3/payment_gateways` 返回 HTTP 401，`message: "Consumer secret is invalid."` |
| 疑似问题 | AI OS 配置的 `WOOCOMMERCE_CONSUMER_KEY/SECRET` 失效 |
| 任务 | D8-A2：恢复 WooCommerce↔AI OS 生产数据连接，验证订单同步可靠、正确、幂等 |

---

## 2. 环境拓扑澄清（重要纠偏）

诊断初期曾误判"未安装 WooCommerce Stripe 插件"，根因是**查错服务器**。澄清后的真实拓扑：

| 组件 | 部署位置 | 说明 |
|---|---|---|
| **WooCommerce B2C 站点**（nuotaooutdoor.com） | **独立托管**（非 Hetzner） | WordPress + WooCommerce + 官方 Stripe Gateway 插件 + WooPayments |
| **Nuotao AI OS 后端** | Hetzner 95.217.218.178（uvicorn:8000） | 通过 WooCommerce REST API 远程读取订单/商品 |
| AI OS 与 WC 关系 | 跨服务器 REST API 调用 | AI OS 经公网 HTTPS 调 nuotaooutdoor.com 的 `/wp-json/wc/v3/*` |

**关键**：WooCommerce 站点与 AI OS 后端不在同一台服务器，AI OS 通过 REST API（consumer key 认证）访问 WC。

---

## 3. 诊断过程与证据

### 3.1 consumer key/secret 有效性复测

对生产 `.env` 中的 `WOOCOMMERCE_CONSUMER_KEY`（`ck_` 前缀，len 43）与 `WOOCOMMERCE_CONSUMER_SECRET`（`cs_` 前缀，len 43）多次实测：

| 端点 | consumer key 结果 | 应用密码结果 |
|---|---|---|
| `orders?per_page=1` | **HTTP 200**（count=0） | HTTP 200 |
| `products?per_page=1` | **HTTP 200**（count=1） | HTTP 200 |
| `payment_gateways` | **HTTP 200 ×3**（连续 3 次复测） | HTTP 200 |
| `settings` | **HTTP 200** | — |
| `settings/general` | **HTTP 200** | — |
| `reports/top_sellers` | **HTTP 200** | — |
| `system_status` | — | HTTP 200 |

### 3.2 原始 401 异常登记（按 ChatGPT 第七轮要求补充）

#### 3.2.1 异常发生记录

| 项 | 内容 |
|---|---|
| 发生时间 | 2026-11-19（D8-A2 首次连接诊断时） |
| 请求端点 | `GET https://nuotaooutdoor.com/wp-json/wc/v3/payment_gateways` |
| 认证方式 | WooCommerce Consumer Key/Secret（HTTP Basic） |
| HTTP 状态码 | **401** |
| 响应摘要 | `{"code":"woocommerce_rest_authentication_error","message":"Consumer secret is invalid.","data":{"status":401}}` |
| 当时结论 | 据此怀疑 consumer key/secret 失效，触发本任务 |

#### 3.2.2 后续连续成功请求记录（同一凭证，未更换）

| 时间 | 端点 | HTTP 状态码 | 备注 |
|---|---|---|---|
| 2026-11-19 | `GET /wc/v3/payment_gateways` | **200** | 第 1 次复测 |
| 2026-11-19 | `GET /wc/v3/payment_gateways` | **200** | 第 2 次复测 |
| 2026-11-19 | `GET /wc/v3/payment_gateways` | **200** | 第 3 次复测 |
| 2026-11-19 | `GET /wc/v3/orders?per_page=1` | **200** | count=0 |
| 2026-11-19 | `GET /wc/v3/products?per_page=1` | **200** | count=1 |
| 2026-11-19 | `GET /wc/v3/settings` | **200** | |
| 2026-11-19 | `GET /wc/v3/settings/general` | **200** | |
| 2026-11-19 | `GET /wc/v3/reports/top_sellers` | **200** | |

#### 3.2.3 凭证状态与根因判定

- **当前凭证未更换**：整个诊断过程中 `WOOCOMMERCE_CONSUMER_KEY/SECRET` 保持原值，未轮换、未重新生成。
- **暂不认定根因**：原始 401 归类为**一次性偶发异常**，但**不能直接认定为网络瞬断或 WooCommerce 故障**——目前没有足够证据确定根因。
- **后续处置**：通过监控观察是否复现。若复现，再深入排查（网络路径、WooCommerce 服务端状态、请求时序等）。
- **状态标记**：原始 401 = **MONITORED**（保留记录，观察复现）；当前连接 = **VERIFIED**。

> ChatGPT 第七轮审核要求："一次性 401 可以暂时归类为偶发异常，但不能直接认定为网络瞬断或 WooCommerce 故障，因为目前没有足够证据确定根因。"本节据此如实登记，不臆断根因。

### 3.3 凭证格式检查

- `consumer_key`：`ck_` 前缀，长度 43 ✅ 格式正确
- `consumer_secret`：`cs_` 前缀，长度 43 ✅ 格式正确
- 无空格/截断/编码问题

---

## 4. 结论

| 结论项 | 判定 |
|---|---|
| WooCommerce consumer key/secret 是否失效 | ❌ **未失效，完全有效** |
| AI OS ↔ WooCommerce API 连接 | ✅ **正常**（orders/products/settings 均可达） |
| 是否需要修复 key | ❌ **无需修复**（key 没坏，401 是偶发误报） |
| 是否需要轮换 key | ❌ 本轮不需要（无安全事件触发轮换） |
| 订单同步核心链路（orders/products） | ✅ API 层面**通畅** |

---

## 5. 订单同步端到端验证的当前限制

虽然 API 连接正常，但**订单同步的端到端验证当前受限**：

| 项 | 现状 |
|---|---|
| WooCommerce 订单数 | **0**（此前 D3 测试订单 #2922 已清理，无真实订单） |
| WooCommerce 商品数 | 1 |
| 端到端订单同步验证 | ⬜ **无法执行**（无真实订单可同步） |

订单同步的"稳定、正确、幂等"端到端验证，需待 **WooCommerce 有真实订单**后执行（关联 D4 生产运营数据）。

---

## 6. 支付网关现状记录（本轮只记录，不修改）

经 `payment_gateways` 实测，B2C 站点已启用 8 个支付网关，其中两套卡支付系统并存：

| 网关 | 类型 | 模式 |
|---|---|---|
| `stripe` (Credit/Debit Card) | WooCommerce 官方 Stripe Gateway | LIVE |
| `stripe_klarna` / `stripe_link` | Stripe 子支付方式 | LIVE |
| `woocommerce_payments` (Card) | WooPayments | LIVE |
| `woocommerce_payments_p24/wechat_pay/apple_pay/google_pay` | WooPayments 子方式 | LIVE |

- `stripe` 与 `woocommerce_payments` 两套卡支付**均 LIVE**，Owner 确认"两个都部署好，不用动"。
- **本轮不修改**，仅记录现状。潜在关注点（供后续评估，不在本轮处理）：结账页是否同时展示两个卡入口、是否存在重复支付/Webhook 冲突风险。

---

## 7. 对 D8-A2 范围的建议

基于诊断结论，建议调整 D8-A2：

| 原 D8-A2 假设 | 实际 | 建议 |
|---|---|---|
| WooCommerce API key 失效（401） | key 有效，401 偶发误报 | 无需"修复 key"/"轮换 key" |
| 需恢复中断的连接 | 连接正常 | 标记"连接已通" |
| 验证订单同步 | orders=0，无法端到端验证 | 待真实订单（D4）后验证 |

**建议**：D8-A2 的"连接恢复"部分标记完成（本就正常）；"订单同步端到端验证"部分待 WooCommerce 有真实订单后执行。避免在无真实订单时用测试订单污染生产（遵守"禁止真实扣款/污染真实数据"）。

---

## 8. 遵守的禁止事项（本轮自检）

- ✅ 未修改 WooCommerce 支付配置 / 密钥 / API key
- ✅ 未撤销或轮换任何 key（无安全事件，且 key 有效）
- ✅ 未创建测试订单 / 未真实扣款 / 未修改真实订单
- ✅ 未改动 WooCommerce 双卡支付配置（Owner 要求不动）
- ✅ 只读诊断，未对 WooCommerce 或 AI OS 做任何写操作

---

## 9. 交付物清单（D8-A2）

| # | 报告 | 状态 |
|---|---|---|
| 1 | **WOOCOMMERCE_API_CONNECTIVITY_AUDIT.md**（本报告） | ✅ 已产出 |
| 2 | WOOCOMMERCE_API_KEY_ROTATION_REPORT.md | N/A（key 有效，无需轮换） |
| 3 | WOOCOMMERCE_API_PRODUCTION_VERIFICATION.md | 待端到端（需真实订单） |
| 4 | ORDER_SYNC_RELIABILITY_REPORT.md | 待端到端（需真实订单） |
| 5 | STRIPE_PAYMENT_ARCHITECTURE_CORRECTION.md | 待产出（纠正此前审计） |
| 6 | D8_A2_EXECUTION_SUMMARY.md | 待产出 |

---

**DSH 执行状态**：D8-A2 连接审计完成。结论：WooCommerce API 连接正常（consumer key 有效，401 偶发误报），无需修复。订单同步端到端验证待真实订单。等待 ChatGPT 对 D8-A2 范围调整的确认与下一步指令。
