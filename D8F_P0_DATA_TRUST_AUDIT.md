# D8-F P0-1｜商品数据真实性门禁审计报告

> 阶段：D8-F 第一阶段（审计现有实现，输出架构缺口和改造计划）。
> 日期：2026-11-20。执行：DSH (sensenova)。
> 核心原则：宁可少采集一个商品，也不能让虚假商品信息进入选品/利润分析/商品发布/采购决策。
> 本报告只报实际读到的代码，每处结论标注文件路径+行号。

---

## 0. 审计结论速览

| 检查点 | 现状 | 风险等级 |
|---|---|---|
| import_from_1688 调用链 | 已定位，闸门仅一处且条件过窄 | 🔴 高 |
| data_source 判断逻辑 | 仅 `hardcoded_fallback` 被拦，登录墙 `scrapling` 占位**不拦** | 🔴 高 |
| hardcoded_fallback 使用位置 | 3 处产生（scrape_1688/product_pipeline×2） | 🟡 中 |
| 商品分析入口 | `import_and_analyze_from_1688` **绕过闸门** | 🔴 高 |
| 自动上架入口 | 有 `listing_gate`，但**不校验 data_source 真实性** | 🟠 中高 |
| WooCommerce 发布接口 | 有 gate（利润/文案/候选状态），缺真实性校验 | 🟠 中高 |
| 数据库商品来源字段 | 有 `source/source_url/source_offer_id/data_integrity_*`，**缺 data_source/collected_at/evidence_grade** | 🟠 中高 |
| 现有测试覆盖 | 仅 1 条路径，5 类缺口 | 🟠 中高 |

**一句话**：现有闸门只挡住了"hardcoded_fallback + auto_run_pipeline=True"这一条窄路径；登录墙占位数据、分析路径绕过、WooCommerce 真实性校验缺失、字段级来源追溯缺失，是四大高危缺口。

### 深挖补充（子代理交叉验证后新增，3 个更隐蔽的严重缺口）

| # | 缺口 | 严重度 | 位置 |
|---|---|---|---|
| N1 | **price 抓取失败被硬编码为 35.8，但 data_source 仍标 `scrapling`（真实）**——假价格披真实外衣，闸门按定义无法识别 | 🔴🔴 最高 | scrape_1688.py:437 |
| N2 | `_hydrate_product_info` 直接抓取回填 price/variations，**全程不查 data_source**，fallback 假数据回填进主管线 | 🔴 高 | product_pipeline_service.py:1416-1435 |
| N3 | `data_source` **不随 product_info 下传**，V3.0 选品闸门/AI 分析/WooCommerce 上架全程对来源"失明" | 🔴 高 | :2527 convert_1688_to_pipeline_input 不写入 |
| N4 | API 层与异步任务**仅凭 success=True 判定导入成功**，不读 data_source/pipeline_skipped_reason | 🔴 高 | product_pipeline.py:396；product_import_job_service.py:210 |
| N5 | 965536473576 占位商品（代码自述 placeholder，stock=1000/800 编造）登记进 _KNOWN_PRODUCTS | 🟡 中 | scrape_1688.py:909-956, :830 |

---

## 1. import_from_1688 完整调用链

```
调用方（API endpoint / 批量导入 / Agent）
  └─ import_from_1688(url_or_id, auto_run_pipeline, auto_list, ...)   [product_pipeline_service.py:3142]
       ├─ _cached_fetch_1688_product(url_or_id)                       [:3177]  ← 缓存+幂等
       │    └─ _fetch_1688_product(url_or_id)                          [:2845]
       │         ├─ parse_1688_url → product_id                        [:2856]
       │         ├─ parse_1688_moon_chair_data_for_id(product_id)      [:2871]  ← 预检 _KNOWN_PRODUCTS
       │         ├─ [若非已知商品] scrape_1688_product(url_or_id)        [:2882]  ← Scrapling/playwright
       │         │    └─ generic 检测 + 重试 2 次                        [:2888-2906]
       │         ├─ [若 generic/已知] → hardcoded_fallback              [:2919-2958]
       │         └─ [否则] → data_source="scrapling"                    [:2961-2981]
       ├─ 闸门：仅当 data_source=="hardcoded_fallback" 且 auto_run_pipeline  [:3186-3198]
       ├─ [auto_run_pipeline=False] → 直接返回（**不过闸门**）           [:3200-3201]
       └─ [auto_run_pipeline=True] → run_pipeline(product_info, auto_list) [:3209]
            └─ WooCommerce 上架（经 listing_gate）                       [listing_gate.py]
```

