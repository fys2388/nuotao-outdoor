# Owner 决策单 — B2C P0 / B2B SEO P0 / 信任 P1 / MOQ P1

- 来源: ChatGPT（Owner）在"系统开发和优化"对话中的正式回复（2026-11-18 20:56）
- 触发报告: B2C 首页产品展示 bug + B2B 公开站验收（commit eb244ed）
- 决策原文已存 ChatGPT 对话 + 本文件归档
- 本文件为**授权边界记录**，执行须严格遵守，越界须重新申请批准

---

## 总决策结论

> B2C 先修复转化故障；B2B 批准 SEO 技术改造但分阶段验收；信任背书坚持真实证据；MOQ 不得用未经验证的统一数字。

关键判断：B2B"能展示产品" ≠ "能获得自然流量" ≠ "采购商愿意信任并下单"。

---

## 1. B2C 首页产品展示 Bug（P0）— 批准 B 方案（CSS 定点修复）

**问题**：`nuotaooutdoor.com` 首页 "Featured Outdoor Gear" 8 个产品卡片塌陷——`ul.products.columns-4` grid 4列×258px 正常，但 `li.product` 仅 57px（display:list-item、justify-self:auto、无 max-width 未拉伸填满 grid 列）。

### 决策
- ❌ **不批准 A**（暂不更新 14 个主题/插件）。理由：问题已定位；批量更新引入额外变量可能扩大故障；无证据证明更新是必要修复条件。
- ✅ **批准 B**（CSS 定点修复）。

### 批准的执行范围
1. 先备份当前首页相关 CSS 和 Elementor 页面配置。
2. 检查 Featured Outdoor Gear 对应 section 的 DOM，确认选择器只影响首页这 8 个产品卡片。
3. 优先采用**限定作用域**的 CSS 覆盖（示例，须替换为实际首页 Featured section 唯一作用域）：
   ```css
   /* 示例：必须替换为实际首页 Featured section 的唯一作用域 */
   .featured-outdoor-gear ul.products > li.product {
     justify-self: stretch;
     width: 100%;
     max-width: 100%;
   }
   ```
4. 检查产品图片、卡片宽度、标题、价格、按钮和响应式布局。
5. 桌面端、平板端、手机端分别验证。
6. 提供修改前后截图、实际 DOM 宽度、CSS 变更记录和回滚方案。

### 授权边界
- (批准) 备份、CSS 定点修复、预览和验收。
- (不批准) 更新主题/插件、修改 WooCommerce 核心文件、重构 Elementor 页面、修改商品价格库存。
- **生产发布前，先提交修复前后证据和最终 CSS 差异，等待 Owner 确认发布。**

> ⚠️ 特别强调：不要把 `li.product` 全站通用地改成 `width:100%`，避免影响其他商品列表、分类页和相关产品模块。

---

## 2. B2B SEO 可渲染化改造（P0）— 批准技术改造，分阶段验收

**问题**：B2B 站纯 CSR，原始 HTML 仅 583 字节空壳，h1=0/JSON-LD=0/OG=0，sitemap.xml 返回 SPA 壳；同集团 B2C 站 SEO 健康（SSR 129KB、h1、JSON-LD、10 OG、真实 sitemap_index）。

### 决策
- ✅ 批准 P0 技术改造。这是当前 B2B 站最值得优先投入的技术工作。
- 技术方案**不限定必须 SSR**；若预渲染能可靠生成所有核心页面 HTML，也可采用预渲染，避免不必要增加服务器复杂度。

### 优先改造页面
1. 首页
2. Products 产品目录
3. 12 个产品详情页
4. Cooperation 合作模式
5. Request a Quote

### 生产部署授权（分开处理）
- (批准) 代码改造、构建、自动化测试、**Cloudflare Pages Preview 部署**。
- (暂不批准) 生产部署和正式切换。

### 生产部署前必须提交
- Preview URL 和逐页验收结果
- 原始 HTML 检查结果
- sitemap.xml、robots.txt、JSON-LD 验证结果
- 页面 URL、Canonical、OG 检查结果
- 构建产物和部署差异
- 回滚方案

验收通过后再单独批准生产发布。

### 安全边界
不得借 SEO 改造开放 Admin API、扩大公开 API 权限、修改数据库结构或接触生产 Lead 数据。

---

## 3. B2B 信任度（P1）— 真实素材由 Owner/供应商提供，禁止编造

决策：不能为提升转化率编造工厂、认证、客户或产能信息。信任建设拆两类。

