# M4 V2.8 历史数据导出脚本审阅 + 30 天样本数据质量验证方案（EXPORT 审阅续）

> 工作项：`V2.8-HISTORICAL-DATA-EXPORT-PREP`（Owner 终审收口指令 V1.0 E 节 + 初步验证回复授权，EXPORT 脚本审阅继续）。
> 角色：`v28-export-review`。分支：`audit/pricing-v28-historical-export`（HEAD `60e89fa`，worktree `phase-export`）。
> 基准：`docs/V2_8_HISTORICAL_DATA_EXPORT_PLAN.md`（V1.0）、`docs/_audit/V2_8_OWNER_FINAL_REVIEW_DIRECTIVE_V1_0.md`、`docs/V2_8_GAP_AND_RISK_REGISTER.md`（R1–R7/R12/R13）、`docs/V2_8_DATA_LINEAGE_AUDIT.md`（§8/§11）。
> 状态：**审阅完成，30 天样本验证方案已起草（READY FOR REVIEW），未执行任何生产 SQL、未连接任何真实库**。不宣称 V2.8 通过；0076 继续冻结，未触碰。

---

## 0. 本文件范围与红线遵守声明

- 本轮**只读审阅**：只读 `docs/V2_8_HISTORICAL_DATA_EXPORT_PLAN.md`、`scripts/v28_export_desensitize.py`、`scripts/v28_recalc_quantify.py`、`tests/test_v28_export_desensitize.py`、`tests/test_v28_recalc_quantification.py`、`tests/fixtures/v28_export_sample/`。
- 本轮**未连接生产数据库**；**未执行任何 SQL**；**未运行脱敏/验证脚本对真实数据**（仅对合成 fixture 跑既有测试）。
- **未索取/未接收生产密码/Cookie/API Token**；未连 WooCommerce/Stripe；未部署；未切换定价引擎。
- **未用合成数据冒充历史真实数据**（合成 fixture 仅用于逻辑自校验，`make_fixture.py` 标注 `NOT production data`）；**未把未知字段填成 0 或推测值**（脚本 `annotate_missing` 保留 NULL/空并标 `missing_reason`，`ZERO_IS_LEGIT` 仅对原始即 0 的业务零打 `value_is_zero=true`）。
- **0076 未触碰**：`git diff` 为空、`git rev-parse HEAD:...` 与 `git hash-object` 一致（blob `ac01bbf...`），未提交/未读 diff/未清理。
- **未宣布 V2.8 通过**；本文件仅交付审阅结论 + 30 天样本验证方案（草案），真实数据验证待 Owner 授权、生产脱敏副本到位后执行。

---

## 1. 只读 SQL 审阅结论（计划 §2，7 组）

### 1.1 结论：**通过（符合只读要求）**

| 项 | 结论 |
|---|---|
| 语句类型 | 全部为 `SELECT`（§2.0–§2.7 共 9 条：计数 1 + A/B/C/D/E/F/G 各 1–2 条），无 `INSERT/UPDATE/DELETE/DROP/CREATE/ALTER/TRUNCATE/GRANT/REVOKE/MERGE` |
| 生产库连接 | 无任何连接串 / `host`/`dbname`/`DSN`/`DATABASE_URL`；SQL 仅以 `:workspace_id`、`:start_date`、`:end_date`、`:cursor`、`:cursor_pk`、`:batch_size` 参数化 |
| 写操作 | 无。`COPY ... TO CSV` 仅在计划文字中作为「生产侧 DBA 执行导出」的**操作说明**出现（§2 引言、§5 步③），非 SQL 语句本体；其语义为读库导出，不改写数据 |
| 凭据 | SQL 无任何硬编码密码 / token / cookie / API key |
| 分页 | 大表用 keyset pagination（`(received_at, id) > (:cursor, :cursor_pk)`），避免 OFFSET 深扫；无 OFFSET/LIMIT 深分页 |
| 作用域 | 全部 `WHERE workspace_id = :workspace_id` 限定；B2C 订单链限定 `business_model='B2C'`；D 组限定 `deleted_at IS NULL` 且 `meta->>'price' IS NOT NULL` |

### 1.2 关键点核验

