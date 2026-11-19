# GDPR Consent 实施设计（Cookie 同意机制）

> **任务编号**：D8-C · 交付物 #2
> **日期**：2026-11-18
> **状态**：方案设计（Draft）· **待 Owner 审批**
> **目标站点**：B2C `nuotaooutdoor.com`（WooCommerce 自托管）
> **目标市场**：欧盟 / 德国（**GDPR + TTDSG 合规为硬约束**）
> **性质**：方案设计与实施计划，**本轮不改动任何生产代码 / 配置**
> **选型前提**：CMP 采用开源 WP 插件方案（首选 Complianz，见《CMP_TECHNICAL_SELECTION_REPORT.md》）

---

## 0. 本轮范围

### 0.1 本轮做

- 定义 Cookie 分类体系（4 类）与默认状态。
- 设计同意机制（banner、分类开关、撤回入口、同意记录）。
- 设计 Google Consent Mode v2 集成（4 核心信号映射、Basic vs Advanced 模式选择）。
- 定义验收条件与分阶段实施计划。

### 0.2 本轮不做

- 不安装/配置 CMP 插件，不修改 `class-tracking.php` 或 GA4/Pixel 注入逻辑。
- 不编写最终隐私政策 / Cookie 政策法律文本（仅定义入口与覆盖要点）。
- 不实施 Phase 3 的服务端同意存证（本轮仅设计）。

---

## 1. 目标

构建符合 **GDPR / TTDSG** 的 Cookie 同意机制，达成：

1. **事前同意**：非必要 Cookie / 追踪在用户同意前**不加载、不采集**。
2. **分类可控**：用户可按目的（Necessary / Analytics / Marketing / Preferences）**选择性同意**，而非只有 Accept All。
3. **可撤回**：用户可**随时、便捷地**撤回或修改同意。
4. **可证明**：留存可审计的同意记录（分类 + 时间戳 + 政策版本）。
5. **联动 Google**：同意状态通过 **Consent Mode v2** 正确传递给 GA4 / Google Ads。

---

## 2. Cookie 分类设计

> 默认原则：**仅 Necessary 默认启用且不可关闭**；其余三类**默认拒绝（denied）**，需用户主动 opt-in。

| 分类 | 用途 | 典型 Cookie / 标签 | 默认状态 | 可关闭 |
|---|---|---|---|---|
| **Necessary（必要）** | 站点核心功能：购物车、登录、安全、会话、防欺诈 | WooCommerce cart/session、登录态、CSRF/安全 cookie | **始终启用** | ❌ 不可关闭 |
| **Analytics（分析）** | 流量与行为分析 | **GA4**（`G-30GWC4FYMG`）、（可选）站点统计 | **默认拒绝** | ✅ |
| **Marketing（营销）** | 广告投放、重定向、转化追踪 | **Google Ads**、**Meta Pixel（Facebook）**、**TikTok Pixel** | **默认拒绝** | ✅ |
| **Preferences（偏好）** | 个性化体验、偏好记忆 | 语言/币种/主题偏好、个性化推荐 | **默认拒绝** | ✅ |

### 2.1 分类与法律依据

| 分类 | 法律依据 | 同意要求 |
|---|---|---|
| Necessary | 合法利益 / 履约必需（ePrivacy 例外） | 无需同意，但须在政策中告知 |
| Analytics / Marketing / Preferences | **同意**（consent） | **须事前 opt-in** |

---

## 3. 同意机制设计

### 3.1 首次访问 Banner

- **触发**：首次访问（无有效同意记录）时展示。
- **内容要求**：
  - 简述 Cookie 用途与分类；
  - **「Accept All」（全部接受）** 按钮；
  - **「Reject All / 仅必要」（全部拒绝）** 按钮 —— 与 Accept All **同等显著**，不得弱化；
  - **「Cookie 设置 / 自定义」** 入口 —— 进入分类开关面板；
  - **Cookie 政策 / 隐私政策** 链接。
- **不使用**「继续浏览即视为同意」的暗模式（dark pattern），不设误导性默认勾选。

### 3.2 分类开关（不只是 Accept All）

- 提供**逐类开关**：Analytics / Marketing / Preferences 各自独立 toggle（默认关）。
- Necessary 显示为「始终启用、不可关闭」。
- 用户保存后，仅启用其**明确勾选**的分类；未勾选分类保持 denied。
- 支持随时重新打开设置面板调整。

