# D8-F 实现报告｜商品数据真实性与采集供应链升级

> 阶段：D8-F 实施总结。日期：2026-11-20。执行：DSH (sensenova)。
> 配套：`D8F_P0_DATA_TRUST_AUDIT.md`（审计）、`D8F_ARCHITECTURE.md`（架构）、`D8F_TEST_REPORT.md`（测试）。
> 核心原则：宁可少采集一个商品，也不能让虚假商品信息进入选品/利润分析/上架/采购决策。
> 铁律：不另起证据标准，与现有 E0-E5（M334）打通。授权内实施：代码/迁移/测试/文档/PR；未做生产部署/批量改生产数据/自动采购/付费API/提取凭据。

---

## 1. 交付概览（4 个 PR，全部合并 main，CI 通过）

| PR | 内容 | 阶段 |
|---|---|---|
| #16 | 审计报告 + 架构蓝图 + migration 0088（provenance DB 字段） | P0-1/P0-2 |
| #17 | 统一 Provider 接口 + ManualProvider + 删 price=35.8 + 白名单闸门 | P0-3/P0-4 |
| #18 | 下游 provenance 贯通（convert 透传 + listing_gate unauthentic_source） | P1-1（C5/C6） |
| #19 | legacy 端点鉴权 + 移除 newton 伪造定价 + Orchestrator fail-closed | P1-1（C2/C3/C4） |

## 2. 六阶段完成情况

| 阶段 | 目标 | 实现 | 状态 |
|---|---|---|---|
| ① 审计 | 摸清真实性门禁缺口 | `D8F_P0_DATA_TRUST_AUDIT.md`：N1-N7 + R1-R7 + C1-C7，双子代理交叉验证 | ✅ |
| ② 字段级来源追溯 | provider/source_reference/collected_at/evidence_grade/trace_id | `data_providers/base.py` 的 `ProductProvenance`/`FieldProvenance`；migration 0088 给 products 加 `data_source/collected_at/evidence_grade/provenance`；`Product` 模型同步 | ✅ |
| ③ 标准化人工 Provider | 不依赖 Cookie，collect/normalize/validate/get_provenance | `I1688ProductProvider` 协议 + `ManualProvider`（is_real=True 但 evidence_grade=E0；占位名/价格≤0 fail-closed） | ✅ |
| ④ fail-closed 覆盖 10 异常 | 见 §3 映射表 | 价格缺失/占位名/hardcoded_fallback/登录墙/来源不可追溯等，闸门白名单 + listing_gate HARD_BLOCK | ✅ |
| ⑤ 接入 E0-E5 | 不另起标准，禁止跳跃，商品级≠字段级 | `EvidenceGrade` 枚举（E0-E5，复用 M334）；ManualProvider 初始 E0；字段级 `field_provenance[*].is_verified` 独立于商品级 | ✅ |
| ⑥ 测试+回归+PR | Ruff + 原有测试全通过 | `test_d8f_data_trust.py` 19 用例 + 回归 46+ passed；CI Pre-check 全绿 | ✅ |

## 3. 10 类异常 → fail-closed 实现映射

| # | 异常 | 检测/处置 | 位置 |
|---|---|---|---|
| 1 | Cookie 失效 | 抓取失败/占位 → data_source 非 scrapling → import 闸门拦 + ManualProvider 兜底 | `product_pipeline_service.import_from_1688` |
| 2 | 登录墙 | 登录墙占位/unknown 来源 → 闸门拦（白名单外一律拦） | 同上 :3206 |
| 3 | 占位名 | `_PLACEHOLDER_NAMES` 黑名单 + 极短名 → validate 拒 | `manual.py.validate` |
| 4 | 价格为空 | price≤0 → ManualProvider 拒；**删除 scrape_1688 price=35.8 伪造** | `manual.py` + `scrape_1688.py` |
| 5 | 规格缺失 | 不伪造 SKU；无规格仍可建档（基础信息真实），不阻断 | `manual.py.normalize` |
| 6 | 页面 ID 不匹配 | 来源 reference 记录 offer_id，可校验（存量逻辑 + provenance.source_reference） | `product_source_identity` + provenance |
| 7 | 解析器不兼容 | generic 判定含 price≤0 → 走 fallback/fail-closed | `product_pipeline_service` generic |
| 8 | 原始数据不可追溯 | listing_gate 拦 data_source 缺失；provenance 强制记录 provider/时间/trace_id | `listing_gate` + `base.py` |
| 9 | 来源冲突 | 白名单只认 scrapling/1688_open_api/manual，其余标记人审 | import 闸门 + listing_gate |
| 10 | hardcoded_fallback 意外调用 | import 闸门白名单拦（无论 auto_run_pipeline）；listing_gate HARD_BLOCK `unauthentic_source` 不可 force | `import_from_1688` + `listing_gate` |

## 4. 关键代码改动

**新增**
- `backend/app/services/data_providers/{__init__,base,manual}.py`：Provider 接口 + 来源追溯模型 + ManualProvider
- `backend/alembic/versions/0088_product_provenance_fields.py`：products 加 4 个 provenance 字段（可空不回填）
- `backend/tests/test_d8f_data_trust.py`：10 异常 + E0-E5 专项测试

**修复（堵审计缺口）**
- `scrape_1688.py`：删 price=35.8 伪造（N1 最高危）
- `product_pipeline_service.py`：generic 判定补 price≤0（两处）；import 闸门白名单化；`convert` 透传 data_source/is_authentic；`_generate_listing_data` 透传来源标记
- `listing_gate.py`：HARD_BLOCK 加 `unauthentic_source`（Product 行 + dict 两路径，不可 force）
- `product_listing.py`：legacy 4 端点补 `CurrentUser` 鉴权（C2 Critical）
- `newton_sourcing_storage.py`：移除 `×3/min$5` 伪造定价，改 `pricing_policy.suggested_retail_price`（C4）
- `pipeline_orchestrator.py`：pricing 不再返回硬编码 $29.99（fail-closed）；listing 查业务结果（C3）

## 5. 合规与边界

- **未做**：生产部署、批量改生产数据、自动采购、付费 API、提取凭据（授权禁止项全部未触碰）。
- migration 0088 只加可空列不回填历史；下游修复为设计+代码，未对生产数据做批量写。
- 不改变现有商品分析 Agent 业务接口（Agent 仍走 services 白名单）。
- 与 E0-E5（M334）打通，未另起证据标准；市场研究 A-E 体系未被混淆。

## 6. 已知边界 / 后续

- 页面 ID 不匹配（异常6）目前靠 `source_offer_id` 存量逻辑 + provenance 记录，未新增独立强校验（存量可覆盖，标注为后续增强）。
- 来源冲突（异常9）当前策略是"白名单外标记人审"，未做多 Provider 数值比对（Official API 接入后再增强）。
- E0-E5 升级流程的"逐级补证归档"UI/流程属业务侧，本阶段只落枚举与初始赋值，升级动作待后续。
