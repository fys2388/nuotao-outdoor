# B2B 与 B2C 数据隔离架构（Analytics Architecture）

> **D8-B 交付物** · GA4/GTM 现状审计 — 方案设计篇
> **日期**：2026-11-19
> **性质**：只读审计 + 方案设计，**未修改任何生产代码/配置**（Owner 未批准改配置）
> **本轮重点**：规划 B2C 数据追踪；同时提出**未来 B2B 独立数据流方案**
> **目标市场**：美国、德国、欧盟（需 GDPR 合规）

---

## 0. 执行摘要

当前 Nuotao Outdoor 存在两类业务：**B2C DTC 电商**（nuotaooutdoor.com，WordPress + WooCommerce，已有部分 GA4 电商事件）与**未来 B2B 展示/批发站**（`frontend-b2b/`，React + Cloudflare Pages，含 RFQ 询盘）。

审计确认：**B2B 侧零 GA4 埋点**（无追踪、RFQ 询盘无任何打点），也**无 GA4 维度的 B2C/B2B 隔离**。本方案主张：**B2C 与 B2B 必须数据隔离**（独立 GA4 Property 或至少独立 Web Data Stream），核心原因是 **B2B 询盘（lead）≠ B2C 购买（purchase）转化**，混流会污染转化率与 ROAS，导致广告投放与经营决策失真。

---

## 1. 现状基线（三资产）

| 资产 | 技术栈 | 业务性质 | 追踪现状 | GA4 埋点 |
|---|---|---|---|---|
| `frontend/` | React，AI OS 管理控制台 | 内部运营后台 | 无追踪 | ❌ 无（内部系统，**不应接 GA4**） |
| `frontend-b2b/` | React，Cloudflare Pages，B2B 展示/门户 | B2B 展示 + RFQ 询盘 + 批发 | 无追踪，RFQ 询盘零埋点 | ❌ 无 |
| B2C 商城 | WordPress + WooCommerce @ nuotaooutdoor.com | B2C DTC 电商 | FB/TikTok/GA4 三端打点（`class-tracking.php`） | ⚠️ 部分（view_item/add_to_cart/purchase） |

**结论**：B2B 完全未接 GA4；B2C 部分接入但漏斗不全；两者在 GA4 维度**无隔离设计**。

---

## 2. 为何 B2C 与 B2B 必须隔离（不能混的原因）

### 2.1 转化语义完全不同

| 维度 | B2C | B2B |
|---|---|---|
| 核心转化事件 | `purchase`（订单实付金额） | `generate_lead`（RFQ 询盘提交）、批发注册、sample_request |
| 转化价值 | 每单有明确金额（revenue） | 询盘**无即时金额**，价值在后续成交（长周期） |
| 转化漏斗长度 | 短（浏览→加购→结账→购买） | 长（浏览→询盘→报价→谈判→批发下单，数周/数月） |
| 决策人 | 消费者个人 | 采购/批发商（公司决策） |
| 量级 | 高流量、低单价、高单量 | 低流量、高客单、低单量 |

### 2.2 混流的危害（若共用同一 GA4 Property / Stream）

1. **转化率失真**：B2B 低流量 + 高价值询盘 与 B2C 高流量 + 低单价订单混算，整体 conversion rate 变成不可解读的混合数。
2. **ROAS 污染**：B2C 广告以 `purchase` revenue 计算 ROAS；若把 B2B `generate_lead` 也计入同一转化集，广告报表把「询盘」当「收入」，ROAS 严重虚高/失真。
3. **归因错乱**：B2B 长周期询盘会拉长 GA4 attribution window 的实际影响，干扰 B2C 短周期归因。
4. **报表口径分裂**：同一个 `conversions` 指标无法同时表达「订单数」和「询盘数」。
5. **数据访问权限难管**：B2B 批发客户名单属商业机密（L2/L3），与 B2C 消费者数据混在一个 Property，权限与合规边界模糊。

### 2.3 设计铁律

