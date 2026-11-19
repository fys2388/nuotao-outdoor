# B2B 独立 GA4 架构设计

> **任务编号**：D8-C · 交付物 #3
> **日期**：2026-11-18
> **状态**：方案设计（Draft）· **待 Owner 审批**
> **目标站点**：B2B `b2b.nuotaooutdoor.com`（展示站，RFQ 询盘，**非交易**）
> **对照站点**：B2C `nuotaooutdoor.com`（WooCommerce，GA4 Property `536153168` / `G-30GWC4FYMG`）
> **性质**：**仅架构设计**，**本轮不创建新 GA4 Property、不部署生产追踪**
> **Owner 决策**：批准方案设计，**暂不进行生产部署**

---

## 0. 本轮范围

### 0.1 本轮做

- 论证 B2B 与 B2C 业务模型差异及混流危害。
- 决策：B2B 采用**独立 GA4 Property**。
- 设计 B2B 事件体系（含「普通表单提交 ≠ 有效询盘」的 qualifying 原则）。
- 明确数据隔离原则与实施前提。

### 0.2 本轮不做

- ❌ 不创建新的 GA4 Property / Measurement ID。
- ❌ 不在 B2B 站部署任何追踪代码 / 埋点。
- ❌ 不改动 B2C 现有 GA4（`536153168`）。
- ❌ 不实施生产部署（待 Owner 后续批准）。

---

## 1. 背景：为什么不能混流

### 1.1 业务模型差异

| 维度 | B2C（nuotaooutdoor.com） | B2B（b2b.nuotaooutdoor.com） |
|---|---|---|
| 业务目标 | 在线**交易**（卖户外/露营产品） | 展示 + **RFQ 询盘**（批发/代理意向） |
| 核心转化事件 | `purchase`（真实成交） | `generate_lead`（询盘意向，非成交） |
| 客单/周期 | 单笔零售、短周期 | 大单、长周期、需线下跟进 |
| 成功度量 | 转化率、ROAS、AOV | 有效询盘量、询盘质量、跟进转化 |
| 转化语义 | **真金白银的收入** | **潜在商机（lead）** |

### 1.2 混流危害

若 B2B 与 B2C 共用同一 GA4 Property（`536153168`）：

| 危害 | 说明 |
|---|---|
| **转化率被稀释/污染** | B2C 的 `purchase`（真实成交）与 B2B 的 `generate_lead`（意向）混在同一转化集，转化率失去可比性与可信度 |
| **ROAS 失真** | Google Ads ROAS 依赖 purchase 价值；混入 B2B lead 会扭曲广告回报计算与出价策略 |
| **归因混乱** | 两个站流量、用户行为、转化路径截然不同，混流导致渠道归因不可解读 |
| **漏斗不可分析** | B2C 结账漏斗与 B2B RFQ 漏斗语义不同，混在一起无法定位各自流失点 |
| **报表口径不可信** | 商业分析 / AI 商业分析 Agent 基于污染数据做决策，结论失真 |

**结论**：B2B 与 B2C 数据**必须隔离**。B2B 采用**独立 GA4 Property**，不与 B2C `536153168` 混流。

---

## 2. 决策：B2B 独立 GA4 Property

| 决策项 | 结论 |
|---|---|
| 是否复用 B2C Property | ❌ 不复用 `536153168` |
| B2B Property | **新建独立 GA4 Property**（本轮不创建，仅设计） |
| Measurement ID | B2B 站使用**独立 Measurement ID**（区别于 `G-30GWC4FYMG`） |
| 账号归属 | 与 B2C 同一 **Google 账号**下的**不同 Property**（便于权限管理与跨站对比） |

> **隔离原则**：Property 是 GA4 数据隔离的基本单位。**独立 Property = 独立数据集、独立事件体系、独立报表**；需要跨站对比时，在同一账号下并排查看两个 Property，而非在同一 Property 内用维度强行切分。

---

## 3. B2B 事件体系设计

> B2B 站为**非交易展示站**，核心度量是**有效询盘（qualified lead）**，而非成交。

### 3.1 事件清单