### 3.3 撤回入口

- 在**页脚**（及/或设置页）提供常驻 **「Cookie 设置」** 链接。
- 点击后重开分类面板，用户可关闭任一已同意分类。
- **撤回后立即生效**：对应标签停止采集（通过 Consent Mode `update` 置 denied + 阻止/卸载标签）。
- 撤回难度须与给予同意相当（GDPR Art.7(3)）。

### 3.4 同意记录存储

**存储结构（localStorage 为主，可选服务端存证）**：

```json
{
  "consent_version": "2026-11-18-v1",
  "policy_version": "privacy-policy-v1",
  "timestamp": "2026-11-18T10:30:00Z",
  "categories": {
    "necessary": true,
    "analytics": false,
    "marketing": false,
    "preferences": false
  },
  "consent_id": "uuid",
  "user_agent_hash": "sha256(...)"
}
```

| 字段 | 说明 | 合规意义 |
|---|---|---|
| `consent_version` | 同意机制/分类版本 | 政策变更后可要求重新同意 |
| `policy_version` | 隐私/Cookie 政策版本 | 证明同意对应哪版政策 |
| `timestamp` | 同意/撤回时间 | 留存时间线 |
| `categories` | 各分类授权状态 | 证明「选择性同意」 |
| `consent_id` | 唯一凭证 ID | 可追溯、可审计 |

- **本地存储**：localStorage（+ 一个可读 cookie 供服务端/CMP 判断），用于跨刷新/跳转保持状态。
- **可选服务端存证（Phase 3）**：将同意凭证同步到后端（FastAPI），落库长期留存，满足 GDPR 问责（accountability）的**可证明性**要求，且不依赖用户清除浏览器数据。

---

## 4. Google Consent Mode v2 集成

### 4.1 4 个核心信号 → Cookie 分类映射

| Consent Mode v2 信号 | 含义 | 映射分类 | 默认 |
|---|---|---|---|
| `ad_storage` | 广告 Cookie 存储（如重定向） | **Marketing** | denied |
| `ad_user_data` | 向 Google 发送用户数据用于广告 | **Marketing** | denied |
| `ad_personalization` | 广告个性化 / 重定向 | **Marketing** | denied |
| `analytics_storage` | 分析 Cookie 存储（GA4） | **Analytics** | denied |

> 辅助信号（按需）：`functionality_storage` / `personalization_storage` / `security_storage` 对应 Preferences / 安全，本项目可从简。

### 4.2 集成流程

```js
// 1) 任何 Google 标签加载前：设置默认（全 denied）
gtag('consent', 'default', {
  ad_storage: 'denied',
  ad_user_data: 'denied',
  ad_personalization: 'denied',
  analytics_storage: 'denied',
  wait_for_update: 500
});

// 2) 用户在 CMP 做出选择后：按分类 update
gtag('consent', 'update', {
  analytics_storage: consent.categories.analytics ? 'granted' : 'denied',
  ad_storage:       consent.categories.marketing ? 'granted' : 'denied',
  ad_user_data:     consent.categories.marketing ? 'granted' : 'denied',
  ad_personalization: consent.categories.marketing ? 'granted' : 'denied'
});
```

- **默认 denied 必须前置**于 GA4 / Google Ads 标签注入（`class-tracking.php` 现逻辑需按此改造）。
- CMP 同意回调触发 `consent update`；撤回时再次 `update` 回 denied。

### 4.3 Basic vs Advanced Consent Mode

| 模式 | 行为 | 合规 | 数据完整性 |
|---|---|---|---|
| **Basic** | 未同意前**完全阻止**标签加载（不发 ping/cookieless） | **更保守、更安全** | 未同意流量无数据（含建模） |
| **Advanced** | 未同意前加载标签但置 denied，走 cookieless ping 建模 | 略激进（依赖 Google 建模合规） | 保留更多建模数据 |

**推荐：先采用 Basic Consent Mode。**

- **理由**：项目面向欧盟/德国，**Basic「未同意即不加载」**与 GDPR「事前同意」最契合，监管风险最低；符合「更保守合规」优先原则。
- **代价**：拒绝用户不产生 GA4 数据（可接受——合规优先于数据量）。
- **演进**：待合规实践成熟、并与法务确认后，可评估是否切换 Advanced 以回收建模数据。

