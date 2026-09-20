# 跨渠道客户身份与隐私合规设计

> 文档版本：v1.1  
> 状态：首期已完成（本地 PostgreSQL 与 Chrome 端到端验收通过）  
> 关联决策：`docs/business_decisions/ADR/PRIVACY-001.md`  
> 目标迁移：`0045`

---

## 1. 需求分析

### 1.1 业务目标

Nuotao AI OS 需要让同一个客户在以下渠道中保持一致身份：

- B2C 独立站与 WooCommerce 客户档案。
- B2B 门户账号、代理商联系人和企业客户。
- 邮件订阅、客服互动、CRM 和后续外部平台。

同时必须回答四个合规问题：

1. 我们基于什么标识把两个渠道记录认定为同一个人？
2. 客户在什么时间、对什么目的、通过什么渠道作出了授权或撤回？
3. 客户要求访问、导出、删除、更正或限制处理时，处理到了哪一步？
4. 删除时哪些数据已删除，哪些财务事实依法保留？

### 1.2 首期范围

首期包含：

- 工作区级 HMAC 身份链接。
- 确定性身份冲突与人工审批合并。
- 追加式同意账本与营销发送门禁。
- 数据主体请求、身份验证、审批和执行审计。
- 数据访问/导出和匿名化删除。
- 管理端 `/settings/customer-data`。

首期不包含：

- 自动模糊合并。
- 自动批准数据主体请求。
- 自动从第三方征信或广告平台抓取身份。
- 完整的字段级加密密钥托管；本阶段只停止新增明文身份并明确现有 B2B PII
  的处理边界。
- 法务保留策略的自动到期删除。

### 1.3 核心约束

- 所有表、服务和 API 必须带 `workspace_id`。
- AI Agent 不得直接执行身份合并、同意变更或数据删除。
- 原始身份值不得写入日志、事件 payload 或身份链接表。
- `business_model` 的 `BOTH` 只用于商品/渠道能力，订单仍严格使用 `B2C | B2B`；
  统一客户账户可使用 `B2C | B2B | BOTH`。

## 2. 架构设计

```text
WooCommerce / Portal / Support / CRM
                 |
                 v
         Identity Intake Service
                 |
        normalize + workspace HMAC
                 |
       +---------+----------+
       |                    |
 identity_hash match    no match
       |                    |
 same account           create account
       |                    |
       +----------+---------+
                  |
          canonical account
                  |
     +------------+-------------+
     |            |             |
  consent      merge         privacy
  ledger       review        requests
     |            |             |
     +------------+-------------+
                  |
        audit / event_log / UI
```

### 2.1 身份链接

`customer_identity_links` 保存可验证的身份指纹。一个账户可以拥有多个链接，
但一个身份哈希在工作区内只能有一个 canonical 账户。

验证状态：

```text
pending  待验证
verified 已验证且可解析到账户
conflict 已检测到另一账户使用同一身份，等待人工处理
rejected 验证失败
revoked  已撤销
merged   合并后停用
```

### 2.2 账户合并

来源账户和目标账户必须属于同一工作区。请求证据要求：

- 两侧各有一个相同身份哈希的链接。
- 至少存在一个 `verified` 链接。
- 不能把目标账户指向另一个已合并账户。
- 来源账户不能是已匿名化或已合并账户。

状态机：

```text
pending -> approved -> completed
pending -> rejected
pending/approved -> cancelled
```

执行合并时：

1. 解析目标 canonical account。
2. 把来源账户的所有未冲突外键重定向到目标账户。
3. 把冲突链接标记为 `merged` 并禁用。
4. 把有效同意继承为目标账户的新追加事件，不覆盖历史。
5. 来源账户写入 `merged_into_account_id` 和 `status=merged`。
6. 写入不可变合并动作和事件日志。

### 2.3 同意

`customer_consent_events` 是追加式账本，字段：

```text
customer_account_id
purpose
channel
status            granted | withdrawn
policy_version
source
evidence_json
occurred_at
recorded_by
idempotency_key
```

当前状态查询：