调用方入口：
- `import_and_analyze_from_1688` [:3230] → 以 `auto_run_pipeline=False, auto_list=False` 调用 import_from_1688 → **绕过闸门**，随后直接做 AI 分析与产品报告。
- 管理端批量导入逐条工作单元（product_intelligence）。
- API endpoint `product_pipeline.py` / `product_analysis.py`。

## 2. data_source 判断逻辑

| data_source 值 | 产生条件 | 真实性 | 产生位置 |
|---|---|---|---|
| `hardcoded_fallback` | 商品在 `_KNOWN_PRODUCTS` 或 Scrapling 返回 generic | ❌ 假（快照/降级） | product_pipeline_service.py:2928, :3042；scrape_1688.py |
| `scrapling` | Scrapling 抓到非 generic 商品 | ✅ 真实（**但登录墙占位名也标 scrapling，见下**） | product_pipeline_service.py:2981 |
| `1688_open_api` | 官方 API（当前 ACL 拒绝，实际不可用） | ✅ 真实 | sourcing_1688_service.py |
| `unknown` | 兜底 | ❓ | :3027, :3118 |

**🔴 致命缺口（登录墙不被识别）**：generic 判定 [:2889-2894, :2910-2915] 在**重试耗尽后**若仍 generic，代码**不 fail-closed**，而是落入 hardcoded_fallback 分支 [:2919]；若商品不在 `_KNOWN_PRODUCTS`，则 `raise RuntimeError` [:2960]——**但仅在非 generic 且无 fallback 时**。关键：当 `use_hardcode=False`（非已知商品）且重试后仍 generic，`is_generic_data=True` → 走 [:2919] → `parse_1688_moon_chair_data_for_id` 返回 None → **raise** [:2960]。此路径 OK。
**但**：若 Scrapling 返回的 `scraped.name` 是登录墙占位名（如 "1688 Product"）且长度 ≥10 或 variations 不匹配 generic 规则，则 `_is_generic=False` → `is_generic_data=False` → **被当成真实 `scrapling` 数据**放行。verify 诊断实测：Cookie 失效时返回 name="1688 Product"（长度 12 ≥10）→ **不会被 generic 规则捕获**。这是真实绕过路径。

## 3. hardcoded_fallback 使用位置

| 位置 | 说明 |
|---|---|
| `scrape_1688.py:822` `_KNOWN_PRODUCTS` | 硬编码商品快照 map（含 964465929482 等） |
| `scrape_1688.py:832` `_get_known_product` | 查表入口 |
| `product_pipeline_service.py:2871, :2926` | 预检 + fallback 构造（generic/已知商品路径） |
| `product_pipeline_service.py:3040` | 异常兜底 fallback（Scrapling 抛异常时） |

`parse_1688_moon_chair_data_for_id` = 对 `_KNOWN_PRODUCTS` 的包装。**这些快照是过期价格/SKU，不代表当前真实商品。**

## 4. 商品分析入口

