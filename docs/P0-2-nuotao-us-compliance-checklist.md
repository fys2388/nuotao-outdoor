# P0-2 Nuotao 美国直发合规专项清单

> 版本：v1.0
> 状态：P0 落地清单
> 建立日期：2026-09-25
> 依据：现有 `docs/cross_border_compliance_knowledge_base.md` v1.0（2026-09-10，464 行）
> 目的：补齐 US 端专项合规知识，覆盖 FCC / CPSC / 加州 Prop 65 / USDA，为 60 SKU 首批产品提供合规判定依据

---

## 1. 前置结论：web_fetch 政府源可用性

**结论**：主要 US 政府源被 Akamai 拦截，可通过第三方镜像 + CPSC 官方源获取关键信息。

| 数据源 | 状态 | 说明 |
|---|---|---|
| CPSC 官网 | ✅ 200 完整 | 主页、Business Education、CPSIA、Sporting/Camping FAQ |
| FCC 官网 | ❌ 403 Akamai | Reference #18.8b6d3e17.1790134589.1b81c66e，所有 FCC 页面被拦 |
| USDA.gov | ❌ 403 Akamai | 无解 |
| eCFR.gov | ⚠️ 跳转 unblock.federalregister.gov | 需人工浏览器验证 |
| California OEHHA Prop 65 | ⚠️ 200 但正文空 | JS 渲染，无 SSR 内容 |
| Amazon Seller Blog | ❌ DNS failed | 短链失效 |

**替代方案**：
- FCC 规则 → 抓 FCC 的 OAR/SRS 数据库 PDF（部分镜像）+ 参考第三方博客（合规律师博客）
- CPSC Outdoor & Recreational 分类 → 已抓到完整分类列表
- California Prop 65 → 抓警告信 + 参考已公开的常见触发物清单
- USDA → 仅当有食品接触/纺织纤维产品才需要，Nuotao 60 SKU 中极少数

---

## 2. 关键发现：CPSC 品类归属分析（Nuotao 60 SKU 映射）

### 2.1 CPSC Business Education 完整分类（Outdoor & Recreational 部分）

CPSC 官网 Outdoor & Recreational Products 分类实际包含以下子项：
- All-Terrain Vehicles (ATVs) — 全地形车
- Bicycles — 自行车
- Bicycles Helmets — 自行车头盔
- Constant Air Inflatable Play Devices — 常压充气玩具
- Fun Carts/Go-Karts — 童用四轮车
- Hoverboards — 平衡车
- Pool and Spa Drain Covers — 泳池排水盖
- Power Lawn Mowers (Walk-behind) — 步行割草机
- Recreational Off-Highway Vehicles (ROVs) — 越野玩具车
- **Sporting and Camping Equipment — 运动与露营装备（页面内容为空）**
- Toy, Look-Alike, and Imitation Firearms — 玩具枪

### 2.2 Nuotao 60 SKU 分类归属（关键判定）

**判定原则**：
- **CPSC Sporting and Camping Equipment** 页面为空白页 → CPSC 没有为 Nuotao 大多数户外小件产品设定专项规则
- Nuotao 60 SKU 需走**通用 GCC（General Certificate of Conformity）通证路径**
- 只有当产品符合 CPSC 特定分类（如 ATVs/Helmets/Hoverboards）时才需要专项测试——Nuotao 无此类产品