| 事件名 | 语义 | 触发点 | 关键参数（建议） |
|---|---|---|---|
| `generate_lead` | **询盘提交**（核心转化事件） | RFQ / 联系表单成功提交 | `lead_type`、`form_id`、`page_location` |
| `qualified_lead` | **合格询盘**（经 qualifying 判定） | 后端/规则判定为有效商机后 | `qualify_reason`、`company_size`、`country`、`source` |
| `rfq_submission` | **RFQ 表单提交**（具体 RFQ 动作） | RFQ 表单提交动作 | `product_category`、`quantity_range`、`file_attached` |
| `wholesale_registration` | **批发注册** | 批发账号/代理注册成功 | `registration_type`、`company_name`(hashed) |
| `contact_request` | **联系请求** | 通用联系表单 / 询盘入口 | `topic`、`channel` |

### 3.2 关键原则：普通表单提交 ≠ 有效询盘

> 这是 B2B 衡量的核心，也是与 B2C 最大的语义差异。

- **`rfq_submission` / `contact_request`（表单提交）**：代表「用户提交了表单」这一**动作**，但**不保证是有效商机**（可能是竞品调研、误填、垃圾、学生问价）。
- **`generate_lead`（询盘提交）**：作为核心转化事件，代表「形成了一个可跟进的询盘」。
- **`qualified_lead`（合格询盘）**：经 **qualifying 逻辑**判定后的**有效商机**，才是 B2B 真正的价值度量。

**qualifying 逻辑（设计要点，待细化）**：

- 基于**可结构化的表单字段**判定，如：公司类型、采购量级（`quantity_range`）、目标市场、是否有网站/营业执照、采购意向明确度。
- **禁止把业务经验值硬编码进业务逻辑**（遵循项目铁律），qualifying 规则放入**配置/知识库**，可由规则引擎或（后续）AI 商业分析 Agent 提议、人工复核。
- **Human-in-the-loop**：qualified 判定可作为「Agent 提议 + 人工确认」的高价值场景，判定结果回写 `qualified_lead`。

### 3.3 事件层级关系

```
rfq_submission / contact_request      ← 动作层（表单提交）
        │  (qualifying 判定)
        ▼
generate_lead                          ← 询盘层（核心转化）
        │  (qualified 判定)
        ▼
qualified_lead                         ← 价值层（有效商机，B2B 真正 KPI）
```

> 报表口径：以 `generate_lead` 为 GA4 转化事件，以 `qualified_lead` 为**业务质量北极星**；`rfq_submission` 仅作过程指标。

---

### 3.4 事件参数与 PII 处理

> B2B 表单天然涉及公司/联系人信息，须严格遵循项目 PII 保护原则。

- **禁止将 PII 明文作为事件参数**上报 GA4（如公司名、邮箱、电话、联系人姓名）。
- 必要的业务标识改为**哈希/脱敏**后传递，或仅在服务端台账留存，GA4 仅接收**非 PII 的分类维度**（如 `company_size`、`country`、`product_category`、`quantity_range`）。
- 事件参数遵循 GA4 命名规范（小写 snake_case），并纳入参数注册表管理。
- B2B 站 GA4 上报同样受 **Consent Mode v2** 约束：未同意不采集（同 B2C 前提）。

---

## 4. 数据隔离设计

### 4.1 隔离层次

| 层次 | 措施 |
|---|---|
| **Property 隔离** | B2B 独立 Property，与 B2C `536153168` 物理分离 |
| **Measurement ID 隔离** | B2B 独立 `G-` ID，前端互不混用 |
| **数据流隔离** | B2B 标签只上报到 B2B Property；B2C 标签只上报到 B2C Property |
| **事件体系隔离** | B2B 用 lead 体系；B2C 用 ecommerce（purchase）体系，互不复用事件语义 |

### 4.2 跨站对比（如需）

- 在**同一 Google 账号**下保留 B2C、B2B 两个 Property。
- 跨站对比时**并排查看两个 Property**，或在 GA4/BigQuery 层做联合分析。
- **不**通过在同一 Property 内加「site」维度来强行区分（会重新引入混流污染）。