- **A 组（§2.1）**：`LEFT JOIN order_items` 保留无行项订单（异常订单也是审计对象）；keyset 游标 `(received_at, o.id)` 正确；`profit_snapshot`/`rule_results` JSON 整列导出，脱敏在脚本内逐键处理——SQL 保持纯只读，符合「脱敏不在 SQL 内做」的设计意图（§2 引言）。
- **B 组（§2.2）**：推导税率 `CASE WHEN o.total > o.tax_total THEN ROUND(...) ELSE NULL END`，无法推导时 NULL 不填 0；行级税分摊为**推导值**并标 `'derived_not_stored'`，**不伪造**行级税列（§1.4 红线「不把未知字段填成 0 或推测值」遵守）。
- **C 组（§2.3）**：C-1 多版本快照（`valid_from >= :start_date - INTERVAL '30 days'` 略提前覆盖跨窗口成本变更）；C-2 以子查询限定「时间窗内订单引用过的 product_id」，最小必要，避免全表扫。
- **D 组（§2.4）**：`p.meta->>'price'` 等 JSON 提取；`'LEGACY_NO_PUBLICATION_RECORD' AS price_lineage` 如实标注 R6 缺口（无价格发布记录表），**不伪造**逐次发布历史。
- **E 组（§2.5）**：订单级支付列 + `refund_cases` 退款生命周期；`payment_refund_id`/`woocommerce_refund_id` 稳定伪 ID（脚本层）；未落支付流水表（`missing_reason='payment_transactions_not_stored'` 如实标注，不造流水）。
- **F 组（§2.6）**：`shipment_records` LEFT JOIN `logistics_events`；`origin/destination/location` 为城市/仓位（非详细地址）保留；`tracking_number` 稳定伪 ID。
- **G 组（§2.7）**：campaigns 计划级 spend/revenue + 订单侧 `orders.advertising_cost`；`raw_payload` 大 JSON 不导出（`missing_reason='payload_excluded'`）；历史逐订单营销分摊不存在（`missing_reason='attribution_history_not_stored'`）。

**审阅意见**：SQL 无安全问题，可交生产 DBA 只读执行（§5 步③）。唯一提示：B 组 SQL 内给字面量 `'derived_not_stored'`/`'derived'` 仅是初标，计划已说明脱敏脚本会依据 schema 事实改写为 `not_collected`/`derived` 枚举——实施时需确保脚本改写逻辑与 SQL 列名（`line_tax_missing_reason`）对齐。

---

## 2. 匿名化/脱敏脚本审阅结论（`scripts/v28_export_desensitize.py`，计划 §3）

### 2.1 结论：**通过（PII 删除、稳定匿名 ID、密钥管理三方面均符合计划），发现 2 处计划↔实现差异（见 §2.5）**

### 2.2 PII 删除

- **列级删除**：`PII_KEYS` 冻结集合覆盖 `billing_email/first_name/last_name/phone/address_1/2/city/state/postcode/country`、`shipping_*`、`email/phone/first_name/last_name/display_name/customer_name/card_number/cvv/customer_number`；`scrub_pii` 对命中键直接 `continue`（剔除，不进输出列）。
- **值级正则兜底**：`_sweep_text` 对每个字段文本（含 JSON 序列化）做 `EMAIL_RE`/`PHONE_RE`/`CARD_RE`/`TOKEN_KEY_RE` 替换（`[REDACTED:...]`）；`TOKEN_KEY_RE` 覆盖 `api_key/access_token/auth_token/secret/cookie/cvv/client_secret` 键值对。
- **V3 无残留**：`_scan_pii_residue` 对脱敏输出全文重扫，命中即 `FAIL`（exit 1）；测试 `test_no_pii_residue_in_outputs` 断言邮箱/卡号/token 残留为 0。
- **说明**：本系统本地 `orders` 表不存 WC billing/shipping 详情（§1.5），但 fixture 故意混入 `billing_*`/`card_number`/`email`/`phone` 等列以验证脚本确实剥离——剥离逻辑有效。

### 2.3 稳定匿名 ID