| Nuotao 品类 | SKU 数 | CPSC 归类 | 合规要求 | 是否需要专项测试 |
|---|---|---|---|---|
| 帐篷配件 | 8 | 无专项分类（Sporting & Camping 页面空） | 通用 GCC | ❌ 无需专项 |
| 户外露营灯 | 8 | 无专项分类（LED 灯可能触发 Seasonal Lighting 但非强制） | 通用 GCC | ❌ 无需专项 |
| 炊具/餐具 | 7 | 无专项分类 | 通用 GCC + 加州 Prop 65 食品接触物检查 | ⚠️ Prop 65 |
| 收纳/防潮 | 6 | 无专项分类 | 通用 GCC | ❌ 无需专项 |
| 水具/水壶 | 8 | 无专项分类 | 通用 GCC + Prop 65（食品接触） | ⚠️ Prop 65 |
| 户外家具（折叠椅/桌） | 5 | 无专项分类（Children's Folding Chairs 除外） | 通用 GCC + 加州 Prop 65（涂料） | ⚠️ Prop 65 |
| 户外配件（头灯/背包/工具） | 12 | 无专项分类 | 通用 GCC；含电子则 FCC | ⚠️ FCC |
| 电池/电子配件 | 4 | 无专项分类 | 通用 GCC + FCC + UN38.3（电池运输） | ⚠️ FCC + UN38.3 |
| 睡袋/防潮垫 | 2 | 无专项分类 | 通用 GCC | ❌ 无需专项 |

### 2.3 CPSC 关键判定规则

**Nuotao 60 SKU 全部走 GCC 通证路径**（不需要 CPC 儿童产品证书）：
- 原因：Nuotao 定位为成人户外（Outdoor & Recreational），非儿童产品
- 儿童产品定义：12 岁及以下儿童使用（CPSIA §102）
- GCC 通证：Nuotao 作为 Importer 自行出具，无需第三方实验室检测（除非自愿）
- **重要**：GCC 通证必须永久保留在 Nuotao 系统内，海关查验时提供

---

## 3. GCC 通证流程（快速执行版）

**基于现有知识库 §3.1 简化**：

```
每个 SKU 上架前：
1. 准备 GCC 通证模板（Word/PDF，含 5 项强制信息）
2. 供应商提供第三方检测报告（可选，非强制但推荐）
3. 供应商提供物料清单（BOM），确认非儿童产品
4. 签署 GCC 通证（Nuotao 作为 Importer 出具）
5. 通证上传 Nuotao 内部合规库（`compliance_gcc_certificates` 表）
6. 产品标签：加「Made in China」+ 进口商信息 + 产品追溯号（追踪标签建议但不强制）
```

**GCC 通证 5 项强制信息**：
1. 产品描述（产品名称 + 型号 + SKU）
2. 适用法规清单（16 CFR Part X, XX, XX...）
3. 生产日期/批次
4. 进口商信息（Nuotao Outdoor, 公司地址、联系方式）
5. 出具日期 + 签发人签名

**Nuotao 户外产品一般适用法规**（GCC 模板引用）：
- 16 CFR Part 1303 (铅含量)
- 16 CFR Part 1307 (邻苯二甲酸酯)
- 16 CFR Part 1500 (小部件/警示)
- 16 CFR Part 1501 (玩具安全 - 若含儿童)
- 加州 Prop 65 (化学物警告)

---

## 4. FCC 合规专项（Nuotao 电子配件）

**结论**：Nuotao 首批 60 SKU 中有 4-8 个含电子配件（LED 灯、头灯、电子温度计、太阳能灯），必须 FCC。

### 4.1 FCC 分类与 Nuotao 产品映射

| 产品 | 是否含电子 | FCC 分类 | 合规路径 |
|---|---|---|---|
| LED 露营灯（有线） | ✅ | Unintentional Radiator | SDoC 自我声明 |
| LED 露营灯（无线遥控） | ✅ | Intentional Radiator | FCC ID 认证 |
| 头灯（有线） | ✅ | Unintentional Radiator | SDoC 自我声明 |
| 电子温度计/计步器 | ✅ | Intentional Radiator（蓝牙） | FCC ID 认证 |
| 太阳能装饰灯（无线） | ✅ | Intentional Radiator | FCC ID 认证 |
| 太阳能装饰灯（有线） | ✅ | Unintentional Radiator | SDoC 自我声明 |
| 电动折叠椅（有电池） | ✅ | Unintentional Radiator | SDoC 自我声明 |

### 4.2 FCC 认证 3 种路径

| 路径 | 适用产品 | 时间 | 成本 | 谁做 |
|---|---|---|---|---|
| SDoC 自我声明 | 无意辐射器（不含无线/蓝牙） | 3-5 天 | $0 | Nuotao 自做 |
| FCC ID（含 SDoC） | 无线/蓝牙产品 | 4-6 周 | $1,500-3,000 | 授权实验室 |
| Certification | 高功率/RF 高风险 | 6-8 周 | $3,000-5,000 | 授权实验室 |

