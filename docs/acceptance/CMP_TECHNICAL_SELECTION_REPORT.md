# CMP（Cookie Consent Management Platform）技术选型报告

> **任务编号**：D8-C · 交付物 #1
> **日期**：2026-11-18
> **状态**：方案设计（Draft）· **待 Owner 审批**
> **目标站点**：B2C `nuotaooutdoor.com`（WooCommerce 自托管）、B2B `b2b.nuotaooutdoor.com`
> **目标市场**：欧盟 / 德国（**GDPR + TTDSG 合规为硬约束**），兼顾美国（CCPA/CPRA）
> **性质**：方案设计与选型，**本轮不改动任何生产代码 / 配置**

---

## 0. 本轮范围

### 0.1 本轮做

- 说明引入正式 CMP 的合规背景与必要性。
- 对比 3 类候选方案（自建轻量 CMP / 开源 WP 插件 / 商业 SaaS CMP），覆盖 8 个决策维度。
- 给出推荐方案与理由，并明确实施边界。
- 澄清「Consent Mode v2 ≠ CMP」这一常见误区。

### 0.2 本轮不做

- 不安装、不配置任何 CMP 插件，不修改 `class-tracking.php` 或 GA4/Pixel 注入逻辑。
- 不编写 Cookie 政策 / 隐私政策文本。
- 不创建任何 Google / Meta / TikTok 后台配置。
- 不部署生产追踪代码（B2B 站同）。

---

## 1. 背景：为什么现有 banner 不够

### 1.1 现状

当前 B2C 站已通过 WordPress Code Snippets 注入 GA4（Measurement ID `G-30GWC4FYMG`，Property `536153168`），并实施了：

- Google **Consent Mode v2**，默认状态为 denied；
- 一个**简单 Cookie Banner**（Accept / Reject 两个按钮 + `localStorage` 记忆选择）。

Meta Pixel / TikTok Pixel 已配置但**尚未充分验证**。

### 1.2 缺口

上述「简单 banner」只能算 **MVP 占位实现**，距离 GDPR / TTDSG 要求的合规 CMP 还有明确差距：

| 缺口 | 说明 | 合规影响 |
|---|---|---|
| **无 Cookie 分类** | 只有一刀切 Accept / Reject，缺少 Necessary / Analytics / Marketing / Preferences 分级开关 | TTDSG §25 要求按目的区分同意，用户须能「选择性同意」 |
| **拒绝路径弱** | 通常仅「Accept All」突出、「Reject」弱化，缺少「仅必要」与「按分类自定义」的清晰入口 | 违反「同意须自由、明确、可撤回」原则 |
| **撤回入口缺失** | 同意后无页脚 / 设置链接让用户**随时撤回或修改** | GDPR Art.7(3)：撤回须与给予同样容易 |
| **同意记录不足** | 仅 `localStorage` 存一个布尔值，无时间戳、政策版本、分类明细 | GDPR 问责（accountability）要求留存**可证明的同意凭证** |
| **标签阻塞不彻底** | 未同意前，GA4/Pixel 是否真正被阻止加载**未逐项验证** | 「先加载后征求」在欧盟即违规 |
| **无政策链接** | Banner 内通常缺 Cookie 政策 / 隐私政策入口 | 「知情同意」要求告知处理目的与权利 |

**结论**：简单 banner 无法支撑欧盟/德国市场的合规主张，需引入正式 CMP。但「正式 CMP」不等于「必须买商业 SaaS」，需按项目实际（中小 DTC、成本敏感、WP/WooCommerce 技术栈）做选型。

---

## 2. 关键前置澄清：Consent Mode v2 ≠ CMP

这是选型讨论中最易混淆的一点，必须先厘清：

| 概念 | 职责 | 是否获取同意 |
|---|---|---|
| **CMP（Cookie Consent Management Platform）** | 展示 banner、获取用户同意、管理分类开关、记录同意凭证、提供撤回入口 | **是**（同意的「获取与管理者」） |
| **Google Consent Mode v2** | 把 CMP 得到的同意状态，以 `gtag('consent', ...)` 信号形式**传递给 Google**（GA4 / Google Ads），让 Google 标签遵从该状态、在 denied 时走 cookieless/ping 建模 | **否**（只「传递状态」，不获取同意） |

**关系**：Consent Mode v2 依赖 CMP 提供的同意状态作为输入。**没有 CMP，Consent Mode 没有可信的同意来源**；仅有 Consent Mode 而无合规 CMP，无法证明同意的有效性。二者互补，不能互相替代。

> 因此本报告的选型对象是 **CMP**；Consent Mode v2 的集成细节见《GDPR_CONSENT_IMPLEMENTATION_DESIGN.md》（D8-C 交付物 #2）。

---

## 3. 候选方案

### 方案 A：自建轻量 CMP（扩展现有 Code Snippet banner）

在现有 banner 基础上扩展为具备分类、撤回、记录能力的轻量 CMP。