- 算法：`pseudo_id = SHA256(f"{entity_kind}|{workspace_id}|{original}|{salt}")[:32]`（`pseudo_id()`，§1.3 默认方案）；确定性（同输入恒同输出）、不可逆（单向，无盐表反查）、128-bit 截断（碰撞风险可忽略）。
- 覆盖 6 类标识：`external_order_id`、`customer_account_id`/`customer_reference_id`、`payment_refund_id`/`woocommerce_refund_id`、`tracking_number`、`campaign_id`（`PSEUDO_ID_FIELDS`）。
- 跨组一致性：同一原始 ID + 同一 salt 恒映射同一伪 ID（脚本内 `pseudo_map` 先构建、跨文件复用）；V5 校验确定性（`test_pii_keys_dropped_and_pseudo_ids_applied` 断言 32 位 hex + 两次调用一致）。
- SKU、`woocommerce_id`（商品维度业务标识，Owner 指定保留）**不替换**——符合计划 §1.3。

### 2.4 密钥管理

- **salt 来源**：仅 `--salt-file`（Owner 安全渠道交付）；脚本 `run()` 读 salt，空则 `print + return 2`（**fail-closed**，无默认 salt、无环境变量示例、无仓库内 salt）。
- **salt 不入库**：`.gitignore` 第 193–197 行覆盖 `tests/fixtures/v28_export_sample/out/` 与 `test-salt.txt`（测试 salt 为 `v28-test-only-salt-do-not-use-in-prod`，仅测试用，已 gitignore）；生产 salt 由 Owner 保管，不进入仓库，也不交给 DSH 持久保存。
- **salt 不进 SQL 引擎环境**：脱敏在 SELECT 之后本地做（§2 引言），salt 仅在脚本进程内读入。
- **映射表保护**：计划 §1.3/§3.1 声明 `_id_map_pseudo.json`（含原始 ID）与脱敏数据同级保护、交付后由 Owner 决定销毁——**实现未写出该文件（见 §2.5 差异 1）**。
- **红线遵守**：本轮未索取/接收任何生产密码/Cookie/API Token；测试仅用合成 fixture 内 test-only salt。

### 2.5 计划↔实现差异（2 处，审阅发现，均未破坏既有 13 测试）

1. **`_id_map_pseudo.json` 未实现**：计划 §3.1 输出清单（L362）与 §1.3（L58）明确要求脚本输出 `_id_map_pseudo.json`（含原始 ID 的映射表，供关联验证 + Owner 销毁决定），但 `scripts/v28_export_desensitize.py` 的 `run()` 只写出 12 个 CSV + `desensitization_report.json`，`pseudo_map` 仅在内存构建（L439–452）并传给 `verify()`（L490），**从未序列化落盘**。
   - 影响：无法直接拿到「原始 ID → 伪 ID」映射表做反向/正向校验与 Owner 销毁清单；跨文件一致性仍可从输出 CSV 本身校验（如 `external_order_id` 在 orders.csv 与 tax.csv 应相同），但缺少计划约定的显式映射工件。
   - 建议：在 `run()` 末尾把 `pseudo_map`（剔除 `_salt`/`_workspace` 元键）写为 `_id_map_pseudo.json`，并加入 `.gitignore`（计划 §3.3 已列）。**本轮不改动脚本**（改动需重跑 13 测试 + 超出「精确 add 报告+方案」范围），列为真实数据执行前必改项。
2. **V2 关联对齐只校验 refunds**：计划 §3.1 对齐要求「以 A 组 `order_pk` 为主键，校验 B/E/G-2 行集 ⊆ A」，§3.2 V2「每个脱敏副本的 `order_pk` 在 A 组集合中」；但 `verify()` 的 V2 只对 `refunds.csv` 检查 `order_pk ∈ order_pks`（L296–308），**未校验 `tax.csv`/`payments.csv`/`order_marketing.csv`/`orders_lines.csv` 的 `order_pk` 归属**。
   - 影响：若 tax/payments/order_marketing 出现孤立 `order_pk`（不在 A 组），V2 不会 FAIL，违背「对齐率 100%（允许报告孤立行，不允许静默）」。
   - 建议：将 V2 扩展为对 4 个文件（tax/payments/order_marketing/orders_lines）统一做 `order_pk ∈ orders` 检查，孤立行写入报告 detail 而非静默。**本轮不改动脚本**，列为真实数据执行前必改项。

> 说明：上述两处为「实现未达计划承诺」的**保守性缺口**（漏检/漏工件，不会误杀合法数据），非安全漏洞；在真实数据脱敏（§5 步④）前必须补齐，否则关联完整性验证（本文件 §4/§5）可能漏过孤立行。

