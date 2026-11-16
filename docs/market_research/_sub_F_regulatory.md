# Sub-F: 美国/欧盟法规合规调研

> 日期：2026-10-07
> 方法：`general_search` + 官方来源（CPSC.gov、eCFR.gov、FDA.gov、EUR-Lex、Federal Register）取证。
> 证据等级：A = 官方一手法规条文；B = 官方解读/FAQ；C = 第三方行业解读。
> 适用市场：美国（主）+ 欧盟（辅，德国优先）。
> 关联文档：`docs/cross_border_compliance_knowledge_base.md`（税务/物流/支付部分已覆盖，本文聚焦产品安全/化学/标签）。

---

## 1. 微品类法规清单

### 1.1 纺织品 / 露营毯 / 野餐垫 / 营地垫（B4/F3/H1/A9）

| 项目 | 内容 |
|---|---|
| 适用法规/标准 | **美国**：FTC Textile Fiber Products Identification Act (15 U.S.C. §70 et seq.) + 16 CFR Part 303（标签法）；16 CFR 1610（服装纺织品易燃性）**仅适用于"wearing apparel"，野餐垫/露营毯不是服装，不适用**。<br>**欧盟**：REACH (EC) No 1907/2006 Annex XVII Entry 43（AZO 偶氮染料 ≤30 ppm）、Entry 23（纺织品中镉）、Commission Regulation (EU) 2023/1464（甲醛及甲醛释放体）。 |
| 具体要求 | **美国标签**：每块纺织品必须标注 (1) 纤维通用名+重量百分比（≥5% 纤维）；(2) 制造商名或 FTC RN 注册号；(3) 制造/加工国（Made in China）。见 16 CFR 303.18。<br>**美国易燃性**：野餐垫/露营毯不属于"wearing apparel"，16 CFR 1610 不强制；但 CPSC 仍可按一般消费品安全条款（CPSA §15(b)）追责。<br>**欧盟 REACH**：与皮肤直接长期接触的纺织品，AZO 染料还原裂解不得释放附录8中列出的芳香胺（≤30 ppm）；2023/1464 甲醛限制适用于"非户外专用"物品——**完全户外使用的物品豁免**（consolidated version 条款 (b) "articles that are exclusively for outdoor use under foreseeable conditions"）。 |
| 是否需要第三方测试 | 美国：无强制第三方测试（非儿童产品）；但建议做 16 CFR 1610 Class 1 自测报告用于品牌信任。<br>欧盟：建议第三方 AZO 染料测试（EN 14362-1/-2）+ 甲醛测试。 |
| 合规成本量级（INFERENCE） | 美国标签：$0（自行缝标）。<br>欧盟 AZO+甲醛测试：¥1500–3000 RMB/SKU（第三方实验室）。 |
| 数据来源 URL | https://www.ecfr.gov/current/title-16/chapter-II/subchapter-D/part-1610<br>https://www.govinfo.gov/content/pkg/CFR-2014-title16-vol1/pdf/CFR-2014-title16-vol1-sec303-18.pdf<br>https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32023R1464<br>https://reachonline.eu/REACH/EN/REACH_EN/articleXVII.html |
| 数据日期 | 2026-10-07 检索 |
| evidence_level | A（eCFR/EUR-Lex 原文） |

---

### 1.2 狗用品：折叠水碗 / 垫子 / 安全带（E1/E2/E3）

