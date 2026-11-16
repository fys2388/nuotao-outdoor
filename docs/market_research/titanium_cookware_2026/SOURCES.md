# SOURCES.md — 来源清单与数据真实性审计

> 调研日期：2026-10-30｜证据等级：A=政府/法规/官方统计，B=行业权威/独立测试，C=品牌/零售商，D=真实用户/社区，E=第三方/媒体二手
> 铁律：核心事实必须有来源；未证实 = UNKNOWN；禁止为凑完整度而编造

---

## 一、竞品来源（Evidence Level: C-High，品牌官网 Shopify JSON）

| 品牌 | 来源 URL | 证据 |
|------|---------|------|
| TOAKS（12 款） | toaksoutdoor.com/products/{pot-750,pot-1100,pot-1300,pot-650-l,pot-550-l,pot-900-d115,ckw-1100,ckw-1600,cup-450-l,cup-450-dw,cs-11,cs-12} | High - Shopify JSON |
| Vargo（2 款） | vargooutdoors.com/products/{t-466,t-496} | High - Shopify JSON |
| MSR（6 款） | cascadedesigns.com/products/{msr-titan-kettle-900ml,msr-titan-kettle-1400ml,msr-titan-cup-450ml,msr-titan-double-wall-mug,msr-titan-long-spoon,msr-titan-spork} | High - Shopify JSON |

**限制**：Snow Peak（Cloudflare 403）、SOTO、EVERNEW、Keith、SilverAnt、FireMaple、REI、Backcountry、Decathlon、Amazon 均反爬不可达 → Rating/Review Count = UNKNOWN，未编造。

## 二、用户评论来源（Evidence Level: D，真实用户）

| 来源 | 条数 | URL |
|------|-----:|-----|
| Reddit r/Ultralight | 38 | reddit.com/r/Ultralight/search/?q=titanium+pot(+dent/handle/lid)&restrict_sr=1 |
| REI Co-op 用户评论 | 3 | rei.com/product/139459/toaks-titanium-750-ml-pot |
| **实际采集** | **41**（目标≥60，未达，如实报告） | — |

**限制**：Amazon 评论页需登录（/ap/signin）、web_search 402 余额、BackpackingLight/YouTube 反爬 → 实际 41 条，如实报告。

## 三、1688 供应链来源（Evidence Level: B-C，工厂黄页 + wiki）

| 供应商 | 来源 | 证据 |
|--------|------|------|
| 潮州英迪钛业 | wiki.1688.com + 超级工厂徽标 | B - 工厂黄页/超级工厂 |
| 潮州顾家五金 | 1688 factory b2b-2207597689141e4ab3 | B - 工厂黄页（2019成立/11-50人/VR看厂） |
| 揭阳钛帮手 | 1688 factory b2b-2217155227110ee896 | B - 工厂黄页（2023成立/52商品） |
| 揭阳新熹/钛锐晟/部总/鼎欣/钛尚 | 1688 factory b2b-* | B - 工厂黄页 |
| 潮州双子五金 MUTTI | wiki + 超级工厂徽标 | B - 超级工厂（回头率60%） |
| 其余 10 家 | wiki.1688.com + chanpin 快照 | C - 二手引用，需人工复核 |

**限制**：1688 详情页/detail 反爬（JS 渲染）→ MOQ/净重/包装重 = UNKNOWN；认证均为供应商自述，非独立验证。

## 四、材料工程来源（Evidence Level: B-High）

| 来源 | 内容 |
|------|------|
| 美国 Titanium Industries 合金数据手册（87页 PDF） | ASTM/AMS/UNS/EN 化学成分 + 力学/物理性能 |
| Titanium Industries 耐腐蚀技术页 | TiO₂ 钝化膜/耐腐蚀 |
| EFSA / EC 1935/2004 + EU 10/2011 | 食品接触框架 |
| Wikipedia（引用 ASTM/期刊） | 密度 4.502 g/cm³、热导率 21.9 W/(m·K)、E 120 GPa |

## 五、法规来源（Evidence Level: A-High）

| 法规 | 状态 |
|------|------|
| 21 CFR Part 177 | A - 原文已取（聚合物法规，钛不在其中） |
| EC 1935/2004 + 2023/2006 | A - 原文已取（框架 + GMP） |
| SI 2005/1803（GB GPSR） | A - 原文已取（2023/988 不适用于 GB） |
| 加 F-27 + B.23.001 | A - 原文已取 |
| Google Patents（CPC A47J） | B - 4,756 件 |
| FDA FCN / EUR-Lex GPSR / ECHA / USITC / OEHHA / ACCC | C - 待核（用于决策前需补验） |

## 六、经济性来源（Evidence Level: B-C）

| 项目 | 来源 |
|------|------|
| 中国 FOB $15-25 | made-in-china.com（宝鸡钛业） |
| 美国关税 30.5% | tariffs.wove.com（HTS 8108.90.30） |
| 中国→美国空运 $4.50-8.20/kg | King-Hor Supply Chain（2026-04） |
| 欧盟 €3 固定关税/IOSS | 欧盟 DG Trade |
| 汇率 1 USD=0.8959 EUR | exchangerate-api.com（2026-10-30） |

---

## 七、数据真实性审计（任务书第 26 节）

| 统计项 | 数值 |
|--------|-----:|
| Total Factual Claims（核心结论） | ~60 |
| Claims With Sources | ~55 |
| Claims Without Sources（标注 UNKNOWN） | ~5 |
| Official Sources（A 级） | 8（法规原文） |
| Industry Sources（B 级） | 6（材料手册/工厂黄页/Google Patents） |
| Commercial Sources（C 级） | 23（品牌官网 JSON + wiki） |
| Community Sources（D 级） | 41（Reddit/REI 真实用户） |
| Company Reported | 认证/自述（标非独立验证） |
| Third-party Estimates | 敏感性参数（标注 ASSUMPTION） |
| Inference | 材料刚度/热性能工程推导（标注公式） |
| Unknown | MOQ/净重/包装重/复购率/到岸报价/税率/体积重 |

### 必须注意（任务书第 26 节）
- 商品标价（品牌官网）≠ 实际成交价
- 评论数（REI 162条）≠ 销量
- 品牌产品组合（TOAKS 12款）≠ 复购率
- 供应商材料描述 ≠ 独立检测
- 产品页面重量（TOAKS 官网）≠ 包装发货重量（需打样实测）
- 产品有钛材质 ≠ 整个套装都是钛（CAROTE 含钛/钛陶瓷，非纯钛板材）

### 证据覆盖结论
- **核心事实（市场/竞品/供应链/法规）均有来源**（A/B/C/D 级）
- **复购率、到岸报价、实际税率、体积重 = UNKNOWN**（无真实订单/报价数据，不得编造）
- 敏感性格局（Conservative/Base/Optimistic）为**假设**，非真实业绩
