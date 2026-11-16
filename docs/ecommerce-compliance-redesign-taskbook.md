# Nuotao 独立站合规改造技术任务书

> 版本：v1.0
> 状态：待执行（等待 Codex 开发执行）
> 建立日期：2026-09-25
> 依据：`docs/P0-2-nuotao-us-compliance-checklist.md`（DEC-021 + DEC-022）
> 关联：`docs/cross_border_compliance_knowledge_base.md` §8、`docs/website_p0_p1_fix_plan.md`（页脚 / 隐私政策 P0 未完成）
> 目标站点：nuotaooutdoor.com（WooCommerce + Elementor + Rank Math）
> 目的：一次性完成 11 项合规改造，覆盖 CPSC/FCC/Prop 65/FTC/GDPR/CCPA/州销售税 全部合规展示要求

---

## 1. 任务范围概览

| # | 任务 | 类型 | 优先级 | 预估工时 | 依赖 |
|---|---|---|---|---|---|
| T1 | 页脚添加通用加州 Prop 65 警示 | Elementor 编辑 | P0 | 0.5h | 无 |
| T2 | 产品详情页模板添加 Prop 65 警示模块 | Elementor + WooCommerce | P0 | 1h | 无 |
| T3 | 隐私政策页面重建（GDPR + CCPA + PIPL 三合一） | 页面新建 | P0 | 2h | 无 |
| T4 | Terms of Service 页面更新（GDPR + CCPA + FTC 广告披露） | 页面更新 | P0 | 1.5h | 无 |
| T5 | 州销售税说明页面（Tax & Shipping Policy） | 页面新建 | P1 | 1h | 无 |
| T6 | CPSC 进口商信息披露（Importer Info 页面） | 页面新建 | P0 | 1h | 无 |
| T7 | Cookie 同意横幅（Complianz 或 Cookie Notice 插件） | 插件安装 + 配置 | P0 | 1h | 无 |
| T8 | Affiliate Disclosure（联盟披露）页面 | 页面新建 | P1 | 0.5h | 无 |
| T9 | 60 SKU 电子配件 FCC 声明（元数据字段 + 详情页展示） | WooCommerce 字段 + 模板 | P1 | 2h | 合规库表 |
| T10 | 60 SKU 材质/成分清单（Materials & Composition 元数据 + 详情页展示） | WooCommerce 字段 + 模板 | P0 | 2h | 供应商 BOM |
| T11 | GCC 通证文件库（内部合规库，不公开，供海关查验） | 数据库 + 内部页面 | P0 | 3h | GCC 通证模板 |
| **合计** | | | | **15.5h** | |

**执行顺序**：T1 → T2 → T6 → T11 → T10 → T3 → T4 → T5 → T7 → T8 → T9

---

## 2. 各任务详细规格

### T1 — 页脚添加通用加州 Prop 65 警示

**位置**：Elementor 全局页脚模板
**当前状态**：页脚残缺（`website_p0_p1_fix_plan.md` P0-3 未修复）
**目标状态**：完整页脚 + 通用 Prop 65 警示

**实施步骤**：
1. Elementor → 模板 → 全局页脚 → 编辑
2. 在页脚最底部（版权声明上方）添加新 Section
3. 添加 Widget：**Alert**（Elementor 内置）或 **Text Block**
4. 内容：
   ```
   ⚠ WARNING: This product can expose you to chemicals known to the State of California
   to cause cancer and birth defects or other reproductive harm. www.P65Warnings.ca.gov
   ```
5. 样式：字号 12px，灰色（#666666），居中，上下 padding 16px
6. 响应式：手机端同样显示，不换行截断

**验收标准**：
- 桌面端 + 移动端均可见
- 与页脚其他内容（Shop/Help/Company 链接）不打架
- 链接 `https://www.P65Warnings.ca.gov` 可点击跳转

---

### T2 — 产品详情页模板添加 Prop 65 警示模块

**位置**：Elementor + WooCommerce 单品模板
**当前状态**：所有 SKU 无警示
**目标状态**：所有 SKU 详情页显示通用警示

