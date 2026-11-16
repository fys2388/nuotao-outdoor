# NT-1688-1044360115390 户外旅行收纳袋 — WooCommerce 商品图生产方案 V1.0

> SOP 依据：`docs/ai_image_generation_sop_wc.md` V3.4
> 素材目录：`woo_images/storage_bag_refs/`（38 张，manifest 见 `_manifest.json`）
> 状态：**待 Owner 审批**（决策点见 §0）

---

## 0. Owner 决策记录（待确认）

| # | 决策点 | 建议默认 | 状态 |
|---|--------|---------|------|
| 1 | 尾程运费口径（计费重敏感性，见 §C.2） | 沿用 config `pricing_default_last_mile=$5.00`，实测计费重后回调 | ⚠️ 待确认 |
| 2 | 采购价↔SKU 映射（1688 仅给区间 ¥3.30–4.70） | 未确认前全 SKU 统一定价 $13.99（按最高档保守测算） | ⚠️ 待供应商报价单 |
| 3 | 品牌印字策略 | 沿用 YD2324 先例：AI 图去除供应商印字、不烧 NUOTAO logo 进像素；品牌走 alt/SEO/包装 | ✅ 建议采纳 |
| 4 |  Moisture-resistant 等定性词入图 | 不入图，仅 alt/描述定性使用 | ✅ 建议采纳 |

---

## A. 信息提取

### A.1 文字层（1688 页面属性表 / 卖点 / 商家信息）

| 项 | 值 | 出处 |
|---|---|---|
| 品名 | 户外旅行收纳袋（ Oxford 布） | 标题 |
| 型号/货号 | 01B1649；系列代号 Nu-M/L/XL、ZY-2031/2539/3755 | 属性表 + 详情规格表 |
| 材质 | 牛津布 420D | detail09/10 规格表 |
| 价格区间 | ¥3.30–4.70（**非包邮**，运费 ¥2.5–3 起） | 价格层 |
| SKU | 15 个：Nu 系列 3 色×3 码 + ZY 系列 2 色×3 码 | SKU 层 |
| 重量 | 20–60g/只（分档见 §C.1） | detail09/10 |
| 品牌授权 | 可授权自有品牌 | 属性表 |
| 供应商 | 丽水一咚家居（14 年店龄，跨境专供，官方验厂 2026-08-28） | 商家层 |

### A.2 图片层（38 张本地核验，V1.0）

主图 5 + 详情 14 + SKU 15 + 买家晒图 4，全部下载成功（38/38）。逐张核验结论：

- **main5**：唯一干净白底图（Nu 黄色空袋平枕态）→ R1 参考图。
- **main1–4**：带中文营销文字叠层，仅作结构/场景参考，入 I2I 前需裁切文字区。
- **SKU 图 15 张**：每张带尺寸标注线，§C.1 尺寸表全部来自图内标注，非估算。
- **review1–4**：买家实物与主图一致；确认织带印字 `Travle And Life`、袋身印 `飞机图标 + Enjoy a wonderful life / ORI Weekeight` 为**出厂标配**（拼写错误亦为标配）；无明显质量瑕疵，review3 见折叠褶皱。

### A.3 双结构事实（文字层未明示，图证发现）

| 系列 | 闭合结构 | 提手 | 形态 | 颜色 | 码段 |
|---|---|---|---|---|---|
| **Nu** | 卷口下折 + POM 插扣闭合 | 插扣织带环（可提可挂） | 立体箱型，底宽 9.5cm 风琴 | 黄/绿/格纹半透明 | M/L/XL |
| **ZY** | 顶部横向拉链 | 固定拱形织带提手 | 扁平枕型，无风琴 | 黄/绿 | 2031/2539/3755 |

9 + 6 = 15，与 SKU 层吻合。**生图与变体严禁混用两系列结构。**

---

## B. 图证核验修正记录（V1.0 发现清单）