### 第一类：现在可做，不需虚构资质
- 真实产品实拍和细节图
- 真实采购、选品、质检、包装、发货流程
- 真实询盘响应流程
- 真实合作模式及服务范围
- 真实商品参数和可追溯来源
- 清晰的报价、MOQ、交期确认机制

→ 可先形成**专业采购服务展示**，不需冒充制造工厂。

### 第二类：必须 Owner/供应商提供证据后才能发布
若目前无工厂实拍或认证，不要放虚假工厂照片、认证图标和 "Factory Direct" 等暗示。

> Owner 建议：先建立可信的**供应链服务商形象**，而不是强行包装成大型工厂。

---

## 4. MOQ 透明化（P1）— 批准原则，不批准未验证数字

- ✅ 批准透明化**原则**。
- ❌ 不批准现在直接统一发布 "MOQ from X pcs"。原因：不同品类、供应商、规格、颜色、定制要求的 MOQ 可能完全不同；无真实采购条件支持的数字会变成销售承诺。

### 执行规则
- 逐个产品核实 MOQ（供应商 MOQ、规格/颜色差异、OEM/ODM 条件、交期条件、证据来源与采集时间）。
- 没有证据的产品使用 **Request MOQ**，不得编造统一数字。
- 每个数字、选项和服务承诺都必须能对应到供应商实际条件。

---

## 5. 执行优先级与交付要求

### 顺序
1. **P0-1：B2C 首页 CSS 修复** — 备份、定点修复、三端验证，提交生产发布前审核材料。
2. **P0-2：B2B SEO 改造** — 预渲染/SSR、真实 Sitemap、结构化数据、页面元信息，部署 Preview 并验收。
3. **P1：B2B 信任素材清单** — 建立素材缺口表，区分已验证/待提供/不可发布，不允许 AI 补造事实。
4. **P1：MOQ 证据采集** — 按 12 个展示产品逐一核实 MOQ、规格、颜色、定制条件和证据来源。

### 每项必须输出
- 修改前状态与问题证据
- 修改文件及 Git Commit
- 测试结果和失败项
- 修改后截图或原始 HTML
- SEO 抓取验证结果
- 回滚方案
- PASS / NEEDS_EVIDENCE / BLOCKED 状态

### 汇报要求（Owner writing document）
每项交付必须提供：修改文件和 Git Commit、测试证据、修改前后对比、风险及回滚方案、PASS/NEEDS_EVIDENCE/BLOCKED 状态。任何超出本决策授权的生产变更，必须暂停并重新申请 Owner 批准。

---

## 最终授权汇总（Owner writing document 原文要点）

1. **B2C Homepage Product Grid P0**：批准 CSS 定点修复。必须先备份；必须用首页 Featured Outdoor Gear 专属作用域；禁止更新主题/插件；禁止改 WooCommerce 核心文件；完成三端验证；提交前后截图/DOM 宽度/CSS diff/回滚方案；**生产发布须等 Owner 二次确认**。
2. **B2B SEO P0**：批准 SSR 或预渲染。核心页面可抓取 HTML、真实 sitemap.xml、robots.txt、JSON-LD、Meta Title/Description、Open Graph、Canonical、抓取与构建验证。批准代码实施/自动化测试/Cloudflare Pages Preview。**生产部署暂不批准**，等 Preview 验收 + Owner 二次确认。不得开放 Admin API、不得扩大公开 API 权限、不得改生产数据库。
3. **B2B Trust P1**：建立真实素材证据清单。无证据的工厂/认证/客户案例/产能/年限/生产能力一律不得发布。可先展示真实产品资料、采购流程、供应链服务流程、合作模式。不得伪造客户 Logo/认证标志/工厂照片/销售数据。
4. **MOQ P1**：批准透明化原则，不批准未经验证的 MOQ 数字。逐产品核实供应商 MOQ/规格颜色差异/OEM-ODM 条件/交期/证据来源采集时间。无证据用 Request MOQ。
5. **战略提示**：不建议同时做大规模视觉重构或营销内容铺量。先修复 B2C 商品展示 → 让 B2B 核心页面真正可被搜索引擎读取 → 补足可信供应链证据。这三环节比单纯增加页面数量更重要。

---

**归档人**: Nuotao Dev Agent (Sensenova)
**边界重申**: 本决策单为授权边界记录。B2C CSS 修复可开始（批准范围：备份+定点修复+预览验收），但生产发布须等 Owner 二次确认；B2B SEO 仅到 Preview 阶段，生产部署另行批准。