- **`import_and_analyze_from_1688` [:3230]**：以 `auto_run_pipeline=False` 调用 import_from_1688 → **完全绕过 hardcoded_fallback 闸门** [:3187 条件不满足] → fallback 假数据直接进入 `product_info` → AI 分析与产品报告。**🔴 高危：分析路径无真实性门禁。**
- V3.0 选品闸门（run_pipeline 内）有 6 道硬闸门 [:selection_workflows.py:105]，但那是**商业规则闸门**（成本/利润），非**数据来源真实性闸门**。
- `product_analyst.py:63` PROFIT-003 gate：UNKNOWN cost 禁止 test 决策——是成本门禁，不查 data_source。

## 5. 自动上架入口

- `run_pipeline(product_info, auto_list, ...)` [:3209] → `listing_gate`。
- **`listing_gate` [:listing_gate.py] 校验项**：missing_sku、missing_price、unapproved_candidate、cjk_without_localization、negative_margin（硬阻断）；unapproved_copy、thin_copy、below_margin_target（需复核）。
- **🟠 缺口**：listing_gate **不校验 `data_source`**。若一个 hardcoded_fallback 或登录墙占位商品恰好价格/文案/SKU 齐全（如 fallback 快照本身字段完整），它能通过 listing_gate 的所有检查 → 推到 WooCommerce。**上游闸门（import_from_1688）只在 auto_run_pipeline=True 时拦 hardcoded_fallback，且完全不拦登录墙 scrapling 占位。**
- `Listing Approved` gate（listing_publish.py:37-39）：force=true 不可绕过，是硬前置。但同样不查 data_source。

## 6. WooCommerce 发布接口

- `POST /products/{id}/push-woocommerce` → `listing_publish.py`（gate-controlled，router.py:106-111 确保走 gated endpoint）。
- 三态：passed → 推送；needs_review(409) → 前端"我已人工复核，强制放行"(?force=true)；blocked(422) → 硬停不可强制。
- **校验的是商业完整性（价格/利润/文案/候选状态），非数据来源真实性。**

## 7. 数据库商品来源字段

**已有**（products 表，product.py）：
- `source` [:53, default="manual"]：来源类别（manual/1688/woocommerce...）
- `source_url` [:54]、`source_offer_id` [:59]：1688 链接 + 规范化 offer id（去重防线）
- `data_integrity_status/score/missing/checked_at/trace_id/version` [:83-92]：V3.0 完整性追踪
- `mastered_at/mastered_by/mastered_trace_id` [:70-76]：审批追溯
- 独立 `ProductSource` 表（product_intelligence.py:64, product_sources）+ `ProductScoreEvidence` [:323]

**🔴 缺失**（D8-F P0-2 需补）：
- **抓取方式**：无 `data_source` 字段（hardcoded_fallback/scrapling/login_wall 这层信息**没落库**，只在 import 返回值里短暂存在）。
- **采集时间**：无 `collected_at`（无法判断数据新鲜度/过期）。
- **证据等级**：无 `evidence_grade`（E0-E5）字段——现有 E0-E5 体系只在 `reports/b2b/M334_*` 文档里，**未落库、未与采集链路打通**。
- **字段级 provenance**：现有都是商品级；无字段级（名称/价格/SKU 各自来源+证据状态）。
- `trace_id`：有 import_id 但未贯穿到采集→分析→上架全链。

## 8. 现有测试覆盖（test_1688_fallback_gate.py）

**已覆盖**：
- hardcoded_fallback + auto_run_pipeline=True → 阻断 + 带 pipeline_skipped_reason [:27-47]
- scrapling 真实数据 + auto_run_pipeline=True → 正常流转 [:50-71]

**🔴 缺口（5 类）**：
1. `auto_run_pipeline=False`（**分析路径**）不测——绕过闸门无测试。
2. 登录墙占位（name="1688 Product"，标 scrapling）不测——会被当真实数据。
3. `import_and_analyze_from_1688` 绕过路径不测。
4. 缺失 data_source（unknown/None）不测。
5. 不上溯到 listing_gate/WooCommerce——上架层真实性无测试。

---

## 9. 绕过风险清单（按严重度）