| # | 文字层印象 | 图证结论 | 处置 |
|---|-----------|---------|------|
| 1 | 「收纳袋」单一结构 | 实为 Nu/ZY 双结构 | 身份锁定句分两句；变体命名含系列代号 |
| 2 | 「透明」色 | 实为**格纹半透明**（可透见内容物轮廓，非全透 PVC） | 文案写 semi-transparent mesh-look，禁写 clear/transparent PVC 语义 |
| 3 | 无印字信息 | 袋身/织带有供应商印字且含拼写错误 | negative_prompt 增补；AI 图为素色袋身 |
| 4 | 尺寸仅区间 | 6 码全尺寸标注齐备 | §C.1 直接采用，无估算 |
| 5 | 重量 20–60g 笼统 | 分档到码（含透明款单独克重） | §C.1 采用 |

---

## C. 尺寸口径结论

### C.1 规格表（全部源自 SKU 图标注 + detail09/10 规格表，双源互证）

| 代号 | 顶宽 | 底宽 | 风琴厚 | 高 | 重量 | 结构 |
|---|---|---|---|---|---|---|
| Nu-M | 25 | 15 | 9.5 | 19 | 30g | 卷口 |
| Nu-L | 36.5 | 26 | 9.5 | 26 | 40g（透明 45g） | 卷口 |
| Nu-XL | 39.2 | 28.5 | 9.5 | 41.5 | 55g（黄）/60g（绿、透明） | 卷口 |
| ZY-2031 | 20 | — | — | 31 | 20g | 拉链 |
| ZY-2539 | 25 | — | — | 39 | 25g | 拉链 |
| ZY-3755 | 37 | — | — | 55 | 35g | 拉链 |

单位 cm。detail10 声明手工测量 ±1–2cm 误差 → 图文尺寸表述保留整数 cm，不写小数位精度承诺。

### C.2 计费重判定（Owner 口径：体积重 vs 实重）

软体袋无刚性结构，**运输态 = 压缩折叠**（detail14 图证：可折扁塞入背包前袋）。

| 态 | Nu-XL 体积估算 | 体积重 @6000（专线） | 实重 |
|---|---|---|---|
| 满载立态 | ≈33.9×9.5×41.5 ≈ 13,345 cm³ | 2.22 kg | 0.06 kg |
| 压缩折叠态（假设厚 5cm） | 39.2×41.5×5 ≈ 8,134 cm³ | 1.36 kg | 0.06 kg |

**结论：计费重 = 体积重**（任何态下体积重 ≫ 实重）。但压缩厚度无实测值 → ⚠️ 待确认（实测或供应商装箱数据；detail09/10 箱规 60×45×35cm 装 300–500 只可反推单只压缩态 ≈ 1.8–2.4L，与 5cm 厚假设同量级）。

**敏感性**（`minimum_price`，费率取 config）：

| 尾程假设 | Nu-XL 落地成本 | 价格底线 | .99 建议价 |
|---|---|---|---|
| $5.00（config 默认） | $6.78 | $13.09 | $13.99 |
| $8.00 | $9.78 | $18.63 | $18.99 |
| $10.00 | $11.78 | $22.33 | $22.99 |

未实测前按 config 默认 $5.00 出底线（$13.09），**实测计费重后若尾程 > $5 必须重跑定价再上架**（门禁会自动拦截负毛利，但低于目标毛利仅告警，故此处人工复核不可省）。

### C.3 定价建议

- 统一售价 **$13.99**（全 15 SKU），最高档净利 28.5%、最低档 30.4%，均过 25% 红线。
- 供应商报价单到后可分档优化（小码 $12.99 / 大码 $13.99），映射未确认前不分档——防映射反转导致小码价低于底线。

---

## D. 卖点分层与合规闸门

### D.1 视觉主线

`Roll It, Clip It, Carry It` —— 卷口圈数自由调节容量（detail03 图证两步操作），是一句话差异点；同类压缩袋多为抽绳或纯拉链，卷口+插扣提手双用（提/挂）为稀缺组合。