**实施步骤**：
1. Elementor → 模板 → WooCommerce → Single Product → 编辑
2. 在"产品描述"下方（Description tab 内）或"产品元数据"下方（Details tab 内）添加新 Section
3. 添加 Widget：**Alert**
4. 内容同 T1
5. 位置：优先放在 Details tab 底部（因为 Details 是合规信息聚集区）

**验收标准**：
- 所有 60 SKU 详情页都显示警示
- 位置一致（不因为产品模板变体而消失）
- 移动端换行正确

---

### T3 — 隐私政策页面重建（GDPR + CCPA + PIPL 三合一）

**位置**：`/privacy-policy/`
**当前状态**：可能是空的或 WooCommerce 默认的占位页
**目标状态**：完整覆盖 GDPR（欧盟）+ CCPA（加州）+ PIPL（中国）+ 跨境传输条款

**页面结构**：
1. **概述**（3-4 段，涵盖 Nuotao 数据处理原则）
2. **收集的数据类型**（用户账户、订单、浏览行为、Cookie、支付信息）
3. **数据收集的目的**（订单履约、营销、分析、合规）
4. **法律依据**（GDPR Art 6 + CCPA + PIPL）
5. **第三方接收方**（支付网关、货代、物流、Google Analytics、Meta 广告、Mailchimp/EDM）
6. **国际数据传输**（中国直发场景下的美国-中国数据传输）
7. **用户权利**（访问/更正/删除/可携带/反对/自动化决策）
8. **数据保留期**
9. **安全保护措施**
10. **未成年人保护**（GPC/GPC 处理）
11. **联系方式**（DPO 邮箱 + Nuotao 公司地址）
12. **变更历史**

**参考模板**：TermsFeed Privacy Policy Generator + Iubenda（Nuotao 用哪个）
**内容要求**：
- 至少 2,000 字英文
- 明确提及 California Consumer Privacy Act（CCPA）+ GDPR
- 明确提及跨境数据传输（EU-US Data Privacy Framework 或 SCC）

**验收标准**：
- Rank Math SEO 收录，meta description 正确
- 从页脚可点击
- 页面 URL slug：`/privacy-policy/`

---

### T4 — Terms of Service 页面更新

**位置**：`/terms-conditions/`（当前链接指回自身，见 `website_p0_p1_fix_plan.md` P0-5）
**目标状态**：完整 TOS + FTC 广告披露

**页面结构**：
1. **接受条款**（勾选框）
2. **产品描述**（保留修改权）
3. **订单与取消政策**（含 30 天退货期）
4. **退款政策**（含运费谁承担）
5. **保修责任**（12 个月保修）
6. **责任限制**（不含间接损失）
7. **知识产权**（Nuotao 品牌 + 商标）
8. **适用法律**（美国特拉华州法）
9. **争议解决**（仲裁条款）
10. **变更历史**
11. **Affiliate Disclosure**（若使用联盟营销，需 FTC 广告披露声明）
12. **Cookie 政策链接**（跳转到隐私政策）

**参考模板**：Iubenda TOS Generator
**内容要求**：
- 至少 1,500 字英文
- 明确 FTC Affiliate Disclosure（若做联盟）
- 明确 GDPR 数据删除权（Right to Erasure）

**验收标准**：
- 链接从结算页 "Terms & Conditions" 可跳转
- 当前 "Terms 指回自身" 问题修复

---

### T5 — 州销售税说明页面

**位置**：`/tax-shipping-policy/`
**目标状态**：解释 Nuotao 各州销售税收取逻辑

**页面结构**：
1. **各州销售税规则**（California 7.25% / Texas 6.25% / New York 4% / Florida 6% 等）
2. **经济关联**（Economic Nexus）：Nuotao 在超过 $100K 销售额的州需缴税
3. **WooCommerce Tax 插件机制**：按客户地址自动计算
4. **退货时销售税处理**
5. **联系地址**（Nuotao 主营业地）

**内容要求**：
- 至少 500 字英文
- 列出 Nuotao 已开通销售税的州（初期可能只有 California + Texas + 纽约）

**验收标准**：
- 从结算页可跳转
- WooCommerce Tax 插件配置与页面说明一致

---

### T6 — CPSC 进口商信息披露页面

**位置**：`/importer-info/`
**目标状态**：Nuotao 作为美国进口商的合规披露

