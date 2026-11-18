# M440-01 前置审计报告（M4.4 — B2B Lead Management & Sales Workflow）

> 阶段：M440-01 前置审计（只读检查）
> 审计对象：`b2b_leads` 数据域（模型/服务/API/迁移/安全）
> 结论：**审计完成，发现 P0（PII 明文）+ P0（secret-scanning 根因未明）+ 状态机需扩展（含 DB 迁移，需 Owner 审批）**

## 1. 仓库与 Git 基线
| 项 | 值 | 结论 |
|---|---|---|
| 分支 | `main` | ✅ |
| 最新 commit | `d72d1c8`（docs(m43) 状态报告）、`ffc56ff`（字段映射修复）、`057c7be`（视觉优化） | ✅ 与 M4.3 一致 |
| 变更文件 | 本次仅新增审计/迁移/测试/报告 | ✅ 无越界 |

## 2. b2b_leads 数据结构（`backend/app/models/b2b_leads.py`）
- 表 `b2b_leads`（B2BLead：Base + TimestampMixin + WorkspaceMixin）
- **核心字段**：`reference_number`（unique）、`company_name`、`contact_name`、`email`（**PII 明文**）、`country`、`business_type`、`products_of_interest`(AI_JSON)、`message`、`privacy_consent`、`consent_at`
- **内部管理字段**：`assigned_to`、`internal_notes`、`follow_ups`(AI_JSON)、`converted_application_id`(FK b2b_agents)、`converted_at`、`closed_lost_reason`、`spam_reason`
- **状态**：`status`（**当前 7 状态**，CheckConstraint）
- **索引**：`ix_b2b_leads_status_created`、`ix_b2b_leads_email`、`ix_b2b_leads_country` ✅
- **约束**：`uq_b2b_leads_reference_number`、`ck_b2b_leads_status`（7 状态）、`ck_b2b_leads_source` ✅

### 状态机现状 vs 指令
| 来源 | 状态集合 |
|---|---|
| 现状 | `new/reviewing/qualified/contacted/converted/closed_lost/spam`（7） |
| M440-02 指令 | `NEW/ASSIGNED/CONTACTED/QUALIFIED/QUOTING/QUOTED/NEGOTIATING/CONVERTED/CLOSED_WON/CLOSED_LOST/SPAM`（11） |

**差距**：现状**无** `assigned`/`quoting`/`quoted`/`negotiating`/`closed_won`；现状**有** `reviewing`（指令无）。→ **M440-02 需重构状态机 + DB `ck_b2b_leads_status` 迁移（生产 DB 迁移需 Owner 审批）**。

## 3. 服务层（`b2b_showcase_service.py`）
- `create_public_lead`：source 服务端固定 `b2b_public_website`，**绝不创建 b2b_agents** ✅；`status="new"`；`email` 小写/去空格；`event_log`（`b2b_lead.created`，**不含 PII/正文**）✅
- `update_lead`：**非法状态迁移抛 `LeadStateError`** ✅；`closed_lost`/`spam` **必须有书面原因** ✅；每次业务变更 append `event_log`（`status_changed`/`assigned`/`note_added`/`followup_scheduled`）✅
- `convert_lead_to_application`：**仅 `qualified`/`contacted` 可转**；**幂等**（已转直接返回）✅；`event_log`（`b2b_lead.converted`）✅；终态 `converted` 须关联真实 agent ✅
- `LEAD_STATUS_TRANSITIONS`：7 状态矩阵（`new→reviewing/qualified/closed_lost/spam` 等；终态无出边）——**待按 M440-02 扩展**
- **事件审计**：`event_service.create_event`（append-only，payload 仅 reference/state/actor，**无 PII**）✅

## 4. 通知可靠性（`b2b_lead_notification.py`，M440-05）
- **先持久化 Lead，后通知**；通知失败**绝不回滚 Lead** ✅
- 无 recipient 配置 → **优雅跳过**（`skipped: no_recipient_configured`，非发送失败）✅
- 通知失败 → **append `b2b_lead.notification_failed`（retryable=True，仅 reference，无 PII）** ✅
- 邮件内容**不含完整联系详情/正文**（仅 reference/company/country/business_type + 认证控制台链接）✅
- 无营销内容、无虚构收件人 ✅
- **差距（M440-05）**：无**通知状态/重试次数/重试记录/重复通知防护**列——**待增强**（需迁移）

## 5. API 认证 / RBAC（`b2b_showcase.py`）
- `admin_router`（`/admin/b2b/leads`）：**`Depends(get_current_user)` + `get_current_workspace_id`** ✅ 需认证
- `showcase_admin_router`（`/admin/b2b/showcase`）：**`Depends(get_current_user)`** ✅ 需认证
- 公开端点（public catalog / public submit lead）：无认证（预期，公开表单）✅
- **差距（M440-03/06）**：需确认 `get_current_user` 是否含**角色/RBAC**（admin/运营/只读）——M440-03 需角色分级；内部字段（`internal_notes`/`follow_ups`/`assigned_to`）**不得暴露公开**——需在 schema 层确认（当前 admin 专用 response_model）。

## 6. 安全与隐私（M440-06）
- **P0：`email`/`contact_name` PII 明文存储**（`b2b_leads.email` String(255)、`contact_name` String(100)）——**违反 AGENTS.md §4.1 L4（PII 加密存储）**。需：**报告 + 加密迁移方案**（AES-256 + KMS 或应用层加密）——**生产 DB 迁移需 Owner 审批**。
- `event_log` payload：**无 PII 明文** ✅（仅 reference/state/actor）
- 通知邮件：**无 PII 全文** ✅
- **差距**：`b2b_leads` 无 `trace_id`（M440-01 指令检查项）——**待补**（可加 `trace_id` 列，迁移）。

## 7. 测试 Lead 标记（M440-07 相关）
- 已知测试 Lead：`LD-20261117-6B43B6`（API 验证）、`LD-20261117-3ECF02`（浏览器 E2E）——公司名 `M4.3 Pipeline Test` / `M4.3 Browser Test`
- **现状**：`b2b_leads` **无 `is_test` 标记列**——**待补**（迁移；或按 reference/公司名约定排除）——**M440-07 明确：不得计入真实销售统计**。
- **查询位置**：生产 DB `b2b_leads`（`/opt/nuotao-ai-os/backend`，需 SSH 只读确认——**审计只读，不修改**）。

## 8. secret-scanning 0-job（独立问题，ChatGPT 要求查明）
- 现状：每次 push `failure`，`total_jobs=0`、`run log: not found`、`conclusion_reason` 空、`event=push`、`head_sha=d72d1c8`。
- `secret-scanning.yml` 结构：`on: push/pull_request`、`gitleaks`（matrix `mode:[diff]`）、`history`（main only）、`gitleaks/gitleaks-action@v2`、`trufflehog`（push main）、`permissions: security-events: write`。
- **根因待深查**（候选：`branches: ["**"]` 匹配/解析、`gitleaks-action@v2` 引用、`permissions` 或触发条件）——GitHub 侧未提供 reason。
- **独立记录**：见 `M440-09` 验收 + 独立问题清单；**不作为 M4.4 阻塞**（预先存在），但**M440-09 需给明确结论**。

## 9. 结论与下一步
- **M440-01 完成**（审计发现记录如上）。
- **P0 项**：① PII 明文（需迁移方案 + Owner 审批）；② secret-scanning 根因未明（独立深查）；③ 状态机扩展（含 DB 迁移）。
- **下一步**：M440-02（Lead 状态机重构 + 转换矩阵 + 审计）+ 迁移文件（本地，部署时 Owner 审批）。
