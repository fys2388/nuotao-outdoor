# STRIPE_PAYMENT_ARCHITECTURE_AUDIT.md — Stripe 支付架构审计（D8-A）

> **Nuotao AI OS · V2.1 第二阶段 D8-A（Stripe Test Mode 支付链路验证）· 交付物 1/5**
>
> 执行角色：DSH 技术负责人 / 支付集成工程师
> 审核人：ChatGPT（逐轮放行） · Owner：项目负责人
> 执行日期：2026-11-19
> 授权状态：OWNER APPROVED（仅 Test Mode，禁止 LIVE / 真实扣款）

---

## ⚠️ 报告状态：SUPERSEDED / CORRECTED（2026-11-19 纠偏）

> **本报告基于一个错误前提，其"根本性发现"与最终结论已被后续生产实测推翻。保留原文仅作历史记录，当前有效结论以下方纠偏块为准。**

### 错误前提

本报告在执行时**查错了服务器**：只审计了 Hetzner 服务器（Nuotao AI OS 后端）上的代码与配置，据此得出"Stripe 支付链路完全不存在、需从零自研"的结论。

### 纠偏后的真实情况（生产实测）

B2C 站点 **nuotaooutdoor.com 是独立托管的 WooCommerce**（不在 Hetzner 服务器上）。实测其 WooCommerce REST API `payment_gateways` 端点（HTTP 200）发现：

| 已启用支付网关 | 类型 | 模式 |
|---|---|---|
| `stripe` (Credit/Debit Card) | **WooCommerce 官方 Stripe Gateway 插件** | **LIVE（真实收款）** |
| `stripe_klarna` / `stripe_link` | Stripe 子支付方式 | LIVE |
| `woocommerce_payments` (Card) | WooPayments | LIVE |
| `woocommerce_payments_p24/wechat_pay/apple_pay/google_pay` | WooPayments 子方式 | LIVE |

### 纠偏后的正确结论

1. **Stripe 支付链路并非不存在，而是已由 WooCommerce 官方 Stripe Gateway 插件承担，且已在 LIVE 模式真实收款通畅。**
2. 本报告第 5 节主张的"从零构建完整自研 Stripe 链路"（自研 PaymentIntent / webhook / 前端 Stripe.js）**应作废**——官方插件已全包，正是审核人强调的"若官方支付插件能承担，就没必要重复开发一套支付系统"。
3. AI OS 后端 `integrations/payment.py` 的 Stripe 死代码（create_payment_intent / verify_stripe_webhook）：**不激活、不扩建**，清理留待技术债务评估。
4. 支付由 WooCommerce 官方插件负责；AI OS 仅通过 WooCommerce REST API / webhook 获取订单（该链路已验证通畅）。

### 最终状态标记

| 项 | 最终状态 |
|---|---|
| `WOOCOMMERCE_STRIPE_GATEWAY` | **VERIFIED_LIVE**（官方插件，LIVE 收款通畅） |
| `STRIPE_CUSTOM_IMPLEMENTATION`（自研路线） | **NOT_APPLICABLE / CLOSED** |
| 本报告自研构建主张 | **SUPERSEDED**（由本纠偏块取代） |
| Owner 决策 | 关闭 Stripe 自研路线，不动现有双支付插件 |

> 审核记录：ChatGPT 第六轮确认关闭 Stripe 自研路线；Owner 确认"两个都部署好，不用动"。本纠偏经 ChatGPT 第七轮要求修订（保留历史版本 + 纠偏说明，不得抹掉）。

---

## 0. 执行摘要（给审核人的一页结论）

D8-A 授权验证 Stripe Test Mode 支付链路。经**生产环境实测 + 后端/前端/webhook 全链路代码审查**，得到一个根本性发现：

> **Stripe 支付链路当前完全不存在——不是"已构建但未配置"，而是"仅有孤立函数定义、从未接入系统"。**

因此 D8-A 名义上的"验证支付链路"任务，其**验证对象当前不存在**。本报告如实记录架构现状、代码缺陷、构建完整链路所需的工作与硬阻塞，并就不改变既有成熟模块的前提下如何推进，向审核人提交决策请求（见第 7 节 Q1–Q3）。

本轮**未擅自开发**任何支付模块（遵守"禁止重建已有成熟的订单和支付模块"与"先规划后编码"铁律），暂停在配置检查 + 架构审计完成、发现硬阻塞、等待审核人决策。

---

## 1. 生产配置现状（实测 2026-11-19）

对生产环境 `/opt/nuotao-ai-os/backend/.env`（权限 600）实测，脱敏检查结果：

