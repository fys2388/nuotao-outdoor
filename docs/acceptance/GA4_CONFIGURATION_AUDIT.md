# GA4 配置现状审计报告

> **交付物**：D8-B「GA4/GTM 现状审计」之 GA4 部分
> **审计日期**：2026-11-19
> **审计性质**：只读审计 + 方案设计，**未修改任何生产配置 / 代码**
> **审计范围**：B2C WordPress 站（nuotaooutdoor.com）、`frontend/`（AI OS 控制台）、`frontend-b2b/`（B2B 门户）
> **参考素材**：生产实测（curl 渲染 HTML）、前端代码 grep、WP 插件源码、`docs/` 文档

---

## 一、执行摘要

GA4 呈现 **「代码已实现 + 文档称已配置」vs「生产实测未生效」的重大矛盾**，这是本次审计最核心的发现（P0，需 Owner 立即复核）。

- **代码层**：B2C WP 插件 `nuotao-social-enhancements` 已实现完整 GA4 注入逻辑（gtag.js + dataLayer + `gtag('config', ID, {anonymize_ip:true})`）。
- **文档层**：`docs/ga4_social_utm_guide.md` 记录 Property ID `536153168`、Measurement ID `G-30GWC4FYMG`、数据流 `14811702943`，并称「已填入插件、已验证注入」。
- **生产实测层**：curl 首页 + `/shop/` 页渲染 HTML，**未检测到 GTM 脚本、未检测到 G- Measurement ID、未找到 dataLayer、未找到 Cookie Consent / Consent Mode**。另一份验收报告 `B2C_ACCEPTANCE_REPORT.md:126` 同样判定「GA4/GTM 全站缺失」（G- id=0、GTM-=0、gtag/js=False）。

**结论**：GA4 在生产环境**当前大概率未注入、无数据进入**。代码与文档声称的配置与生产实际不符，原因待 Owner 复核（见 §四）。在矛盾解决前，所有依赖 GA4 的分析（渠道归因、转化、AI 商业分析）均建立在**无数据**的基础上，属高风险。

---

## 二、逐项审计（ChatGPT 清单 A）

> 每项含 5 要素：当前状态 / 证据 / 风险等级 / 建议方案 / 是否需要 Owner 批准

### A1. 是否已创建 GA4 Property

| 要素 | 内容 |
|---|---|
| **当前状态** | 文档称已创建，代码侧无法验证（Property 创建发生在 Google Analytics 后台，不在仓库代码内）。**未经生产数据侧证实**。 |
| **证据** | `docs/ga4_social_utm_guide.md:12-13`：`GA4 属性 nuotaooutdoor.com ✅ 已存在`、`Property ID 536153168 ✅`。属文档自述，仓库内无 Google 后台截图或 API 验证。 |
| **风险等级** | **P1（中）** —— Property 是否真实存在影响后续一切；但即便存在，若 Measurement ID 未注入则等同无效。 |
| **建议方案** | Owner 登录 Google Analytics 后台，确认 Property `536153168` 状态、时区、币种；截图归档到 `docs/`。 |
| **是否需要 Owner 批准** | **否**（仅后台查看确认，不改配置）。 |

### A2. Measurement ID 是否已配置并生效

| 要素 | 内容 |
|---|---|
| **当前状态** | **矛盾项（P0）**：文档称 `G-30GWC4FYMG` 已填入插件；但插件默认值为空、生产实测未检测到该 ID。 |
| **证据** | ① `class-tracking.php:121` 从设置读取 `ga4_measurement_id`；`:102` 默认值 `''`；`:123-125` 空则 `return` 不注入。② `docs/ga4_social_utm_guide.md:14` 称已填入。③ 生产 curl 首页/`/shop/`：无 `G-` Measurement ID（grep 到的 `g-xxx` 为 CSS 类名）。④ `B2C_ACCEPTANCE_REPORT.md:126`：G- id=0、gtag/js=False。 |
| **风险等级** | **P0（高）** —— Measurement ID 是 GA4 生效的关键；未注入 = 全站无 GA4 数据。 |
| **建议方案** | Owner 复核 WP Admin → Settings → Nuotao Social → GA4 Measurement ID 是否**已保存** `G-30GWC4FYMG`；确认插件**已激活**；清除页面缓存后重新 curl 验证。 |
| **是否需要 Owner 批准** | **否**（复核查看）；若需改配置/激活插件，**是**（Owner 未批准改生产）。 |