### 2.6 其他观察（非阻塞）

- `CARD_RE = \b(?:\d[ \-]?){12,18}\d\b` 为**数字串启发式**，非 Luhn 校验——长数字串（非卡号）可能误报（V3 对 32 位 hex 伪 ID 已豁免，但 13–19 位纯数字业务 ID 仍可能被标为卡）。保守方向（误报→FAIL）安全，但真实数据可能触发；建议改用 Luhn 校验以降低误报。
- JSON 内嵌套敏感**键名**（如 `name`/`address`/`city`）若其值为普通文本（非邮箱/电话/卡号/token），`_sweep_text` 不会按键名剔除（仅列级 `PII_KEYS` + 值级正则兜底）。因计划 §2 SQL 从不 SELECT 此类列、本地 schema 亦不存（§1.5），实际风险低；建议作为加固项在真实数据前确认 `profit_snapshot`/`rule_results` 已知键白名单。

---

## 3. 既有测试结果 + ruff 观察

### 3.1 测试结果（本轮实跑）

- 命令：`python -m pytest tests/test_v28_export_desensitize.py tests/test_v28_recalc_quantification.py -v`
- 环境：Python 3.12.10 / pytest 9.1.1（`E:\AI\nuotao-ai-os\.venv`）
- 结果：**13 passed in 1.76s**（`test_v28_export_desensitize.py` 7 项 + `test_v28_recalc_quantification.py` 6 项，全部 PASSED）
- 覆盖：salt 缺失 fail-closed、V1–V7 自校验、PII 无残留、PII 键剔除 + 伪 ID 稳定、NULL 不填 0（legit 0 保留）、孤立退款检出（V2）、行数不一致检出（V1）、重算三态 + 缺失原因、R1 虚增金额/比例、R2 口径差方向、R7 版本缺口、全量分析端点。
- 结论：**13/13 全绿，符合计划 §5 步①门禁「13/13 单测全绿（仅合成 fixture，无生产数据）」**。

### 3.2 ruff 观察

- 本轮**无新增脚本**（仅新增本报告 .md），「ruff（新增脚本若有）」门禁不触发。
- 附带检查既有 V2.8 脚本（ruff 0.16.4 默认配置，因 `backend/ruff.toml` 仅作用于 backend/ 子树）：`scripts/v28_export_desensitize.py`、`scripts/v28_recalc_quantify.py`、`tests/test_v28_export_desensitize.py`、`tests/test_v28_recalc_quantification.py` 共报 **14 项**（UP012、FURB157、PLC0206、SIM102、PIE800、SIM118、RUF100、PLW1510），均为**风格/现代语法建议**，无正确性或安全类问题；且为 HEAD `60e89fa` **既有提交**，非本变更引入。
- 处理：**不自动修复**（超出本工作项范围，避免改动已通过 13 测试的提交代码）；列入「真实数据执行前」低优先级清理项。若按项目基线用 `backend/ruff.toml` 规则（backend 子树）+ ruff v0.8.4 钩子，需在真实数据前统一确认（根目录无 ruff 配置，pre-commit ruff-pre-commit v0.8.4 对 scripts/ tests/ 用默认规则）。

---

## 4. 30 天样本数据质量验证方案（草案，Owner 授权 + 生产脱敏副本到位后执行）

> 依据 Owner 初步验证回复：先做 30 天样本验证**字段完整性、关联关系、金额平衡、时间范围、脱敏稳定性**，通过后再考虑扩展至 90 天。
> **本方案仅在 `data/desensitized/`（脱敏副本）上跑，不连生产、不执行 SQL、不读原始导出中的 PII**；原始导出只用于行配对校验（仅数字/时间列）。

### 4.0 前置条件（Owner 门禁）

| 步 | 前置 | 说明 |
|---|---|---|
| P0 | 生产 DBA 只读执行计划 §2 SQL（30 天窗口） | 产物落 `data/raw_export/`，执行记录（时间/行数/sha256）回传 |
| P1 | Owner 安全渠道提供 salt | 仅 `--salt-file`，不入库、不交 DSH 持久保存 |
| P2 | DSH 本地跑 `v28_export_desensitize.py`（V1–V7 全绿才产出） | 产出 `data/desensitized/` + `desensitization_report.json` |
| P3 | **先补齐 §2.5 两处差异** | `_id_map_pseudo.json` 落盘 + V2 扩展 B/E/G-2 行集校验；否则本方案 §5 无法完整执行 |

