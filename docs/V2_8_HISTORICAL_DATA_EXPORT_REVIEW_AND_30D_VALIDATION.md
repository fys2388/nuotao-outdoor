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

### 2.1 结论：**通过（PII 删除、稳定匿名 ID、密钥管理三方面均符合计划；G3/G4 两项缺口已在本工作项修复，见 §2.5）**

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
- **映射表保护（G3 已修复）**：`_id_map_pseudo.json`（含原始 ID）只写入 **Owner 受控独立受限目录** `--id-map-dir`（必须已存在、非符号链接、不与 raw/out 嵌套或重叠、**不在任何 Git 工作树内**），0600 文件 / 0700 目录、O_EXCL 防覆盖、fsync；**不随脱敏包交付、不入 Git（`.gitignore` 兜底 `_id_map_pseudo.json`）、不进日志/异常输出**；保留期由 `--id-map-retention-days` 显式声明，**销毁时点由 Owner 决定**（30 天审阅 + Owner 签署后执行）。映射文件仅当 V1–V7 全通过才产出。
- **红线遵守**：本轮未索取/接收任何生产密码/Cookie/API Token；测试仅用合成 fixture 内 test-only salt。

### 2.5 G3/G4 修复实现（本工作项，原审阅发现的 2 处差异）

**原差异 1（映射工件未落盘）→ G3 已修复**：

- 新增 `ID_MAP_FILENAME = "_id_map_pseudo.json"`、`ID_MAP_SCHEMA_VERSION = "v28-id-map-v1"`、`ID_MAP_DIR_MODE = 0o700`、`ID_MAP_FILE_MODE = 0o600`。
- 新增 `RestrictedIdMapError`（**消息刻意不含路径/workspace/原始 ID/映射内容**，异常路径不泄漏）。
- 新增受限目录解析 `resolve_restricted_id_map_dir(raw_dir, out_dir, id_map_dir)`（fail-closed）：要求目标目录**已存在**、非符号链接、不与 raw/out 嵌套或重叠、且**不在任何 Git 工作树内**（含 `.git` 文件/目录的任意祖先，兼容 worktree）。
- 新增 `write_restricted_id_map(...)`：O_EXCL 防覆盖、`os.chmod(0o600/0o700)`、fsync、OSError 时删除半成品并抛 `RestrictedIdMapError`；payload 剔除 `_salt`/`_workspace` 元键，含 `schema_version`、`entries`、`workspace_id`、`security`（`file_mode_octal/directory_mode_octal/git_tracked/salt_included/retention_days/destruction_owner_decision_required`）。
- `run()` 现在：**先**校验受限目录（读 salt 前、任何输出前）；仅当 `rep.passed` 才写映射；报告新增 `id_map` 元数据（`written/entry_count/storage_class/delivered_with_package/git_tracked/retention_days`，**不含路径与原始 ID**）；任何受限存储错误 → `return 2`（无 traceback、无原始 ID）。
- `main()` 新增**必填** `--id-map-dir` 与 `--id-map-retention-days`（`_positive_int`）。

**原差异 2（V2 只校验 refunds）→ G4 已修复（本工作项扩展至全部 12 个实际输出文件）**：