| # | 风险 | 严重度 | 位置 | 证据 |
|---|---|---|---|---|
| R1 | 登录墙占位名（"1688 Product" 长度≥10）被标 scrapling 当真实数据，绕过 generic 规则 | 🔴 高 | product_pipeline_service.py:2889-2894, :2910-2915 | verify 实测 Cookie 失效返回 "1688 Product"(len12) |
| R2 | `import_and_analyze_from_1688` 以 auto_run_pipeline=False 绕过 fallback 闸门，假数据进 AI 分析 | 🔴 高 | :3230, :3245-3249 | 闸门条件 :3187 仅 auto_run_pipeline=True |
| R3 | listing_gate 不校验 data_source，字段齐全的 fallback/占位商品可推 WooCommerce | 🟠 中高 | listing_gate.py:32-51 | HARD_BLOCK/REVIEW_REQUIRED 无 data_source 项 |
| R4 | 采集方式/采集时间/证据等级不落库，无法事后审计数据是否真实/新鲜 | 🟠 中高 | product.py:53-59 无 data_source/collected_at/evidence_grade | 模型字段清单 |
| R5 | E0-E5 体系仅在文档，未落库未与采集链路打通 | 🟠 中高 | M334_EVIDENCE_GRADE_SYSTEM.md（纯文档） | 无对应 DB 字段/代码引用 |
| R6 | 仅 success=true 即判定商品可用，未强制校验 data_source ∈ 真实集 | 🟠 中 | :3178 只查 success | import_from_1688 入口 |
| R7 | 字段级来源缺失，商品级真实≠字段级真实 | 🟡 中 | 无字段级 provenance | D8-F 指令明确要求 |

### 深挖新增（子代理交叉验证，全部读代码确认）

| # | 风险 | 严重度 | 位置 | 证据 |
|---|---|---|---|---|
| N1 | **price 抓取失败静默填 35.8（月亮椅默认价），data_source 仍标 scrapling（真实）**——假价格伪装成真实数据流入选品/利润/定价，闸门按定义无法识别 | 🔴🔴 最高 | scrape_1688.py:435-437 | `if price == 0: price = 35.8  # Default for moon chair`，随后 :443-451 返回，:2961-2981 标 scrapling |
| N2 | `_hydrate_product_info` 抓取回填 price/variations **全程不查 data_source**，fallback 假数据（含 35.8）回填进主管线 | 🔴 高 | product_pipeline_service.py:1416-1435 | :1421 仅判断 fetched.success，:1427-1435 直接把 fresh 字段写入 merged，无 data_source 读取 |
| N3 | `data_source` 不随 product_info 下传，V3.0 选品闸门/AI 分析/WooCommerce 上架全程"失明"，违反"缺失来源信息的数据不得进入自动化决策" | 🔴 高 | :2527 convert_1688_to_pipeline_input | 不接收也不写入 data_source；run_pipeline(:1447-1578) 无来源校验 |
| N4 | API 与异步任务**仅凭 success=True 判定导入成功**：同步接口 commit、异步任务标 succeeded，兜底假数据被当成功导入的正式商品 | 🔴 高 | product_pipeline.py:396-398；product_import_job_service.py:210-217 | 兜底数据在 :2930/:3044 返回 success=True；两处调用方均不读 data_source/pipeline_skipped_reason |
| N5 | 965536473576（XHP70）占位商品登记进 _KNOWN_PRODUCTS：代码自述 placeholder，stock=1000/800 编造，抓取失败即以占位数据返回 success=True | 🟡 中 | scrape_1688.py:909-956, :830 | 912-913 行注释自述 "Data placeholder" "This is a fallback" |
| N6 | 仓库根目录多份 scrape_1688 副本（_new/_fix/_final/fix_*.py）同样内嵌 _KNOWN_PRODUCTS，非生产链但属重复假数据源，误用风险 | 🟡 低 | 仓库根目录 | grep 确认多副本 |
| N7 | 1688_open_api 取值仅存在于 docstring(:3156)，代码实际直接走 Scrapling，该"优先官方API"设计未实现 | 🟡 低 | product_pipeline_service.py:3156 | docstring vs 实际代码不符 |

