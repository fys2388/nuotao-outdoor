# B2B 公开站验收 — 纵向 / 横向对比（信任度 + 流量）

- 对象: `https://b2b.nuotaooutdoor.com`（frontend-b2b 公开批发门户）
- 日期: 2026-11-18
- 方法: 浏览器实际渲染观察（Home / Products / 产品详情 / Cooperation / Request a Quote）+ 只读 SEO 基线检测（curl）+ 全页价格泄露正则扫描
- 边界: **只读验收**，未提交真实询盘、未改生产配置/数据/价格/库存

---

## 一、验收结论（展示层）

| 检查项 | 结果 |
|---|---|
| 渲染正确性（非旧 AI OS 控制台） | ✅ title "Nuotao Outdoor — B2B Wholesale Portal" |
| 首页产品目录 | ✅ 9 分类 / 12 产品（Featured Products） |
| Products 目录页 | ✅ 分类筛选 + 分页，12 产品，**无价格** |
| 产品详情页 | ✅ 主图+6缩略图+分类+描述+Request a Quote，**零价格泄露** |
| Cooperation 合作模式 | ✅ Wholesale / Distribution / Sourcing / Long-term / OEM-ODM 五类 |
| Request a Quote 询盘表单 | ✅ 12 字段（Company/Contact/Email/Country/BusinessType/Products/WhatsApp/WeChat/Qty/AnnualRange/Destination/Message）+ GDPR 同意 + Submit Enquiry |
| 联系渠道 | ✅ WhatsApp(wa.me) + Email B2B Team + 表单 |
| 价格泄露正则扫描（详情页） | ✅ 文本/HTML：$、€、£、price、wholesale_price、retail_price、add_to_cart、sku、stock、cost、supplier 全 0；唯一 "margin" 命中为 CSS 变量 `--ant-margin-xxs` |
| 错配修复确认 | ✅ 不再渲染旧 "Nuotao AI OS 控制台" 空壳 |

**展示层验收：PASS**（错配已修复，公开展示层零价格泄露）。

---

## 二、纵向对比（B2B 站自身历史演进）

| 维度 | 历史（BLOCKED，见 reports/b2b/M0_B2B_DEPLOYMENT_AUDIT.md） | 现在（本次验收） |
|---|---|---|
| b2b 子域渲染 | 旧 "Nuotao AI OS 户外电商智能运营系统" 控制台空壳 | 正确 frontend-b2b 批发门户 |
| `/apply` | soft-404（返回 index.html 假成功） | Cooperation 页正常 |
| 页脚 Wholesale/B2B 入口 | 指向空壳 | 指向真实批发门户 |
| 产品目录 | 空 | 9 类 / 12 产品 |
| 询盘链路 | 无 | Request a Quote 12 字段表单 |
| 价格泄露 | — | 零泄露（已扫描取证） |

**纵向结论**：从"部署错配/BLOCKED"演进到"正确批发门户/展示层 PASS"，产品目录、询盘链路、价格保护均从无到有。

---

## 三、横向对比（vs 同行 B2B 外贸站）— 聚焦信任度 + 流量

> 说明：本轮 autoglm-websearch token 服务未运行、web_search 缺 DEEPSEEK_API_KEY，无法实时抓取同行站点。以下横向基准基于**行业通行 B2B 外贸站手法** + 仓库已有竞品/SEO 调研（docs/video-marketing/b2b_page_design.md 等）。如需精确同行逐项对标，待联网检索恢复后补。

### 3.1 信任度（Trust）

| 信任信号 | 同行通行做法 | 本站现状 | 差距 |
|---|---|---|---|
| 工厂/产线实拍、视频 | 工厂 tour、产线照片、视频 | ❌ 无 | **大** |
| 认证资质 | ISO 9001 / BSCI / CE / REACH 徽章 + 证书 | ❌ 无 | **大** |
| 成立年限 / 产能 | "10+ years / 月产能 X 万件" | ❌ 无 | **大** |
| 客户 logo / 案例 | 合作品牌墙、案例研究 | ❌ 无 | **大** |
| 检测报告 | 产品测试报告下载 | ❌ 无 | 中 |
| DTC 动销社会证明 | "DTC 站月销 1000+" | ❌ 无（未跨站引用） | 中 |
| MOQ 透明 | "MOQ from 50pcs" 明示 | ⚠️ 仅文字"discuss MOQ"，无数值 | 中 |
| 联系实体信息 | 公司注册地址、贸易展、联系人 | ⚠️ 仅 WhatsApp/Email | 中 |
| GDPR / 隐私同意 | 询盘同意勾选 | ✅ 有 | 达标 |
| 合作模式清晰 | 多模式分类 | ✅ 5 类清晰 | 达标 |
| 询盘流程清晰 | How it works | ✅ How to Start | 达标 |

**信任度结论**：**结构与流程信任已达基础线**（合作模式、流程、多渠道、隐私同意齐全），但**硬信任背书几乎空白**——无工厂实拍、无认证资质、无年限产能、无客户案例、无 DTC 动销证明。这是 B2B 外贸转化最大短板：采购商无法判断"是否真实工厂/可靠供应商"。

### 3.2 流量（Traffic / SEO）— 实测数据（2026-11-18）

#### SEO 基线实测（只读 curl）