**页面结构**：
1. **Nuotao Outdoor LLC** 公司信息（地址、电话、邮箱、DUNS 号若已注册）
2. **美国代理地址**（美国境内物理地址，供 CPSC 联系）
3. **产品追溯责任**（Nuotao 作为 Importer 承担 CPSC 追溯责任）
4. **产品责任保险**（Product Liability Insurance $1M+，见 DEC-015 B2B 前置要求，DTC 阶段也应具备）
5. **召回联系方式**（recall@nuotaooutdoor.com）
6. **CPSC 报告义务**（SaferProducts.gov 报告流程）

**内容要求**：
- 至少 300 字英文
- 明确 Nuotao 承担 CPSC Importer of Record 责任

**验收标准**：
- 从页脚"Importer"链接可跳转
- 内容符合 CPSC 16 CFR Part 1132（追踪标签要求）

---

### T7 — Cookie 同意横幅（GDPR 合规）

**位置**：全站页面底部
**当前状态**：未安装（Nuotao 用 Cookie Notice 或 Complianz 插件）
**目标状态**：GDPR 合规的 Cookie 同意横幅 + 分类管理

**实施步骤**：
1. WooCommerce → 插件 → 安装 **Complianz GDPR** 或 **Cookie Notice & Consent**
2. 激活插件
3. 配置：
   - 横幅位置：底部居中
   - 按钮文案："Accept All" + "Manage Preferences"
   - Cookie 分类：必需 / 分析 / 营销
   - 默认状态：仅"必需"Cookie 勾选
   - 同意记录：保存 GDPR 同意日志
4. 与 Rank Math + Google Analytics 集成（GA 延迟加载直到用户同意）

**验收标准**：
- 首次访问弹横幅
- 关闭后可通过"Cookies"按钮重新打开
- Google Analytics + Facebook Pixel 在未同意前不加载

---

### T8 — Affiliate Disclosure 页面

**位置**：`/affiliate-disclosure/`
**当前状态**：可能不存在
**目标状态**：符合 FTC 广告的披露声明

**内容**：
```
Affiliate Disclosure

At Nuotao Outdoor, we may earn commissions from third-party 
partners when you click links on our website and make purchases. 
This does not affect the price you pay, and we only recommend 
products we trust. This disclosure is made in accordance with 
FTC Guidelines (16 CFR Part 255) on Endorsements and Testimonials.
```

**验收标准**：
- 从页脚"Affiliate"链接可跳转
- Rank Math SEO 收录

---

### T9 — 60 SKU 电子配件 FCC 声明

**目标**：为有线 LED 灯/头灯等 6-8 款电子配件添加 FCC 声明

**技术方案**：
1. WooCommerce → 设置 → 自定义字段（Custom Fields）→ 新增字段：
   - 字段名：`is_electronic_product`（布尔）
   - 字段名：`fcc_certification_type`（下拉：None / SDoC / FCC ID）
   - 字段名：`fcc_certificate_id`（文本，若 SDoC 则填写"SDoC-YYYY-NNN"）
2. WooCommerce → 产品编辑 → 60 SKU 中电子配件逐一填写字段
3. WooCommerce → 产品模板 → 在 Details tab 添加 Widget：**Product Meta**（读取自定义字段）
4. 展示 FCC 声明：
   - 若 `fcc_certification_type` = `SDoC`：显示 "This product complies with Part 15 of the FCC Rules."
   - 若 `fcc_certification_type` = `FCC ID`：显示 FCC ID 号

**验收标准**：
- 60 SKU 中电子配件（约 6-8 款）显示 FCC 声明
- 非电子 SKU 不显示

---

### T10 — 60 SKU 材质/成分清单

**目标**：所有 60 SKU 显示材质成分（Prop 65 合规必需）

**技术方案**：
1. WooCommerce → 自定义字段 → 新增字段：
   - 字段名：`materials_composition`（文本，如 "ABS plastic, stainless steel, silicone"）
   - 字段名：`fiber_composition`（下拉：Nylon / Polyester / Cotton / Wool / Down / Polyester / Other，仅纺织类）
