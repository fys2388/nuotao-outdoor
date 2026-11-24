# V2.8 EXPORT G1/G2 准备文档（仅 PREPARE，未执行）

> 工作项：`V2.8-HISTORICAL-DATA-EXPORT-PREP`（Owner「定价原则评审 (2)」EXPORT G3/G4 审阅与 30 天验证最终指令，2026-11-24）。
> 角色：`v28-export-g4-workspace`。分支：`audit/pricing-v28-historical-export`（HEAD `122127f` → 本工作项新 HEAD）。
> 状态：**G1/G2 为「准备」，本工作项只产出计划与 SOP，未执行**。红线遵守：未连接生产库、未运行生产 SQL、未导出真实数据、未读取/接收生产 Salt、未对真实数据脱敏、未做历史财务重算。真实 30 天导出等待 Owner 单独书面批准。
> 关联：本文件与 `docs/V2_8_HISTORICAL_DATA_EXPORT_PLAN.md`（§1 字段映射、§2 SQL、§3 脚本设计）、`docs/V2_8_EXPORT_G3_ENV_PRECHECK.md`（G3）配套。

---

## 1. G1 准备：字段映射（已就绪，引用计划 §1 + schema 复核）

- 字段映射表在计划 §1（`docs/V2_8_HISTORICAL_DATA_EXPORT_PLAN.md` §1.x），逐实体给出「源列 → 导出列」。
- **schema 复核结论（已通过 `backend/app/models/` 确认）**：12 个导出实体全部 workspace-scoped（`WorkspaceMixin.workspace_id` 非空）或显式 `workspace_id`（`ProductMapping`）。因此**每个导出文件都必须投影 `workspace_id`**（见 G4，计划 §2 SQL 已同步补上 C/D/F/G 组的 `workspace_id` 投影）。
- 导出列 = 计划 §2 各 SELECT 投影列；`orders` 用 `o.id AS order_pk`、`orders_lines` 用 `oi.id AS line_pk` 等。

## 2. G1 准备：查询执行计划（只读，未在生产执行）

- **仅准备**，**未连接生产**。生产 DBA 执行前应做的只读步骤（全部 `EXPLAIN`/`EXPLAIN (ANALYZE)`，无 DDL/DML）：
  1. `EXPLAIN (ANALYZE, BUFFERS) <计划 §2.1 A 组 SQL>` —— 验证 `orders(received_at)` 索引与 `workspace_id` 过滤选择性；
  2. 逐组 `EXPLAIN` B/C/D/E/F/G —— 重点：C-2 子查询（`order_items.workspace_id` + `order_id IN orders`）无嵌套循环放大、D 组 `products(workspace_id, deleted_at)` 过滤、F 组 `shipment_records(workspace_id, created_at)` 与 `logistics_events(shipment_id, workspace_id)` 索引；
  3. `EXPLAIN` 时记录 estimated rows / 实际 rows / 时间，供 Owner 判断窗口规模与成本上限；
  4. **只读**：全部为 `SELECT`/`EXPLAIN`；无 `COPY` 到生产侧之外的写操作（`COPY (SELECT...) TO STDOUT` 为只读导出，落到 DBA 侧只读副本目录）。
- 阻塞项：**G1 真实执行计划未运行**（需生产 DBA 权限；本工作项无权连接生产）。

## 3. G1 准备：输出文件清单（已就绪）

| 组 | 输出文件（`data/desensitized/`） | 来源 SQL | 是否含 `workspace_id` |
|---|---|---|---|
| A | `orders.csv` | §2.1 | ✅ `o.workspace_id` |
| A | `orders_lines.csv` | §2.1（`oi.*` 列） | ✅ `oi.workspace_id` |
| B | `tax.csv` | §2.2 | ✅ `o.workspace_id` |
| C | `cost_snapshots.csv` | §2.3 C-1 | ✅（本轮补） |
| C | `cost_current.csv` | §2.3 C-2 | ✅（本轮补） |
| D | `price_history.csv` | §2.4 | ✅（本轮补） |
| E | `payments.csv` | §2.5 E-1 | ✅ `o.workspace_id` |
| E | `refunds.csv` | §2.5 E-2 | ✅ `r.workspace_id` |
| F | `shipments.csv` | §2.6 F-1 | ✅（本轮补） |
| F | `logistics_events.csv` | §2.6 F-2 | ✅（本轮补） |
| G | `campaigns.csv` | §2.7 G-1 | ✅（本轮补） |
| G | `order_marketing.csv` | §2.7 G-2 | ✅ `o.workspace_id` |

