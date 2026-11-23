# M4 V2.6 Product / Variation 身份模型执行报告

> 版本：v2.6.0 | 执行人：`v26-identity-impl`（子代理）| 日期：2026-11-23

## 1. 交付物清单

| 文件 | 说明 |
|---|---|
| `app/models/product_mapping.py` | 三态身份 + 部分唯一索引 |
| `app/models/order.py` | OrderItem 变体关联 |
| `app/models/supply_chain.py` | InventorySnapshot 变体级库存 |
| `app/models/product.py` | ProductCost 变体维度 |
| `app/models/product_intelligence.py` | ProductCostSnapshot 变体维度 |
| `app/models/supplier_offer_mapping.py` | **新表** 供应商/Offer 映射 |
| `app/models/__init__.py` | 注册新模型 |
| `app/services/identity_model_v26.py` | 身份服务（三态判定 + 关联 + 回填） |
| `alembic/versions/0092_identity_model.py` | 迁移（**草稿，未执行**） |
| `tests/test_identity_model_v26.py` | 19 项测试（交付文件） |
| `tests/test_identity_model_v26_pg.py` | PG 集成测试（无 PG/Docker 时跳过） |
| `tests_v26/` | 本地隔离运行入口（独立 conftest） |
| `docs/PRICING_V2_6_IDENTITY_IMPLEMENTATION.md` | 实现文档 |
| `docs/PRICING_V2_6_ER_DIAGRAM.md` | ER 图 |
| `docs/PRICING_V2_6_SUPPLIER_OFFER_MAPPING.md` | 供应商/Offer 映射说明 |
| `docs/_audit/PRICING_V2_6_BUSINESS_RELATION_REFACTOR.md` | 业务关系重构报告 |
| `docs/_audit/PRICING_V2_6_71ROW_BACKFILL_REPORT.md` | 71 行回填报告 |
| `docs/_audit/PRICING_V2_6_EXECUTION_REPORT.md` | 本报告 |

## 2. 验证结果

| 项 | 结果 | 备注 |
|---|---|---|
| 单元/隔离测试 | **19 / 19 PASS** | SQLite 内存 + StaticPool；覆盖三态、唯一性、SKU、workspace 隔离、多 Offer、失效、冲突、Inventory、成本快照、回填幂等、migration 语法/元数据、event_log+trace_id、历史兼容、71 行分类 |
| Ruff | **通过** | 4 服务/模型文件 + 2 测试文件（migration 在 alembic 排除） |
| Migration 语法 | **通过** | `ast.parse` + 模型元数据 `create_all` |
| PG 集成测试 | **未运行** | 无可用 PG/Docker（testcontainers 未安装），文件按设计 `skipif` |
| 生产迁移 | **未执行** | 指令 §8；仅草稿 |
| 生产回填 | **未执行** | 指令 §8；隔离模拟验证 |

## 3. 环境与阻塞

- `backend/.env` 无 `DATABASE_URL`；`localhost:5432` 关闭；无 Docker CLI；testcontainers 未安装 → **PG 集成测试无法运行**。
- 共享 `tests/conftest.py` 顶层 `from app.api...` 触发 `slowapi 0.1.10` 与 `starlette 1.6.0` 不兼容（`Config._read_file()` 签名）→ 本地 pytest 无法加载共享 conftest。**非本次变更引起**。解决：新增 `tests_v26/`（独立 conftest，无 app.api import）作为本地运行入口；交付文件仍为 `tests/test_identity_model_v26.py`（CI/正确依赖版本下运行）。
- `tests_v26/test_identity_model_v26.py` 为 `from tests.test_identity_model_v26 import *` 复用入口。

## 4. 修复记录（开发中）

1. `product_mapping.py` UUID 类型：`postgresql.UUID` 在 SQLite 下 NUMERIC affinity 把全数字 UUID 转整数 → 改用跨方言 `Uuid`（PG 原生 UUID / SQLite CHAR(32)）。
2. 移除 `uq_product_mappings_workspace_nuotao`：一商品多变体映射所需。
3. `SupplierOfferMapping` 唯一性改「活跃行」部分唯一：允许历史 archived 与当前 mapped 同键共存。
4. `upsert_offer_mapping` 冲突分支逻辑修正（更旧请求整体归档，不落入 mapped）。
5. `backfill_71_rows` 内部归一化（`row_from_csv_row` 幂等），接受 CSV 原始行或归一化行。
6. datetime 统一 UTC 比较（SQLite naive vs PG aware）。

## 5. 合规确认（指令 §8 禁止项）

以下**均未执行**：生产 DB 迁移、生产回填、库存同步、WC API 写入、自动采购/加购、促销/价格/SKU 变更、规则变更、部署。全部仅模型/服务/测试/草稿迁移/隔离模拟。

## 6. 后续（需 Owner 授权）

- 迁移 0092 `upgrade`（生产前需 Owner 书面授权）。
- 生产 71 行回填（授权后执行，按 `PRICING_V2_6_71ROW_BACKFILL_REPORT.md` 结论）。
- PG 集成测试（需可用的 PG 或 Docker）。
- 提交/PR：由父代理（lead）统一处理。