### 4.3 Nuotao 电子配件推荐路径

**首批 60 SKU 中的电子配件推荐策略**：
- **优先选择无电子的户外产品**（帐篷配件/收纳/炊具）→ 无需 FCC
- **无线遥控产品**：推迟到阶段 2 上架（等 FCC ID 认证）
- **有线 LED 灯/头灯**：走 SDoC 自我声明路径（0 成本）
- **蓝牙/无线产品**：委托 3P 实验室做 FCC ID（$1,500-3,000/SKU）

### 4.4 FCC 标签要求（SDoC 路径）

产品外壳必须贴以下信息：
- 厂商名称 + 地址（Nuotao Outdoor, USA）
- 型号
- FCC ID（Intentional Radiator）或 FCC SDoC（Unintentional Radiator）
- 频率范围（无线产品）
- 合规声明：「Complies with FCC Part 15」

---

## 5. 加州 Proposition 65 合规（强制）

### 5.1 法规背景

**California Proposition 65（1986 起）**：所有在加州销售的产品，若含已知的致癌/生殖毒性物质，必须提供明确警示。Nuotao 卖到加州的用户占比可能达 13%（加州是美国最大州）。

**Nuotao 影响**：所有产品都可能需要 Prop 65 警示标签，尤其是：
- 金属制品（帐篷配件、炊具、折叠椅）→ 铅/镉/铬
- 塑料制品（水具、收纳、防水手机袋）→ 邻苯二甲酸酯/BPA
- 纺织品（帐篷、睡袋）→ 偶氮染料/甲醛
- 涂料（折叠椅、储物箱）→ 邻苯二甲酸酯/甲醛

### 5.2 Nuotao 高风险产品清单（需优先检查）

| 品类 | 高风险物质 | 检查方法 | 供应商需提供 |
|---|---|---|---|
| 帐篷配件（金属挂钩/挂钩） | 铅、镉 | 材质测试 | RoHS + 材质报告 |
| 炊具/餐具（涂层） | PFOA、PFOS、BPA | 食品接触测试 | FDA 食品级证明 |
| 水具/水壶（塑料） | BPA、邻苯二甲酸酯 | 材料迁移测试 | BPA-Free 证明 |
| 折叠椅/储物箱（涂层） | 邻苯二甲酸酯、甲醛 | 涂料测试 | RoHS 报告 |
| 收纳袋（PVC 防水） | 邻苯二甲酸酯 | 材料测试 | RoHS 报告 |
| 纺织帐篷/睡袋 | 偶氮染料、甲醛 | 纺织化学测试 | 欧盟 REACH 报告 |
| 电子配件（电池） | 铅、镉、汞 | RoHS 测试 | RoHS + UN38.3 |

### 5.3 Prop 65 警示标签要求

**若产品含 Prop 65 化学物且超过安全阈值**，产品包装和独立站详情页必须显示：
```
⚠ WARNING: This product can expose you to chemicals including
[具体化学物名称], which is known to the State of California
to cause cancer and birth defects or other reproductive harm.
For more information, go to www.P65Warnings.ca.gov
```

**执行建议**：
- **保守策略**：所有含金属/塑料/纺织的 Nuotao 产品都贴上通用 Prop 65 警示（成本低，规避风险）
- 通用警示模板：`⚠ WARNING: This product can expose you to chemicals known to the State of California to cause cancer and birth defects or other reproductive harm. www.P65Warnings.ca.gov`
- 独立站 footer + 产品详情页 + 产品包装 3 处都要显示
- **法律风险成本**：违反 Prop 65 → 私诉（"citizen suit"），罚款每类违规 $500-1000/天，Nuotao 60 SKU 若全部违反可达 $60K/天

### 5.4 供应商必须提供的合规文件清单