2. WooCommerce → 60 SKU 逐一填写材质
3. WooCommerce → 产品模板 → Details tab 添加 Widget：**Product Meta**

**60 SKU 材质参考表**（取自 `docs/shop_launch_plan.md` + `docs/P0-2-nuotao-us-compliance-checklist.md` §7）：

| WC ID | 商品 | 材质 | 分类 |
|---|---|---|---|
| 930 | LED 感应头灯 | ABS, PC, LED, USB-C | 电子 |
| 942 | 太阳能露营灯 | ABS, Solar panel, LED | 电子 |
| 968 | 不锈钢保温瓶 | 304 stainless steel | 金属 |
| 957 | 折叠硅胶水壶 | Food-grade silicone | 塑料 |
| 907 | 3L 战术水袋背包 | TPU, Nylon | 尼龙 |
| 917 | 月亮椅 | 600D Oxford, Aluminum | 纺织+金属 |
| 990 | 防水收纳袋套装 6 件 | TPU, Nylon | 塑料 |
| 991 | 迷你急救包 100PCS EVA 硬壳 | EVA, Polyester | 塑料 |
| 992 | 铝合金登山杖 | 7075 Aluminum | 金属 |
| 993 | 多功能工具卡（去刀片） | 201 stainless steel | 金属 |
| 994 | 复古太阳能露营马灯 | ABS, Solar panel, LED | 电子 |
| 995 | 便携卡式炉 | Aluminum, Stainless steel | 金属 |
| 996 | 10 件套铝制锅具 | Aluminum, Teflon coating | 涂层 |
| 997 | 40L 徒步背包 | Polyester, Nylon, Waterproof coating | 纺织 |
| 998 | 3-4 人自动速开帐篷 | 210T Polyester, 600D Oxford, Coating | 纺织 |
| 1009 | 信封式睡袋 | 190T Nylon, Polyester fill | 纺织 |
| 1010 | 自充气睡垫 | EVA foam, TPU laminate | 塑料 |
| 1011 | 3×3m 涂银天幕 | 210D Polyester, Silver coating | 纺织 |
| 1012 | 铝合金折叠蛋卷桌 | Aluminum 6061 | 金属 |
| 1013 | 35L 折叠收纳箱 | Wood, Polyester | 木材+纺织 |
| 1014 | 不锈钢折叠烧烤架 | 304 Stainless steel | 金属 |
| 1021 | USB-C 感应头灯 | ABS, LED, Sensor | 电子 |
| 1022 | 便携净水壶 | PP plastic, Food-grade filter | 塑料 |
| 1023 | 高背躺椅 | Polyester, Aluminum | 纺织+金属 |
| ... | 剩余 33 SKU | 待补 | 待补 |

**验收标准**：
- 60 SKU 全部有材质字段
- 详情页 Details tab 展示材质

---

### T11 — GCC 通证文件库（内部，非公开）

**目标**：建立 Nuotao 内部合规数据库，存放每个 SKU 的 GCC 通证

**技术方案**（分两部分）：

#### 11.1 WooCommerce 自定义字段（Importer 内部字段）

1. WooCommerce → 自定义字段 → 新增字段：
   - `gcc_certificate_number`（文本，如 `GCC-2026-001`）
   - `gcc_issue_date`（日期）
   - `gcc_supplier_bom_link`（内部链接到供应商 BOM PDF）
   - `gcc_compliance_laws`（多选：16 CFR Part 1303 / 1307 / 1500 / 1501）

#### 11.2 内部合规库页面（Admin-only）

1. WordPress → 页面 → 新建 `/compliance-library/`
2. 页面设置：Visibility = Private（只有管理员可见）
3. 页面内容：表格列出所有 60 SKU 的 GCC 通证号、日期、下载链接
4. 下载链接指向 `/wp-content/uploads/gcc-certs/`（GCC 通证 PDF 存放目录）