### 4.1 维度一：字段完整性（每 CSV × 必需列 × 缺失分布）

- **方法**：对 12 个脱敏 CSV，逐一核对计划 §1.2 必需列是否齐全；对每个数值/时间/标识列统计 `NULL/空` 计数、占比、`missing_reason` 分布、`value_is_zero` 分布。
- **通过标准**：
  1. 无必需列缺失（列头与计划 §1.2 一致，脚本只删 `PII_KEYS` 列）；
  2. 每个空值行均有 `missing_reason`（`not_collected`/`field_not_stored`/`unknown_value`/`legacy_no_record`/`payload_excluded`/`derived_not_stored`）；
  3. `value_is_zero=true` 仅出现在原始即 0 的合法业务零列（`ZERO_IS_LEGIT`），无「原始 NULL 被填 0」行（V4 反向扫描）；
  4. 缺失字段清单与计划 §4.2 枚举一致：`order_items.cost_snapshot_id/version`（schema 无 → `field_not_stored`）、`pricing_rule_version`、`pricing_engine_version`、`evidence_grade`、行级税、退款手续费返还、营销历史分摊、价格发布记录。
- **输出**：`table.field → (null_count, null_rate, missing_reason)` 矩阵 + `value_is_zero` 计数。

### 4.2 维度二：关联关系（6 链 + 实体集）

- 见 §5 关联完整性验证清单（12+ 项检查），对齐率 100% 为通过；孤立行清单（前 50 条）报告而非静默。

### 4.3 维度三：金额平衡（逐单对账）

- **订单级**（容差 ε=0.01）：
  - `total ≈ subtotal + shipping_total − discount_total + tax_total`；
  - `refunded_amount ≤ total`；
  - `payment_fee ≥ 0` 且 `≤ total`；
  - `advertising_cost ≥ 0`（允许 > total，但报告此类行并给出分布）；
  - `Σ order_items.line_total ≈ subtotal`（容差 ε）；
- **行级**：`line_total ≈ quantity × unit_price`（容差 ε）；
- **退款**：`executed_amount ≤ approved_amount ≤ requested_amount`（单调），`executed_amount ≤ total`；
- **币种一致性**：`order.currency == payments.currency == tax.currency`；退款 `payment_provider` 与订单 `payment_method` 关联（允许不匹配则报告）；
- **成本**：`total_landed_cost ≈ Σ(purchase_cost + domestic_shipping + first_leg + last_leg + international + packaging + tax_estimate + handling)`；`total_cost ≈ total_landed_cost + payment_fee + marketing_amortization + after_sales_loss`（按快照 version 逐版本核对）；
- **价格**：`order_items.unit_price` 与 D 组 `price_current` 在订单时点核对（允许历史调价，报差异分布而非硬失败）；
- **物流**：`actual_cost_currency` 与订单币种一致（允许不同币种，报清单）；`delivery_time_days ≥ 0`；
- **营销**：`campaign.roas ≈ campaign.revenue / campaign.spend`（spend>0 时，容差 0.05）；`campaign.spend` 与 `orders.advertising_cost` 汇总对账（`attribution_history_not_stored` 时如实标注不可对账）。
- **通过标准**：不平衡订单占比 < 1%（且逐条列明）；币种不一致逐条列明；无 NaN/Inf。

### 4.4 维度四：时间范围（30 天窗口）

- **订单**：`received_at ∈ [start_date, end_date)`，越界行 = 0（越界即 FAIL，列清单）；
- **成本快照**：`valid_from ∈ [start_date − 30d, end_date)`（计划 §2.3 C-1 略提前窗口），越界 = 0；
- **退款**：`created_at/executed_at` 允许在窗口外（对窗口内订单的退款），但越界需列清单并说明；
- **价格**：`created_at ≤ updated_at`；`price_modified_at` 无未来值（> end_date + 1d 报清单）；
- **物流**：`ship_date ≥ created_at − 1d`（容差）；`delivery_time_days ≥ 0`；
- **营销**：`started_at/ended_at` 与窗口有交集（或窗口内无 spend 的无归因态）；
- **脱敏时间戳**：脱敏不得改时间戳（V6 抽检逐字节一致）。
- **通过标准**：严格窗口实体越界 = 0；宽限实体（退款/物流）越界清单化并确认合理。