1. 找到账户在目的和渠道下 `occurred_at` 最新的账本事件。
2. 有事件时以事件状态为唯一真值。
3. 没有事件时，仅对 `marketing_email` 回退到旧 `email_subscriptions`。
4. 删除、限制处理会写入 `withdrawn` 事件。

### 2.4 数据主体请求

`data_subject_requests` 是请求主表，`data_subject_request_actions` 是追加式动作
日志。访问、导出、删除、更正和限制处理共用同一生命周期。

执行语义：

| 类型 | 自动处理 | 结果 |
|---|---|---|
| access/export | 返回受控 JSON 快照 | 包含账户、链接、同意、画像、订单/B2B 事实摘要 |
| delete | 匿名化直接身份、删除行为数据、撤回同意 | 财务事实保留 |
| restrict | 账户置为 `restricted`，撤回非必要处理同意 | 阻断营销和个性化 |
| correct | 人工修正后登记结果 | 必须填写执行说明 |

## 3. 数据库设计

### 3.1 `customer_accounts` 扩展

| 字段 | 类型 | 说明 |
|---|---|---|
| `merged_into_account_id` | UUID nullable | canonical 目标账户 |
| `merged_at` | timestamptz nullable | 合并时间 |

现有 `status` 扩展为 `active / restricted / anonymized / merged`。

### 3.2 `customer_identity_links`

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | UUID | PK |
| `workspace_id` | UUID | 必填、索引 |
| `customer_account_id` | UUID | FK、必填 |
| `channel` | varchar(32) | 渠道 |
| `external_system` | varchar(64) | 来源系统 |
| `identity_type` | varchar(32) | 类型 |
| `identity_hash` | varchar(128) | 工作区 HMAC |
| `hash_key_version` | varchar(32) | 密钥版本 |
| `fingerprint` | varchar(32) | 审计指纹 |
| `verification_status` | varchar(16) | 状态 |
| `verified_at` | timestamptz | 验证时间 |
| `last_seen_at` | timestamptz | 最近观测 |
| `disabled_at` | timestamptz | 停用时间 |
| `source` | varchar(64) | 来源说明 |
| `metadata_json` | JSONB | 非 PII 元数据 |

唯一约束：

```text
(workspace_id, customer_account_id, channel, external_system,
 identity_type, identity_hash)
```

应用层额外保证一个哈希只有一个 canonical 账户。

### 3.3 `customer_account_merges`

保存来源、目标、匹配哈希、匹配类型、证据、原因、申请人/审批人、结果和时间。
状态为 `pending / approved / rejected / completed / cancelled`。

### 3.4 `customer_consent_events`

追加式同意账本。`idempotency_key` 在工作区内唯一，防止网络重试产生重复事件。

### 3.5 `data_subject_requests`

保存请求编号、账户、类型、状态、身份验证方式、期限、处理人、决定、结果摘要和
证据。账户删除后仍保留去标识化请求记录。

### 3.6 `data_subject_request_actions`

不可变动作日志，动作包括：

```text
received / verified / approved / rejected / export_generated
identity_links_revoked / consent_withdrawn / profile_erased
b2b_contact_anonymized / account_anonymized / completed
```

### 3.7 渠道表关联

- `orders.customer_account_id`：B2C 订单直接关联统一账户。
- `email_subscriptions.customer_account_id`：旧订阅迁移到统一账户。
- 现有 `customer_profiles`、`b2b_agents` 和 B2B 销售/财务表继续使用账户 FK。

## 4. 技术选型

| 方案 | 成本 | 优点 | 缺点 | 适用场景 |
|---|---|---|---|---|
| 明文身份表 | 低 | 查询简单 | 泄露风险高，法规风险大 | 不可用于生产 |
| 无密钥 SHA-256 | 低 | 实现简单 | 低熵字段可被彩虹表反推，跨工作区可关联 | 仅非敏感去重 |
| 工作区派生 HMAC-SHA256 | 低 | 确定性、不可跨租户关联、可轮换版本 | 需要密钥管理 | 首期最佳平衡 |
| 云端 KMS + 字段级加密 | 中高 | 密钥托管、审计完善 | 成本和集成复杂度较高 | 生产规模化后升级 |

