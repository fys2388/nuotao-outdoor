# Nuotao Outdoor Phase 1 执行手册

> **版本**: v1.0 | **日期**: 2026-10-08 | **状态**: READY TO EXECUTE
> 本文件是 Phase 0 验证期的完整执行手册，可直接使用。

---

## 目录

1. [Phase 1 选品决策](#1-phase-1-选品决策)
2. [3 个 Hero SKU 详细规格](#2-3-个-hero-sku-详细规格)
3. [1688 供应商清单](#3-1688-供应商清单)
4. [询盘模板 (中英文)](#4-询盘模板-中英文)
5. [产品页文案](#5-产品页文案)
6. [定价与 Landed Cost 模型](#6-定价与-landed-cost-模型)
7. [Phase 0 执行计划 (8 周)](#7-phase-0-执行计划-8-周)
8. [TikTok 内容脚本 (前 5 条)](#8-tiktok-内容脚本-前-5-条)
9. [WooCommerce 产品数据结构](#9-woocommerce-产品数据结构)
10. [风险检查清单](#10-风险检查清单)

---

## 1. Phase 1 选品决策

### 1.1 为什么选这 3 个

| 维度 | Trunk Organizer Pro | Trail Repair Kit | Buckle Repair Kit |
|------|--------------------|------------------|-------------------|
| **市场验证** | 41,240 评论 (Drive Auto) | 8,212 评论 (GEAR AID Tape) | 4,207 评论 (BEYOURD) |
| **复购机制** | 塑料扣 1 年断 → 替换 | 胶带用完 → 消耗补货 | 扣断 → 替换 |
| **客单价** | $39.99 | $19.99 | $14.99 |
| **1688 成熟度** | 高 (多个供应商) | 高 (产业带成熟) | 极高 (义乌/温州) |
| **法规风险** | 无 (纯织物) | 无 (固体压敏胶) | 无 (POM 塑料) |
| **退货率预期** | 5-8% (车型适配) | 1-2% (通用) | 1-2% (通用) |
| **差异化空间** | 金属扣替代塑料扣 | 无液体版 (可直发) | 24h 发货 vs 官方 6-8 周 |

### 1.2 SKU 组合逻辑

```
Trunk Organizer Pro ($39.99) — 拉新 Hero，教育市场
    ↓ 客户买了后备箱收纳箱 → 是 car camping 用户
    ↓
Trail Repair Kit ($19.99) — 第二单，配件 attach
    ↓ 客户有帐篷/背包 → 需要维修配件
    ↓
Buckle Repair Kit ($14.99) — 第三单，跨品类扩展
    ↓ 客户有多个背包 → 需要更多扣件
```

### 1.3 为什么不选其他品类

| 候选 | 排除原因 |
|------|----------|
| Hydration Bite Valve | 需 FDA 食品级硅胶认证，Phase 0 做不了 |
| Tent Stakes/Guyline | 客单价太低 ($10-15)，CAC 压力大 |
| 防雨罩 | 红海，尺寸退货率高 (12-15%) |
| 厨房收纳 | 体积大运费高，Phase 1.5 再做 |
| 照明配件 | 灯钩竞争尚可，但电源条需 UL 认证 |

---

## 2. 3 个 Hero SKU 详细规格

### SKU 1: Nuotao Trunk Organizer Pro (NUO-TO-01)

#### 产品定义
**1680D Oxford 后备箱收纳箱，金属 D 环扣 + 硅胶防滑底 + 可拆分隔板升级版**

#### 规格参数

| 参数 | 规格 | 对标 (Drive Auto B071F82CYJ) |
|------|------|------------------------------|
| 外尺寸 | 44 × 32 × 22 cm (折叠后: 44 × 32 × 6 cm) | 41 × 30 × 20 cm |
| 容量 | 28L (可扩展至 35L) | ~25L |
| 面料 | 1680D Oxford 涤纶 + TPU 涂覆 | 600D Oxford |
| 底部 | TPU 涂层 + 硅胶防滑点 (12 颗) | TPU 涂层 (无防滑) |
| 扣件 | **304 不锈钢 D 环 + 塑料扣组合** | 全塑料扣 |
| 绑带 | 加厚尼龙织带 + 金属钩 | 塑料扣 |
| 分隔板 | **可拆式 PP 硬板分隔 (3 片)** | 无分隔 |
| 拉链 | YKK #5 防水拉链 (主开合) | 普通拉链 |
| 提手 | 加宽织带提手 (2 个) | 普通提手 |
| 侧袋 | 侧边网袋 × 2 + 前袋 × 1 | 侧袋 × 2 |
| 颜色 | 军绿色 / 黑色 | 黑色 / 灰色 |
| 重量 | 1.2 kg | 1.0 kg |

#### 痛点解决对照

| 客户投诉 (Drive Auto) | Nuotao 解决方案 |
|----------------------|-----------------|
| "The clamps have failed in every single one" (190 votes) | 304 不锈钢 D 环，非塑料扣 |
| "Bottom part is slick so it slides" | 硅胶防滑点 12 颗 + TPU 底部 |
| "Flimsy construction" | 1680D Oxford (vs 600D) + PP 硬板分隔 |
| "Straps too short" | 加长绑带 + 金属钩 |

#### 1688 成本估算

| 组件 | 单价 (¥) | 来源 |
|------|----------|------|
| 1680D 箱体 | ¥45-55 | 上海臻充琦 (944138010136) |
| 金属 D 环 × 4 | ¥2-3 | 义乌五金产业带 |
| 硅胶防滑点 × 12 | ¥1-2 | 东莞硅胶厂 |
| PP 分隔板 × 3 | ¥3-5 | 包装厂 |
| 织带绑带 + 金属钩 | ¥2-3 | 温州织带厂 |
| 拉链 | ¥2-3 | YKK 代理 |
| 包装 | ¥3-5 | 纸箱 + 彩盒 |
| **总计** | **¥61-76 ($8.5-10.5)** | |

---

### SKU 2: Nuotao Trail Repair Kit (NUO-TRK-01)

#### 产品定义
**无液体户外维修套件 — 胶带 + 补丁 + 拉链头 + 迷你针线 + 弹力绳小样**

#### 规格参数

| 组件 | 规格 | 对标 (GEAR AID Camp & Trail Kit) |
|------|------|----------------------------------|
| 修补胶带 | 3" × 20ft (2.54cm × 6m), TPU 基材, 黑色 | GEAR AID Tenacious Tape 2.5" × 20' |
| 面料补丁 | Hex 圆角 4 片 (10cm, 8cm, 6cm, 4cm) | 方形补丁 (会翘边) |
| 拉链头 | 通用 #5 YKK 兼容 3 个 (S/M/L) | 无 |
| 迷你针线 | 3 色尼龙线 + 弯针 + 顶针 | 无 |
| 弹力绳 | 1/8" × 2ft 小样 + 穿引针 | 无 |
| 收纳 | 尼龙收纳袋 15 × 10 × 5 cm | 纸盒 |
| 说明书 | 中英双语维修手册 (8 页) | 无 |
| **重量** | 250g | ~200g |

#### 痛点解决对照

| 客户痛点 | Nuotao 解决方案 |
|----------|-----------------|
| 液体胶不能中国直发 | 全部固体压敏胶 |
| 补丁方角翘边 | Hex 圆角设计 |
| 拉链头断了找不到 | 通用 3 尺寸兼容 |
| 帐篷杆断了没工具 | 弹力绳 + 穿引针 DIY |
| 不会修 | 8 页图解手册 |

#### 1688 成本估算

| 组件 | 单价 (¥) | 来源 |
|------|----------|------|
| TPU 修补胶带 | ¥3-5 | 惠州风译 (TPU 修补贴) |
| Hex 面料补丁 × 4 | ¥1-2 | 义乌冰野 (¥0.6/个) |
| 拉链头 × 3 | ¥1-2 | 温州拉链厂 |
| 迷你针线套装 | ¥2-3 | 义乌文具厂 |
| 弹力绳小样 | ¥1-2 | 泰州华昊 (¥0.20/m) |
| 收纳袋 + 印刷 | ¥2-3 | 通用 |
| 说明书印刷 | ¥1-2 | 数字印刷 |
| **总计** | **¥11-19 ($1.5-2.6)** | |

---

### SKU 3: Nuotao Buckle Repair Kit (NUO-BRK-01)

#### 产品定义
**户外扣件套装 — 1"/1.5" 分体插扣 4 只 + 胸带带扣半成品 + 尺寸指南卡**

#### 规格参数

| 组件 | 规格 | 对标 (Sea to Summit Field Repair) |
|------|------|----------------------------------|
| 1" 插扣 | 4 只 (POM 塑料, 黑色) | 1 只 $6-12 |
| 1.5" 插扣 | 4 只 (POM 塑料, 黑色) | 1 只 $6-12 |
| 胸带带扣 | 半成品 2 套 (含织带 30cm) | 无 |
| 金属 D 环 | 2 个 (304 不锈钢) | 无 |
| 尺寸指南卡 | 卡纸, 标注 1"/1.5"/25mm 适用场景 | 无 |
| 收纳 | 透明密封袋 15 × 10 cm | 无 |
| **重量** | 80g | ~30g |

#### 痛点解决对照

| 客户痛点 | Nuotao 解决方案 |
|----------|-----------------|
| Osprey 等 6-8 周 | 24h 发货 (现货) |
| 尺寸不确定 | 尺寸指南卡 |
| 胸带断了 | 含胸带半成品 |
| 只有一种尺寸 | 1" + 1.5" 混合 |
| 扣断了没工具 | 含金属 D 环 |

#### 1688 成本估算

| 组件 | 单价 (¥) | 来源 |
|------|----------|------|
| POM 插扣 1" × 4 | ¥1.2-2 | 义乌佳信 (¥0.80/个) |
| POM 插扣 1.5" × 4 | ¥1.6-2.4 | 温州瑜澤合 (¥0.08-1.20/个) |
| 胸带半成品 × 2 | ¥2-3 | 通用织带厂 |
| 304 金属 D 环 × 2 | ¥1-2 | 义乌五金 |
| 尺寸指南卡 + 印刷 | ¥1-2 | 数字印刷 |
| 包装 | ¥1-2 | 密封袋 |
| **总计** | **¥8-13.4 ($1.1-1.9)** | |

---

## 3. 1688 供应商清单

### 3.1 Trunk Organizer Pro 供应商

| 优先级 | 供应商 | 产品 | 价格 | 链接 | 备注 |
|--------|--------|------|------|------|------|
| ⭐ 首选 | 上海臻充琦 | 1680D 后备箱箱 | ¥49.8-74.5 | [1688](https://detail.1688.com/offer/944138010136.html) | 明确做 wish/速卖通/独立站/LAZADA |
| 备选 | 义乌百鑫 | 55L 后备箱箱 | UNKNOWN | [1688](https://detail.1688.com/offer/860634964355.html) | 大容量版 |
| 备选 | 未知供应商 | 后备箱收纳箱 985844738591 | UNKNOWN | [1688](https://detail.1688.com/offer/985844738591.html) | 需询盘 |

### 3.2 Trail Repair Kit 供应商

| 优先级 | 供应商 | 产品 | 价格 | 链接 | 备注 |
|--------|--------|------|------|------|------|
| ⭐ 首选 | 惠州风译 | TPU 修补贴 | ¥21.48 | 1688 搜索 | 质量优 |
| 备选 | 惠州博力德 | PVC 修补贴 | ¥17 | 1688 搜索 | 价格优 |
| 首选 | 义乌冰野 | TPU 修补片 | ¥0.6/个 | 1688 搜索 | 月销 565 |
| 首选 | 潞旺 | PE 修补胶带 | ¥5.5-48 | 1688 搜索 | 多规格 |
| 首选 | 泰州华昊 | 尼龙弹力绳 | ¥0.20/m | 1688 搜索 | 成交 587 万米 |
| 首选 | 泰州瑞成 | 尼龙弹力绳 | ¥0.80/m | 1688 搜索 | 备选 |
| 首选 | 温州拉链厂 | 拉链头 | ¥0.5-2/个 | 1688 搜索 | 通用 |

### 3.3 Buckle Repair Kit 供应商

| 优先级 | 供应商 | 产品 | 价格 | 链接 | 备注 |
|--------|--------|------|------|------|------|
| ⭐ 首选 | 义乌佳信 | POM 插扣 1" | ¥0.80/个 | 1688 搜索 | 月销 2.6 万 |
| 首选 | 温州瑜澤合 | 日字扣 | ¥0.08-1.20/个 | 1688 搜索 | 成交 33 万 |
| 首选 | 东莞虎门顺裕达 | 插扣 2.5-3.8cm | ¥0.33/个 | 1688 搜索 | 成交 26 万 |
| 首选 | 义乌安创 | 塑料插扣 | ¥0.50/个 | 1688 搜索 | 成交 86 万 |
| 首选 | 义乌品瑞 | 金属 D 环 | ¥0.24/个 | 1688 搜索 | 成交 297 万 |

### 3.4 通用供应商 (包装/印刷)

| 类别 | 供应商 | 价格 | 备注 |
|------|--------|------|------|
| 彩盒印刷 | 深圳/东莞印刷厂 | ¥1-3/个 (500+) | 需找 |
| 说明书印刷 | 数字印刷 (单页 ¥0.1-0.3) | ¥0.5-2/本 | 需找 |
| 透明密封袋 | 通用供应商 | ¥0.1-0.3/个 | 需找 |

---

## 4. 询盘模板 (中英文)

### 4.1 Trunk Organizer 询盘

```
标题: [Nuotao] 1680D 后备箱收纳箱 OEM/ODM 询盘 — 月需 500+ pcs

Hello,

We are Nuotao Outdoor, a DTC brand targeting the US market.
We are looking for a manufacturer for our trunk organizer product.

Specifications:
- Material: 1680D Oxford + TPU coating
- Size: 44 × 32 × 22 cm (folds to 44 × 32 × 6 cm)
- Hardware: 304 stainless steel D-rings (NOT plastic clasps)
- Bottom: TPU + 12 silicone anti-slip dots
- Divider: 3 removable PP hard dividers
- Zipper: YKK #5 waterproof
- Color: Army green / Black

Questions:
1. What is your MOQ? (We need 500-1000 pcs for first order)
2. Can you do OEM (our logo/branding)?
3. What is the lead time?
4. Can you provide samples? Sample cost?
5. Do you export to US? Any experience with DTC brands?
6. Can you customize the hardware (metal D-rings instead of plastic)?
7. What certifications do you have? (ISO/BSCI/etc.)

We are ready to place a PO within 2 weeks. Please send:
- Product catalog
- Price list with MOQ tiers
- Export documentation capability

Best regards,
[Nuotao Team]
```

### 4.2 Repair Kit / Buckle Kit 询盘

```
标题: [Nuotao] 户外维修配件 OEM 询盘 — 多品类, 月需 1000+ pcs

Hello,

We are Nuotao Outdoor, a DTC brand targeting the US market.
We are sourcing multiple outdoor repair components.

Products needed:
1. TPU repair tape: 3" × 20ft, black
2. Hex fabric patches: 4 sizes (10cm/8cm/6cm/4cm), 4 pieces per kit
3. Universal zipper pulls: #5 YKK compatible, 3 sizes
4. POM side-release buckles: 1" × 4 + 1.5" × 4 per kit
5. Sternum strap halves: 2 sets with 30cm webbing
6. 304 stainless steel D-rings: 2 pieces per kit
7. Nylon shock cord: 1/8" × 2ft sample + lead wire
8. Mini sewing kit: 3 colors + curved needle + thimble

Questions:
1. Can you supply all items above?
2. What is the price per unit at 1000 pcs?
3. What is the MOQ per item?
4. Can you do packaging in branded kits?
5. Can you provide FDA/REACH/CPSC test reports for the plastic components?
6. Lead time for samples and production?

We need samples within 2 weeks and PO within 3 weeks.

Best regards,
[Nuotao Team]
```

---

## 5. 产品页文案

### 5.1 Trunk Organizer Pro

**标题 (SEO):**
`Nuotao Trunk Organizer Pro — 28L Foldable Trunk Storage Bin with Metal D-Rings, Anti-Slip Base & Removable Dividers (Black/Army Green)`

**五点描述:**

1. **METAL D-RINGS THAT ACTUALLY HOLD** — We replaced every plastic clasp with 304 stainless steel D-rings. No more snapping on bumpy trails. Drive Auto's #1 complaint was "clamps fail" — we built this to not fail.

2. **ANTI-SLIP BASE THAT STAYS PUT** — 12 industrial silicone dots + TPU-coated base grip any surface. No more organizer sliding around in your trunk when you hit a pothole.

3. **1680D OXFORD — 3× STRONGER THAN 600D** — Built with triple the fabric weight of standard organizers. Resists tears, UV, and water. This bin lasts seasons, not weeks.

4. **3 REMOVABLE DIVIDERS FOR CUSTOM LAYOUTS** — Three PP hard dividers create any configuration: tall items, flat items, or mixed. Dividers fold out when you need trunk space.

5. **FOLDS FLAT TO 2.4 INCHES** — Collapses from 28L to a 6cm flat pack. Stores in your car floor or garage shelf between trips.

**描述:**

```
Your car trunk is organized — until it isn't.

Every car camping trip, the organizer slides. Every rough trail, the plastic clasps snap. Every time you need a flat layout, the dividers are useless.

We spent 6 months talking to car campers, overlanders, and road trippers. We found the same 3 complaints on every organizer sold in America:

1. Plastic clasps break — especially the clamps that hold straps down
2. Bottom is slick — the organizer slides around in transit
3. Dividers are useless — can't reconfigure for different gear

So we built the Trunk Organizer Pro from scratch:

■ 304 STAINLESS STEEL D-RINGS replace every plastic clasp
■ 12 INDUSTRIAL SILICONE DOTS + TPU base grip any surface
■ 1680D OXFORD fabric is 3× stronger than standard 600D
■ 3 REMOVABLE PP HARD DIVIDERS create any layout you need
■ YKK #5 WATERPROOF ZIPPER survives rain and splash
■ FOLDS FLAT to 2.4 inches (6cm) for storage

SPECIFICATIONS:
• Outer Dimensions: 44 × 32 × 22 cm (17.3" × 12.6" × 8.7")
• Folded Dimensions: 44 × 32 × 6 cm (17.3" × 12.6" × 2.4")
• Capacity: 28L (expandable to 35L)
• Weight: 1.2 kg (2.6 lbs)
• Material: 1680D Oxford + TPU coating + silicone
• Color: Black / Army Green
• Includes: 3 removable PP dividers, 2 side mesh pockets, 1 front pocket

THIS IS NOT A FOLDING BIN. This is a purpose-built trunk organizer engineered for real-world car camping, overlanding, and road trips.

WHAT'S IN THE BOX:
• 1 × Trunk Organizer Pro (44 × 32 × 22 cm)
• 3 × Removable PP Hard Dividers
• 1 × Assembly & Use Guide (bilingual EN/ES)

WARRANTY: 1-year limited warranty on fabric and hardware.

SHIPPING: Ships from US warehouse within 48 hours. Free returns within 30 days.
```

**FAQ:**

```
Q: How is this different from Drive Auto's organizer?
A: Three key differences: (1) Metal D-rings instead of plastic clasps — our #1 competitor's top complaint is "clamps fail" (190+ votes). (2) 12 silicone anti-slip dots on the base — competitor's base is slick. (3) 3 removable dividers — competitor has no dividers.

Q: Can I machine wash this?
A: Hand wash recommended. TPU coating and silicone dots may degrade in washing machine. Spot clean with mild soap and water.

Q: Does this fit in a sedan?
A: Folded size is 44 × 32 × 6 cm (17.3" × 12.6" × 2.4"). Fits in most sedan trunk floors, cargo areas, or car floor mats.

Q: What is 1680D Oxford?
A: Denier is a measure of fabric weight. 1680D is triple the weight of standard 600D Oxford fabric. It's more tear-resistant, more UV-resistant, and more water-resistant.

Q: Do the dividers clip in?
A: Yes, each divider has a soft-touch fabric sleeve that clips onto organizer edges. They don't slide or fall.

Q: Can I use this for a dog crate?
A: Not recommended. This is a trunk organizer, not a hard-sided dog crate. It doesn't meet any vehicle crash test standards.

Q: What's the warranty?
A: 1 year limited warranty on fabric and hardware. If a D-ring pulls out of the fabric or the zipper fails within 12 months, we replace it free.
```

---

### 5.2 Trail Repair Kit

**标题 (SEO):**
`Nuotao Trail Repair Kit — 5-Piece No-Liquid Backpack Repair Kit with Repair Tape, Hex Patches, Zip Pulls & Sewing Kit (Backpack, Tent, Hammock)`

**五点描述:**

1. **NO LIQUIDS — SHIPS FROM CHINA, ARRIVES IN 7-12 DAYS** — All solid pressure-sensitive adhesive. No liquids, no chemicals, no shipping restrictions. This kit ships anywhere in the world.

2. **HEX PATCHES THAT DON'T PEEL** — Unlike square patches that peel at corners, our hex patches distribute stress evenly. 4 sizes (10/8/6/4 cm) for every rip, gash, or hole.

3. **UNIVERSAL ZIPPER PULLS (#5 YKK COMPATIBLE)** — 3 sizes (S/M/L) that fit most outdoor gear zippers. When your slider breaks mid-trail, you're not stranded.

4. **SHOCK CORD + LEAD WIRE FOR POLE REPAIRS** — Includes 1/8" nylon shock cord sample + lead wire threader. Re-cord a broken tent pole in 20 minutes without a soldering iron.

5. **BILINGUAL INSTRUCTIONS (EN/ES) — FIX 10 COMMON BREAKDOWNS** — Step-by-step illustrated guide for repairing: tent poles, backpack straps, rainfly tears, sleeping pad holes, zipper sliders, webbing, buckles, and more.

**描述:**

```
Your backpack strap broke. Your tent pole snapped. Your zipper slider is stuck.

You're 3 miles from camp. The sun is setting.

Stop. Breathe. Open this kit.

The Nuotao Trail Repair Kit contains everything you need to fix the 10 most common backcountry breakdowns — in under 15 minutes, with no soldering iron, no liquid adhesive, and no trip back to town.

THIS IS NOT A "FIX-IT-A-KIT" FOR YOUR DESK. This is a purpose-built field repair kit for people who walk, hike, bike, and camp away from civilization.

WHAT'S IN THE KIT:
• 1 × TPU Repair Tape: 3" × 20ft (7.6cm × 6m) — pressure-sensitive, works on nylon, polyester, Oxford, silicone, aluminum
• 4 × Hex Fabric Patches: 10cm / 8cm / 6cm / 4cm — rounded corners prevent peeling
• 3 × Universal Zipper Pulls: S/M/L (#5 YKK compatible)
• 1 × Mini Sewing Kit: 3 nylon thread colors + curved needle + thimble
• 1 × Shock Cord Sample: 1/8" × 2ft + lead wire threader
• 1 × Nylon Pouch: 15 × 10 × 5 cm
• 1 × Illustrated Guide: 8 pages, bilingual EN/ES

WHAT YOU CAN FIX:
✓ Backpack strap rips (tape + sewing)
✓ Tent pole snaps (shock cord + lead wire)
✓ Rainfly tears (hex patches)
✓ Sleeping pad punctures (tape)
✓ Zipper sliders (universal pulls)
✓ Webbing fraying (sewing + tape)
✓ Hammock fabric tears (hex patches)
✓ Tent footprint holes (tape)
✓ Backpack buckle breaks (tape reinforcement)
✓ Dry bag zipper leaks (tape)

WHY OUR PATCHES DON'T PEEL:
Hexagonal shape distributes stress 360° around the repair. Square patches have 4 stress concentration points (corners) that peel first. Our hex patches have zero sharp corners.

WHY NO LIQUIDS:
GEAR AID sells liquid seam sealer — great product, but it's Class 3 flammable and can't ship from China. Our kit is all solid pressure-sensitive adhesive. We ship from China, you get it in 7-12 days. No customs delays, no hazmat fees.

SHIPPING: Ships from China warehouse. 7-12 day delivery to US. Free returns within 30 days.

WARRANTY: 1-year warranty. If any component fails due to manufacturing defect, we replace the kit free.
```

---

### 5.3 Buckle Repair Kit

**标题 (SEO):**
`Nuotao Buckle Repair Kit — 4-Pack Side Release Buckles (1" + 1.5") + Sternum Strap + D-Rings (Fix Broken Backpack Straps No Sew)`

**五点描述:**

1. **SHIPS IN 24 HOURS — NOT 6-8 WEEKS** — Osprey sends free replacement buckles, but their "All Mighty Guarantee" takes 6-8 weeks. We have them in stock and ship within 24 hours. Your pack is repairable tonight.

2. **TWO SIZES IN ONE KIT** — 1" buckles for standard webbing (25mm packs, sternum straps) + 1.5" buckles for heavy-duty webbing (load lifters, hip belts). 8 total buckles.

3. **POM PLASTIC — SAME MATERIAL AS YOUR PACK** — POM (Polyoxymethylene) is the same engineering plastic used in premium backpack buckles. Stronger than nylon, doesn't creep, doesn't crack in cold.

4. **STERNUM STRAP HALVES INCLUDED** — Two pre-assembled sternum strap halves (30cm webbing + buckle). Just splice to your existing strap. No sewing required.

5. **SIZE GUIDE CARD — KNOW WHAT YOU NEED** — Includes a tear-off card showing which buckle fits which webbing width. No more guessing between 1" and 1.5".

**描述:**

```
Your sternum strap broke.

You have a 60L pack, 20 pounds of gear, and 5 miles to camp.

You're not going to carry it with one hand.

Open this kit. Fix it. Walk.

The Nuotao Buckle Repair Kit contains 8 side-release buckles (4 × 1" + 4 × 1.5") — the same POM plastic used in premium backpacks — plus sternum strap halves and D-rings. No sewing required.

WHY 6-8 WEEKS IS NOT ACCEPTABLE:
Osprey's All Mighty Guarantee is legendary. Free replacement buckles, webbing, sternum straps — all for free. But it takes 6-8 weeks. If you're on a thru-hike or waiting for your next trip, 6-8 weeks is not an option.

We ship in 24 hours. Your pack is repaired tonight.

WHAT'S IN THE KIT:
• 4 × 1" Side Release Buckles (POM plastic, black)
• 4 × 1.5" Side Release Buckles (POM plastic, black)
• 2 × Sternum Strap Halves (30cm webbing + buckle)
• 2 × 304 Stainless Steel D-Rings
• 1 × Size Guide Card (tear-off, EN)
• 1 × Sealable Pouch (15 × 10 cm)

WHICH SIZE DO I USE?
• 1" (25mm): Sternum straps, pack straps, waist straps
• 1.5" (38mm): Load lifters, hip belt side-release, heavy-duty straps
• Size guide card in the kit shows exact measurements

NO SEWING REQUIRED:
For sternum straps: cut the old buckle section, splice the new strap half in with the included buckle. Done in 2 minutes.
For webbing straps: thread webbing through the buckle, trim excess, melt cut ends with a lighter. Done in 1 minute.

COMPATIBILITY:
Fits most standard webbing widths. Check our size guide card before ordering if unsure.

SHIPPING: Ships from US warehouse. 24-48 hour processing. Free returns within 30 days.

WARRANTY: Lifetime warranty. If a buckle fails due to manufacturing defect, we replace the kit — forever.
```

---

## 6. 定价与 Landed Cost 模型

### 6.1 定价表

| SKU | 1688 成本 (¥) | 1688 成本 (USD) | 国际运费 | 国内运费 | 包装 | 关税 | 支付费 | 退货预留 | Landed Cost | 售价 | 毛利率 |
|-----|---------------|-----------------|----------|----------|------|------|--------|----------|-------------|------|--------|
| Trunk Organizer Pro | ¥70 | $10.00 | $4.00 | $1.00 | $1.00 | $0.50 | $1.20 | $2.00 | **$19.70** | **$39.99** | **50.7%** |
| Trail Repair Kit | ¥15 | $2.10 | $1.50 | $0.50 | $0.50 | $0.10 | $0.60 | $0.30 | **$5.60** | **$19.99** | **71.9%** |
| Buckle Repair Kit | ¥10 | $1.40 | $1.00 | $0.30 | $0.30 | $0.05 | $0.45 | $0.20 | **$3.70** | **$14.99** | **75.3%** |

### 6.2 Bundle 定价

| Bundle | 组成 | 单买总价 | Bundle 价 | 折扣 | 毛利 |
|--------|------|----------|-----------|------|------|
| Starter Kit | Trunk Organizer + Repair Kit | $59.98 | **$49.99** | 17% | 52% |
| Outdoor Repair Bundle | Repair Kit + Buckle Kit | $34.98 | **$29.99** | 14% | 74% |
| Full Kit | All 3 | $74.97 | **$59.99** | 20% | 55% |

### 6.3 运费策略

| 选项 | 月订单量 | 运费成本 | 说明 |
|------|----------|----------|------|
| 中国直发 (小包) | <100 单/月 | $3-8/单 | 7-12 天，Phase 0 验证期 |
| 中国直发 (专线) | 100-500 单/月 | $2-4/单 | 8-15 天，Phase 1 起 |
| 美国海外仓 | >500 单/月 | $0.5-1/单 | 2-3 天，Phase 2 起 |

### 6.4 关税说明

| 产品 | HS 编码 | 关税 (估计) | 备注 |
|------|---------|-------------|------|
| Trunk Organizer (Oxford) | 4202.92 | 3.0-7.5% | 箱包/收纳类 |
| Repair Tape (rubber/TPU) | 3919.90 | 5.3% | 橡胶制品 |
| Fabric Patches (textile) | 5911.90 | 16.6% | 纺织辅料 |
| POM Buckles (plastic) | 3926.90 | 3.4% | 塑料制品 |
| 304 D-Rings (steel) | 7326.90 | 14.3% | 钢铁制品 |
| Nylon Cord (textile) | 5401.20 | 6.5% | 合成纤维长丝 |
| Zip Pulls (plastic) | 9607.19 | 10.6% | 拉链附件 |

> ⚠️ 关税为估算，具体需根据实际 HTS 编码和中美贸易政策确认。建议 Phase 0 找报关行确认。

---

## 7. Phase 0 执行计划 (8 周)

### Week 1: 样品采购

| 天数 | 任务 | 预算 |
|------|------|------|
| D1-D2 | 联系 1688 供应商 (3 个品类各 3 家) | $0 |
| D3-D5 | 下单样品 (每款 5 件) | ¥500-800 ($70-110) |
| D6-D7 | 等待样品 (国内快递 2-3 天) | $0 |
| **Week 1 总计** | | **~$100** |

### Week 2: 质量评估

| 天数 | 任务 | 预算 |
|------|------|------|
| D1-D3 | 测试 Trunk Organizer (承重、拉链、D 环) | $0 |
| D4-D5 | 测试 Repair Kit (胶带粘性、补丁耐用性) | $0 |
| D6-D7 | 测试 Buckle Kit (插拔次数、承重) | $0 |
| **Week 2 总计** | | **$0** |

### Week 3-4: 独立站搭建

| 天数 | 任务 | 预算 |
|------|------|------|
| D1-D3 | 注册域名 + 搭建 WooCommerce/Shopify | $50 (域名+主题) |
| D4-D5 | 产品页文案 (用本手册文案) | $0 |
| D6-D7 | 拍摄产品图 (手机 + 自然光) | $0 |
| D8-D10 | 上传 3 个 SKU + 2 个 Bundle | $0 |
| D11-D12 | 设置 Stripe/PayPal 收款 | $0 |
| D13-D14 | 设置物流 (中国直发小包) | $0 |
| **Week 3-4 总计** | | **~$100** |

### Week 5-6: 内容制作

| 天数 | 任务 | 预算 |
|------|------|------|
| D1-D3 | 拍摄 5 条 TikTok 短视频 | $0 |
| D4-D5 | 剪辑 + 发布 | $0 |
| D6-D7 | 发布博客文章 (SEO) | $0 |
| D8-D10 | 联系 5 个户外 YouTuber/TikToker | $0 |
| **Week 5-6 总计** | | **$0** |

### Week 7: 小流量测试

| 天数 | 任务 | 预算 |
|------|------|------|
| D1-D3 | Google Ads 测试 (3 组关键词) | $200 |
| D4-D7 | 每日优化 (关键词/出价/产品页) | $0 |
| D8-D10 | 分析数据 (CTR/转化率/CAC) | $0 |
| D11-D14 | 调整策略 | $0 |
| **Week 7 总计** | | **$200** |

### Week 8: 决策

| 天数 | 任务 |
|------|------|
| D1-D3 | 汇总 30 天数据 |
| D4-D5 | 计算真实 CAC/LTV/退货率 |
| D6-D7 | 决策: 继续/调整/停止 |

### 总预算

| 类别 | 金额 |
|------|------|
| 样品采购 | $100 |
| 独立站搭建 | $100 |
| Google Ads 测试 | $200 |
| 缓冲 | $100 |
| **总计** | **$500** |

### 成功/失败标准

| 指标 | 成功标准 | 失败标准 |
|------|----------|----------|
| CAC | < $15 | > $30 |
| 转化率 | > 2% | < 1% |
| 退货率 | < 5% | > 10% |
| 复购率 | > 20% (30 天内) | < 10% |
| 总花费 | < $1,000 | > $2,000 |

**决策矩阵:**
- ✅ CAC < $15 + 转化率 > 2% → 进入 Phase 1 (批量采购 500 件)
- ⚠️ CAC $15-25 + 转化率 1-2% → 调整产品/定价/流量渠道，再测 2 周
- ❌ CAC > $30 + 转化率 < 1% → 停止，换品或换模式

---

## 8. TikTok 内容脚本 (前 5 条)

### 视频 1: "塑料扣 1 年就断？我们做了金属扣的"

**时长**: 30 秒 | **格式**: 问题→解决→产品

```
[0-3s] 特写: 一个后备箱收纳箱的塑料扣断裂
字幕: "Every car camping organizer breaks here."

[4-8s] 快剪: 3 个不同品牌的收纳箱，塑料扣全部断裂
字幕: "Plastic clasps = #1 failure point."

[9-15s] 产品特写: Nuotao 304 不锈钢 D 环，金属质感
字幕: "We replaced every clasp with 304 stainless steel."

[16-22s] 测试: 用力拉扯 D 环，纹丝不动
字幕: "Tested: 200lb pull strength."

[23-28s] 全景: 收纳箱在颠簸路面上，不滑动
字幕: "12 anti-slip dots. Your gear stays put."

[29-30s] Logo + CTA
字幕: "Link in bio. $39.99"
```

### 视频 2: "6-8 周？我 24 小时修好我的背包"

**时长**: 25 秒 | **格式**: 痛点→解决方案

```
[0-4s] 特写: 背包胸带断裂
字幕: "Your sternum strap broke. Camp is 5 miles away."

[5-8s] 文字叠加: "Osprey: 6-8 weeks for replacement."
字幕: "They send it free. But you can't wait 6 weeks."

[9-14s] 手: 打开 Nuotao Buckle Kit，取出插扣
字幕: "We ship in 24 hours."

[15-20s] 演示: 2 分钟换好胸带
字幕: "2 minutes. No sewing."

[21-23s] 背包背好，开始走
字幕: "Keep hiking."

[24-25s] Logo + CTA
字幕: "Link in bio"
```

### 视频 3: "5 分钟修好 10 种户外装备损坏"

**时长**: 40 秒 | **格式**: 快速教程合集

```
[0-2s] 标题卡
字幕: "5 Min × 10 Repairs = Backcountry Survival"

[3-7s] 帐篷杆折断 → 弹力绳 + 穿引针 → 穿回
字幕: "#1 Tent pole snap → Re-cord in 20 min"

[8-11s] 背包带裂开 → 胶带 → 缝补
字幕: "#2 Backpack strap tear → Tape + sew"

[12-15s] 防雨罩破洞 → Hex 补丁 → 按压
字幕: "#3 Rainfly rip → Hex patch"

[16-19s] 拉链头断了 → 换拉链头
字幕: "#4 Zipper slider break → Swap in 10 sec"

[20-23s] 睡袋破洞 → 胶带
字幕: "#5 Sleeping pad puncture → Tape"

[24-27s] 背包扣断裂 → 插扣套装
字幕: "#6 Buckle break → No-sew fix"

[28-31s] 背包带磨损 → 织带补强
字幕: "#7 Webbing fray → Reinforce"

[32-35s] 防潮垫漏气 → 补丁
字幕: "#8 Dry bag leak → Patch"

[36-38s] 帐篷地钉断了 → 绳子固定
字幕: "#9 Stake break → Cord tie-off"

[39-40s] Logo + CTA
字幕: "Full kit = $19.99. Link in bio."
```

### 视频 4: "后备箱收纳箱滑来滑去？问题在底部"

**时长**: 20 秒 | **格式**: 问题→根因→解决

```
[0-4s] 收纳箱在后备箱滑动，东西倒出来
字幕: "Your organizer slides. Your gear spills."

[5-8s] 特写: 普通收纳箱底部，光滑 TPU
字幕: "Problem: slick plastic bottom."

[9-12s] 特写: Nuotao 12 颗硅胶防滑点
字幕: "Solution: 12 industrial silicone dots."

[13-16s] 测试: 颠簸路面，收纳箱不动
字幕: "Even on rough roads."

[17-20s] Logo + CTA
字幕: "Anti-slip base. $39.99."
```

### 视频 5: "1680D 是什么？为什么你的收纳箱只有 600D"

**时长**: 25 秒 | **格式**: 科普→对比→选择

```
[0-5s] 两个收纳箱并排
字幕: "600D vs 1680D. What's the difference?"

[6-10s] 面料特写，放大
字幕: "Denier = fabric weight. 1680D = 3× heavier."

[11-15s] 撕裂测试对比
字幕: "1680D resists tears. 600D rips."

[16-20s] UV 老化测试对比
字幕: "1680D resists UV. 600D fades."

[21-25s] Logo + CTA
字幕: "Built for seasons, not weeks. Link in bio."
```

---

## 9. WooCommerce 产品数据结构

### 9.1 产品表结构

```sql
CREATE TABLE wp_posts (
    post_title VARCHAR(255),
    post_content TEXT,
    post_excerpt TEXT,
    post_status VARCHAR(20),
    post_type VARCHAR(20),
    post_name VARCHAR(200),
    guid VARCHAR(255)
);

CREATE TABLE wp_postmeta (
    post_id BIGINT,
    meta_key VARCHAR(255),
    meta_value TEXT
);
```

### 9.2 产品 1: Trunk Organizer Pro

```json
{
  "name": "Trunk Organizer Pro - 28L Foldable Trunk Storage Bin with Metal D-Rings",
  "sku": "NUO-TO-01-BK",
  "regular_price": "39.99",
  "sale_price": "",
  "manage_stock": true,
  "stock_quantity": 500,
  "stock_status": "instock",
  "weight": "1.2",
  "length": "44",
  "width": "32",
  "height": "22",
  "categories": [{"name": "Trunk Organizers"}, {"name": "Car Camping"}, {"name": "Outdoor Storage"}],
  "tags": [{"name": "metal d-rings"}, {"name": "anti-slip"}, {"name": "1680D oxford"}, {"name": "foldable"}],
  "short_description": "<p><strong>Metal D-Rings. Anti-Slip Base. 3× Stronger Fabric.</strong><br>28L foldable trunk organizer built with 304 stainless steel D-rings, 12 silicone anti-slip dots, and 1680D Oxford fabric. 3 removable dividers. Folds to 2.4 inches.</p>",
  "description": "(see product copy above)",
  "images": [{"src": "trunk-organizer-main.jpg", "alt": "Nuotao Trunk Organizer Pro"}]
}
```

### 9.3 产品 2: Trail Repair Kit

```json
{
  "name": "Trail Repair Kit - 5-Piece No-Liquid Backpack Repair Kit with Tape, Patches & Zip Pulls",
  "sku": "NUO-TRK-01",
  "regular_price": "19.99",
  "sale_price": "",
  "manage_stock": true,
  "stock_quantity": 1000,
  "stock_status": "instock",
  "weight": "0.25",
  "length": "15",
  "width": "10",
  "height": "5",
  "categories": [{"name": "Repair Kits"}, {"name": "Outdoor Gear"}, {"name": "Backpack Accessories"}],
  "tags": [{"name": "repair kit"}, {"name": "no-liquid"}, {"name": "backpack repair"}, {"name": "tent repair"}],
  "short_description": "<p><strong>Fix 10 Backcountry Breakdowns. No Liquids. Ships from China.</strong><br>5-piece repair kit with TPU tape, hex patches, universal zip pulls, sewing kit, and shock cord. Bilingual instructions. 7-12 day delivery.</p>",
  "description": "(see product copy above)"
}
```

### 9.4 产品 3: Buckle Repair Kit

```json
{
  "name": "Buckle Repair Kit - 4-Pack Side Release Buckles (1\" + 1.5\") + Sternum Strap",
  "sku": "NUO-BRK-01",
  "regular_price": "14.99",
  "sale_price": "",
  "manage_stock": true,
  "stock_quantity": 2000,
  "stock_status": "instock",
  "weight": "0.08",
  "length": "15",
  "width": "10",
  "height": "3",
  "categories": [{"name": "Repair Kits"}, {"name": "Backpack Accessories"}, {"name": "Buckles"}],
  "tags": [{"name": "buckle repair"}, {"name": "sternum strap"}, {"name": "no-sew"}, {"name": "24h shipping"}],
  "short_description": "<p><strong>Ships in 24 Hours. Not 6-8 Weeks.</strong><br>8 POM side-release buckles (4×1\" + 4×1.5\") + sternum strap halves + D-rings. Fix broken backpack straps in 2 minutes. No sewing required.</p>",
  "description": "(see product copy above)"
}
```

### 9.5 Bundle 产品

```json
{
  "name": "Starter Kit - Trunk Organizer Pro + Trail Repair Kit",
  "sku": "NUO-START-01",
  "regular_price": "49.99",
  "sale_price": "",
  "manage_stock": true,
  "stock_quantity": 300,
  "stock_status": "instock",
  "weight": "1.45",
  "length": "44",
  "width": "32",
  "height": "22",
  "categories": [{"name": "Bundles"}, {"name": "Car Camping"}],
  "tags": [{"name": "starter kit"}, {"name": "bundle"}, {"name": "value pack"}],
  "short_description": "<p><strong>Save 17%. Get the Organizer + Repair Kit together.</strong><br>Everything you need to organize your trunk and fix gear in the field. One box, everything covered.</p>",
  "description": "(see product copy above)"
}
```

---

## 10. 风险检查清单

### 10.1 法规检查

| 检查项 | Trunk Organizer | Repair Kit | Buckle Kit | 状态 |
|--------|----------------|------------|------------|------|
| 含电池? | ❌ 否 | ❌ 否 | ❌ 否 | ✅ PASS |
| 含液体? | ❌ 否 | ❌ 否 (固体胶) | ❌ 否 | ✅ PASS |
| 含燃料? | ❌ 否 | ❌ 否 | ❌ 否 | ✅ PASS |
| 含化学品? | ❌ 否 | ⚠️ 压敏胶 (无毒) | ❌ 否 | ✅ PASS |
| 食品接触? | ❌ 否 | ❌ 否 | ❌ 否 | ✅ PASS |
| 儿童产品? | ❌ 否 (标成人) | ❌ 否 | ❌ 否 | ✅ PASS |
| 医疗器械? | ❌ 否 | ❌ 否 | ❌ 否 | ✅ PASS |
| 需要 UL/ETL? | ❌ 否 | ❌ 否 | ❌ 否 | ✅ PASS |

### 10.2 质量检查

| 检查项 | 测试方法 | 通过标准 |
|--------|----------|----------|
| 背包扣承重 | 静态拉伸测试 | ≥50kg (110lb) |
| 背包扣插拔 | 10,000 次插拔 | 无断裂/卡死 |
| 织带断裂力 | 拉伸至断裂 | ≥100kg (220lb) |
| 拉链循环 | 5,000 次开合 | 无卡死/脱齿 |
| 面料撕裂 | 标准撕裂测试 | ≥50N (1680D 标准) |
| 胶粘力 | 180° 剥离测试 | ≥5N/cm |
| 硅胶点防滑 | 倾斜测试 | ≥30° 不滑动 |

### 10.3 物流检查

| 检查项 | 方案 | 风险 |
|--------|------|------|
| 中国直发小包 | 万邑通/YunExpress | 7-12 天，无问题 |
| 退货处理 | 退回中国仓库 | 运费高，建议美国退货 |
| 退货成本 | 美国退货: $5-10/件 | 预算 5% 退货率 |
| 关税预付 | DDP 模式 | 建议找报关行确认 |

### 10.4 品牌检查

| 检查项 | 状态 |
|--------|------|
| 域名注册 | ⚠️ 待办 |
| 商标申请 | ⚠️ Phase 1 后 |
| 商标注册 (美国) | ⚠️ Phase 1.5 |
| GDPR/CCPA 合规 | ⚠️ 独立站设置 |
| 退款政策 | ✅ 30 天 |
| 保修政策 | ✅ 1 年 |

---

## 附录 A: 关键联系人

| 类别 | 名称 | 联系方式 |
|------|------|----------|
| 上海臻充琦 (Trunk Organizer) | 1688 店铺 | [1688 联系](https://detail.1688.com/offer/944138010136.html) |
| 义乌佳信 (Buckles) | 1688 店铺 | 1688 搜索"义乌佳信 POM 插扣" |
| 泰州华昊 (Shock Cord) | 1688 店铺 | 1688 搜索"泰州华昊 弹力绳" |
| 物流 (中国直发) | 万邑通/YunExpress | 官网注册 |
| 报关行 | 待找 | Phase 0 需要 |
| 独立站搭建 | 自建/服务商 | Phase 0 Week 3 |

## 附录 B: 关键词列表 (SEO/Ads)

### Trunk Organizer

**Google Ads (高转化):**
- trunk organizer car camping
- car trunk storage bin
- foldable trunk organizer
- truck bed storage organizer
- SUV trunk organizer

**Google Ads (竞争低):**
- trunk organizer metal clasp
- anti slip trunk organizer
- foldable trunk bin with dividers

**Long-tail (低 CPC):**
- best trunk organizer for car camping 2026
- foldable trunk organizer with dividers
- trunk organizer that stays in place
- heavy duty trunk organizer metal clasp

### Trail Repair Kit

**Google Ads:**
- backpack repair kit
- tent repair kit outdoor
- no liquid repair kit
- backpack strap repair

**Long-tail:**
- how to fix broken backpack strap
- tent pole repair kit
- backpack repair tape
- outdoor gear repair kit

### Buckle Repair Kit

**Google Ads:**
- backpack buckle replacement
- sternum strap replacement
- side release buckle kit

**Long-tail:**
- fix broken backpack sternum strap
- backpack strap buckle replacement
- no sew backpack repair
- osprey buckle replacement fast

---

> **下一步**: 将本手册导入执行系统，开始 Phase 0 Week 1 (1688 供应商联系 + 样品采购)。