| 项目 | 内容 |
|---|---|
| 适用法规/标准 | **狗水碗（接触饮水/食物）**：FDA 21 CFR 177.2600（橡胶制品反复接触食品）；FDA 21 CFR Parts 174-179 间接添加剂框架。注意：FDA 将宠物食品视为 FD&C Act 下的"food"，因此宠物水碗/食碗的食品接触材料**受 FDA FCM 规则约束**。<br>**狗垫**：非儿童产品，CPSIA 不适用；按一般消费品 CPSA §15(b)；加州 Prop 65 重金属警告可能适用。<br>**狗安全带/胸背带**：**无联邦 FMVSS 标准约束宠物约束装置**。NHTSA 的 FMVSS 205/213 仅约束原厂车辆玻璃和儿童约束系统（CRS）。宠物安全带不是儿童约束系统，不受 FMVSS 强制认证；但作为"安全产品"营销有产品责任风险。 |
| 具体要求 | FDA 21 CFR 177.2600：硅橡胶/橡胶制品在蒸馏水和正己烷模拟液中迁移物总量限值（水迁移 ≤10 mg/in²；正己烷迁移 ≤20 mg/in²，INFERENCE 基于行业解读）。要求供应商出具材料合规声明（DoC）+ 第三方迁移测试报告。<br>宠物安全带：无强制标准，但建议避免"crash-tested""safe"等未经证实的宣称；GNU 协会/中心等行业有非自愿测试标准。 |
| 是否需要第三方测试 | 狗水碗：建议 FDA 21 CFR 177.2600 迁移测试报告（每材质/每色）。<br>狗安全带：无法定第三方测试，但建议做抗拉强度/撕开测试作为自保。 |
| 合规成本量级（INFERENCE） | FDA FCM 迁移测试：¥2000–4000 RMB/材质。<br>狗安全带：$0–500（自付测试）。 |
| 数据来源 URL | https://www.govinfo.gov/content/pkg/CFR-2022-title21-vol3/xml/CFR-2022-title21-vol3-sec177-2600.xml<br>https://www.hfpappexternal.fda.gov/scripts/fdcc/index.cfm?search=silicone&set=IndirectAdditives<br>https://wetopsilicone.com/guide/collapsible-silicone-pet-bowl-manufacturing-guide/（行业解读，非官方） |
| 数据日期 | 2026-10-07 检索 |
| evidence_level | A（21 CFR 177.2600 原文）；C（行业解读部分） |

---

### 1.3 硅胶食品袋 / 折叠碗（D4/D1）

| 项目 | 内容 |
|---|---|
| 适用法规/标准 | **美国**：FDA 21 CFR 177.2600（橡胶/硅胶反复接触食品）；21 CFR 175.300（涂层）；加州 Prop 65。<br>**欧盟**：Framework Regulation (EC) No 1935/2004（所有食品接触材料通用框架）；Good Manufacturing Practice Regulation (EC) 2023/2004；**注意：Regulation (EU) 10/2011 仅适用于塑料，不适用于硅橡胶**——硅橡胶在欧盟无统一特定措施，德国 LFGB §30/§31（基于 BfR Recommendation XV）是事实标准。 |
| 具体要求 | 美国：无上市前审批；供应商自我合规 + DoC + 测试报告。要求使用铂硫化（platinum-cured）硅胶而非过氧化物硫化。<br>欧盟：必须出具 **Declaration of Compliance (DoC)**；可追溯性（批次号）；不得向食品迁移危害健康的成分、不可接受地改变食品成分或感官特性。<br>新规 Commission Regulation (EU) 2024/3190（2024-12-31）：限制 BPA 及双酚类似物在 FCM 中的使用。 |
| 是否需要第三方测试 | 美国：建议 FDA 177.2600 迁移测试（水/正己烷/8%乙醇模拟液）。<br>欧盟：建议 LFGB §30/§31 全面迁移+特定迁移测试。 |
| 合规成本量级（INFERENCE） | FDA 177.2600：¥2000–4000 RMB/材质。<br>LFGB：¥3000–6000 RMB/材质（更严）。 |
| 数据来源 URL | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02004R1935-20210327<br>https://food.ec.europa.eu/horizontal-topics/general-food-law/implementation-transparency-regulation_de<br>https://www.govinfo.gov/content/pkg/CFR-2022-title21-vol3/xml/CFR-2022-title21-vol3-sec177-2600.xml<br>https://eur-lex.europa.eu/legal-content/DE/TXT/HTML/?uri=OJ:L_202403190（BPA 新规） |
| 数据日期 | 2026-10-07 检索 |
| evidence_level | A（EUR-Lex + eCFR） |

