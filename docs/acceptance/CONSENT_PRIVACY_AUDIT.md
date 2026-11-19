# Consent 与隐私合规现状审计报告

> **交付物**：D8-B「GA4/GTM 现状审计」之 Consent / 隐私部分
> **审计日期**：2026-11-19
> **审计性质**：只读审计 + 方案设计，**未修改任何生产配置 / 代码**
> **目标市场**：美国、德国、欧盟（**GDPR 合规基线必须遵守**）
> **参考素材**：生产实测、全仓库 grep、WP 插件源码、`docs/` 文档、`frontend-b2b/`、`frontend/` 源码

---

## 一、执行摘要

**核心结论：全站缺失 Cookie Consent 机制与 Google Consent Mode，追踪脚本默认无条件加载，在 GDPR（欧盟/德国）下构成 P0 级合规风险。**

- **无 Cookie Banner**：全站（B2C WP 插件、frontend、frontend-b2b）无任何 Cookie 同意横幅 / 同意管理平台（CMP）。
- **无 Google Consent Mode v2**：全仓库无 `gtag('consent', ...)` / `ad_storage` / `analytics_storage` / consent default 配置。
- **追踪默认无条件加载**：GA4（若生效）与 TikTok Pixel 在页面加载即注入，不等用户同意；`docs/social_media_p0_deployment.md:108` 明确「默认加载，后续可集成 Cookie 同意」，并把这列为 P1 未做项。
- **GDPR 视角**：欧盟/德国要求在用户**同意前**不得加载非必要追踪 Cookie / 不得采集个人数据；当前「先加载、后（且实际没）征求同意」的模式违反该原则。

> 需澄清一个易混淆点：`frontend/src/pages/CustomerDataPage.tsx` 有「客户同意管理」模块（consent purpose/history，对接 `/admin/customer-data/consent*` API），但这是 **AI OS 后台对客户主数据的 GDPR 台账**，**不是**面向终端用户的前端 Cookie Consent / Consent Mode，二者不可混为一谈。

---

## 二、逐项审计（ChatGPT 清单 D）

> 每项含 5 要素：当前状态 / 证据 / 风险等级 / 建议方案 / 是否需要 Owner 批准

### D1. Cookie Consent（Cookie 同意横幅 / CMP）

| 要素 | 内容 |
|---|---|
| **当前状态** | **全站无 Cookie Banner / 无 CMP（确定）** |
| **证据** | 生产实测首页 + `/shop/`：无 Cookie Consent 组件。WP 插件 grep `consent`/`cookie`/`gdpr`/`ccpa`/`cookiebot`/`complianz`：0 命中（仅 TikTok SDK 的 `enableCookie` 方法名，非同意机制）。`frontend/`、`frontend-b2b/`：无 Cookie Banner 实现。 |
| **风险等级** | **P0（高）** —— 欧盟/德国 GDPR 要求非必要 Cookie 需用户事前同意；美国部分州（CCPA/CPRA）要求提供退出/告知机制。无任何机制 = 直接合规缺口。 |
| **建议方案** | 引入 CMP（如 open-source 的 Complianz / Cookiebot / 自建），在用户同意前**阻止** GA4/Pixel 加载；分类管理（必要/分析/营销）；记录同意状态。需先做方案设计再由 Owner 批准实施。 |
| **是否需要 Owner 批准** | **是**（引入 CMP + 改追踪加载逻辑，涉及生产）。 |

### D2. Google Consent Mode v2

| 要素 | 内容 |
|---|---|
| **当前状态** | **全站未实现（确定）** |
| **证据** | 全仓库 grep `gtag('consent')` / `ad_storage` / `analytics_storage` / `consent default`：0 命中。GA4 注入代码 `class-tracking.php:131-138` 仅 `gtag('js')` + `gtag('config')`，**无** `gtag('consent', 'default', {...})` 前置。 |
| **风险等级** | **P0（高）** —— Consent Mode v2 是 Google 要求（2024 起欧盟 EEA 必需）用于在无同意时以 cookieless/ping 方式建模、并让 GA4/Google Ads 遵从同意状态。缺失则既不合规，也无法在拒绝场景下保留建模数据。 |
| **建议方案** | 在 GA4/任何 Google 标签加载前注入 `gtag('consent','default',{ad_storage:'denied',analytics_storage:'denied',ad_user_data:'denied',ad_personalization:'denied',wait_for_update:500})`；CMP 同意后 `gtag('consent','update',{...granted})`。与 D1 的 CMP 联动。 |
| **是否需要 Owner 批准** | **是**。 |

