# ADR PRIVACY-001 - 跨渠道客户身份、同意与数据主体权利

> 状态：**Accepted**（2026-09-13）  
> 决策编号：PRIVACY-001  
> 关联：`COMMERCE-001`、`FINANCE-001`、`FINANCE-003`

---

## Context（背景）

B2C 与 B2B 共用 `customer_accounts` 后，客户可以在独立站、B2B 门户、邮件、
客服和未来第三方 CRM 中留下不同标识。当前实现存在以下问题：

- WooCommerce 连接器、订单同步服务和批量同步服务使用三套截断长度不同的
  SHA-256，不能稳定对应同一个统一账户。
- B2C 订单只有 `customer_reference_id`，没有直接关联 `customer_accounts`。
- B2B 联系人姓名、邮箱、电话和地址为明文；门户订单地址也包含 PII。
- 营销同意只存在于 `email_subscriptions`，不能按目的和渠道追溯，也没有稳定
  关联统一账户。
- 现有删除接口仅删除单条行为记录，不能完成身份解绑、同意撤回、联系人匿名化
  和可保留财务事实的处理。
- 缺少数据访问、导出、删除、更正和限制处理的请求台账、验证责任与期限。

如果继续按渠道分别修修补补，将无法回答“这个人是谁”“谁同意了什么”
以及“删除请求执行到哪一步”，也无法满足 GDPR 类监管要求。

## Decision（决策）

### 1. 统一账户是身份和同意的唯一入口

`customer_accounts` 保持非 PII 主数据。渠道档案、B2B 门户账号、订单和营销订阅
只引用统一账户，不各自创建身份真值。

账户允许状态扩展为：

```text
active / restricted / anonymized / merged
```

合并后的来源账户通过 `merged_into_account_id` 指向目标账户。服务层读取时必须
解析 canonical account，禁止分析、营销和客服各自实现重定向。

### 2. 原始身份值不落库，只保存工作区级 HMAC 指纹

身份链接支持：

```text
channel          = b2c_store | b2b_portal | email | support | crm | other
external_system  = woocommerce | b2b_portal | manual | import | other
identity_type    = email | phone | woocommerce_customer_id | company_tax_id | other
```

原始邮箱、电话或外部 ID 只在请求内存中使用。落库字段为：

```text
identity_hash = HMAC-SHA256(master_key, workspace_id + key_version + normalized_value)
fingerprint   = 哈希前缀，仅用于审计定位
```

主密钥通过 Secrets 管理。生产环境缺少密钥时身份写入失败关闭，不使用公开常量
或明文回退。

### 3. 合并必须基于确定性证据，禁止模糊合并

一个身份哈希只能有一个 canonical 账户。检测到同一哈希落到另一个账户时：

1. 不自动合并。
2. 记录冲突链接。
3. 生成待审批的 `customer_account_merges`，保存来源账户、目标账户、匹配哈希、
   匹配类型和证据。
4. 只有管理员可批准并执行。
5. 执行时把来源账户标记为 `merged`，重定向业务外键，保留来源链接作为审计。

禁止按姓名相似度、模糊邮箱、地址接近程度或 LLM 判断自动合并。

### 4. 同意使用追加式账本

`customer_consent_events` 按“账户 + 目的 + 渠道”记录授权或撤回。事件不可覆盖，
当前状态由最新事件派生。

首期目的：

```text
marketing_email
transactional_email
analytics
personalization
ai_processing
```

营销邮件发送必须检查对应目的的当前同意。已有 `email_subscriptions` 只作为迁移期
兼容来源；一旦统一账户存在同意账本，账本优先级更高，撤回立即阻断发送。

### 5. 数据主体请求具有完整生命周期

`data_subject_requests` 支持：

```text
access / export / delete / correct / restrict
```

生命周期：

```text
received -> verifying -> approved -> processing -> completed
received/verifying -> rejected
approved/processing -> cancelled
```

请求必须记录身份验证方式、受理人、处理人、期限、决定原因、执行结果和不可变动作
日志。删除和限制处理只允许管理员执行，查询与导出结果只通过认证管理接口返回。