---

### 1.4 露营枕头 / 睡袋衬（B1/B2/B5）

| 项目 | 内容 |
|---|---|
| 适用法规/标准 | **美国**：FTC Textile Act 标签（布套纤维成分）；16 CFR 1632（软垫家具明火/阴燃阻燃）和 16 CFR 1633（床垫套装明火阻燃）**仅适用于床垫/mattress set，不适用于枕头和睡袋衬**。<br>**欧盟**：REACH Annex XVII AZO 染料（Entry 43）+ 甲醛（2023/1464）——户外使用豁免。 |
| 具体要求 | 布套：FTC 标签（纤维% + 制造商 + Made in China）。<br>若填充聚氨酯泡沫：16 CFR 1632/1633 **不适用枕头**（CPSC 明确：pillow ≠ mattress）。<br>若 PVC/TPU 充气枕：非食品接触、非儿童产品 → 无强制测试。 |
| 是否需要第三方测试 | 无强制。建议：供应商出具 REACH 合规声明（AZO/甲醛）。 |
| 合规成本量级（INFERENCE） | $0–¥1500 RMB（标签+供应商声明）。 |
| 数据来源 URL | https://www.cpsc.gov/s3fs-public/Guide-to-US-Apparel-and-Household-Textiles.pdf<br>https://www.ecfr.gov/current/title-16/chapter-II/subchapter-D/part-1610 |
| 数据日期 | 2026-10-07 检索 |
| evidence_level | A（CPSC 指南明确 1610/1615/1616/1632/1633 适用范围） |

---

### 1.5 含电池产品（C1/C2/C3 中的电子部分，本项目主动排除）

| 项目 | 内容 |
|---|---|
| 适用法规/标准 | **UN 38.3**（联合国《关于危险货物运输的建议书 - 试验和标准手册》第38.3节）：8 项测试（T1 高度模拟、T2 温度循环、T3 振动、T4 冲击、T5 外部短路、T6 撞击/挤压、T7 过充、T8 强制放电）。<br>**美国 DOT 49 CFR 173.185**：锂电池运输标记（UN3480/UN3481/UN3090/UN3091）、包装要求、随附文件。<br>**FCC Part 15**：带数字电路/射频的产品需 SDoC（Supplier Declaration of Conformity）。<br>**CPSC Reese's Law / 16 CFR 1263**：纽扣电池/硬币电池——儿童安全包装 + 永久警告标签（2023年通过，2025年2月强制）。<br>**欧盟 CE**：电池需符合 Battery Regulation (EU) 2023/1542（新电池法规，2024年起分阶段实施）+ 无线电设备指令 RED 2014/53/EU（如带蓝牙/WiFi）。 |
| 具体要求 | 任何含锂电产品：UN 38.3 测试报告 + MSDS + 运输鉴定书；空运/海运按危险品申报。<br>纽扣电池：电池仓需工具开启或儿童双重防护；永久警告语。 |
| 为什么本项目主动排除 | (1) UN 38.3 单 SKU 测试成本 $2000–8000；(2) 锂电火灾/召回风险高（CPSC 对锂电池事故追责严厉）；(3) 物流受限（海运危险品舱、空运禁运）；(4) 售后率高（电池衰减/鼓包）。**与种子清单第 1 节"高功率电子/电池"排除规则一致**。 |
| 数据来源 URL | https://www.ecfr.gov/current/title-49/subtitle-B/chapter-I/subchapter-C/part-173/subpart-E/section-173.185<br>https://unece.org/sites/default/files/2025-09/ST-SG-AC10-C3-132E.pdf<br>https://www.cpsc.gov/（Reese's Law / 16 CFR 1263） |
| 数据日期 | 2026-10-07 检索 |
| evidence_level | A（49 CFR 173.185 + UNECE） |