- 新增 `ORDER_FK_FILES = {"orders_lines.csv": "line_pk", "tax.csv": None, "payments.csv": None, "order_marketing.csv": None, "refunds.csv": "refund_pk"}`。
- V2 重构为 `V2_referential`（五文件 `order_pk ∈ orders`，**按 `(workspace_id, order_pk)` 解析，绝不只用 `order_pk` 跨 workspace 匹配**；缺失列记 `missing_required_association_fields`；孤立行按文件记 `order_pk_orphans`；`refunds` 采样继续用 `refund_pk`，保持既有 `samples == ["r-404"]` 行为）、`V2_primary_key_integrity`（`PRIMARY_KEY_FIELDS` 八文件：缺失列 → `missing_primary_key_field`，空/重复计数）、`V2_workspace_consistency`（**全部 12 个实际输出文件**均须有 `workspace_id`、每行非空且等于 CLI `--workspace-id`；父子记录（orders↔五关联文件、shipments↔logistics_events）以 `(workspace_id, 关联键)` 校验一致；跨 workspace 同 `order_pk` 记 `cross_workspace_keys` 并 FAIL；缺失 `workspace_id` 列的文件按 `SCHEMA_WORKSPACE_FILES` 区分：schema 明确有该字段 → FAIL（`missing_workspace_reasons=...schema_requires_workspace_but_export_missing`），schema 明确无 → `STRUCTURAL_ASSOCIATION_LIMITS`；每文件 manifest 记录 `rows/has_workspace_id/schema_requires_workspace_id/empty_workspace_rows/workspace_mismatch_rows/status`）。
- 新增 `SCHEMA_WORKSPACE_FILES`（**全部 12 → True**，经 `backend/app/models/` 确认 `WorkspaceMixin.workspace_id` 非空 / `ProductMapping.workspace_id` 显式）、`WORKSPACE_PARENT`（orders=None；orders_lines/tax/payments/order_marketing/refunds→orders 经 `order_pk`；logistics_events→shipments 经 `shipment_id/shipment_pk`；其余 None）、`ORDER_LINKED_FILES`。
- 新增 `STRUCTURAL_ASSOCIATION_LIMITS`：`shipments/logistics_events/campaigns → orders` 无 FK、`tax/payments/order_marketing` 无代理主键、`order_items.cost_snapshot_id` schema 无——**如实记 `structural_limitations`，绝不伪造 FK/关联键**。
- fixture/计划 SQL 同步暴露 `workspace_id`：合成 fixture **全部 12 个 raw CSV** 均带 `workspace_id`（首列，`ws-test-1`）；计划 §2 全部组 SQL 投影 `workspace_id`（本轮补齐 C/D/F/G 组，F 组拆分为 F-1 shipments/F-2 logistics_events 两查询）。
- **G4 新增 17 项用例**：六个非订单链实体（cost_snapshots/cost_current/price_history/shipments/logistics_events/campaigns）workspace 不匹配、空 workspace、任意实体缺 `workspace_id` 列 FAIL、跨 workspace 同 `order_pk` 永不匹配（子文件）、跨 workspace 同 `order_pk` 在 orders 检出、logistics_events 父 workspace 不匹配、workspace manifest 覆盖全 12 文件且全 ok。

> 本工作项**保留全部既有 13 测试**（未删除/未放宽），G4 补充后 `test_v28_export_desensitize.py` 23→40 项 + `test_v28_recalc_quantification.py` 6 项 = **46 项**（见 §3.1）。

### 2.6 其他观察（非阻塞）

- `CARD_RE = \b(?:\d[ \-]?){12,18}\d\b` 为**数字串启发式**，非 Luhn 校验——长数字串（非卡号）可能误报（V3 对 32 位 hex 伪 ID 已豁免，但 13–19 位纯数字业务 ID 仍可能被标为卡）。保守方向（误报→FAIL）安全，但真实数据可能触发；建议改用 Luhn 校验以降低误报。
- JSON 内嵌套敏感**键名**（如 `name`/`address`/`city`）若其值为普通文本（非邮箱/电话/卡号/token），`_sweep_text` 不会按键名剔除（仅列级 `PII_KEYS` + 值级正则兜底）。因计划 §2 SQL 从不 SELECT 此类列、本地 schema 亦不存（§1.5），实际风险低；建议作为加固项在真实数据前确认 `profit_snapshot`/`rule_results` 已知键白名单。

---

## 3. 既有测试结果 + ruff 观察

### 3.1 测试结果（本轮实跑）

