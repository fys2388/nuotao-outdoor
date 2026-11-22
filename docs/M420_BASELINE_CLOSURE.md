# M4.2.0 基座收口报告

M4.2.0「基座收口」为 M4.2.1 供应商智能分析建立干净地基（路线图 §3，第 31 行前置约束）。
本报告记录 T0.1~T0.6 的最终状态、整改证据与验证结果。

## 任务状态总览

| 任务 | 内容 | 状态 | 落地位置 |
|---|---|---|---|
| T0.1 | 注册 Supply Chain Agent 骨架 + generic 路径 deprecated | ✅ | `agent_seed.py` 播种 + `supply_chain_analyst_prompt.py` + L2；`agents_generic.py` 标 deprecated |
| T0.2 | 统一采购单范式（DB 唯一真源 + 封堵直建 approved） | ✅ | PR #26 已合并（`procurement_service` 强制 draft） |
| T0.3 | 补齐事件审计 | ✅ | procurement/purchase_automation/fulfillment 均接 event_service + trace_id |
| T0.4 | 修 profit_margin 失效 bug | ✅ | `procurement_service.generate_procurement_suggestions` |
| T0.5 | 迁移基础数据模型 | ✅ | 迁移 0090/0091（risk_score/source/confidence/reorder_point/shipment 成本） |
| T0.6 | 基座测试 | ✅ | 负向测试 + 事件审计断言 + 迁移往返测试 + PG 真实迁移往返测试 |

## T0.4 profit_margin 修复（关键业务逻辑）

`generate_procurement_suggestions` 原有两处数据真实性缺陷（经 ChatGPT 复审核实）：

1. **profit_margin 赋 None 后从未计算** → high/medium 利润率判定是死代码。
2. **缺失成本被算成 100% 利润率** → `ProductCost` 不存在时 `unit_cost` 读作 0，
   `(售价-0)/售价=1.0` 会把未知成本误判为 high 优先级采购信号。

**修复**（区分「真实成本为 0」与「没有成本记录」）：
- `has_cost_record = cost is not None` 守卫：只有存在真实 `ProductCost` 记录才计算 `profit_margin`。
- 缺失成本记录 → `profit_margin=None`、`unit_cost=None`、`total_cost=None`，**未知保持未知**（不伪造 0，不升级 high/medium）。
- 真实零成本记录（`landed_cost=0`）→ 保留合法 0 语义，可算出 100% 毛利率。
- 售价来源：`product.meta["price"]` 优先、`sale_price` 回落；无效售价 fail-closed。
- 序列化：缺失成本的 `unit_cost`/`total_cost` 输出 JSON `null`（非 0）；summary 的 `total_estimated_cost` 跳过未知成本项。

## T0.5 数据模型迁移

迁移链 `0089 → 0090 → 0091`（`alembic heads=0091`），字段全 nullable（NULL=未量化/未标注，既有记录不被填伪造值）：
- `0090`：`supplier_profiles.risk_score`(+model_version/calibrated_at，M4.2.1 风险评分卡输入)、`product_cost.source`/`confidence`(M4.2.2)
- `0091`：`inventory_snapshots.reorder_point`(M4.2.4)、`shipment_records.promised_delivery`/`actual_cost`/`actual_cost_currency`(M4.2.4)

## 验证

- **回归**：M4.2.0 全量回归 60 passed（含 T0.4 修复 7 测试 + T0.5 迁移往返 5 测试 + PG 真实迁移往返 + T0.1/T0.2/R3 系列）。
- **PG 迁移往返**：`test_m420_t05_pg_migration.py` 对真实 PostgreSQL 执行 `upgrade 0089→0090→0091→downgrade 0089` 全链路，断言每步 revision、新列存在、既有行新列 NULL、downgrade 移除列。本地无 Postgres 时 skip，CI `postgres-concurrency` job 对真实 postgres:16 真跑。
- **ruff / py_compile**：全绿。
- **CI**：Backend·PostgreSQL dual-connection concurrency（真并发 + 迁移往返）+ smoke + Frontend build + Dependency Review + gitleaks 全 pass。

## 明确禁止（持续遵守）

未自动采购/审批/下单、未接真实支付、未部署生产、未改全局硬规则、未引入自动汇率、未扩展 M4.2.1。
