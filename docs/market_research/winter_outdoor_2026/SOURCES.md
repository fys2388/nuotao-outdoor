# SOURCES.md — 来源清单与数据真实性审计

> 调研日期：2026-10-31｜证据等级：A=政府/官方，B=行业权威/独立测试，C=品牌/零售商，D=真实用户/社区，E=第三方二手
> 铁律：核心事实必须有来源；未证实 = UNKNOWN；禁止为凑完整度编造

---

## 一、品类地图来源（Evidence Level: C，40 品类）

| 来源 | 证据 |
|------|------|
| Kahtoola / NEMO / Outdoor Research / Sea to Summit / CascadeDesigns(MSR/Therm-a-Rest) / Snow Peak / GEAR AID / Zpacks 品牌页 | L1（真实价格直读） |
| Walmart / Target / Lowe's 价格摘要（DuckDuckGo HTML 快照） | L1（BAGSMART $29.99 / Kahtoola $83.95 / ABORON $69.99） |
| REI / Amazon / Backcountry / GearJunkie / SwitchbackTravel / SectionHiker | 反爬 403，未纳入（如实报告） |

**限制**：REI/Amazon 反爬；12 品类 L1、21 品类 L2（品类确认+行业公认价格带）、7 品类 L3（估算）。

## 二、季节性来源（Evidence Level: A-B）

| 来源 | 内容 |
|------|------|
| NOAA/NCEI + Wikipedia Meteorological reckoning（引 NOAA/Met Office/BOM） | 北半球 Dec-Feb、南半球 Jun-Aug |
| NOAA CPC（NDJ/DJF 2026-27 发布窗口） | 2026/27 冬季正在启动 |
| OIA ConsumerVue/Reports Library（live + Wayback） | 零售季节奏 |
| Retail Dive 2026-10 假日报道 | 黑五→圣诞高峰 |
| 澳洲/新西兰官方 6/1-8/31 | 南半球官方定义 |
| Google Trends API / SIA | 429 限流/反爬，未直接取数 |

## 三、竞品来源（Evidence Level: C-High，820 行）

winter_competitor_research.json（Walmart 商品页评分 + Sea to Summit/Smartwool/Big Agnes 服务端评分 + GEAR AID/Vargo/Snow Peak 部分 UNKNOWN）。

## 四、用户痛点来源（Evidence Level: D，36 条真实）

| 来源 | 条数 |
|------|-----:|
| Reddit（r/CampingGear, r/Ultralight, r/camping, r/CampingandHiking, r/backpacking, r/BuyItForLife, r/WildernessBackpacking, r/sewing, r/Frugal, r/laundry, r/rooftoptents, r/WorkBoots, r/photography, r/flashlight, r/AskReddit） | 27 |
| BackpackingLight 论坛 | 4 |
| 其它户外论坛（Mountain Project/StackExchange/BushcraftUK/4WDTalk） | 4 |
| 户外博客评论（pineconeattack） | 1 |
| **实际采集** | **36**（≥30 达成） |

**限制**：Amazon 低星评论需登录；web_search 402；1-3 星评分条目 0（论坛为主，如实报告）。

## 五、1688 供应链来源（Evidence Level: B-C，20+ 家）

| 供应商 | 来源 | 证据 |
|--------|------|------|
| 金华品世/义乌宇宏/慕野/本策/圣薇/德通厚源 | 1688 wiki 商品卡 | B-C（五星/超级工厂徽标） |
| 浙江含光/中山普毅/巨基/辰石/杭州鑫耀/易哲 YIZHE/博蓝/森悦 | 1688 wiki + 搜索快照 | B-C（超级工厂/实力商家） |
| 平阳芝帅/合肥丛林部落/东莞三美/宁波金狐/深圳曼巴/福建三梵 | 1688 搜索快照 | C（工厂，无 offer_id） |

**限制**：1688 详情页反爬 → MOQ/净重/包装重/尺寸 = UNKNOWN（需后台询盘）；认证均为自述非独立。

## 六、经济性来源（Evidence Level: A-B）

| 来源 | 内容 |
|------|------|
| Federal Register API | de minimis 时间线、Sec301、IEEPA（2026-02 法院推翻） |
| 项目 us-outdoor-market-research-2026.md | 真实 DDP 报价（云途/燕文）、关税表 |
| EU DG Trade | ≤€150 €3 固定关税 + IOSS |
| 钛炊具多国到岸成本模型 | 交叉验证 |
| exchangerate-api.com | 汇率 |

**限制**：UK/CA/AU 无真实物流报价 → SHIPPING_COST_UNKNOWN；IOSS 示例号 IM1234567890 需真实注册。

## 七、法规来源（Evidence Level: A）

21 CFR（美国）、EC 1935/2004 + GPSR 2023/988 + REACH + PPE 2016/425（欧盟）、SI 2005/1803（英国）、CCPSA（加拿大）、ACL/ACIC（澳大利亚）、UN3481（锂电）、ANSI/ISEA 107（高可见）。

## 八、数据真实性审计（任务书第 20 节）

| 统计项 | 数值 |
|--------|-----:|
| Total Factual Claims | ~140 |
| Claims With Sources | ~125 |
| Claims Without Sources（标 UNKNOWN） | ~15 |
| Official Sources（A 级） | 12 |
| Industry Sources（B 级） | 8 |
| Commercial Product Sources（C 级） | 40（品类）+ 31（竞品 CSV） |
| Community Sources（D 级） | 36（痛点） |
| Third-party Estimates | 敏感性参数（标 ASSUMPTION） |
| Company Reported | 供应商认证/自述（非独立） |
| Inference | 消费者场景推断（Casual/Snow-Mountain 标 INFERENCE） |
| Unknown | CA/AU 物流、计费重、IOSS/VAT 注册、复购率、低温测试 |

### 必须注意（任务书第 20 节）
- 竞品价格 ≠ 销量；评论数 ≠ 市场占有率
- 产品会磨损 ≠ 客户会重复购买（有配件 ≠ 高复购）
- 产品可发货 ≠ 跨境成本可接受（CA/AU 无报价）
- 供应商自述材质 ≠ 独立检测；产品净重 ≠ 实际发货重量（含包装需打样实测）
- 预计利润 ≠ 真实经营利润（UK/CA/AU 估算）
- 产品需求 ≠ Nuotao 一定能获得订单

### 证据覆盖结论
- 核心事实（品类/季节/竞品/痛点/供应链/法规/经济性 US-EU-UK）均有来源
- **复购率、CA/AU 真实物流报价、计费重、IOSS/VAT 注册、低温测试 = UNKNOWN**（无真实数据，不得编造）
- 敏感性格局（Conservative/Base/Optimistic）为**假设**，非真实业绩