### 4.3 命名与配置规范（供实施参考）

| 项 | B2C | B2B（规划） |
|---|---|---|
| Property 名 | Nuotao B2C | Nuotao B2B |
| Measurement ID | `G-30GWC4FYMG` | 待创建（独立） |
| 核心转化 | `purchase` | `generate_lead` / `qualified_lead` |
| 流域 | nuotaooutdoor.com | b2b.nuotaooutdoor.com |

---

## 5. 实施前提

> B2B 站在部署 GA4 追踪**之前**，必须先满足以下前提：

1. **B2B 站先部署 CMP**：B2B 站同样面向欧盟/德国，受 **GDPR 约束**，须先按《GDPR_CONSENT_IMPLEMENTATION_DESIGN.md》部署 Cookie 同意机制 + Consent Mode v2（默认 denied）。**无 CMP 即上线追踪 = 合规缺口。**
2. **qualifying 逻辑设计确认**：`qualified_lead` 的判定规则需先定义（配置化，非硬编码），否则该事件无法准确埋点。
3. **Owner 批准创建新 Property**：本轮仅设计，创建 Property、生成 Measurement ID、部署埋点均需后续 Owner 批准。

---

## 6. 报表与分析设计（供实施参考）

### 6.1 B2B 核心报表口径

| 报表 | 关键指标 | 事件来源 |
|---|---|---|
| 询盘量报表 | 询盘提交数、按渠道/页面分布 | `generate_lead` / `rfq_submission` |
| 询盘质量报表 | 合格询盘数、合格率（qualified / generate_lead） | `qualified_lead` ÷ `generate_lead` |
| 注册漏斗 | 批发注册数、注册→询盘转化 | `wholesale_registration` → `generate_lead` |
| 渠道归因 | 各渠道带来的有效询盘、获客成本 | `qualified_lead` + 流量来源 |

> **北极星指标**：合格询盘数（`qualified_lead`）及其合格率，而非单纯表单提交量。

### 6.2 与 B2C 报表的差异

| 维度 | B2C 报表 | B2B 报表 |
|---|---|---|
| 核心转化 | `purchase` 收入 / ROAS | `qualified_lead` 商机 / 合格率 |
| 漏斗 | 结账漏斗（view→checkout→purchase） | 询盘漏斗（submit→lead→qualified） |
| 价值度量 | 订单金额 | 商机质量（后续线下成交，GA4 内不可直接归因） |

> 注意：B2B 的**真实成交**发生在线下跟进后，GA4 只能追踪到「有效询盘」这一前置环节；最终营收归因需结合 CRM / 后端台账，不应强行塞入 GA4 purchase 语义。

---

## 7. 待 Owner 批准事项

| # | 待批准项 | 说明 |
|---|---|---|
| 1 | **批准「B2B 独立 GA4 Property」决策** | 不与 B2C `536153168` 混流 |
| 2 | **批准 B2B 事件体系** | 5 个事件（generate_lead / qualified_lead / rfq_submission / wholesale_registration / contact_request） |
| 3 | **批准「表单提交 ≠ 有效询盘」原则** | `qualified_lead` 作为业务北极星 |
| 4 | **后续是否创建 Property / 部署追踪** | 本轮仅设计，生产部署待 Owner 另行批准 |
| 5 | **确认 B2B CMP 先行** | B2B 追踪上线前须先部署 Cookie 同意机制 |

---

## 8. 关联文档

- 《GDPR_CONSENT_IMPLEMENTATION_DESIGN.md》（D8-C #2）：B2B 站实施追踪的 CMP 前提。
- 《CMP_TECHNICAL_SELECTION_REPORT.md》（D8-C #1）：CMP 选型。
- 《B2B_B2C_ANALYTICS_ARCHITECTURE.md》《B2B_ACCEPTANCE_REPORT.md》《D8_B_AUDIT_SUMMARY.md》：B2B 埋点与隔离现状审计来源。

---

> **免责声明**：本文为数据架构方案设计。GA4 Property 创建、埋点部署、生产变更均需 Owner 批准后另行实施。