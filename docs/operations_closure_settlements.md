# 运营闭环补齐：回款台账 + 利润核算接入周报

> 版本：v1.0 · 2026-09-07
> 依据：P1-P2 评审后运营维度（70 分）修复主线，优先级第 1、2 项
> 关联：AGENTS.md 数据资产原则（结构化记录资金流）、决策铁律 5（禁止凭感觉）

## 1. 背景与断点

运营闭环链路（获客→转化→支付→履约→物流→**回款**→售后→**数据回流**→策略→获客）两处断裂：

| 断点 | 现状 | 后果 |
|------|------|------|
| 回款无台账 | 代码库无 settlement/对账模块；Correos COD 回款、匈牙利清关账单靠表格+邮件+人工追讨 | 资金流不可见、不可审计；哪单没回款、被扣什么费全部靠记忆 |
| 周报用模拟数据 | `weekly_report_service` 缺省走 `_generate_mock_business_data` | 决策数据底座为空，策略版本闭环（P2-⑨）无真实数据可喂 |

## 2. 设计

### 2.1 settlements 表（回款/结算台账）

| 字段 | 类型 | 说明 |
|------|------|------|
| id / workspace_id | Uuid | 主键 / 工作区隔离 |
| order_id | FK orders.id SET NULL | 关联订单（可空：物流费/清关账单可不挂订单） |
| external_order_id | String(64) | 外部单号冗余，对账用 |
| carrier | String(64) | 渠道：correos / clearance_hungary / stripe / paypal ... |
| settlement_kind | String(24) | cod 回款 / clearance 清关 / fee 杂费 / refund 退款 |
| expected_amount | Numeric(12,2) | 应回款 |
| received_amount | Numeric(12,2) | 实收（默认 0） |
| fees | Numeric(12,2) | 扣费（COD 手续费、清关杂费等） |
| currency | String(8) | 默认 USD |
| status | String(24) | expected 待收 / partial 部分回款 / received 已收 / disputed 争议 |
| due_date / received_at | Date / DateTime | 应回款日 / 实收时间 |
| note | Text | 争议说明、跟进记录 |

状态机：`expected → partial → received`（按实收金额推进）；争议单标记 `disputed` 保留待追讨。

### 2.2 服务层 settlement_service.py

- `register_settlement`：登记一笔应回款（金额、渠道、关联订单、到期日、备注）
- `record_receipt`：登记实收（金额、扣费），自动推进状态：
  - 实收 ≥ 应回款 → `received`
  - 0 < 实收 < 应回款 → `partial`（差额留待追讨）
- `list_settlements`：按 status / carrier / kind 筛选 + 分页
- `settlement_stats`：按状态汇总（待收笔数/金额、已收金额、争议金额）+ 按渠道分组

### 2.3 周报真实数据源 real_business_data.py

`build_business_data_from_db(session, week_start, week_end)` 从业务库聚合，输出与既有 mock 同构的 `key_metrics`：

- total_orders / total_revenue：orders 表按 received_at 区间
- gross_profit：Σ profit_snapshot.contribution_margin（订单入库即算，审计快照）
- gross_margin / avg_order_value / refund_rate
- ad_spend：Σ orders.advertising_cost（订单归因口径，文档注明）
- roas = revenue / ad_spend（ad_spend=0 → null）
- **新增回款指标**：settled_amount（已回款）、pending_settlement_amount（待回款 = Σ(expected−received)）、disputed_amount
- 输出携带 `data_source: "database"` 标记

### 2.4 周报 API 接线

`POST /api/v1/weekly-report/generate` 增加 `data_source` 参数：
- `auto`（默认）：优先从 DB 聚合真实数据；DB 空/失败时回退 mock 并显式标记 `data_source: "mock"`（**禁止模拟数据冒充真实**，AGENTS.md 铁律）
- `mock`：显式请求模拟数据（联调用）

### 2.5 前端

新增「回款台账」页（Settlements.tsx）：统计卡（待收/已收/争议）+ 状态筛选表格 + 登记/实收操作，模式复用 MemoryReview.tsx。

## 3. 验证计划（已执行）

- 单元测试 test_settlement_service.py：12 条（登记/实收状态机 full+partial+扣费口径/争议/列表筛选/统计汇总/周报真实数据源空库+有单/API 流程）✅ 全绿
- 全量 pytest（排除 integration）：601 项 ✅ 零失败
- 前端 npm run build（含回款台账页）✅ 构建成功
- 端到端探测：登记→实收 115.5+扣费 4.5=120 → received；100/300 → partial pending 200 ✅

### 状态机口径（已定）

- 实收 + 渠道扣费 ≥ 应回款 → `received`（全额结清）
- 0 < 实收 < 应回款 → `partial`（差额待追讨）
- 待收金额 = max(应回款 − 实收 − 扣费, 0)

## 4. 变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-09-07 | 回款台账 + 利润核算接入周报设计定稿 |