**GCC 通证 PDF 模板**（Word 或 PDF）：
```
General Certificate of Conformity

Product Description: [产品名称 + 型号 + SKU]
Manufacturer: [供应商名称 + 地址]
Importer: Nuotao Outdoor LLC, [美国地址], www.nuotaooutdoor.com

This product complies with the following consumer product safety rules:
- 16 CFR Part 1303 (Ban on Lead in Paint)
- 16 CFR Part 1307 (Phthalate Content in Toys and Child Care Articles)
- 16 CFR Part 1500 (Small Parts Warning)
- 16 CFR Part 1501 (Toy Safety Standards - if applicable)
- California Proposition 65

Date of Issuance: [YYYY-MM-DD]
Certificate Number: GCC-2026-NNN

Signed: __________________
[Authorized Representative Name]
[Title]
```

**验收标准**：
- 60 SKU 全部有 GCC 通证 PDF
- 内部页面 `/compliance-library/` 只管理员可见
- 海关查验时可在 30 分钟内提供

---

## 3. 需要人工提供的输入

以下数据无法由 Codex 自动生成，需人工准备：

| 输入 | 用途 | 负责人 |
|---|---|---|
| Nuotao Outdoor LLC 美国注册地址 | T3, T4, T6 | 主 |
| Nuotao DPO 邮箱（数据保护官） | T3 | 主 |
| Nuotao 客服邮箱 + 电话号码 | T4, T6 | 主 |
| Product Liability Insurance 保单号 | T6 | 主（或推迟到 M1 前购买） |
| 已注册销售税的州清单 | T5 | 主 |
| 各 SKU 供应商 BOM（材质清单） | T10, T11 | 供应商 |
| GCC 通证 PDF 模板（Word 文件） | T11 | 主 + AI 系统 |
| Complianz 或 Cookie Notice 插件账号 | T7 | 主（如需付费版） |
| 60 SKU 完整列表（含 WC ID） | T9, T10, T11 | 主 |

---

## 4. 执行顺序与依赖

```
Week 1 (M0 Day 1-3) — 前端改造
├─ T1 页脚 Prop 65 警示（0.5h）
├─ T2 产品详情页警示模块（1h）
├─ T6 进口商信息披露页面（1h）
└─ T7 Cookie 同意横幅（1h）

Week 2 (M0 Day 4-7) — 政策页面
├─ T3 隐私政策重建（2h）
├─ T4 服务条款更新（1.5h）
├─ T5 州销售税说明页面（1h）
└─ T8 Affiliate 披露（0.5h）

Week 3 (M0 Day 8-10) — 数据层
├─ T9 电子配件 FCC 声明（2h，需人工填写 6-8 SKU）
├─ T10 60 SKU 材质清单（2h，需供应商 BOM）
└─ T11 GCC 通证库（3h，需 Word 模板）

Total: 15.5h（含 4-6h 需人工准备输入）
```

---

## 5. 验收标准

### 5.1 P0 硬性要求（必须完成）

- [ ] 页脚显示加州 Prop 65 警示（T1）
- [ ] 所有 60 SKU 详情页显示 Prop 65 警示（T2）
- [ ] 隐私政策页面完整（GDPR + CCPA + PIPL）（T3）
- [ ] 服务条款页面完整（GDPR + FTC）（T4）
- [ ] CPSC 进口商信息披露页面（T6）
- [ ] Cookie 同意横幅全站生效（T7）
- [ ] 60 SKU 全部有材质清单（T10）
- [ ] 60 SKU 全部有 GCC 通证（T11）

### 5.2 P1 建议完成

- [ ] 州销售税说明页面（T5）
- [ ] Affiliate Disclosure 页面（T8）
- [ ] 电子配件 FCC 声明（T9）

### 5.3 全站点合规扫描清单

改造完成后，使用以下工具扫描：
- Google Search Console 检查所有新页面是否被收录
- Rank Math SEO 检查 meta description + canonical
- Screaming Frog SEO Spider 检查 404 死链
- Iubenda Site Shield 检查 GDPR 合规

---

## 6. 委派 Codex 执行的说明（供协调 Agent 参考）

**Codex 任务书**（可复制到 Codex CLI 委派）：