- 另产出 `desensitization_report.json`（报告，无原始 ID、无路径）+ 受限 `--id-map-dir/_id_map_pseudo.json`（G3，不入交付包）。
- 共 **12 个数据文件 + 1 报告 + 1 受限映射**。

## 4. G1 准备：生产脱敏副本「接收/核验」流程（SOP，未执行）

> 目的：生产 DBA 只读导出后，DSH 接收脱敏副本时先核验再处理，确保不误收未授权/被污染数据。**本工作项未接收任何真实副本。**

1. **接收前声明**：Owner 书面授权范围（workspace_id、时间窗、批次）；DSH 只在授权范围内接收。
2. **完整性核验**（脚本外，DSH 侧）：
   - 文件数 == 12；`sha256sum` 逐文件比对 DBA 提供的清单；
   - 行数核对（与 DBA `count(*)` 一致，`wc -l` 交叉）；
   - 列头核对：每文件列头 == 计划 §2 投影列（含 `workspace_id`，G4）；缺列 → 拒绝处理并回退 Owner；
   - `workspace_id` 每行非空且等于授权 workspace（G4 V2 已内置，接收时再人工抽查 ≥10 行）。
3. **落盘**：仅落到 `data/raw_export/`（gitignore，不入库）；**不触碰任何生产侧路径**。
4. **处理**：`scripts/v28_export_desensitize.py` 在纯本地运行（无网络/无 DB），V1–V7 + G3/G4 全通过才写受限映射。
5. **交付**：脱敏副本（12 CSV + 报告）交 Owner 复核；受限映射仅留在 Owner 受限目录，销毁时点 Owner 决定。
6. **异常路径**：任一核验失败 → 不处理、不脱敏、不写映射，记录并回退 Owner。

## 5. G2 准备：salt 注入说明（未接收真实 Salt）

- **生成**：Owner/有权限人员生成高熵随机 salt（≥32 字节，`secrets.token_hex` 级别）；**不进入仓库、不写入文档、不进环境变量示例**。
- **交付**：经安全渠道（加密文件 `--salt-file`，权限 0600，或受控 CLI）；交付后 DSH 侧**立即只读进内存**，不落盘副本、不打印。
- **读取**：脚本仅 `--salt-file` 读入；缺失/空 → `exit 2` fail-closed，**不写默认 salt、不降级**。
- **隔离**：salt 不进 SQL 引擎环境（脱敏在 SELECT 之后、本地进程）；无网络/无 DB（脚本 docstring 明确）。
- **测试 salt**：仅合成 fixture 用 `v28-test-only-salt-do-not-use-in-prod`（已 gitignore）；生产 salt 绝不进测试。
- **阻塞项**：**G2 salt 尚未由 Owner 提供** → 脱敏脚本对真实数据无法运行（fail-closed），需 Owner 置备。

## 6. 阻塞项汇总（本工作项如实报告，不绕过）

| # | 阻塞项 | 状态 | 责任方 | 解除条件 |
|---|---|---|---|---|
| G1 | 生产 DB 未只读导出、未脱敏 → 无生产脱敏副本 | 阻塞（本工作项无权） | 生产 DBA | Owner 书面批准后，DBA 执行计划 §2 只读导出 → 交 DSH 按 §4 SOP 接收核验 |
| G2 | 生产 salt 未由 Owner 提供 | 阻塞 | Owner/有权限人员 | 安全渠道提供 `--salt-file`（§5） |
| G3 | 真实 id_map_dir 未置备（合成预检已过；Windows 宿主 POSIX 0600/0700 不生效） | 阻塞（真实置备） | Owner | 目标宿主置备目录 + `stat`/`icacls`/`getfacl` 证据 → DSH 启用前复验（见 G3 报告 §4） |
| G4 | —— | 本工作项已实现 | 本工作项 | 46 测试全绿（见审阅报告） |
| G5 | ruff 14 项风格提示（HEAD 既有） | 低优先级（本工作项不修） | 后续 | 统一 ruff 配置后清理 |
| G6 | `price_publication_records`/行级税/退款手续费返还/营销历史分摊缺失（R6/R12 等） | 如实标注不伪造 | 设计层 | 长期 |

---

*（本文件为 EXPORT G1/G2「准备」证据；任何一项均未对生产执行。）*