### 4.5 维度五：脱敏稳定性

- **确定性**：同一 raw + 同一 salt 连续两次脱敏 → 12 CSV + report 逐字节一致（sha256 相同，V5）；
- **跨文件伪 ID 一致**：同一原始 ID（如 `external_order_id`）在 `orders.csv` 与 `tax.csv` 映射为相同伪 ID（跨文件一致性）；
- **无 PII 残留**：V3 全文扫描命中 = 0；
- **fail-closed**：无 salt / 空 salt → exit 2，不产出任何文件；
- **不可逆性**：伪 ID 无 salt 无法反查（文档化属性，脚本内不存储可逆映射）；
- **通过标准**：以上全部满足；任一 FAIL → 停止并修复，不扩展时间窗。

---

## 5. 关联完整性验证清单（12 项，对应 Owner 要求 #5）

| # | 关联 | 检查 | 期望 | 失败处理 |
|---|---|---|---|---|
| 1 | 订单主键 | `orders.order_pk` 唯一 | 无重复 | FAIL |
| 2 | 订单↔订单行 | `order_items.order_id ∈ orders.order_pk` | 孤立行 = 0 | 报告孤立行 |
| 3 | 订单↔退款 | `refund_cases.order_id ∈ orders.order_pk` | 孤立退款 = 0 | 报告孤立行 |
| 4 | 订单↔支付 | `payments.order_pk ∈ orders.order_pk` 且 1:1 | 无孤儿/无重复 | 报告 |
| 5 | 订单↔营销 | `order_marketing.order_pk ∈ orders.order_pk` | 孤立行 = 0 | 报告孤立行 |
| 6 | 订单行↔成本 | `order_items.(product_id, wc_variation_id)` 命中 C 组同 key 快照（含 `variation_id IS NULL` 商品级回退） | 每条线 ≥ 1 版本 | 列未命中清单 |
| 7 | 成本版本唯一 | `cost_snapshots.(product_id, variation_id, version)` 唯一 | 无重复版本 | FAIL |
| 8 | 订单行↔价格 | `order_items.sku` 命中 D 组 `sku` | 命中率 100%（允许 `LEGACY_NO_PUBLICATION_RECORD`） | 列未命中清单 |
| 9 | 物流↔事件 | `logistics_events.shipment_id ∈ shipment_records.id` | 孤立事件 = 0 | 报告 |
| 10 | 营销↔商品 | `campaigns.product_id` 引用 products（或 NULL 允许） | 无悬空非 NULL | 报告 |
| 11 | 映射↔商品 | `product_mappings.nuotao_product_id → products.id` | 无悬空 | 报告 |
| 12 | 跨文件伪 ID 一致 | 同一原始 ID 跨文件（orders/tax/payments/marketing/refunds）映射同伪 ID | 100% 一致 | FAIL |
| 13 | 行级金额闭合 | `Σ order_items.line_total = orders.subtotal`（容差 ε） | 差异 < 1% 订单 | 报告分布 |
| 14 | 成本版本时点 | `cost_snapshots.valid_from ≤ orders.received_at`（订单当时可用版本） | 逐线可版本化（否则 `LEGACY_UNKNOWN`） | 列 `LEGACY_UNKNOWN` 清单 |

> 注：计划 §1.2 F 组已说明 B2C 订单行无 shipment 外键（schema 中 shipment 关联 purchase_order/b2b_order），订单↔物流以 `orders.shipping_total`（客户付费运费）与成本快照 `last_leg_shipping`（尾程成本）**成本侧对齐**，**不算断链**（如实报告，不伪造关联键）。

---

## 6. 密钥管理说明（配合计划 §1.3/§3.3 的落实口径）