### D.2 五组卖点

| 组 | 卖点 | 视觉方向 | 互证 |
|---|---|---|---|
| 1 差异化 | 卷口密封 + 圈数调容量 | 卷折两步演示、高低对比 | 详情文案+线稿图+买家实物 |
| 2 场景 | 徒步/溯溪/皮划艇/漂流 | 四宫格实拍风 | detail05 四场景 |
| 3 便利 | 可提可挂、折扁塞包 | 挂树枝/挂背包/塞前袋 | detail04/06/14 |
| 4 材质 | 420D 牛津布格纹防撕、POM 插扣 | 面料微距、插扣特写 | 规格表+detail11/12 |
| 5 信任 | 超轻 20–60g、14 年厂 | 克重数字标 | 规格表（厂龄不入图，仅描述区） |

### D.3 合规红线表（三态）

| 候选文案 | 判定 | 处置 |
|---|---|---|
| `ROLL-TOP SEAL` | ✅ detail02「卷口密封设计」 | 入图 M3 |
| `420D RIPSTOP OXFORD` | ✅ 规格表 420d + 格纹图证 | 入图 M3/D6 |
| `FOLDS FLAT` | ✅ detail14 折扁塞包 | 入图 M3 |
| `FROM 20G` | ✅ 规格表分档克重 | 入图 D6 |
| `10L / 20L CAPACITY` | ✅ detail03 明示 | 仅 D6 规格表（HTML 叠加） |
| `WATERPROOF / IPX*` | ❌ 页面仅「隔湿防潮」 | 禁 |
| `MOISTURE-RESISTANT` | ⚠️ 定性可、定量不可 | 仅 alt/描述，不入图 |
| `CE / FCC / 质检徽章 / PATENTED` | ❌ 属性表认证：无 | 禁 |
| `WARRANTY / FREE SHIPPING / 30-DAY RETURN / 24/7 SUPPORT` | ❌ 政策未定 | `{{WARRANTY}}` `{{SHIPPING_POLICY}}` `{{RETURN_POLICY}}` `{{SUPPORT_CHANNEL}}` 占位，D6 承诺区留空 |
| 供应商印字（飞机图标/ORI Weekeight/Travle And Life） | ❌ 非我方品牌 | negative_prompt 增补，AI 图素色袋身 |
| 三色并排 | ✅ 门槛满足（3 色 15 SKU 真实可下单） | M5 出图 |

占位符责任人：Owner（售后/物流政策沿用 YD2324 已定口径时可直接解除）。

---

## E. 视觉策略：5 主图 + 6 详情图

M5 门槛满足（≥2 真实颜色 SKU）→ 主图 5 张；详情 6 张。尺寸：主图 2048×2048，详情 1536×2048；WebP，主图 ≤200KB / 详情 ≤150KB。

### E.1 I2I 参考图槽位

| 槽位 | 资产 | 预处理（V1.0 已执行并目检通过） |
|---|---|---|
| R1 白底正面 | `crops/r1_white.jpg`（main5 原图） | 无需 |
| R2 展开/开口态 | `crops/r3_open.jpg` | 去右下中文 |
| R3 使用场景 | `crops/r2_scene.jpg` | 去顶部中文 |
| R4 细节特写 | `crops/r4_buckle.jpg`（detail11 上半区） | 无中文叠层 |
| R5 多形态对比 | `crops/r5_compare.jpg` | 去顶部中文 |

ZY 系列任务参考：`crops/r_zy_yellow.jpg`（去标注线与中文标签）。

> 残留风险：裁切资产仍带供应商实物印字（袋身飞机图标、织带 Life 字样），靠身份锁定句「solid-color body with NO printed graphics」+ negative_prompt 双重压制；质检 §6.2 必查印字是否复现，复现即重生成。

### E.2 图位清单