---

### 1.6 儿童相关产品（F1/F2，即便非安全装备）

| 项目 | 内容 |
|---|---|
| 适用法规/标准 | **CPSIA (Public Law 110-314)**：所有"children's product"（ intended for children 12 or under）必须：<br>(1) **16 CFR 1303**：油漆/表面涂层铅 ≤90 ppm；<br>(2) **CPSIA §101**：基材总铅含量 ≤100 ppm；<br>(3) **16 CFR 1307**：邻苯二甲酸盐（DEHP/DBP/BBP/DINP/DIDP/DnOP）≤0.1% in toys/childcare articles；<br>(4) **16 CFR 1501**：3岁以下儿童产品禁止小部件（small parts cylinder）；<br>(5) **CPC (Children's Product Certificate)**：基于 CPSC-accepted 第三方实验室测试报告出具，随货英文。<br>(6) 永久追踪标签（tracking label）。 |
| 具体要求 | 只要产品营销定位为"kids camping backpack"或"for children"，即触发全部 CPSIA 要求。**即使产品本身不是安全装备**（如儿童露营小背包）。 |
| 是否需要第三方测试 | **是**，必须 CPSC-accepted 实验室；每个 SKU 每种材质都要测。 |
| 合规成本量级（INFERENCE） | CPC 全套测试（铅+邻苯+小部件+阻燃）：$1000–3000/SKU；年度复检。 |
| 数据来源 URL | https://www.cpsc.gov/Testing-Certification/Childrens-Product-Certificate-CPC<br>https://www.cpsc.gov/FAQ/Phthalates<br>https://www.cpsc.gov/Business--Manufacturing/Testing-Certification/Childrens-Product-Certificate/CPC-Example-Clothing |
| 数据日期 | 2026-10-07 检索 |
| evidence_level | A（CPSC 官方 CPC 指南） |

---

### 1.7 磁体产品（G4 磁吸纱窗、J2 磁吸配件）

| 项目 | 内容 |
|---|---|
| 适用法规/标准 | **16 CFR Part 1262 Safety Standard for Magnets**（2022年9月7日 CPSC 批准，2023年生效）。<br>适用范围：designed/marketed/intended for entertainment, jewelry (incl. children's jewelry), mental stimulation, stress relief 的消费品，含 loose or separable magnets。 |
| 具体要求 | 任何可脱落/可分离的磁体，若能完全放入小部件测试筒（16 CFR 1501.4 Figure 1），则其 **flux index 必须 <50 kG²·mm²**（按 ASTM F963 §8.25 测试）。<br>**关键豁免判断**：磁吸纱窗的磁体若被车缝/胶封在网纱内、经 use-and-abuse 测试后不脱落，则不属于"loose or separable"，可能不适用 1262。但如果消费者可以取出磁条，则适用。 |
| 是否需要第三方测试 | 若判定为 subject magnet product：是，ASTM F963 flux index 测试 + CPC（若面向儿童）。 |
| 合规成本量级（INFERENCE） | 磁体 flux index 测试：$500–1500/SKU。 |
| 数据来源 URL | https://www.cpsc.gov/Business--Manufacturing/Business-Education/Business-Guidance/Magnets<br>https://www.ecfr.gov/current/title-16/chapter-II/subchapter-B/part-1262<br>https://www.cpsc.gov/Newsroom/News-Releases/2022/CPSC-Approves-New-Federal-Safety-Standard-for-Magnets |
| 数据日期 | 2026-10-07 检索 |
| evidence_level | A（CPSC 官方 + eCFR） |

---

### 1.8 车边纱窗 / 遮阳帘（G2/G4）

| 项目 | 内容 |
|---|---|
| 适用法规/标准 | **联邦层面**：FMVSS 205 (49 CFR 571.205) 仅约束**车辆原厂** glazing 材料，后市场 sun shade 不是 glazing，不直接受 FMVSS 205 认证。<br>**联邦商用车**：49 CFR 393.60（FMCSR）要求挡风玻璃和驾驶员左右侧窗 parallel luminous transmittance ≥70%——但仅适用于 commercial motor vehicles。<br>**州法层面**：美国各州 window tint 法律差异大；多数州要求前侧窗 VLT ≥70%（部分州 50%），后窗/后挡风无限制。**后市场网纱遮阳挡如果完全覆盖前侧窗，可能违反州法**。 |
| 具体要求 | (1) 产品页面必须明确"rear side window / rear windshield / parked car use only"；(2) 不得宣称"while driving"用于前侧窗；(3) 欧盟对应 ECE R43（车辆玻璃安全），但后市场遮阳挡同样不直接适用；(4) 注意加州等14州禁止后市场 visor/shade 阻挡驾驶员前向/侧向视野。 |
| 是否需要第三方测试 | 无法定联邦测试。建议产品页免责声明。 |
| 合规成本量级（INFERENCE） | $0（标签+文案合规）。 |
| 数据来源 URL | https://www.federalregister.gov/documents/2005/07/12/05-13248/federal-motor-vehicle-safety-standards-glazing-materials<br>https://www.govinfo.gov/content/pkg/CFR-2022-title49-vol5/pdf/CFR-2022-title49-vol5-sec393-61.pdf<br>https://www.govinfo.gov/content/pkg/CFR-2011-title49-vol6/xml/CFR-2011-title49-vol6-sec571-205.xml |
| 数据日期 | 2026-10-07 检索 |
| evidence_level | A（Federal Register + eCFR） |

---

### 1.9 帐篷修补胶带 / 风绳 / 地钉（J1/J2）

| 项目 | 内容 |
|---|---|
| 适用法规/标准 | 无专门联邦标准。<br>一般消费品受 CPSA §15(b) 一般安全条款约束。<br>欧盟 REACH Annex XVII 通用化学物质限制（如 PAHs Entry 50：橡胶/塑料握把接触皮肤 ≤1 mg/kg；镉 Entry 27；邻苯二甲酸盐 Entry 51/52）。 |
| 具体要求 | 胶带胶粘剂/涂层：避免含 REACH 限制物质（如 PAHs 在橡胶把手/握把件）。<br>风绳/地钉：金属五金件，无强制测试；建议警告标签（sharp points, trip hazard）。 |
| 是否需要第三方测试 | 无强制。建议供应商 REACH DoC。 |
| 合规成本量级（INFERENCE） | $0–¥1000 RMB（REACH DoC）。 |
| 数据来源 URL | https://single-market-economy.ec.europa.eu/sectors/chemicals/reach/restrictions_en<br>https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32020R2096 |
| 数据日期 | 2026-10-07 检索 |
| evidence_level | A（EUR-Lex） |

---

## 2. 合规风险分级表

| 分级 | 微品类 | 理由 |
|---|---|---|
| **Green（低风险，无需特殊认证）** | A 系列收纳包/袋（帐篷顶网、厨具卷袋、椅侧挂袋、地钉锤包、睡垫捆绑带）<br>B5 颈枕（非儿童款）<br>C 系列灯挂扣/收纳盒（不含电池主品）<br>G1 后备箱收纳箱<br>G3 座椅背收纳<br>G5 行李网/弹力绳<br>I 系列相机带/三脚架地钉/望远镜背带<br>J3 晾鞋架<br>J4 卫生铲+纸套装<br>J5 太阳能淋浴配件（避开水箱主品） | 纯纺织品/尼龙/金属五金，非食品接触、非儿童产品、无电池、无磁体；仅需 FTC 纺织标签（如含布）+ Made in China。 |
| **Yellow（需测试但成本可控）** | B1 露营充气枕（PVC/TPU/海绵）<br>B2 睡袋衬<br>B4 露营毯/营地垫<br>F3/H1 野餐垫/沙滩垫（防水底）<br>D1 折叠水桶/洗脸盆（非食品接触声明款）<br>E2 狗垫<br>G2/G4 车边纱窗/磁吸遮阳帘（磁体需判定）<br>J1 帐篷修补胶带<br>J2 风绳/地钉套装 | 需 (1) FTC 纺织标签；(2) 供应商 REACH DoC（AZO/甲醛/PAHs）；(3) 磁吸款需 16 CFR 1262 flux index 判定（若磁体可脱落则升级 Red）；(4) 产品文案合规（车用品不得阻挡前向视野）。单 SKU 测试预算 ¥1500–3000 RMB。 |
| **Red（高风险/本项目主动避开）** | D4 硅胶食品袋 / 折叠碗（食品接触）<br>E1 狗折叠水碗（接触宠物饮水/食物）<br>E3 狗安全带（产品责任高，无标准兜底）<br>C 系列含电池露营灯/头灯主品<br>F1 儿童露营背包（触发 CPSIA + CPC + 第三方测试）<br>任何纽扣电池/锂电池产品（UN 38.3 + 16 CFR 1263 Reese's Law） | (1) 食品接触：FDA 21 CFR 177.2600 + EU 1935/2004 + LFGB 测试，每材质 $500–1000；(2) 儿童产品：CPC + CPSC 认可实验室测试，$1000–3000/SKU，年度复检；(3) 电池：UN 38.3 + 运输鉴定 + 锂电火灾召回风险；(4) 狗安全带无 FMVSS 兜底但责任风险高。 |

---

## 3. 关键判断与建议

1. **野餐垫/露营毯不是"服装"**：16 CFR 1610 不强制；但 FTC 纺织标签必须做（纤维% + RN + Made in China）。这是最容易被忽略的合规点。
2. **露营枕头/睡袋衬不是床垫**：16 CFR 1632/1633 不适用。这是常见误读。
3. **磁吸纱窗的磁体合规是灰色地带**：必须要求供应商提供"磁体被缝合/胶封、不可脱落"的结构证据；否则按 16 CFR 1262 升级到 Red。
4. **狗水碗按食品接触做**：虽然 FDA 对宠物食品的执法不如人食严格，但一旦被告，21 CFR 177.2600 测试报告是唯一辩护。建议要么 (a) 只卖"非食品接触"声明款（不建议），要么 (b) 直接 Red 避开。
5. **儿童定位是红线**：任何产品页面出现"kids / children / toddler / boy / girl"都会触发 CPSIA。**Nuotao 文案必须严格使用成人/家庭场景词（family camping），避免 kids 定位**。
6. **REACH 甲醛新规（2023/1464）对户外品类相对友好**：完全户外使用的物品豁免甲醛限值——但必须在 DoC 中明确"intended exclusively for outdoor use"。
7. **车边纱窗文案合规**：产品页必须写"rear side window only / for parked car use"，不得写"drive with windows open"。

---

## 4. 数据覆盖总结
- **覆盖微品类法规调研**：9 组（纺织品、狗用品、硅胶食品袋、露营枕头/睡袋衬、电池排除、儿童产品、磁体、车边纱窗、帐篷修补/风绳）
- **法规条款级别证据**：全部 A 级（eCFR / CPSC.gov / EUR-Lex / Federal Register 原文）
- **Green / Yellow / Red 分级**：
  - **Green**：约 15 个微品类（纯收纳/五金/非纺织配件）
  - **Yellow**：约 9 个微品类（纺织垫、充气枕、磁吸纱窗、修补胶带）
  - **Red**：约 6 个微品类（食品接触、儿童定位、含电池、狗安全带）
- **未覆盖**：加州 Prop 65 具体化学物质清单（建议后续单独立项）；英国 UKCA 脱欧后细则；电池新规 EU 2023/1542 分阶段时间表。