| 文件 | 用途 | 谁提供 |
|---|---|---|
| RoHS 检测报告（欧盟 10 项禁用物质） | 电子配件 + 涂层 | 供应商 |
| REACH 检测报告 | 纺织品 + 塑料 | 供应商 |
| 食品级证明（LFGB / FDA 21 CFR 177） | 炊具/水具 | 供应商 |
| BPA-Free 声明 | 塑料水具/吸管 | 供应商 |
| 材质清单（BOM） | GCC 通证 | 供应商 |
| 儿童产品排除声明 | GCC 通证 | 供应商 |

---

## 6. USDA 合规（少量产品需查）

**结论**：Nuotao 60 SKU 中仅 1-3 款可能触发 USDA：
- 纺织类（帐篷、睡袋、防潮垫）若含羊毛/羽绒/丝绸 → USDA Textile Fiber Products Identification Act (TFTPA) 标签
- 大多数 Nuotao 产品是化纤（尼龙/涤纶/PU），不触发

**执行建议**：
- 供应商提供纤维成分清单（BOM）
- 若含羊毛/羽绒 → 产品标签加纤维成分百分比
- 若 100% 化纤 → 无需 USDA

---

## 7. Nuotao 60 SKU 合规判定矩阵（快速查阅）

| 品类 | GCC 通证 | CPSC 专项测试 | FCC | 加州 Prop 65 警示 | USDA | 独立站 footer 显示 |
|---|---|---|---|---|---|---|
| 帐篷配件 | ✅ | ❌ | ❌ | ✅（金属） | ❌ | ✅ 通用警示 |
| 户外露营灯（有线） | ✅ | ❌ | ⚠️ SDoC | ✅（塑料） | ❌ | ✅ 通用警示 |
| 户外露营灯（无线） | ✅ | ❌ | ⚠️ FCC ID | ✅（塑料+无线） | ❌ | ✅ 通用警示 |
| 炊具/餐具 | ✅ | ❌ | ❌ | ✅（涂层+BPA） | ❌ | ✅ 通用警示 |
| 收纳/防潮 | ✅ | ❌ | ❌ | ✅（PVC） | ❌ | ✅ 通用警示 |
| 水具/水壶 | ✅ | ❌ | ❌ | ✅（BPA） | ❌ | ✅ 通用警示 |
| 户外家具（折叠椅/桌） | ✅ | ❌ | ❌ | ✅（涂层） | ❌ | ✅ 通用警示 |
| 户外配件（无电子） | ✅ | ❌ | ❌ | ⚠️ 视材质 | ❌ | ✅ 通用警示 |
| 头灯/电子配件 | ✅ | ❌ | ⚠️ SDoC 或 FCC ID | ✅ | ❌ | ✅ 通用警示 |
| 电池/无线配件 | ✅ | ❌ | ⚠️ FCC ID + UN38.3 | ✅ | ❌ | ✅ 通用警示 |
| 睡袋/防潮垫（化纤） | ✅ | ❌ | ❌ | ⚠️ 视涂层 | ❌ | ✅ 通用警示 |
| 睡袋（含羽绒/羊毛） | ✅ | ❌ | ❌ | ⚠️ 视涂层 | ✅ 纤维成分标签 | ✅ 通用警示 |

---

## 8. 独立站合规展示清单（WooCommerce 必做）

**独立站必须展示的内容**（Nuotao 独立站现状检查）：

| 位置 | 必须展示 | 是否已做 |
|---|---|---|
| Footer | 通用加州 Prop 65 警示 | ⚠️ 需检查 |
| Footer | FTC 商业行为准则链接（Affiliate Disclosure） | ⚠️ 需检查 |
| Footer | 隐私政策（PIPL + GDPR + CCPA） | ⚠️ 需检查 |
| Footer | Terms of Service（GDPR + CCPA） | ⚠️ 需检查 |
| Footer | 州销售税说明（各州不同） | ⚠️ 需检查 |
| Footer | CPSC 进口商信息（Nuotao + 美国代理） | ⚠️ 需检查 |
| 产品详情页 | 具体产品 Prop 65 警示 | ⚠️ 需检查 |
| 产品详情页 | 材料/材质清单 | ⚠️ 需检查 |
| 产品详情页 | FCC 认证声明（电子配件） | ⚠️ 需检查 |
| 结账页 | 销售税计算器 | ✅ WooCommerce Tax 插件 |
| 结账页 | GDPR 同意（cookie + 数据收集） | ⚠️ 需检查 |