### 下游发布层 Critical 缺口（第二子代理交叉验证，上架比 import 更靠下游更危险）

| # | 风险 | 严重度 | 位置 | 证据 |
|---|---|---|---|---|
| C1 | **fallback 假数据经 confirm-list 推 WooCommerce（人工一点即过）**：confirm-list 只拦 funnel_stage==rejected，fallback 导入因跳过闸门从未建档评分、funnel_stage 为 NULL → 放行 | 🔴🔴 Critical | product_pipeline.py:250-255 → product_listing_service.py:472 | confirm_and_list(:2018) 只做管制词+图片门禁，不查 data_source |
| C2 | **无鉴权 legacy listing 端点接受任意 JSON 发布**：`/products/listing/single`、`/batch` 无 CurrentUser，直接 list_to_woocommerce 推 WC（对比 listing_publish.py:49-52 已补鉴权） | 🔴🔴 Critical | product_listing.py:69-94；router.py:99,138 | 端点签名无 _current_user |
| C3 | **PipelineOrchestrator 无 V3.0 闸门 + 失败自动降级**：sourcing→analysis→copy→pricing→listing→seo 整条链无来源校验，`_safe_call` 捕获所有异常返回降级字符串而非 fail-closed | 🔴 高 | pipeline_orchestrator.py:27-37,200,233；selection_listing_bridge.py:34-190 | 与 product_pipeline 门禁体系割裂 |
| C4 | **newton 硬编码倍率 fabricate 售价污染利润/选品**：`retail_price_usd = max(purchase_cost*3, 5.0)`，price 缺失仍给 $5 伪造售价，写入 meta.regular_price 被当真实售价计算利润 | 🔴 高 | newton_sourcing_storage.py:229-232,246-247 → product_cost_service.py:530 | 违反 AGENTS.md §1.2.5 禁止硬编码业务经验值 |
| C5 | listing_gate 的 `evaluate_gate` / `evaluate_gate_from_dict` **均不校验 data_source**，HARD_BLOCK 只有结构完整性项（缺 SKU/价/候选/中文/负利润），无来源真实性项 | 🔴 高 | listing_gate.py:32-41, 153-384 | 纯伪造 name+price+SKU 的 dict 直接 passed |
| C6 | convert_1688_to_pipeline_input **丢弃 source 标记**，下游 run_pipeline/confirm_and_list/AI 分析再也无从判定来源 | 🔴 高 | product_pipeline_service.py:2527-2646 | 只提取 name/price/desc/attrs/images |
| C7 | run_pipeline session=None 时 V3.0 选品闸门**静默 skipped** | 🟠 中高 | product_pipeline_service.py:1447-1465,1719-1752 | product_readiness_gate 明文 "Does NOT block" |

## 10. fail-closed 状态评估

| 异常 | 当前行为 | 应有行为 | 是否 fail-closed |
|---|---|---|---|
| Scrapling 返回 generic + 商品在 _KNOWN_PRODUCTS | 落 hardcoded_fallback，import 层拦截 auto-run | 拦截 ✅（但仅 auto_run=True） | 🟡 部分 |
| Scrapling 返回 generic + 非已知商品 | raise RuntimeError [:2960] | 拒绝 ✅ | ✅ 是 |
| Scrapling 抛异常 + 非已知商品 | 返回 success=False [:3067] | 拒绝 ✅ | ✅ 是 |
| Scrapling 抛异常 + 已知商品 | 落 hardcoded_fallback [:3040] | 拦截（同上仅 auto_run） | 🟡 部分 |
| 登录墙占位名（≥10 字符） | **当 scrapling 真实数据放行** | 应拒绝 | 🔴 **否** |
| success=true 但 data_source 缺失/unknown | 放行 | 应拒绝或标记 | 🔴 否 |
| auto_run_pipeline=False 路径 | 完全不查 data_source | 应拒绝假数据进分析 | 🔴 否 |
| listing_gate | 不查 data_source | 应拒绝假数据上架 | 🔴 否 |