- 命令：`python -m pytest tests/test_v28_export_desensitize.py tests/test_v28_recalc_quantification.py -q`
- 环境：Python 3.12.10 / pytest 9.1.1（`E:\AI\nuotao-ai-os\.venv`）
- 结果：**46 passed in 3.03s**（`test_v28_export_desensitize.py` 40 项 + `test_v28_recalc_quantification.py` 6 项，全部 PASSED）。
- **既有 13 项全部保留**（未删除/未放宽，全部仍 PASSED）：salt 缺失 fail-closed、V1–V7 自校验、PII 无残留、PII 键剔除 + 伪 ID 稳定、NULL 不填 0（legit 0 保留）、孤立退款检出（V2，`samples == ["r-404"]`）、行数不一致检出（V1）、重算三态 + 缺失原因、R1 虚增金额/比例、R2 口径差方向、R7 版本缺口、全量分析端点。
- **新增 G4 补充 17 项用例**：六个非订单链实体（cost_snapshots/cost_current/price_history/shipments/logistics_events/campaigns）× workspace 不匹配 + 空 workspace（各 6）、任意实体缺 `workspace_id` 列 FAIL、跨 workspace 同 `order_pk` 永不匹配（子文件）、跨 workspace 同 `order_pk` 在 orders 检出、logistics_events 父 workspace 不匹配、workspace manifest 覆盖全 12 文件且全 ok。
- **既有 G3/G4 首轮 16 项仍全绿**：五关联文件孤立 `order_pk`、workspace 不匹配、缺 `workspace_id` 列明确标记、重复主键、空主键、必需关联字段缺失标记（不伪造 FK）、映射写入受限目录（0600/0700/保留期/无 salt/不入交付包）、映射不在 Git 且工作树内路径 fail-closed、缺 `--id-map-dir` fail-closed、受限路径与 out 重叠 fail-closed、日志/报告不泄漏原始 ID、两次运行字节一致（CSV + 映射 + 报告）。
- 结论：**46/46 全绿**（仅合成 fixture，无生产数据、无 DB、无网络），满足「原 13 项全绿」门禁并新增 G4 全实体 workspace 覆盖。

### 3.2 ruff 观察

- 本轮变更文件（`scripts/v28_export_desensitize.py`、`tests/test_v28_export_desensitize.py`、`tests/fixtures/v28_export_sample/make_fixture.py`、`tests/v28_export_g3_env_precheck.py`）经 pre-commit `ruff`（v0.8.4，`--fix`）**Passed**，`ruff-format` 已格式化（复跑 46 测试仍全绿）；**变更代码无 ruff 报错**。
- 既有 `scripts/v28_recalc_quantify.py` 等未触碰文件仍有 HEAD `60e89fa` 遗留的 14 项风格提示（UP012、FURB157、PLC0206、SIM102、PIE800、SIM118、RUF100、PLW1510），**非本变更引入**，仍列入「真实数据执行前」低优先级清理项（G5）。

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
| P3 | G3/G4 已修复（本工作项） | `_id_map_pseudo.json` 只写受限目录 + V2 五文件/主键/workspace 校验已实现并通过 29 测试（§3.1） |

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
4. **映射表保护（G3 已修复）**：`_id_map_pseudo.json`（含原始 ID）只写入 Owner 受控独立受限目录 `--id-map-dir`（仓库外、0600/0700、O_EXCL、fsync），**不随脱敏包交付、不入 Git（`.gitignore` 兜底）、不进日志/异常输出**；保留期由 `--id-map-retention-days` 声明，**销毁时点由 Owner 决定**。
5. **隔离**：salt 不进 SQL 引擎环境（脱敏在 SELECT 之后、本地进程内）；脱敏脚本无网络/无 DB（`v28_export_desensitize.py` docstring 明确 `no DB connection, no network`）。
6. **测试 salt**：仅合成 fixture 用 `v28-test-only-salt-do-not-use-in-prod`（`test-salt.txt` 已 gitignore）；生产 salt 绝不写入测试。

---

## 7. 已知缺口（数据源未就绪，待有权限人员提供）