| 指标 | B2B (`b2b.nuotaooutdoor.com`) | B2C (`nuotaooutdoor.com`, WooCommerce) |
|---|---|---|
| 原始 HTML 体积 | **583–595 字节（SPA 空壳）** | **~129 KB（SSR 完整正文）** |
| SSR 正文 | ❌ 无（`<div id="root">` + JS） | ✅ WooCommerce SSR |
| h1 数量（原始 HTML） | **0** | 1 |
| JSON-LD 结构化数据 | **0** | 1 |
| OG 标签 | **0** | 10 |
| sitemap.xml | ❌ **返回 SPA index.html（路由 miss 回退壳），无 `<url>/<loc>`** | ✅ 301 → `sitemap_index.xml`（200，真实） |
| robots.txt | ⚠️ 存在（content-signal 说明），未见 Sitemap 指令 | ✅ 存在 |
| 首页 TTFB/体积 | 200 / 1.0s / 583B | 200 / 2.0s / 128KB |
| products 页 | 200 / 3.7s / 583B（壳） | — |

#### SEO 要素逐项

| SEO 要素 | 同行通行做法 | 本站现状 | 差距 |
|---|---|---|---|
| 服务端渲染 / 预渲染 | SSR / SSG / prerender，首屏有正文 | ❌ **纯 CSR，原始 HTML 583B 空壳** | **致命** |
| 首屏 h1/h2 | 语义化标题 | ❌ 原始 HTML h1=0（JS 渲染后才出现） | **大** |
| 结构化数据 JSON-LD | Organization / Product | ❌ 0 | **大** |
| OG / Twitter 卡片 | 分享预览 | ❌ 0 | 中 |
| canonical / hreflang | 规范 URL / 多语言 | ❌ 无 | 中 |
| sitemap.xml | 真实 URL 列表 | ❌ **返回 SPA 壳，无 URL** | **大** |
| 内容营销（博客/指南） | 月更博客、批发指南 | ❌ 无 | 大 |
| 内容厚度 | 每产品完整 spec/FAQ | ⚠️ 12 产品，描述偏薄 | 中 |

**关键对照**：同集团的 **B2C WooCommerce 站 SEO 是健康的**（SSR 129KB、h1、JSON-LD、10 个 OG、真实 sitemap_index），而 **B2B React SPA 站 SEO 几乎为零**（583B 空壳、0 结构化数据、sitemap 缺失）。两者技术栈差异（WooCommerce SSR vs React CSR）直接造成 SEO 可见性天差地别。

**流量结论**：**B2B 站 SEO 技术底座存在致命缺陷**——纯客户端渲染，搜索引擎抓到的首屏是 583 字节空壳，无 h1/结构化数据/sitemap 正文。即使内容再好、投放再猛，自然搜索流量也几乎无法获取，且付费流量的落地页 SEO 权重极低。这是当前流量问题的**第一优先级技术阻塞**。

---

## 四、核心问题诊断（信任度 + 流量）

1. **流量（更紧急、技术性）**：B2B 站纯 CSR → SEO 几乎不可见。需引入 SSR/SSG/预渲染（或对营销落地页做静态化/prerender），补 sitemap.xml（真实 URL）、robots Sitemap 指令、JSON-LD、OG/canonical、h1 语义化。**不解决渲染，内容营销和投放引流都会漏（落地页 SEO 权重极低）。**
2. **信任度（更根本、内容性）**：缺硬信任背书。需补：工厂实拍/视频、认证资质（ISO/BSCI/CE）、成立年限/产能、客户案例/logo、产品检测报告、DTC 动销社会证明、MOQ 透明区间。这些是 B2B 采购决策的关键转化因子。
3. **两者关系**：流量解决"被找到"，信任解决"敢询盘"。当前**两个都未达标**——即便付费/社媒引流到位，CSR 空壳落地页 + 无信任背书会导致高跳出、低询盘转化。

---

## 五、建议优先级（待 Owner 决策，不擅自执行）

**P0（流量技术阻塞）**
- B2B 站 SEO 可渲染化：SSR/SSG 或营销页 prerender；补真实 sitemap.xml + robots Sitemap 指令 + JSON-LD(Organization/Product) + OG/canonical + h1。
- 注：属前端构建/部署变更，需 Owner 批准后实施（涉及生产部署）。

**P1（信任度内容建设）**
- 补信任背书内容：工厂实拍/视频、认证资质扫描件、成立年限/产能数据、客户案例/logo、产品检测报告、DTC 动销数据跨站引用、MOQ 透明区间。
- 内容资产来源需 Owner/业务侧提供真实素材（不可编造认证/案例）。

**P2（流量运营）**
- 内容营销（B2B 博客、产品批发指南、行业报告）、B2C→B2B 互链转化、B2B 目录站外链、（可选）付费投放。

---

## 六、Owner 待决事项

1. 流量 P0：是否批准 B2B 站 SEO 可渲染化改造（SSR/预渲染 + sitemap/结构化数据），授权生产部署？
2. 信任度 P1：真实素材（工厂/认证/案例/产能）由谁提供、是否已有？禁止编造。
3. MOQ 是否公开透明区间（"MOQ from X pcs"）？涉及定价策略，需 Owner 定。
4. 横向精确对标：是否等联网检索恢复后补同行逐项对标？

---

**验收人**: Nuotao Dev Agent (Sensenova)
**边界重申**: 本次仅只读观察与检测；未提交询盘、未改价格/库存/生产配置；所有生产变更（SEO 改造部署、内容上线）待 Owner 明确授权。