| 配置项 | 实测状态 | 说明 |
|---|---|---|
| `STRIPE_SECRET_KEY` | **未配置（len=0）** | 无 sk_test_/sk_live_ 值 |
| `STRIPE_PUBLISHABLE_KEY` | **未配置（len=0）** | 无 pk_test_/pk_live_ 值 |
| `STRIPE_WEBHOOK_SECRET` | **未配置（len=0）** | 无 whsec_ 值 |
| `PAYMENT_GATEWAY` | 未设置（默认 `woocommerce`） | 当前实际支付走 WooCommerce |
| `stripe` Python SDK | **未安装** | `create_payment_intent` 会抛 ImportError |

**测试/生产密钥混用检查**：不适用（三类密钥均为空，无 sk_test_ 与 sk_live_ 并存风险）。
**结论**：Stripe 三类密钥均未配置，进程启动时 `PAYMENT_GATEWAY` 解析为 `woocommerce`，系统当前通过 WooCommerce 处理支付。

---

## 2. 后端代码审查

### 2.1 集成层存在 Stripe 函数，但为**孤立死代码**

`backend/app/integrations/payment.py`（221 行）定义了：

| 函数 | 位置 | 调用情况（grep 全仓验证） |
|---|---|---|
| `create_payment_intent()` | L48 | **无任何 API 端点调用** |
| `verify_stripe_webhook()` | L171 | **无任何 webhook 路由调用** |
| `get_payment_config()` | L25 | 配置状态自省（未被支付主流程依赖） |
| `get_payment_status()` | L197 | 走 **WooCommerce API**（非 Stripe） |

- `create_payment_intent` 与 `verify_stripe_webhook` **仅被定义，从未被任何 router / service 调用**（`grep create_payment_intent|verify_stripe_webhook` 全仓仅命中定义处）。
- 即：支付创建与 webhook 验证能力存在于代码库，但**未接入任何 HTTP 端点**，属于未完成集成（dead code）。

### 2.2 Webhook 端点现状

`backend/app/api/v1/endpoints/webhooks.py`（199 行）：
- 实现 **WooCommerce webhook**（`X-Wc-Webhook-Signature` HMAC-SHA256 + Base64，ORDER_CREATED 通道，幂等 ingestion，trace_id 传播）。
- **不处理 Stripe webhook**（无 `/webhooks/stripe` 端点，无 `verify_stripe_webhook` 调用）。
- `webhooks_generic.py` / `wc_clickback.py` 亦无 Stripe 处理。

### 2.3 代码缺陷（即使配置凭证也会失败）

- `create_payment_intent`（L67-75）创建 PaymentIntent 时**未传 `idempotency_key`** → 直接违反 D8-A 第 2.2 场景"重复点击支付按钮 / 重复提交订单"与"同一支付事件多次到达幂等性"要求。修复需在创建时以 `order_id` 等派生幂等键。
- 模块级 `STRIPE_SECRET_KEY = os.getenv(...)`（L14-16）在进程启动时读取并固化 → 配置密钥后必须重启后端才生效（运维注意项）。
- `verify_stripe_webhook` 用 `stripe.Webhook.construct_event` 验签正确，但缺乏上游 webhook 端点与幂等落库逻辑（需构建）。

### 2.4 退款能力

`services/refund_service.py`（L384-516）支持 `provider == "stripe"` 分支，调用 `stripe.Refund.create`。同样依赖未配置的 `STRIPE_SECRET_KEY` 与未安装的 SDK。支付/退款 provider 枚举已含 `stripe|paypal|woocommerce|manual`（models/customer.py:225、schemas/refund.py:45）。

---

## 3. 前端代码审查

对 `frontend/src` 全量 grep（`stripe|Stripe|payment_intent|PaymentIntent|client_secret`）：

| 文件 | 命中性质 |
|---|---|
| `pages/ApiManagement.tsx` | **占位符 mock**（`sk_live_********************` 为演示字符串，非真实密钥） |
| `pages/CRM.tsx` / `pages/Settlements.tsx` | 演示用 mock 订单数据 / UI 下拉选项 |
| `pages/UnifiedAuthPage.tsx` | 营销文案（"✓ Stripe/PayPal安全支付"） |

**结论**：前端**无真实 Stripe.js 集成**——无 stripe.js 脚本加载、无 PaymentIntent `client_secret` 消费、无 Elements/Checkout 组件。全部为界面演示数据。

---

## 4. 支付一致性核验链现状

审核人要求的核验链：

```
Stripe Payment → WooCommerce Order → Nuotao AI OS Order → event_service → event_log → Business Analytics
```

现状逐段核对：

| 链路段 | 现状 |
|---|---|
| Stripe Payment | ❌ **不存在**（无凭证/无端点/SDK未装） |
| WooCommerce Order | ✅ 存在（WooCommerce 真实订单体系） |
| → AI OS Order（orders 表） | ✅ 已验证（D3：测试订单 #2922 落库，total=69） |
| → event_service / event_log | ⚠️ 架构存在，订单域接入情况待订单侧确认 |
| → Business Analytics | ⬜ 待真实运营数据（D4） |