| # | 缺口 | 影响 | 责任方 | 解除条件 |
|---|---|---|---|---|
| G1 | **无生产脱敏副本**（生产 DB 未只读导出，未脱敏） | 30 天样本验证**无法执行**；真实数据数字（R1/R2/R7）无法产出 | 生产 DBA（有权限人员） | 只读执行计划 §2 SQL 30 天窗口 → 产物交 DSH |
| G2 | **salt 未由 Owner 提供** | 脱敏脚本无法运行（fail-closed） | Owner/有权限人员 | 安全渠道提供 `--salt-file` |
| G3 | ~~`_id_map_pseudo.json` 未实现~~（已修复；真实置备待 Owner） | ~~无法显式拿到原始↔伪映射表~~ | 本工作项（代码已关闭）/ Owner（真实置备） | 受限目录落盘 + `.gitignore` 兜底 + 46 测试通过（§3.1）；**合成环境预检见 `docs/V2_8_EXPORT_G3_ENV_PRECHECK.md`**（Windows 宿主 POSIX 0600/0700 不生效 → 真实置备须在目标宿主复验 `stat`/`icacls`/`getfacl`） |
| G4 | ~~V2 仅校验 refunds~~（已修复） | ~~tax/payments/order_marketing/orders_lines 孤立行可能静默漏检~~ | 本工作项（已关闭） | V2 已扩展**全部 12 文件** workspace/主键/关联（`(workspace_id, order_pk)` 解析、跨 workspace 检出、schema 违约区分），46 测试通过（§3.1） |
| G5 | **ruff 14 项风格提示**（HEAD 既有，非本变更） | 不影响功能；低优先级 | 本工作项（后续，可选） | 统一 ruff 配置（backend/ruff.toml 或根配置）后清理 |
| G6 | **无 `price_publication_records`、无订单行级税、无退款手续费返还、无营销历史分摊**（R6/R12 等 schema 缺口） | 相应维度标 `LEGACY_NO_PUBLICATION_RECORD`/`not_collected`，不伪造 | 设计层（已记录 R 系列） | 长期；本次如实标注即可 |

---

## 8. 结论与下一步

- **只读 SQL**：通过（纯 SELECT、参数化、无生产连接、无凭据；计划 §2 全部组 SQL 投影 `workspace_id`）。
- **匿名化脚本**：通过（PII 删除 + 稳定伪 ID + salt fail-closed + NULL 不填 0 + **G3 受限映射目录 + G4 全 12 文件 workspace/主键/关联自校验**）；原 §2.5 两处差异已在本工作项修复。
- **既有 + 新增测试**：**46/46 全绿**（原 13 项全部保留未删除/未放宽 + G3/G4 首轮 16 项 + G4 补充 17 项，本轮实跑确认）。
- **G3 合成环境预检**：见 `docs/V2_8_EXPORT_G3_ENV_PRECHECK.md` —— 合成环境 11 项中 9 项通过，**2 项为 Windows 宿主 POSIX 模式不生效/ACL 未收紧（真实置备须在目标宿主复验）**；真实 id_map_dir 由 Owner 置备（本工作项未创建真实映射文件、未接收生产 Salt）。
- **G1/G2 准备**：见 `docs/V2_8_EXPORT_G1_G2_PREP_BLOCKERS.md` —— 字段映射/查询执行计划/输出文件清单/生产脱敏接收核验 SOP/salt 注入说明均已准备，**未执行**；G1（无生产脱敏副本）、G2（salt 未提供）仍阻塞。
- **0076**：冻结未触碰（blob 与 HEAD 一致）。
- **下一步（Owner 门禁）**：Owner 提供 salt（G2）+ 置备真实受限目录（G3 复验）→ 生产 DBA 只读导出 30 天（G1，按 G1/G2 文档 §4 SOP 接收核验）→ DSH 脱敏（V1–V7 + G3/G4）→ 本文件 §4/§5 验证 → Owner 决定 30→90 天扩展与受限映射销毁时点。
- **不宣称 V2.8 通过**；V2.8 相关结论待 Owner 依据真实数据验证结果单独宣布。

---

*（本文件为 EXPORT 审阅续证据，与 `docs/V2_8_HISTORICAL_DATA_EXPORT_PLAN.md` 配套；不替代计划，仅补充审阅结论 + 30 天样本验证方案 + 关联完整性清单 + 密钥管理口径。）*