- **实现方式**：在 WP 主题 / Code Snippet 中自写 vanilla JS + 少量 PHP；分类开关、`localStorage`/`cookie` 存储同意对象、Consent Mode `update` 回调。
- **优势**：零许可成本、完全可控、无第三方依赖、体积最小、不引入外部数据处理器（DPA 简单）。
- **劣势**：合规文案、多语言、可访问性、跨浏览器兼容、政策版本迁移全需自维护；缺法律更新跟进；开发与长期维护负担落在项目自身。

### 方案 B：开源 / WP 插件 CMP（Complianz、Klaro!、Cookie Consent 等）

采用成熟开源方案，优先 WP 插件形态以贴合 WooCommerce 技术栈。

- **Complianz**（WordPress 插件，开源核心 + 付费 Pro）：WP 原生集成、Cookie 扫描、分类管理、Consent Mode v2 支持、多语言、撤回入口、同意记录。
- **Klaro!**（开源 JS CMP，有 WP 集成方式）：轻量、可自托管、privacy-focused、可深度定制 UI。
- **Cookie Consent（Osano / 开源 JS 库）**：纯前端库，灵活但需自行接线 WP 与 Consent Mode。

- **优势**：许可成本低（核心开源）、WP/WooCommerce 集成度高、社区维护、合规特性相对齐全（分类/撤回/记录）、比自建省维护。
- **劣势**：Pro 功能常需付费；配置有一定学习成本；部分插件对 Consent Mode v2 支持需确认版本；插件质量参差需评估维护活跃度。

### 方案 C：商业 SaaS CMP（Cookiebot、Usercentrics、OneTrust）

- **Cookiebot**（Usercentrics 旗下）、**Usercentrics**、**OneTrust**：托管式 CMP，自动 Cookie 扫描、合规文案持续更新、跨域同意、企业级审计、多法规（GDPR/CCPA/LGPD）覆盖。
- **优势**：合规能力最强、法律更新由厂商跟进、审计与凭证最完善、几乎零自维护、有正式 DPA。
- **劣势**：**按量/按域名订阅收费**（对中小 DTC 是持续成本）；引入第三方数据处理器；对 WP 集成通常走脚本注入，灵活度低于原生插件；功能冗余（项目用不到企业级大部分能力）。

---

## 4. 选型对比矩阵

> 评分：● 强 / ◐ 中 / ○ 弱。结合「中小 DTC + WP/WooCommerce + 欧盟/德国合规」场景评估。

| 维度 | A 自建轻量 | B 开源 WP 插件（Complianz 等） | C 商业 SaaS（Cookiebot 等） |
|---|---|---|---|
| **GDPR/TTDSG 合规性** | ◐（取决于实现质量，易留缺口） | ●（核心覆盖分类/撤回/记录） | ●（最完善，法律更新跟厂商） |
| **Consent Mode v2 支持** | ◐（需自行实现 `consent` 信号） | ●（Complianz 已支持，需核对版本） | ●（原生支持） |
| **成本** | ● 零许可（人力成本高） | ●/◐ 核心免费，Pro 付费（中低） | ○ 订阅制持续成本（中高） |
| **维护负担** | ○ 全自担（文案/兼容/迁移） | ● 社区+插件更新承接 | ● 厂商全托管 |
| **WP/WooCommerce 集成难度** | ◐（自写接线，需自维护） | ● WP 原生，集成简单 | ◐（多为脚本注入，非原生） |
| **Cookie 分类（4 类）** | ◐（自行定义） | ● 内置分类管理 | ● 内置 + 自动扫描 |
| **撤回机制** | ◐（自行实现入口） | ● 内置撤回/设置入口 | ● 内置 + 跨页一致 |
| **同意记录存储** | ◐（仅 localStorage，凭证弱） | ● 分类+时间戳+版本 | ● 完整审计凭证（跨会话） |

### 4.1 关键权衡分析

- **合规 vs 成本**：方案 C 合规最强但持续付费；对中小 DTC，方案 B 能以极低成本覆盖 90% 合规需求，是性价比拐点。
- **集成 vs 可控**：方案 A 最可控但把合规责任与维护成本全压回项目；合规文案与法律更新是**自建最容易被低估的长期负担**。
- **WP 生态贴合度**：项目是 WooCommerce 自托管，方案 B 的 WP 原生插件在安装、分类、撤回、与 WooCommerce 结账页兼容上最省事。
- **Consent Mode v2 联动**：方案 B（Complianz）已内建 Consent Mode v2 支持，能与现有 GA4 注入较快打通；方案 A 需自写 `consent` 信号回调，方案 C 原生支持但需外部脚本。

---

### 4.2 选型决策标准与权重

> 结合本项目定位（中小 DTC、WP/WooCommerce、欧盟/德国合规）赋予权重，用于解释为何推荐方案 B。

| 决策标准 | 权重 | 说明 |
|---|---|---|
| GDPR/TTDSG 合规性 | 高 | 硬约束，必须达标，不可为省成本妥协 |
| 成本（含持续） | 高 | 中小 DTC 成本敏感，符合「低成本」铁律 |
| WP/WooCommerce 集成难度 | 中高 | 贴合现有技术栈可显著降低落地与维护成本 |
| Consent Mode v2 支持 | 中高 | 与现有 GA4 打通的关键，需内建支持 |
| 维护负担 | 中 | 长期可持续性，避免自建的高维护 |
| Cookie 分类 / 撤回 / 记录 | 中 | 合规功能完备度 |
| 演进可迁移性 | 低-中 | 未来可平滑升级，不被锁死 |