> **B2B 询盘（lead）绝不能与 B2C 购买（purchase）混为一谈。** 两者在事件名、价值模型、漏斗、归因窗口上都是不同业务对象。隔离是数据资产（AGENTS.md §1.2 第 4 条「数据是资产」）与合规（GDPR）的双重要求。

---

## 3. 推荐架构：隔离方案

### 3.1 方案对比

| 方案 | 描述 | 隔离强度 | 管理成本 | 建议 |
|---|---|---|---|---|
| **A. 独立 GA4 Property**（推荐） | B2C 与 B2B 各建一个 GA4 Property，各自 Measurement ID | ★★★★★ 完全隔离 | 中（两套配置） | ✅ 首选 |
| B. 同 Property，独立 Web Data Stream | 一个 GA4 Property，两个 stream（不同 Measurement ID） | ★★★★ 数据流隔离，但报表共享 | 低 | 次选（若需跨站看总量） |
| C. 同 Property/Stream + 维度区分 | 用 `site_type`/`audience` 自定义维度区分 | ★★ 弱隔离，易误用 | 低 | ❌ 不推荐（混流风险高） |

### 3.2 推荐落地：方案 A（独立 Property）

- **B2C Property**：`Nuotao B2C - DTC`，Measurement ID `G-B2CXXXX`，绑定 nuotaooutdoor.com。
  - 启用 GA4 Ecommerce，事件体系见《B2C_ECOMMERCE_TRACKING_PLAN.md》。
  - 转化（Key Events）= `purchase`（主）、`begin_checkout` 等。
- **B2B Property**：`Nuotao B2B - Wholesale`，Measurement ID `G-B2BXXXX`，绑定 B2B 站（frontend-b2b 域名）。
  - 转化（Key Events）= `generate_lead`（RFQ 询盘，主）、`wholesale_signup`、`sample_request`。
  - **不接入 WooCommerce purchase**，不与 B2C revenue 混算。
- **内部控制台 `frontend/`**：**不接 GA4**（内部运营系统，流量为员工/内部，接入会污染且无业务价值）。

### 3.3 隔离要点

1. **Measurement ID 物理分离**：B2C 站只加载 B2C ID，B2B 站只加载 B2B ID，绝不交叉。
2. **两套 Consent Mode v2**：各自独立 Cookie Banner / Consent 配置（GDPR，德国/欧盟必需）。
3. **转化定义分离**：GA4 后台分别把 B2C `purchase`、B2B `generate_lead` 设为 Key Event，互不可见。
4. **报表/受众分离**：GA4 Audience、Exploration、与 Google Ads 转化导入，按 Property 分开，杜绝 B2B lead 进入 B2C ROAS 计算。
5. **访问权限分离**：B2B Property（含批发客户线索）访问权限最小化，符合 AGENTS.md 数据分级 L2/L3。

---

## 4. B2B 关键业务事件设计（未来数据流）

> B2B 站当前零埋点，以下为**未来实施的目标事件设计**，全部需 Owner 批准后实施。

| # | 事件名 | 业务含义 | 触发时机 | 关键参数 | GA4 类别 |
|---|---|---|---|---|---|
| B1 | `generate_lead` | **RFQ 询盘提交**（核心转化） | 用户提交 RFQ / 询盘表单成功 | `form_id`、`product_category`、`quantity_range`、`country`、`lead_source` | Lead（**非 revenue**） |
| B2 | `wholesale_signup` | 批发客户注册 | 批发账户注册成功 | `company_type`、`country`、`registration_method` | Lead/Signup |
| B3 | `sample_request` | 样品申请 | 用户申请样品 | `product_id`、`quantity`、`country` | Lead |
| B4 | `view_wholesale_catalog` | 浏览批发目录/价格页 | 批发目录页曝光 | `catalog_section`、`items[]`（可选） | Engagement |
| B5 | `download_price_list` | 下载价格表/产品目录 | 下载动作 | `file_type`、`category` | Engagement（弱转化） |
| B6 | `contact_wholesale_team` | 联系批发团队（邮件/表单） | 提交联系表单 | `topic`、`country` | Lead |

### 4.1 B2B 事件设计约束