---

## 5. 验收条件

> 部署后须逐项验证（建议结合浏览器 DevTools + GA4 DebugView / Tag Assistant）。

| # | 验收项 | 通过标准 |
|---|---|---|
| V1 | **未同意不加载非必要标签** | 首次访问、未做选择时，GA4 / Meta / TikTok 标签**不加载、不采集** |
| V2 | **拒绝后无追踪** | 点击「Reject All / 仅必要」后，网络面板无 GA4/Pixel 采集请求 |
| V3 | **同意后按类加载** | 仅勾选 Analytics 时只加载 GA4；勾选 Marketing 才加载 Pixel |
| V4 | **撤回立即停止** | 撤回某分类后，对应标签**立即**停止采集 |
| V5 | **状态跨刷新/跳转保持** | 同意/拒绝状态在页面刷新、站内跳转后保持一致 |
| V6 | **移动 + 桌面正常** | Banner 与设置面板在移动端、桌面端均正常展示与操作 |
| V7 | **政策入口可达** | Banner 及页脚可访问 Cookie 政策 / 隐私政策 |
| V8 | **Consent Mode 信号正确** | DebugView / Tag Assistant 显示 consent 信号随选择正确 granted/denied |
| V9 | **必要功能不受影响** | 购物车、登录、结账（Necessary）在「仅必要」模式下正常工作 |
| V10 | **无暗模式** | Reject 与 Accept 同等显著；无误导默认勾选 |

---

## 6. 实施计划（分阶段）

### Phase 1 —— 基本 CMP Banner + 分类（P0）

- 部署 CMP（Complianz），配置 4 类 Cookie 分类与默认状态（仅 Necessary 启用）。
- 展示首次访问 banner（Accept All / Reject All / Cookie 设置 / 政策链接）。
- 接入 **Basic Consent Mode v2**：默认 denied 前置，同意后 update。
- 改造 GA4 / Meta / TikTok 注入，未同意不加载。
- **下线现有简单 Code Snippet banner**，避免双 banner 冲突。
- **产出**：达成 V1、V2、V3、V6、V9、V10。

### Phase 2 —— 撤回入口 + 同意记录（P1）

- 页脚 / 设置增加常驻「Cookie 设置」撤回入口，支持修改与撤回。
- 完善同意记录（localStorage，含 timestamp / policy_version / categories / consent_id）。
- 政策版本变更触发重新同意。
- **产出**：达成 V4、V5、V7、V8。

### Phase 3 —— 服务端同意存证（P2，可选）

- 同意凭证同步至 FastAPI 后端并落库长期留存。
- 提供导出/查询能力，支撑 GDPR 问责与数据主体权利请求。
- 评估是否迁移 Advanced Consent Mode。
- **产出**：可证明的跨会话同意审计链。

---

## 7. 待 Owner 批准事项

| # | 待批准项 | 说明 |
|---|---|---|
| 1 | **批准本实施设计进入 Phase 1** | 涉及 GA4/Pixel 加载逻辑改造 + CMP 部署（生产变更） |
| 2 | **确认 Basic Consent Mode** | 采用保守模式，拒绝用户不产生 GA4 数据 |
| 3 | **确认分类默认状态** | Analytics/Marketing/Preferences 默认拒绝 |
| 4 | **批准下线现有简单 banner** | 由正式 CMP 替代 |
| 5 | **政策文本与法律审阅** | 隐私/Cookie 政策由法务/DPO 最终确认 |
| 6 | **Phase 3 服务端存证是否实施** | 涉及后端开发，按优先级排期 |

---

## 8. 关联文档

- 《CMP_TECHNICAL_SELECTION_REPORT.md》（D8-C #1）：CMP 选型对比与推荐。
- 《B2B_GA4_ARCHITECTURE.md》（D8-C #3）：B2B 独立 GA4 架构（前提：B2B 站先部署本设计之 CMP）。
- 《CONSENT_PRIVACY_AUDIT.md》（D8-B）：Consent 缺口审计来源。
- 《GA4_CONFIGURATION_AUDIT.md》《GTM_CONFIGURATION_AUDIT.md》（D8-B）。

---

> **免责声明**：本文为技术实施设计，不构成法律意见。GDPR/TTDSG 具体适用以项目法务/DPO 意见为准。