| 位 | 内容 | 系列 |
|---|---|---|
| M1 | 白底主图（卷口黄色立态） | Nu |
| M2 | 溯溪场景挂载背包 | Nu |
| M3 | 三卖点促销图（文字烧入 ≤3 条） | Nu |
| M4 | 卷口+插扣结构特写 | Nu |
| M5 | 三色并排（黄/绿/半透明） | Nu |
| D1 | 品牌场景主视觉（NUOTAO 小字标，无 slogan） | Nu |
| D2 | 核心差异化：卷折两步调容量 | Nu |
| D3 | 结构标注图（HTML 叠加 ≥4 部位） | Nu+ZY 双列 |
| D4 | 四场景拼图（徒步/溯溪/皮划艇/漂流） | Nu |
| D5 | 面料微距 + POM 插扣特写 | Nu |
| D6 | 规格与保障（HTML 叠加规格表，承诺区占位） | 全系列 |

---

## F. 提示词（V1.1 — 按 SOP §4.6 可靠性规则重构）

**V1.1 变更**（V1.0 的组合构图违反 §4.6 规则 1/2/4，全部重构）：
1. AI 只出**单主体底图**（14 张，清单见 §F.4）；一切并排/拼图/ lineup 用 Pillow 程序化合成（沿用 `backend/scripts/compose_yd2324.py`、`make_d3_d6.py` 模式，新写 `compose_bag.py`）。
2. **图内零文字**：M3 三条卖点、D1 品牌标、D3 标注、D6 规格表全部走 Pillow/HTML 叠加，底图无字。
3. 禁令内嵌正向 prompt 第 6 段（`negative_prompt` 会被适配器丢弃）。
4. D1 去除人物（实测易露脸），改无人场景。

### F.0 共用身份锁定句

Nu 系列任务前置：
```
Use [img0] as the sole reference for the product appearance. Keep 100% unchanged:
soft rectangular box-shaped bag body, 420D Oxford ripstop fabric with fine grid
texture and matte sheen, roll-top closure folded down and locked by a black
webbing strap with a black POM side-release buckle forming a carry loop,
solid-color body with NO printed graphics or text, shaped stitched bottom,
9.5 cm gusset proportion.
```

ZY 系列任务前置：
```
Use [img0] as the sole reference for the product appearance. Keep 100% unchanged:
soft flat pillow-shaped bag body, 420D Oxford ripstop fabric with fine grid
texture and matte sheen, horizontal black zipper across the top with a black
zipper pull at the left end, fixed arched black webbing handle above the zipper,
solid-color body with NO printed graphics or text.
```

### F.1 共用禁令段（内嵌第 6 段；negative_prompt 会被适配器丢弃，仅存档备用）

```
Absolutely no text, letters, digits, logos, printed graphics, airplane icons or
watermarks anywhere in the image; no extra buckles, no zipper on roll-top models,
no drawstring, no human faces; photorealistic fabric, not cartoon, not 3D render.
```

### F.2 单主体底图提示词（13 张，逐张生成逐张质检）

**G01 / M1 白底 Nu 黄**（1:1 2048²，R1=r1_white）
```
[ Nu 身份锁定句 ]
One half-full orange-yellow bag standing upright, three-quarter front view,
centered, 70% of frame height, generous white margin; pure white seamless
background with only a soft contact shadow; soft studio light upper left 5000K
revealing the ripstop grid texture. [F.1 禁令段]
```

**G02 / M2 挂包场景**（1:1，R2=r2_scene）
```
[ Nu 身份锁定句 ]
The orange-yellow bag clipped by its buckle strap onto the side compression
strap of a hiking backpack, hanging vertically, side-back eye-level view, bag
40% of frame; mossy stream-bank background blurred f/2.8, morning light 5600K,
rim light on roll-top edge; no person visible. [F.1 禁令段]
```