1. **salt 生成**：由有权限人员（Owner 或其指定）生成高熵随机 salt；生成后经安全渠道（加密文件 `--salt-file` 或受控 CLI 参数）交付给 DSH 脱敏进程，**不进入仓库、不写入文档、不放进环境变量示例、不交给 DSH 长期保存**。
2. **读取**：脚本仅从 `--salt-file` 读入；文件缺失或内容为空 → `exit 2`（fail-closed），**不写默认 salt**、不降级运行。
3. **伪 ID 性质**：`SHA256(entity_kind|workspace_id|original|salt)[:32]`——确定性（多次导出关联不断）、不可逆（单向，无盐表反查）、跨实体稳定（A/E/F/G 共享映射）。备选 uuid5（计划 §1.3）当前未实现（SHA256 为默认即足够，属「二选一」之合法选择）。
4. **映射表保护**：计划约定 `_id_map_pseudo.json`（含原始 ID）与脱敏数据同级保护、交付后由 Owner 决定是否销毁——**实现缺口见 §2.5 差异 1**，真实数据执行前需补齐落盘并 gitignore。
5. **隔离**：salt 不进 SQL 引擎环境（脱敏在 SELECT 之后、本地进程内）；脱敏脚本无网络/无 DB（`v28_export_desensitize.py` docstring 明确 `no DB connection, no network`）。
6. **测试 salt**：仅合成 fixture 用 `v28-test-only-salt-do-not-use-in-prod`（`test-salt.txt` 已 gitignore）；生产 salt 绝不写入测试。

---

## 7. 已知缺口（数据源未就绪，待有权限人员提供）

| # | 缺口 | 影响 | 责任方 | 解除条件 |
|---|---|---|---|---|
| G1 | **无生产脱敏副本**（生产 DB 未只读导出，未脱敏） | 30 天样本验证**无法执行**；真实数据数字（R1/R2/R7）无法产出 | 生产 DBA（有权限人员） | 只读执行计划 §2 SQL 30 天窗口 → 产物交 DSH |
| G2 | **salt 未由 Owner 提供** | 脱敏脚本无法运行（fail-closed） | Owner/有权限人员 | 安全渠道提供 `--salt-file` |
| G3 | **`_id_map_pseudo.json` 未实现**（计划 §3.1 vs 脚本） | 无法显式拿到原始↔伪映射表；跨文件一致性需从 CSV 间接校验 | 本工作项（后续） | 补写映射表落盘 + gitignore，重跑 13 测试 |
| G4 | **V2 仅校验 refunds**（计划 §3.1/§3.2 vs 脚本） | tax/payments/order_marketing/orders_lines 孤立行可能静默漏检 | 本工作项（后续） | 扩展 V2 到 4 文件，重跑 13 测试 |
| G5 | **ruff 14 项风格提示**（HEAD 既有，非本变更） | 不影响功能；低优先级 | 本工作项（后续，可选） | 统一 ruff 配置（backend/ruff.toml 或根配置）后清理 |
| G6 | **无 `price_publication_records`、无订单行级税、无退款手续费返还、无营销历史分摊**（R6/R12 等 schema 缺口） | 相应维度标 `LEGACY_NO_PUBLICATION_RECORD`/`not_collected`，不伪造 | 设计层（已记录 R 系列） | 长期；本次如实标注即可 |

---

## 8. 结论与下一步

- **只读 SQL**：通过（纯 SELECT、参数化、无生产连接、无凭据）。
- **匿名化脚本**：通过（PII 删除 + 稳定伪 ID + salt fail-closed + NULL 不填 0）；发现 2 处计划↔实现差异（§2.5 G3/G4），**真实数据执行前必补**。
- **既有测试**：13/13 全绿（本轮实跑确认）。
- **0076**：冻结未触碰（blob 与 HEAD 一致）。
- **下一步（Owner 门禁）**：补齐 G3/G4 → Owner 提供 salt（G2）→ 生产 DBA 只读导出 30 天（G1）→ DSH 脱敏（V1–V7）→ 本文件 §4/§5 验证 → Owner 决定 30→90 天扩展。
- **不宣称 V2.8 通过**；V2.8 相关结论待 Owner 依据真实数据验证结果单独宣布。

---

*（本文件为 EXPORT 审阅续证据，与 `docs/V2_8_HISTORICAL_DATA_EXPORT_PLAN.md` 配套；不替代计划，仅补充审阅结论 + 30 天样本验证方案 + 关联完整性清单 + 密钥管理口径。）*