### 6. 删除采用“匿名化事实，删除身份和营销用途”

删除请求执行时必须：

- 禁用全部身份链接并解析 canonical account。
- 撤回营销、个性化和 AI 处理同意。
- 匿名化 B2B 联系人姓名、邮箱、电话、城市和地址，并禁用门户登录。
- 删除无财务保留价值的行为画像、互动和知识条目。
- 清除 B2C 订单上的渠道身份引用。
- 保留订单、报价、合同、发票、收款和账务事实，只通过匿名账户 ID 关联。
- 把账户状态改为 `anonymized`，同时写入动作日志和事件日志。

保留财务事实时不得保留公开可识别的直接联系方式。需要法务保留的字段必须在
请求结果中列出依据和范围。

## Consequences（后果）

### 正面

- B2C 与 B2B 跨渠道身份有一致、可审计的命名空间。
- 营销是否可发送不再依赖单个旧表状态。
- 数据访问、导出、删除和限制处理可追踪、可追责。
- 财务与合同事实可保留，个人身份可断开，避免“一删全断”或“只删 UI”。
- 后续接入 CRM、Shopify、Amazon 或客服系统时复用同一身份协议。

### 成本

- 需要配置和轮换身份 HMAC 主密钥。
- 合并与删除必须人工审批，运营流程增加一步。
- 旧 `customer_accounts` 和 `email_subscriptions` 存在迁移期兼容逻辑。
- 当前 B2B 明文 PII 的字段级加密仍需在后续安全迁移中完成，本 ADR 先实现
  身份、同意、删除与审计边界，不把加密密钥写入数据库。

## Alternatives（备选与否定理由）

| 方案 | 成本 | 优点 | 缺点 | 适用场景 |
|---|---|---|---|---|
| 按邮箱明文直接合并 | 低 | 实现快 | 泄露风险高，大小写/别名仍会分叉 | 内部低敏原型 |
| 每渠道独立客户 ID | 低 | 边界简单 | 无法形成统一 CRM 和数据飞轮 | 渠道完全独立 |
| 姓名/地址模糊匹配自动合并 | 中 | 命中率高 | 错并不可逆，隐私和业务风险高 | 有专门身份治理团队和人工复核 |
| 本 ADR：HMAC + 确定性冲突 + 人工审批 | 中 | 可审计、可迁移、低误合并 | 需要密钥和审批流程 | B2C + B2B 一体化经营 |

## Rollout（上线顺序）

1. 迁移 `0045` 建立身份链接、合并、同意和数据主体请求表。
2. B2C 订单与 WooCommerce 客户同步统一使用身份服务。
3. B2B 门户和后台客户创建写入已验证身份链接。
4. EDM 发送增加按目的校验。
5. 管理端 `/settings/customer-data` 开放只读与受控写操作。
6. 完成单测、API/RBAC、迁移往返和 Chrome 端到端验收后再开放生产删除。

## Verification（验收）

- 相同工作区、相同规范化身份总能解析到同一 canonical 账户。
- 不同工作区即使身份值相同，哈希也不同。
- 同一身份落到两个账户时只产生冲突和待审批记录，不自动合并。
- 管理员执行合并后，业务引用指向目标账户，来源账户不可再作为独立身份使用。
- 撤回 `marketing_email` 同意后，EDM 发送被确定性阻断。
- 数据导出只返回该工作区该账户的数据，不泄露其他租户。
- 删除后直接联系方式被匿名化，订单和发票事实保留，身份链接禁用。
- PostgreSQL `0044 -> 0045 -> 0044 -> 0045` 往返通过。
- Google Chrome 可完成身份冲突、合并审批、同意撤回和数据请求状态验收。

## Related Decisions（关联决策）

- `COMMERCE-001`：统一客户主数据与 B2C/B2B 共享底座。
- `FINANCE-001`：发票与应收事实的法定保留边界。
- `FINANCE-003`：客户风控和状态变更的人工审批原则。