**结论**：fail-closed **不彻底**。核心缺陷是"真实性"只等同"非 hardcoded_fallback"，登录墙占位和 unknown 来源都能以 `success=true` 流转。

---

## 11. 改造建议（喂给后续阶段）

1. **P0-1b 立即修 R1**：generic 判定增加登录墙占位名黑名单（"1688 Product"/"1688产品" 等即使长度≥10 也判 generic）；generic 重试耗尽一律 fail-closed，绝不放行占位数据。
2. **P0-1c 修 R2**：闸门条件从 `data_source=="hardcoded_fallback" and auto_run_pipeline` 改为"任何非真实 data_source 一律拦截流转+分析"，覆盖 import_and_analyze 路径。
3. **P0-2**：products 表增 `data_source`、`collected_at`、`evidence_grade`(E0-E5)、字段级 provenance（复用/扩展 ProductSource + data_integrity_*）；采集时落库。
4. **P0-3**：建 ManualProvider（不依赖 Cookie 的人工建档），collect/normalize/validate/get_provenance 四方法；人工来源标 `source="manual"`，**不自动提升证据等级**。
5. **P0-4**：fail-closed 覆盖 10 类异常，统一"隔离+记录 trace_id+保留原始证据+生成待处理状态，绝不静默降级"。
6. **P1-1**：统一 Provider 接口（Manual/BrowserCookie/Official 预留），业务层不写 if/else 分叉。
7. **P1-2**：补 10 类测试（覆盖 R1-R7 + 10 异常 + 链路上溯到 WooCommerce）。
8. **证据体系打通**：把 E0-E5 定义落为代码常量/枚举，采集时按来源赋初始等级，禁止跳跃升级。
9. **N1 最高优先（P0-1b）**：删除 scrape_1688.py:437 的 `price=35.8` 硬编码默认价；price 解析失败应判 generic/抛错（fail-closed），绝不伪造真实价格。
10. **N2**：`_hydrate_product_info` 回填前校验 data_source，兜底/unknown 数据不得回填 price/variations。
11. **N3**：把 data_source 写入 product_info（如 `product_info['meta']['data_source']`），使闸门从"单点"变"全程"，下游选品/上架/AI 分析全程可读。
12. **N4**：API 层与异步任务不应仅凭 success 判定成功，须读 data_source 与 pipeline_skipped_reason；兜底数据返回明确降级状态而非 success=True。
13. **N5/N6**：移除或隔离 965536473576 占位数据，不登记进 _KNOWN_PRODUCTS；清理仓库根目录重复副本；对 _KNOWN_PRODUCTS 条目增加快照时间/是否已核实元数据并定期失效。

---

## 附：证据文件清单

- backend/app/services/product_pipeline_service.py:2845-3227（_fetch_1688_product + import_from_1688 + 闸门）
- backend/app/services/product_pipeline_service.py:3230-3261（import_and_analyze_from_1688 绕过）
- backend/app/services/scrape_1688.py:822, :832（_KNOWN_PRODUCTS）
- backend/app/services/listing_gate.py:32-51（HARD_BLOCK/REVIEW_REQUIRED，无 data_source）
- backend/app/models/product.py:53-92（source/source_url/data_integrity_*，缺 data_source/collected_at/evidence_grade）
- backend/app/models/product_intelligence.py:64（ProductSource 表）
- backend/tests/test_1688_fallback_gate.py:27-71（仅 1 路径覆盖）
- reports/b2b/M334_EVIDENCE_GRADE_SYSTEM.md（E0-E5 定义，纯文档）