### A3. Web Data Stream 是否已创建

| 要素 | 内容 |
|---|---|
| **当前状态** | 文档称已创建（数据流 ID `14811702943`），代码侧不可验证。 |
| **证据** | `docs/ga4_social_utm_guide.md:15`：`数据流 ID 14811702943 ✅`。属文档自述。 |
| **风险等级** | **P1（中）** —— 数据流是 Measurement ID 的载体，与 A2 绑定；若 A2 未生效，此处状态意义有限。 |
| **建议方案** | 随 A2 一并在 Google 后台确认数据流 `14811702943` 关联域名 nuotaooutdoor.com、增强型衡量开关状态。 |
| **是否需要 Owner 批准** | **否**（查看）。 |

### A4. 当前是否有数据进入 GA4

| 要素 | 内容 |
|---|---|
| **当前状态** | **推断为无数据 / 极少数据（P0）** —— 生产未注入 GA4 脚本，则浏览器不会向 GA4 发送任何事件。 |
| **证据** | 生产 curl 首页 + `/shop/`：无 gtag.js、无 dataLayer、无 G- ID。无 GA4 脚本 = 无数据采集。 |
| **风险等级** | **P0（高）** —— 无数据则 D8 之后所有依赖 GA4 的分析（渠道归因、转化率、AI 商业分析 Agent 的输入）均无源。 |
| **建议方案** | 先解决 A2 注入问题；注入后 Owner 在 GA4「实时报告」确认有活跃用户与事件流入。 |
| **是否需要 Owner 批准** | 验证需改配置故**是**；查看实时报告**否**。 |

### A5. 域名及跨域配置

| 要素 | 内容 |
|---|---|
| **当前状态** | **未配置（无证据）** —— 仓库代码与文档中未见跨域（cross-domain）追踪配置；`class-tracking.php:135-137` 的 `gtag('config')` 仅传 `anonymize_ip`，无 `linker` / `domains` 参数。 |
| **证据** | `class-tracking.php:135-137` config 参数仅 `anonymize_ip:true`。文档 `ga4_social_utm_guide.md` 配置表无跨域条目。 |
| **风险等级** | **P2（低，现阶段）** —— 当前仅单一 B2C 域名；未来若 B2B 门户（frontend-b2b，Cloudflare Pages）需与 B2C 打通用户旅程，则升级为 P1。 |
| **建议方案** | 暂不处理；在设计 B2B↔B2C 跨域归因时，再在 GA4 数据流设置中配置 `linker` 跨域域名列表。 |
| **是否需要 Owner 批准** | 未来实施时**是**。 |

### A6. 内部流量过滤（管理员排除）

| 要素 | 内容 |
|---|---|
| **当前状态** | **文档称已启用，代码侧未实现（矛盾 P1）** —— 文档称「管理员访问不追踪」，但 WP 插件 GA4 注入代码（`class-tracking.php:115-141`）中**未看到**按 `current_user_can` / admin cookie 排除管理员的逻辑；`should_inject()`（:116）的判断条件需进一步确认是否含 admin 排除。 |
| **证据** | `docs/ga4_social_utm_guide.md:19`：`管理员排除 已启用（管理员访问不追踪）✅`。代码 `class-tracking.php:115-141` config 无 admin 排除参数；需读 `should_inject()` 实现确认。 |
| **风险等级** | **P1（中）** —— 若未真正排除内部流量，GA4 数据会被 Owner/管理员访问污染，影响转化率与渠道判断的准确性。 |
| **建议方案** | Owner 复核 GA4 后台「数据过滤」是否真配置了内部流量排除（IP/开发者 ID）；或在 `should_inject()` 中加入 admin 判断。二者择一即可，需在文档标注实现方式。 |
| **是否需要 Owner 批准** | 改代码/配置**是**。 |

### A7. 时区 / 币种 / 数据保留设置