**G03 / M4 卷口插扣特写**（1:1，R1+R4）
```
[ Nu 身份锁定句 ]
Macro close-up of the top closure only: rolled fabric edge, black webbing strap
and black POM side-release buckle clicked shut, buckle centered occupying 60%
frame width; neutral gray gradient background blurred; directional soft light
from right 5000K showing webbing weave and buckle mold lines. [F.1 禁令段]
```

**G04 / M5 绿单色**（1:1，R1 换色）
```
[ Nu 身份锁定句 ]
One half-full army-green bag standing upright, three-quarter front view,
centered, 70% of frame height; pure white seamless background, soft contact
shadow; even studio light 5000K. [F.1 禁令段]
```

**G05 / M5 半透明单色**（1:1，R1 换材质色）
```
[ Nu 身份锁定句 but body fabric is semi-transparent grid ripstop ]
One half-full semi-transparent grid bag standing upright with folded clothes
silhouette softly visible inside, three-quarter front view, centered, 70% of
frame height; pure white seamless background, soft contact shadow; even studio
light 5000K; translucency subtle, not clear PVC. [F.1 禁令段]
```

**G06 / D1 黄昏营地无人场景**（3:4 2048×2731，R2）
```
[ Nu 身份锁定句 ]
The army-green bag standing on a wooden camp table at dusk, rolled top clipped
shut; blurred tent and string-light bokeh background, no people; golden hour
4300K side light, matte fabric sheen; bag 45% of frame height centered.
[F.1 禁令段]
```

**G07 / D2 开卷高态**（3:4，R3=r3_open 去人手）
```
[ Nu 身份锁定句 ]
The orange-yellow bag standing tall with the roll-top fully open and mouth
spread wide, empty interior rim visible, front view centered on pure white
seamless background, 75% of frame height; even 5000K studio light; no hands,
no props. [F.1 禁令段]
```

**G08 / D2 卷矮扣合态**（3:4，R1）
```
[ Nu 身份锁定句 ]
The same orange-yellow bag rolled three turns shorter, squat proportion,
buckle strap clipped shut forming the carry loop, front view centered on pure
white seamless background, 55% of frame height; even 5000K studio light; no
hands, no props. [F.1 禁令段]
```

**G09 / D4 溪边岩石**（1:1，R2）
```
[ Nu 身份锁定句 ]
The army-green bag resting upright on a wet mossy rock beside a shallow
mountain stream, water sparkling blurred behind, no people; daylight 5600K,
droplets on rock, fabric matte; bag 50% of frame centered. [F.1 禁令段]
```

**G10 / D4 皮划艇**（1:1，R2）
```
[ Nu 身份锁定句 ]
The army-green bag strapped in front of a kayak cockpit coaming, bow pointing
away on calm lake water, no people; overcast soft light 6000K; bag 45% of frame
center-left. [F.1 禁令段]
```

**G11 / D4 营地悬挂**（1:1，R2）
```
[ Nu 身份锁定句 ]
The army-green bag hanging by its buckle strap loop from a low tree branch at
a campsite, camp chair blurred behind, no people; late afternoon 4800K light
through leaves; bag 50% of frame centered. [F.1 禁令段]
```

**G12 / D5 面料微距**（3:4，R1）
```
[ Nu 身份锁定句 ]
Extreme macro of the army-green fabric surface only, filling the whole frame,
fine ripstop grid weave and matte sheen, slight fold curve for depth; raking
light 5000K from left; shallow depth of field. [F.1 禁令段]
```

**G13 / ZY 白底黄**（1:1，R=r_zy_yellow）
```
[ ZY 身份锁定句 ]
One orange-yellow zippered pillow bag standing upright, front view centered,
75% of frame height, zipper pull at left end, arched webbing handle above;
pure white seamless background, soft contact shadow; even studio light 5000K.
[F.1 禁令段]
```

### F.3 程序化合成映射（`backend/scripts/compose_bag.py`，V1.3 全实拍源）