- **绝不发送 PII 给 GA4**：RFQ 表单含公司名、联系人、邮箱、电话——这些**一律不发送**到 GA4（符合 H5）。GA4 侧只发**非 PII 的业务属性**（品类、数量区间、国家、表单 ID）。真实询盘内容存于内部系统（DB），不经 GA4。
- **`generate_lead` 不赋 revenue**：B2B 询盘在 GA4 中是 **Key Event（计数转化）**，不直接等于收入；收入归因在内部 CRM/ERP 按 lead→deal 闭环核算，**不与 B2C purchase revenue 混算**。
- **长周期归因**：B2B 用更长的 attribution window 视角解读，且主要靠内部 lead 追踪（GA4 仅负责前端行为），避免用 GA4 短窗口误判。

---

## 5. 发现问题清单（5 要素表）

| ID | 发现 | 当前状态 | 证据 | 风险等级 | 建议方案 | 需 Owner 批准 |
|---|---|---|---|---|---|---|
| G1 | B2B 完全未接 GA4 | `frontend-b2b/` 无任何追踪，RFQ 询盘零埋点 | 代码审计：frontend-b2b 无 GA4/GTM/dataLayer | **P1** | 按方案 A 建 B2B 独立 Property，落地 B1-B6 事件（尤其 `generate_lead`） | **是** |
| G2 | 无 B2C/B2B 数据隔离 | GA4 维度无隔离设计；B2B 未接入故暂未混流，但无预案 | 无隔离配置 | **P1** | 采用方案 A（独立 Property），固化隔离原则（§2.3） | **是**（架构决策） |
| G3 | B2B RFQ 询盘无转化度量 | 询盘提交无任何打点，无法度量 B2B 获客 | frontend-b2b RFQ 零埋点 | **P1** | `generate_lead` 作为 B2B 核心 Key Event | **是** |
| G4 | 内部控制台不应接 GA4 | `frontend/` 无追踪（现状正确） | 代码审计 | P2（保持现状） | 明确 `frontend/` **永不接 GA4**，写入规范 | 否（需确认原则） |
| G5 | B2B Consent 缺失（未来） | B2B 站无 Cookie Banner / Consent Mode | frontend-b2b 无 consent | **P0（GDPR，B2B 上线前）** | B2B 接入 GA4 时**同步**落地独立 Consent Mode v2 | **是**（P0 合规） |
| G6 | 无 lead→收入闭环核算设计 | B2B lead 价值无法归因到实际批发成交 | 无相关设计 | P2 | 未来在内部 CRM/ERP 设计 lead→deal 闭环，GA4 仅负责前端行为 | **是**（未来规划） |

---

## 6. 与 B2C 方案的衔接

- **B2C 优先**：本轮（D8-B）重点落地 B2C 事件体系（见《B2C_ECOMMERCE_TRACKING_PLAN.md》），B2B 为未来数据流设计。
- **隔离先行原则**：即便 B2B 尚未实施，**现在就确立隔离原则**（独立 Property），避免未来 B2B 接入时误并入 B2C Property 造成历史数据污染——GA4 历史数据无法回溯拆分，**隔离决策越早越省成本**。
- **统一规范**：两站共用同一份《PII 禁发清单》与 Consent 策略模板，仅 Measurement ID / Consent 配置分离。

---

## 7. 结论

- 现状：**B2B 零埋点、B2C 部分埋点、两者无隔离设计**。
- 核心主张：**B2C 与 B2B 用独立 GA4 Property（方案 A）隔离**，因 B2B 询盘（lead）与 B2C 购买（purchase）在语义、价值、漏斗、归因上根本不同，混流会污染转化率与 ROAS。
- 内部控制台 `frontend/` 不接 GA4。
- 所有 B2B 事件（`generate_lead`/`wholesale_signup`/`sample_request` 等）为**未来实施设计**，**严禁发送 PII**，`generate_lead` 不赋 revenue。
- **本阶段只读 + 方案设计，未修改任何生产代码/配置**；隔离落地与 B2B 埋点**均需 Owner 批准**。

---

*本文档为 D8-B 方案设计交付物，仅作规划用途，未改动任何生产配置。实施需 Owner 显式批准。*