| 要素 | 内容 |
|---|---|
| **当前状态** | **未在文档/代码中记录（P1）** —— 仓库内未见 GA4 Property 的时区、币种、数据保留期设置说明。目标市场为美国/德国/欧盟，时区与币种影响报表口径；数据保留期影响 GDPR 合规（见 CONSENT_PRIVACY_AUDIT.md）。 |
| **证据** | `docs/ga4_social_utm_guide.md` 配置表（:10-19）无时区/币种/数据保留条目。代码侧不涉及（均在 Google 后台）。 |
| **风险等级** | **P1（中）** —— 时区错误会导致按日/按小时报表错位；币种未设为 USD/EUR 会使收入指标混淆；数据保留默认 14 个月，若业务需更长需调整，且涉及 GDPR 存储期限。 |
| **建议方案** | Owner 在 GA4 后台确认并记录：Property 时区（建议按主要市场或 UTC，团队统一口径）、币种（USD 主 + EUR 视需）、数据保留（14 个月 vs 50 个月，权衡业务与 GDPR 最小化原则）。 |
| **是否需要 Owner 批准** | 改后台设置**是**；仅查看记录**否**。 |

---

## 三、三资产架构 GA4 覆盖对照

| 资产 | 定位 | GA4 实现状态 |
|---|---|---|
| B2C 商城（WordPress @ nuotaooutdoor.com） | DTC 主销售站 | **代码已实现，生产疑似未生效（P0 待复核）** |
| `frontend/`（AI OS 控制台，React+Vite+AntD） | 内部管理后台 | **无追踪（正确）** —— 内部后台不应接 GA4；grep 仅文案命中（如 `SEO.tsx:261`「接入GA4数据后展示」） |
| `frontend-b2b/`（B2B 展示/批发门户，Cloudflare Pages） | B2B 门户 | **无 GA4 实现** —— grep 0 命中；若未来需统计 B2B 门户流量需单独配数据流 |

---

## 四、「代码已实现 vs 生产未生效」矛盾根因分析

生产实测与代码/文档矛盾，可能原因（按可能性排序，需 Owner 逐一排除）：

1. **插件未激活**：`nuotao-social-enhancements` 在生产 WP 中可能未启用 → `wp_head` 钩子（`class-tracking.php:28`）不触发。
2. **Measurement ID 未保存**：设置页填了但未点保存，或保存后 `get_settings()` 返回空 → `class-tracking.php:123` 直接 return。
3. **验收时点早于配置**：`B2C_ACCEPTANCE_REPORT.md:126` 的生产实测可能早于 GA4 配置完成时间；但 `ga4_social_utm_guide.md` v1.1 日期为 2026-09-08，早于 2026-11-19 审计，故此解释可能性较低。
4. **页面/CDN 缓存**：生产 HTML 被 WP 缓存插件或 CDN 缓存为未注入版本 → 需清缓存后复测。
5. **`should_inject()` 条件拦截**：该函数（:116）可能含环境判断（如仅非生产、仅特定页型）拦截了注入，需读其实现确认。

> **行动建议**：Owner 依次确认 1→2→4→5，最终以「清缓存后 curl 生产页出现 `G-30GWC4FYMG` + GA4 实时报告有数据」为生效金标准。

---

## 五、风险清单（按等级）

| 等级 | 风险 | 关联项 |
|---|---|---|
| **P0** | GA4 生产未注入，全站无分析数据，渠道归因/转化/AI 分析无源 | A2、A4 |
| **P0** | 代码/文档声称已配置与生产实测矛盾，存在「假配置」认知风险 | 执行摘要、§四 |
| **P1** | Property/数据流存在性仅文档自述，未经后台/数据侧证实 | A1、A3 |
| **P1** | 内部流量过滤代码侧未见实现，数据可能被管理员访问污染 | A6 |
| **P1** | 时区/币种/数据保留未记录，报表口径与 GDPR 存储期限存疑 | A7 |
| **P2** | 跨域未配置，现阶段单一域名影响有限，B2B 打通时升级 | A5 |

---

## 六、结论

1. **GA4 在 B2C WP 站代码层已实现**（`class-tracking.php` 注入逻辑完整），文档记录了完整配置 ID。
2. **但生产实测显示 GA4 未生效、无数据进入**，构成 P0 矛盾，**必须由 Owner 复核** GA4 是否真正注入（插件激活、ID 保存、缓存、`should_inject()` 条件）。
3. 在矛盾解决、GA4 实时报告确认有数据之前，**任何基于 GA4 的分析结论都不可信**。
4. 本报告为只读审计，未修改任何生产配置；所有整改建议均需 Owner 批准后执行。

> 交叉参考：GTM 现状见 `GTM_CONFIGURATION_AUDIT.md`；Cookie Consent / Consent Mode / GDPR 见 `CONSENT_PRIVACY_AUDIT.md`。