```
Objective: 完成 Nuotao Outdoor 独立站（nuotaooutdoor.com）合规改造

Technical Spec: E:\AI\nuotao-ai-os\docs\ecommerce-compliance-redesign-taskbook.md（本文档）

In-Scope Files:
- WooCommerce 主题模板（/wp-content/themes/*/）
- Elementor 全局页脚模板（/wp-content/uploads/elementor/css/globals/）
- Elementor WooCommerce 单品模板
- WordPress 页面：/privacy-policy/, /terms-conditions/, /tax-shipping-policy/, /importer-info/, /affiliate-disclosure/, /compliance-library/
- WooCommerce 自定义字段配置
- Complianz 或 Cookie Notice 插件配置

Out-of-Scope:
- 支付网关（Stripe / PayPal）
- WooCommerce Tax 具体税率配置
- 产品图片/内容重写
- SEO 关键词（由 Rank Math 处理）
- 60 SKU 上架/下架
- 广告投放配置

Test Commands:
- 手动：访问每个新页面，检查 200 状态码 + 内容正确
- 手动：模拟 Googlebot UA 访问，检查爬虫可访问
- 手动：手机端 + 桌面端响应式检查
- 手动：Cookie 未同意时，GA + Facebook Pixel 不应加载
- 手动：60 SKU 逐个检查 Details tab 材质显示

Verify:
- 页脚 Prop 65 警示在桌面端 + 移动端均可见
- 所有 60 SKU 详情页均显示 Prop 65 警示 + 材质
- 隐私政策 + 服务条款 + 州销售税 + 进口商信息 + 联盟披露 5 个页面均可从页脚跳转
- Cookie 同意横幅全站生效
- /compliance-library/ 页面仅管理员可见

Deliverables:
1. 6 个 WordPress 新页面 URL 列表
2. Elementor 模板改动 diff（页脚 + 单品）
3. WooCommerce 自定义字段配置清单
4. 60 SKU 材质 + FCC + GCC 字段填写清单（CSV 格式，供人工核对）
5. 全站合规扫描报告（Screaming Frog 输出）
```

---

## 7. 风险与回滚

| 风险 | 缓解 |
|---|---|
| Elementor 模板改动导致全站样式错乱 | 修改前用 WP All-in-One Backup 备份，改动后逐页检查 |
| WooCommerce 自定义字段破坏现有 API 同步 | 使用独立前缀 `nuotao_` 避免冲突 |
| 隐私政策被 SEO 工具标记为低质量 | 至少 2,000 字英文，覆盖所有关键字段 |
| GCC 通证模板被 CPSC 拒绝 | 咨询合规律师确认模板合规性 |
| Cookie 横幅影响转化率 | 使用最小侵入设计（横幅 60px 高度） |

---

## 8. 参考来源

- CPSC 官方：https://www.cpsc.gov/Business--Manufacturing/Business-Education
- CPSC CPSIA：https://www.cpsc.gov/Regulations-Laws--Standards/Statutes/The-Consumer-Product-Safety-Improvement-Act
- CPSC Sporting and Camping Equipment：https://www.cpsc.gov/FAQ/Sporting-and-Camping-Equipment
- 加州 Prop 65：https://www.P65Warnings.ca.gov
- FTC Affiliate Guidelines：https://www.ftc.gov/business-guidance/advertising-marketing/endorsements
- GDPR 官方：https://gdpr.eu
- CCPA 官方：https://oag.ca.gov/privacy/ccpa
- 项目相关：`docs/cross_border_compliance_knowledge_base.md` §8、`docs/website_p0_p1_fix_plan.md`
- DEC-021（GCC + FCC 分阶段）、DEC-022（Prop 65 通用警示）

---

## 9. 下一步

**主会话（协调 Agent）已交付**：
- ✅ 技术任务书（本文档）
- ✅ 11 项任务详细规格
- ✅ Codex 委派任务书（§6）
- ✅ 需要人工的输入清单（§3）
- ✅ 风险与回滚策略（§7）

**待执行**：
- ⏳ 主（用户）确认技术任务书可执行
- ⏳ 委派 Codex 执行 T1-T11
- ⏳ 人工准备 5-8 项输入（美国地址、DPO 邮箱、供应商 BOM 等）

**委派建议**：
- Codex 可完成 T1, T2, T3, T4, T5, T6, T7, T8, T9, T10, T11 中的模板/字段配置部分
- Codex 无法完成：填写具体数据（如 Nuotao 邮箱、地址）
- 建议在 Codex 执行前先完成人工输入准备