首期选择工作区派生 HMAC-SHA256。配置：

```text
CUSTOMER_IDENTITY_HMAC_KEY
CUSTOMER_IDENTITY_KEY_VERSION=v1
DATA_SUBJECT_REQUEST_DUE_DAYS=30
```

## 5. 开发步骤

1. 新增 `0045` 迁移和 ORM 模型。
2. 新身份服务：规范化、HMAC、账户解析、冲突检测、合并。
3. 新同意服务：追加事件、当前状态、营销门禁。
4. 新数据主体请求服务：受理、验证、审批、导出、删除、限制处理。
5. 新增 `/api/v1/admin/customer-data` API 和 RBAC。
6. 把 WooCommerce 客户、订单同步统一接入身份服务。
7. EDM 发送前置检查统一同意账本。
8. 新增 `/settings/customer-data` 管理端页面。
9. 增加单测、API/RBAC、迁移往返和 Chrome E2E。
10. 更新兼容性审计、前端架构、路线图和业务决策索引。

## 6. 测试方案

### 6.1 单元测试

- 规范化在不同大小写/空格下稳定。
- 相同身份在相同工作区哈希一致，不同工作区哈希不同。
- 身份首次导入创建账户和 verified 链接。
- 同一身份第二个账户产生 conflict，不自动合并。
- 合并必须同工作区、同哈希、管理员执行。
- 合并后来源账户解析到目标账户，业务外键重定向。
- 同意按目的和渠道取最新事件，撤回立即生效。
- 没有账本时兼容旧订阅；有撤回账本时旧订阅不能绕过。
- 删除只匿名化直接身份并保留订单/发票事实。

### 6.2 API/RBAC

- 匿名访问返回 `401`。
- viewer 只读，operator 可登记身份/同意/请求，admin 才能合并、审批和执行删除。
- 所有读取和写入强制工作区条件。
- 请求 body 中的 `workspace_id` 不能切换租户。

### 6.3 迁移

- PostgreSQL `0044 -> 0045 -> 0044 -> 0045`。
- 验证新表、外键、索引和 self-FK。
- 验证 downgrade 删除新增列而不影响旧数据。

### 6.4 前端验收

- `/settings/customer-data` 在桌面和 390px 移动端可用。
- Chrome 中完成真实接口加载、身份冲突展示、合并审批、同意撤回和数据请求状态。
- 无 API `401/403/500`、无控制台错误、文本不重叠。

## 7. 实施与验收记录

验证日期：2026-09-13

- 身份链接、确定性冲突、人工合并、同意账本、EDM 门禁、隐私请求与 API/RBAC
  组合测试共 30 项通过。
- PostgreSQL `0044 -> 0045 -> 0044 -> 0045` 迁移往返通过；当前本地数据库版本为
  `0045`。
- `frontend/e2e/customer-data.spec.ts` 在 Google Chrome 中通过：
  - 桌面端完成身份冲突、合并审批、合并执行、同意授权、同意撤回，以及访问请求的
    “登记 -> 核验 -> 批准 -> 执行 -> 已完成”完整链路。
  - 390px 移动端无横向溢出、无 API `401/403/500`、无控制台错误。
- 数据主体访问/导出快照中的同意时间统一序列化为 ISO 字符串，避免 JSONB
  写入时出现 `datetime` 序列化错误。
- 前端 `npm run typecheck` 与 `npm run build` 通过；仅保留既有
  `antd-vendor` 大包告警。

### 7.1 部署边界

- 代码合并不等同于生产开放删除：生产必须先配置独立
  `CUSTOMER_IDENTITY_HMAC_KEY`，禁止使用开发默认密钥。
- 部署顺序为备份数据库 -> 执行 `0045` -> 配置身份密钥 -> 验证身份解析、EDM
  门禁与隐私请求只读流程 -> 由法务/数据负责人确认保留规则后开放删除和限制处理。
- 生产开放前仍需完成 staging 迁移、密钥轮换演练、备份恢复演练和隐私请求抽样复核。
- 本阶段不包含自动模糊合并、自动批准请求、第三方征信抓取和完整字段级加密托管。