**关键缺口**：核验链**最前端的 Stripe Payment 段完全缺失**。当前系统仅打通"WooCommerce Order → AI OS Order"，Stripe 作为独立支付源尚未接入。

---

## 5. 测试数据隔离现状（D8-A 第六节要求）

要求测试订单可识别 `test_mode / test_order / test_payment`。现状：
- AI OS orders 表当前**无 test_mode / test_payment 隔离标识字段**（D3 测试订单靠人工删除清理）。
- 若构建 Stripe Test 链路，需按"最小改动方案"评估订单结构增加测试隔离标识，禁止将测试订单计入真实经营数据。

---

## 6. 构建 D8-A 完整链路所需工作（阻塞清单）

在**不重建已有成熟订单/支付模块**前提下，补齐 Stripe Test Mode 链路需：

| # | 工作项 | 类型 | 阻塞 |
|---|---|---|---|
| 1 | **Stripe Test Mode 凭证**（`sk_test_` / `pk_test_` / `whsec_`） | 凭证 | 🔴 **硬阻塞：需 Owner 从 Stripe Dashboard 获取，DSH 无法自行生成** |
| 2 | 安装 `stripe` Python SDK | 依赖 | 🟡 需确认版本与依赖审计 |
| 3 | 后端：PaymentIntent 创建端点（含 `idempotency_key`） | 开发 | 🟡 需规划（先文档后编码） |
| 4 | 后端：Stripe webhook 端点（验签 + 幂等落库 + WooCommerce 订单映射 + trace_id） | 开发 | 🟡 需规划 |
| 5 | 修复 `create_payment_intent` 幂等缺陷（2.3） | 开发 | 🟡 随 #3 一并 |
| 6 | 订单测试隔离标识（第 5 节） | 开发/评估 | 🟡 需最小改动方案 |
| 7 | 前端：Stripe.js 集成（Elements/Checkout） | 开发 | 🟡 需规划 |
| 8 | 15 场景支付测试 + Webhook/退款/对账验证 | 验证 | 🔴 依赖 #1–#7 完成 |

🔴 硬阻塞：#1 Stripe Test Mode 凭证必须由 Owner 提供，DSH 无 Stripe 账户访问权限。

---

## 7. 需审核人决策的三个问题（DSH 暂停处）

| # | 问题 | 背景 |
|---|---|---|
| **Q1** | D8-A 范围是"验证现有链路"还是"构建+验证"？ | 现状链路不存在；若要验证必须先构建 #2–#7 |
| **Q2** | Stripe Test Mode 凭证由谁提供？Nuotao 是否已有 Stripe 账户？ | 硬阻塞 #1；无凭证则 15 场景测试均无法执行 |
| **Q3** | 凭证到位前，是否先构建后端端点骨架 + 前端集成（占位/隔离，不碰生产支付开关）？ | 或等凭证到位再整体开发 |

---

## 8. 遵守的禁止事项（本轮自检）

- ✅ 未切换 Stripe LIVE
- ✅ 未使用真实银行卡 / 真实扣款 / 真实退款
- ✅ 未修改真实客户订单 / 真实发货
- ✅ 未将测试数据混入真实经营数据
- ✅ 未在日志/Git 泄露 Stripe Secret Key（本报告全程脱敏，密钥仅前 8 位且当前为空）
- ✅ 未重建已有成熟的订单和支付模块（仅审计，未开发）
- ✅ 测试环境与生产配置无混用（Stripe 全未配置，无混用风险）

---

## 9. 交付物清单（D8-A 5 份）

| # | 报告 | 状态 |
|---|---|---|
| 1 | **STRIPE_PAYMENT_ARCHITECTURE_AUDIT.md**（本报告） | ✅ 已产出 |
| 2 | STRIPE_TEST_MODE_EXECUTION_REPORT.md | ⬜ 阻塞（需凭证） |
| 3 | STRIPE_WEBHOOK_VERIFICATION_REPORT.md | ⬜ 阻塞（需凭证+端点） |
| 4 | STRIPE_ORDER_RECONCILIATION_REPORT.md | ⬜ 阻塞（需链路） |
| 5 | STRIPE_REMAINING_RISKS.md | ⬜ 待 #2–#4 后汇总 |

---

## 10. Git / 回滚

- 本报告为文档新增，无代码/配置/数据库变更，无需回滚。
- 生产未做任何 Stripe 改动（密钥仍空、SDK 仍未装、无新端点），生产支付仍走 WooCommerce，状态与审计前一致。

---

**DSH 执行状态**：D8-A 2.1 配置检查 + 支付架构审计完成，发现根本阻塞（链路不存在 + 需 Owner 提供 Test Mode 凭证）。遵守执行纪律，暂停等待审核人对 Q1–Q3 的决策，未擅自进入 GA4/SEO/数据初始化。