| 交付位 | 合成方式 | 素材（均在 `clean/`） |
|---|---|---|
| M1 白底主图 | 直接使用 | clean_sku_M_yellow |
| M2 场景 | 直接使用 | clean_r2_scene |
| M3 促销图 | 绿袋置左 1/3 + 右侧沙色区 Pillow 三行英文字 | clean_sku_M_green |
| M4 插扣特写 | 黄袋插扣区裁切放大 | clean_sku_M_yellow |
| M5 双色并排 | 黄+绿等高拼排+统一阴影（门槛 ≥2 色满足；半透明变体描述区文字说明，不虚构第三图） | clean_sku_M_yellow, clean_sku_M_green |
| D1 营地品牌视觉 | 直接使用（三袋多尺寸场景） | clean_d02_camp |
| D2 卷折差异化 | 单袋（椅旁绿袋）+ Pillow 弧形箭头 + "ROLL 1 TO 3 TURNS" 文字（§6.5 降级条款） | clean_d13_top |
| D3 结构标注 | 黄袋单结构 + Pillow 引线 4 部位英文标注 | clean_sku_M_yellow |
| D4 场景二联 | 挂包 + 营地横向拼 | clean_r2_scene, clean_d02_camp |
| D5 细节双联 | 绿袋面料块裁切放大（上半）+ 黄袋插扣裁切（下半） | clean_sku_M_green, clean_sku_M_yellow |
| D6 规格保障 | 营地三袋（天然三尺寸 lineup）+ 右侧 Pillow 规格表；承诺区占位不渲染 | clean_d02_camp |

**放弃的修复任务**（残迹不可收敛，改由上表替代源覆盖）：d12_macro 飞机印、ZY 款、半透明款 strap 印。AI 生图通道整体停用（G01 三轮质检失败结论不变）。

文字一律 Pillow 绘制（字体用系统无衬线，拼写人工核对），单图文字 >7 处的 D3/D6 同步在 WC 描述区出 HTML 版本。

### F.4 质检追加项（在 SOP §6.2 九项之上）

- 供应商印字复现检查：袋身/织带不得出现飞机图标或任何英文印字（裁切参考图带实物印字，I2I 可能复现）→ 复现即重生成。
- 结构串型检查：Nu 底图不得出现拉链，ZY 底图不得出现插扣卷口。
- 半透明款检查：G05 不得画成全透 PVC 或全不透明。

---

## G. WC 上架配套

### G.1 变体结构

单变体维度「Option」15 值（如 `Nu-M Yellow`、`ZY-2031 Green`），**不用 Color×Size 双维度**——双维度会产生「透明×ZY 码」等不存在的可下单组合（虚构 SKU 红线）。

### G.2 标题与 SEO（草稿，上架前过 RankMath 流程）

- 标题：`Roll-Top Travel Storage Bag - 420D Ripstop Oxford, 6 Sizes, Clip-On Carry Strap`
- Focus keyword：`roll-top travel storage bag`（连续短语）
- SEO description 含 NUOTAO 品牌词与尺寸区间，定性词仅 `moisture-resistant`。

### G.3 定价

全 SKU 统一 $13.99，无 sale_price；门禁（`pricing_policy.evaluate_price`）应在 push 时自动通过（净利 28.5%–30.4%）。

### G.4 alt 文本（≤125 字符，11 图）

| 图 | alt |
|---|---|
| M1 | NUOTAO roll-top travel storage bag in orange-yellow, half-full standing on white, 420D ripstop Oxford body |
| M2 | NUOTAO roll-top storage bag clipped to a hiking backpack strap beside a mountain stream |
| M3 | NUOTAO roll-top storage bag promo: roll-top seal, 420D ripstop Oxford, folds flat |
| M4 | Close-up of the NUOTAO bag roll-top closure with black POM side-release buckle and webbing strap |
| M5 | NUOTAO roll-top storage bag in three colors: orange-yellow, army-green and semi-transparent grid |
| D1 | Hiker carrying the NUOTAO army-green roll-top storage bag clipped to a backpack on a forest trail |
| D2 | NUOTAO roll-top bag shown open-mouth tall and rolled short with buckle clipped, adjustable volume |
| D3 | NUOTAO storage bag family: roll-top buckle model and top-zippper pillow model side by side |
| D4 | NUOTAO roll-top storage bag in four uses: hiking, stream side, kayak and campsite hanging |
| D5 | Fabric and hardware detail of the NUOTAO storage bag: 420D ripstop grid weave and POM buckle |
| D6 | NUOTAO storage bag size range lineup, six sizes from 20x31 cm to 39.2x41.5 cm |