### D3. 用户同意状态管理

| 要素 | 内容 |
|---|---|
| **当前状态** | **无前端 Cookie 同意状态管理**。GA4/Pixel 默认无条件加载，无同意/拒绝状态记录与传播。 |
| **证据** | `docs/social_media_p0_deployment.md:108`：追踪「默认加载，后续可集成 Cookie 同意」（即当前未集成）。`:213`：将「Cookie 同意横幅」列为 P1 未做。 |
| **风险等级** | **P0（高）** —— 无同意状态则无法证明用户授权，GDPR 问责（accountability）要求留存同意证明；当前无法满足。 |
| **建议方案** | CMP 记录用户同意（分类 + 时间戳 + 版本），并通过 Consent Mode 传播给 GA4/Google；同意状态留存备查。 |
| **是否需要 Owner 批准** | **是**。 |

### D4. 隐私告知（隐私政策 / Cookie 政策链接）

| 要素 | 内容 |
|---|---|
| **当前状态** | **B2B RFQ 表单有同意勾选但无隐私政策链接；页脚无隐私政策/条款入口（缺口）** |
| **证据** | ① `frontend-b2b/src/pages/public/RequestQuote.tsx:261-274`：RFQ 表单有**强制**隐私同意勾选框（未勾不能提交），文案提及 privacy policy 但**无实际隐私政策页链接**。② `frontend-b2b/.../PublicLayout.tsx:172`：页脚仅 © 版权，**无**隐私政策/服务条款链接。③ `README:24`：自述 GDPR 合规**仅指** `anonymize_ip`，无 Cookie 同意机制。 |
| **风险等级** | **P1（中，独立于 Cookie Consent）** —— 即使 B2B RFQ 收集了勾选同意，缺可访问的隐私政策链接使「知情同意」不成立（GDPR 要求告知处理目的/法律依据/数据主体权利）；且 B2C 站无隐私政策入口。 |
| **建议方案** | 编写并上线隐私政策页 + Cookie 政策页（覆盖 GA4/Pixel、数据用途、保留期、数据主体权利、跨境传输）；B2C 页脚 + B2B RFQ 表单 + B2B 页脚均加入可点击链接；RFQ 同意框链接指向隐私政策。 |
| **是否需要 Owner 批准** | 编写政策文本 + 改前端加链接**是**（涉及线上内容）。 |

### D5. GA4/Pixel 加载时机（默认无条件加载）

| 要素 | 内容 |
|---|---|
| **当前状态** | **默认无条件加载（P0 合规风险核心）** |
| **证据** | `class-tracking.php:115-141`（GA4 经 wp_head 注入，无同意前置）、`:100-108`（TikTok Pixel 同样默认注入）。`docs/social_media_p0_deployment.md:108`、`:213` 佐证「默认加载、同意机制未做」。 |
| **风险等级** | **P0（高）** —— 在欧盟/德国，未经同意加载 GA4/Pixel 即采集个人数据（IP、设备、行为），违反 GDPR ePrivacy；`anonymize_ip` **不足以**替代同意（IP 匿名化只降低影响，不豁免同意要求）。 |
| **建议方案** | 改为「同意前不加载」：将 GA4/Pixel 注入逻辑改为由 CMP 同意回调触发（或 Consent Mode 默认 denied + 同意后 update）；这是 D1/D2/D3 的落地。 |
| **是否需要 Owner 批准** | **是**（改追踪加载逻辑，涉及生产）。 |

### D6. 客户同意台账（AI OS 后台）— 区分说明

