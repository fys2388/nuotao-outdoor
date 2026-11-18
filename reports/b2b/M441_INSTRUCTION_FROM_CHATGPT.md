# M4.4 Owner 执行指令（ChatGPT — 2026-11-18）

> 来源：ChatGPT「系统开发和优化」对话，对 M4.4 完成报告的回复（Owner Decision — M4.4 Production Migration Authorization）
> Decision Date: 2026-11-18

## 1. Owner Approval

### APR-M440-DB-001 — 生产 DB 迁移 0085 / 0086
**Status: APPROVED WITH PRE-FLIGHT CONDITIONS**

仅授权这两个迁移：
- 0085 — B2B Lead 状态约束与相关 schema 变更
- 0086 — `b2b_lead_quotes` 表与相关 schema 变更

**执行前必做**：
1. 确认生产当前 Alembic revision
2. 确认 0085/0086 尚未应用，迁移顺序与 SQL 与 Staging 验证版本完全一致
3. 校验生产现有 Lead 记录是否满足新状态约束（历史状态值、空值、非法状态）
4. 确认生产数据库备份成功，记录备份时间、恢复点、恢复责任人
5. 确认不会顺带执行无关待处理迁移
6. 记录操作人、执行时间、迁移输出、trace/reference ID

**执行后验证**：生产 Alembic revision；Lead 状态约束生效；`b2b_lead_quotes` 表与索引；既有 Lead 记录完整性；Admin Lead 管理与报价 API；公开 API 不暴露内部 Lead 字段。

**停止条件**：revision 与预期不符、发现未处理非法状态、备份失败、迁移 SQL 与 Staging 不一致 → 任一出现即 STOP 并报告。
**禁止**：强行迁移、手工改 revision、用 `stamp` 伪装迁移成功、无关 schema 变更。失败时先保留证据再定恢复方案。

### APR-M440-DATA-001 — 标记两条测试 Lead
**Status: APPROVED**

仅以下两条记录：`LD-20261117-6B43B6`、`LD-20261117-3ECF02` → `is_test = true`

限制：不改其他字段；不删除记录；不改其他 Lead；记录操作人/时间/原因/trace_id；验证恰好命中并更新 2 条；验证经营统计排除这两条。**命中数不是 2 即 STOP 并报告。** 必须走现有业务服务或受控数据维护脚本，不得绕过审计。

### APR-M440-PII-001 — 生产 PII 加密迁移
**Status: NOT APPROVED FOR PRODUCTION EXECUTION**

允许：加密架构设计、应用代码实现、自动化测试、Staging 迁移与回填测试、密钥管理与恢复设计、迁移与回滚 runbook。
禁止：修改生产 PII 数据、生产加密回填、删除/覆盖现有明文字段、变更生产加密密钥、PII 加密的生产 schema 迁移。

申请前需提供：邮箱 HMAC-SHA-256 设计与密钥分离；AES-256-GCM + KMS 信封加密设计；`contact_name` 保护策略；旧/新字段双读写过渡；历史回填与核对结果；重复邮箱与规范化处理；Admin 访问与解密授权矩阵；密钥轮换/KMS 故障/恢复方案；备份恢复兼容；生产回滚与明文退役方案；Staging 测试结果与安全评审。

## 2. 明确排除（本次不授权）
其他数据库迁移；生产 Lead 删除或批量修改；PII 加密生产迁移；无关应用变更的生产部署；Admin API 对外暴露；DNS/Cloudflare/基础设施变更；客户邮件活动或自动报价投递；WooCommerce 商品/价格/库存修改。

## 3. 必须交付
生产 pre-flight 报告；备份验证证据；迁移执行日志（脱敏，无密钥与 PII）；迁移后验证报告；两条测试 Lead 更新审计；统计排除验证；PII 加密设计与 Staging 测试报告；Git commit 与变更文件清单；每项审批的最终状态（只用 PASS / NEEDS_EVIDENCE / BLOCKED / NOT_STARTED）。

## 4. M4.4 最终状态认定（Owner 建议拆分）
| 项目 | 认定 |
|---|---|
| M4.4 代码及测试 | PASS（依据报告） |
| Staging 迁移 0085/0086 | PASS（依据报告） |
| Production 迁移 | APPROVED，待执行及验收 |
| 测试 Lead 标记 | APPROVED，待执行及验收 |
| PII 加密设计 | NEEDS_EVIDENCE |
| PII 生产迁移 | NOT_APPROVED |
| Secret-scanning 0-job | BLOCKED / NEEDS_EVIDENCE，待查明 |

> 原则：**批准迁移不等于迁移成功**；批准数据修正不等于数据已修正。DSH 必须提供生产执行证据后，才能把对应事项更新为 PASS。