（D3 alt 中 `top-zippper` 为笔误占位，执行时修正为 `top-zipper`。）

---

## I. 执行记录 V1.2（2026-10-07）：G01 三轮质检失败与路线变更提案

### I.1 G01 三轮质检记录（§6.5 触发：连续 3 次不过 → 停止重试）

| 轮 | 修复动作 | 质检结果 |
|---|---|---|
| 1 | 首版提示词 | ❌ 顶部画拉链（ZY 串型）+ 插扣织带成腰部环带 + 无格纹 + 竖长 |
| 2 | 锁定句补「插扣仅在卷口顶、无拉链、无腰带、格纹可见」 | ❌ 拉链/腰带消除、格纹微弱；仍竖长、卷口折边横带缺失 |
| 3 | 锁定句改「宽=1.3×高、顶部 2–3 圈折边横带」 | ❌ 仍竖长、折边横带缺失、插扣带又移到上 1/3 横带位 |

共耗 ¥0.24。稳定项：零文字零印字、白底干净、无手部畸形。

### I.2 根因

agnes-image-2.5-flash 对「卷口折边横带 + 顶部提手环 + 横向宽高比 + 格纹」四特征并存的 I2I 指令遵循不足；逐轮加约束边际收益为零（特征间相互挤占：修拉链丢折边、修折边丢比例）。与 YD2324 时代「轮毂表盘幻觉」同类，但本品特征数更多。

### I.3 路线变更提案（待 Owner 决策）

**B 路线：实拍去印 + 程序化合成**（替代 AI 生图主力）
- 供应商素材场景已全覆盖：detail05 四场景宫格、detail06 挂树、detail02 营地、main2 挂背包、detail10 六款全家福、detail11/12 细节微距。
- 用 doc-image-scan 技能去除袋身飞机印字/织带 Life 印字/中文标签与标注线，保留真实结构。
- M3/D3/D6 文字仍走 Pillow/HTML 叠加；11 张交付图全部可由此产出。
- 优势：结构 100% 真实（§6.2 第 1 项天然通过）、无 AI 漂移返工；劣势：场景光影受素材限制、去印痕迹需逐张目检。
- AI 生图降级为可选补充（如去印痕迹不可接受时的单点重绘）。

**A 路线（现状）**：继续 AI 生图 + 人工介入调参——已证明 3 轮无收敛，不推荐。

---

## H. 执行清单与阻塞项

1. [ ] Owner 确认 §0 四项决策（阻塞生图提交）
2. [ ] 参考图裁切预处理（main2/3/4、review1、sku_S2539_yellow 去文字/标注线）
3. [ ] 生图 11 张 → 单图质检（SOP §6.2）→ 整体质检（§6.3）→ 多样化矩阵核对（§6.4）
4. [ ] 人工审批（§6.6）
5. [ ] WC 建品：单维度 15 变体、统一定价 $13.99、D3/D6 HTML 叠加、alt 按 §G.4
6. [ ] 上架后缓存纪律双重核验（SOP §7.9.5：cache-buster + no-store，连续两次 miss 确认）
7. [ ] 实测压缩态计费重 → 回调尾程假设 → 重跑 `pricing_policy` 复核售价
8. [ ] 供应商报价单到后分档定价评估

**阻塞项**：§0 决策 1/2 未确认前，禁止提交生图与建品（占位符机制 §3.2.3）。