**加权结论**：方案 B 在「合规达标 + 低成本 + WP 集成 + Consent Mode 支持 + 维护适中」五个高权重维度上综合最优，故为推荐方案。

---

## 5. 推荐方案

### 推荐：**方案 B —— 开源 WP 插件 CMP（首选 Complianz，备选 Klaro!）**

**理由**：

1. **合规够用**：覆盖 GDPR/TTDSG 所需的 Cookie 分类、选择性同意、撤回入口、同意记录，满足本项目欧盟/德国市场基线。
2. **成本可控**：核心开源、Pro 功能按需；符合项目「开源优先、低成本」铁律，避免商业 SaaS 的持续订阅支出。
3. **集成省力**：WP 原生插件，与 WooCommerce / 现有 GA4（`G-30GWC4FYMG`）注入快速打通，且内建 Consent Mode v2 支持，落地最快。
4. **维护适中**：社区与插件更新承接合规文案/兼容性，显著低于方案 A 的全自维护，又不像方案 C 那样功能冗余、成本高。
5. **演进友好**：若未来合规要求升级（如需跨域/企业级审计），可平滑迁移到方案 C，不会被自建方案锁死。

**方案定位对比**：

| 方案 | 适用定位 | 本项目结论 |
|---|---|---|
| A 自建 | 技术团队强、对合规细节极熟、追求零依赖 | 不推荐（长期维护与法律更新负担过重） |
| **B 开源 WP 插件** | **中小 DTC、WP 生态、成本敏感、需合规基线** | **✅ 推荐** |
| C 商业 SaaS | 中大型、多法规多域、需企业级审计 | 备选（当前成本/功能冗余，未来可迁移） |

---

## 6. 风险与实施考量

### 6.1 方案 B（推荐）的残余风险与缓解

| 风险 | 说明 | 缓解措施 |
|---|---|---|
| Consent Mode v2 版本差异 | 部分开源插件对 Consent Mode v2 的 4 信号支持不全或需特定版本 | 选型时核对插件 changelog，确认 `ad_user_data`/`ad_personalization` 支持 |
| Pro 功能付费墙 | 高级扫描/支持可能需 Pro | 先用核心版验证合规基线，按需再评估 Pro |
| 插件维护活跃度 | 开源插件可能停止维护 | 选型时评估更新频率、WP 兼容版本、社区规模 |
| 与现有 GA4 注入冲突 | `class-tracking.php` 硬编码注入需与 CMP 联动 | 实施 Phase 1 时改造注入为「同意前不加载」 |
| 双 banner 冲突 | 正式 CMP 与现有简单 banner 叠加 | 部署 CMP 时下线现有 Code Snippet banner |

### 6.2 成本与工作量估算（量级参考，非精确报价）

| 方案 | 一次性成本 | 持续成本 | 主要成本构成 |
|---|---|---|---|
| A 自建 | 高（开发工时） | 高（维护/法律跟进） | 人力开发 + 长期维护 |
| B 开源插件 | 低-中（配置 + 注入改造） | 低（核心免费 / Pro 订阅） | 配置工时 + 可选 Pro |
| C 商业 SaaS | 低（接入快） | 中-高（按域/量订阅） | 订阅费 + 接入工时 |

> 对中小 DTC，方案 B 的一次性与持续成本组合最优，符合「开源优先、低成本」原则。

---

## 7. 待 Owner 批准事项

| # | 待批准项 | 说明 |
|---|---|---|
| 1 | **是否采用方案 B（Complianz 优先）** | 选型决策；批准后进入实施设计阶段（见交付物 #2） |
| 2 | **是否需要 Pro 版** | Complianz 核心免费，Pro（高级扫描/支持）是否采购待定 |
| 3 | **B2B 站是否同步采用同一 CMP** | B2B 站同样受 GDPR 约束，建议统一方案，待 Owner 确认 |
| 4 | **现有简单 banner 的处置** | 部署正式 CMP 后是否下线现有 Code Snippet banner（避免双 banner 冲突） |
| 5 | **是否引入 Complianz 作为第三方数据处理器** | 涉及 DPA 与隐私政策更新，需法务/Owner 确认 |

---

## 8. 关联文档

- 《GDPR_CONSENT_IMPLEMENTATION_DESIGN.md》（D8-C 交付物 #2）：Consent 分类、Consent Mode v2 集成、验收条件、实施计划。
- 《B2B_GA4_ARCHITECTURE.md》（D8-C 交付物 #3）：B2B 独立 GA4 架构（B2B 站部署 CMP 为其实施前提）。
- 《CONSENT_PRIVACY_AUDIT.md》（D8-B）：Consent 缺口审计来源。

---

> **免责声明**：本文为技术选型与方案设计，不构成法律意见。GDPR/TTDSG 的具体适用以项目法务/数据保护官（DPO）最终意见为准。