| 要素 | 内容 |
|---|---|
| **当前状态** | **已有客户主数据同意台账，但非前端 Cookie Consent** |
| **证据** | `frontend/src/pages/CustomerDataPage.tsx` + `client.ts:1407-1424`：客户同意管理模块（consent purpose / history），对接 `/admin/customer-data/consent*` API。属 AI OS 后台对客户 PII 处理的 GDPR 台账。 |
| **风险等级** | **P2（低，本身是正面资产）** —— 该台账有价值，但**不能替代**前端 Cookie Consent / Consent Mode；两套机制服务不同对象（客户主数据处理 vs 终端浏览器追踪）。 |
| **建议方案** | 保留并完善该台账（对接数据主体权利流程）；同时**单独**建设前端 Cookie Consent / Consent Mode（D1-D3、D5）。在文档中明确二者边界，避免误认为「已有同意管理就合规了」。 |
| **是否需要 Owner 批准** | 完善台账**视具体改动**；新建前端 Consent 机制**是**。 |

---

## 三、合规风险清单（按目标市场）

| 等级 | 风险 | 涉及市场 | 关联项 | 法规依据 |
|---|---|---|---|---|
| **P0** | 追踪脚本（GA4/Pixel）默认无条件加载，未经同意采集个人数据 | 欧盟/德国/美国 | D5、D1 | GDPR ePrivacy、CCPA/CPRA |
| **P0** | 无 Cookie Consent / CMP，无同意横幅 | 欧盟/德国/美国 | D1 | GDPR、ePrivacy |
| **P0** | 无 Google Consent Mode v2 | 欧盟/德国（EEA 强制） | D2 | Google EEA 政策、GDPR |
| **P0** | 无同意状态记录，无法证明授权（问责缺失） | 欧盟/德国 | D3 | GDPR Art.7 |
| **P1** | 隐私政策缺失/无链接，「知情同意」不成立 | 欧盟/德国/美国 | D4 | GDPR Art.13/14 |
| **P1** | `anonymize_ip` 被误当作 GDPR 合规充分条件 | 欧盟/德国 | D5、README:24 | GDPR、ePrivacy |
| **P2** | 客户同意台账与前端 Cookie Consent 边界混淆风险 | 全市场 | D6 | — |

> **市场差异提示**：德国/欧盟对 Cookie 同意执行最严（需事前opt-in、拒绝须与接受同等便捷）；美国加州 CCPA/CPRA 偏 opt-out + 告知。建议以**最严格的 GDPR opt-in 基线**统一实现，简化多市场维护。

---

## 四、整改优先级建议（供 Owner 决策，本审计不实施）

| 顺序 | 动作 | 等级 | 依赖 |
|---|---|---|---|
| 1 | 上线隐私政策 + Cookie 政策页，补全 B2C/B2B 链接 | P1 | 无（内容工作） |
| 2 | 引入 CMP，实现「同意前不加载」追踪 | P0 | 隐私政策（引用其类别） |
| 3 | 实现 Google Consent Mode v2（默认 denied → 同意后 update） | P0 | CMP |
| 4 | 记录并留存用户同意状态备查 | P0 | CMP |
| 5 | 明确区分并文档化「客户同意台账 vs 前端 Cookie Consent」 | P2 | 无 |

> **与 GA4/GTM 审计的衔接**：整改 2/3（CMP + Consent Mode）应与 `GA4_CONFIGURATION_AUDIT.md` 的「GA4 生效」一并设计——在让 GA4 生产生效的同时就带上同意门控，避免先无条件上线再返工。

---

## 五、结论

1. **全站缺失 Cookie Consent 与 Google Consent Mode，追踪默认无条件加载**，在目标市场（尤其欧盟/德国 GDPR）构成 **P0 合规风险**。
2. `anonymize_ip` **不能**替代 Cookie 同意；README 将 GDPR 合规等同于 IP 匿名化是认知误区（P1）。
3. B2B RFQ 有同意勾选但无隐私政策链接、页脚无政策入口，「知情同意」不成立（P1）。
4. AI OS 后台的「客户同意台账」是正面资产，但**不等于**前端 Cookie Consent，二者需分别建设（P2 边界澄清）。
5. 建议以 GDPR opt-in 最严基线统一实现 CMP + Consent Mode v2 + 隐私政策，并优先于「GA4 大规模上线」完成，避免合规返工。
6. 本报告为只读审计，未修改任何生产配置；所有整改均需 Owner 批准后实施。

> 交叉参考：GA4 现状见 `GA4_CONFIGURATION_AUDIT.md`；GTM 现状见 `GTM_CONFIGURATION_AUDIT.md`。