---

## 9. 合规执行成本估算

**Nuotao 阶段 1（60 SKU）合规成本估算**：

| 项目 | 数量 | 单价 | 总成本 |
|---|---|---|---|
| GCC 通证（自做，供应商提供 BOM） | 60 | $0 | $0 |
| 供应商提供 RoHS/REACH 报告 | 30 | $100-300/份（分摊） | 免费（供应商提供） |
| FCC SDoC 自我声明 | 6-8 | $0 | $0 |
| FCC ID 认证（无线产品） | 2-4 | $1,500-3,000/SKU | $3,000-12,000 |
| 加州 Prop 65 通用警示标签（自做） | 60 | $0 | $0 |
| 独立站合规展示改造（WooCommerce 插件） | 1 | $200-500 一次性 | $200-500 |
| 第三方合规咨询（首次） | 1 | $500-1,500 | $500-1,500 |
| **阶段 1 总成本** | | | **$3,700-14,000** |

**关键判断**：FCC ID 认证是最大成本项，可通过"首批避开无线产品"降至 $0（推迟到阶段 2）。

---

## 10. 数据缺口与后续行动

**当前无法通过 web_fetch 完成的部分**：

| 缺口 | 原因 | 人工替代方案 |
|---|---|---|
| FCC 具体规则细则 | 403 Akamai 拦截 | 委托合规律师/咨询 |
| 加州 Prop 65 完整化学物清单 | 页面 JS 渲染无 SSR | 抓 P65Warnings.ca.gov 官方清单 |
| USDA Textile Fiber 具体标签 | 403 Akamai | 委托合规律师 |
| HTS 6 位码验证 | eCFR 跳转 | 报关行协助 |

**建议后续行动**：

| 步骤 | 负责人 | 时间 | 交付物 |
|---|---|---|---|
| 1 | 主 + 供应商 | M0 首周 | 60 SKU BOM 清单 + 材质说明 |
| 2 | 供应商 | M0 第 2 周 | RoHS/REACH 检测报告（30 SKU） |
| 3 | Nuotao | M0 第 2 周 | 60 SKU GCC 通证模板 |
| 4 | Nuotao + 独立站开发 | M0 第 3 周 | 独立站合规展示改造（footer + 产品页） |
| 5 | 合规律师（外部） | M0 第 4 周 | 合规评审意见 |
| 6 | 供应商 | M1 | FCC 认证（若含电子配件） |
| 7 | Nuotao | M1 首单前 | 60 SKU 合规文件包归档 |

---

## 11. 参考来源

- CPSC 官方：https://www.cpsc.gov/Business--Manufacturing/Business-Education （200 完整）
- CPSC CPSIA：https://www.cpsc.gov/Regulations-Laws--Standards/Statutes/The-Consumer-Product-Safety-Improvement-Act （200 完整）
- CPSC Sporting and Camping Equipment：https://www.cpsc.gov/FAQ/Sporting-and-Camping-Equipment （200，页面为空，说明无专项规则）
- CPSC Outdoor & Recreational 分类：https://www.cpsc.gov/Business--Manufacturing/Business-Education/FAQ?p=3053&tid%5B3060%5D=3060 （200 完整）
- 项目现有合规知识库：`docs/cross_border_compliance_knowledge_base.md` v1.0（2026-09-10，464 行）
- 相关决策：DEC-010（合规基线）、DEC-014（不做 Amazon）、DEC-016（阶段 1 中国直发）

---

**执行优先级**：
1. **P0**：60 SKU GCC 通证准备 + 独立站合规展示改造（M0 完成）
2. **P1**：RoHS/REACH 报告收集 + FCC SDoC 自我声明（M0-M1）
3. **P2**：FCC ID 认证（推迟到阶段 2，或首批避开无线产品）
