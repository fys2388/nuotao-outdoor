# YD2324 户外多功能伸缩露营灯 — WooCommerce 商品图生产方案

> 版本：**V1.1**（2026-10-06，图片核验修订版）
> V1.0 → V1.1 变更：① 灯瓣数量 4→**3**；② Type-C 口位置改为**端盖 recessed**；③ 补入喇叭形底座/可拆灯罩/金属挂环/双按钮；④ 露营光改为**暖黄光**；⑤ 尺寸口径定案（25.2/51.8cm 图证）；⑥ D6 删除售后政策块（Owner 决策：商城统一政策页承载）；⑦ 参考图回填本地路径。
> 执行 SOP：`docs/ai_image_generation_sop_wc.md` V3.1
> 适用 Agent：marketing_manager
> 商品来源：https://detail.1688.com/offer/966534719581.html （宁海县易哲电器厂）
> 参考图资产：`woo_images/yd2324_refs/`（19 张，清单见 `_manifest.json`）

---

## 0. Owner 决策记录（2026-10-06）

| # | 决策 | 影响 |
|---|------|------|
| 1 | 参考图走已配置的 1688 采购链路获取 | 排查后查明：已购接口 `alibaba.product.simple.get` 仅能查**已购买商家**的商品（本商品商家未采购过，业务级受限），选品取图不适用。已改用浏览器渲染通道抓取 CDN 图并本地化（详见 §H B1，已闭环） |
| 2 | **售后政策（退货/保修/免邮/客服）不在产品图体现**，商城页有统一政策展示 | D6 删除全部政策占位符，改为纯规格+模式汇总；SOP §7 同步记录该决策 |
| 3 | 尺寸口径以产品图标注为准 | 已核验闭环（§C），无需再向供应商确认 |

---

## A. 信息提取

### A.1 文字层（页面属性表 / 卖点 / 评价）

| 项 | 值 | 出处 |
|---|---|---|
| 品名 | 户外多功能伸缩露营灯调节270度落地补光氛围灯高亮照明强光手电 | 标题 |
| 品牌/型号/货号 | YIZHE / YD2324 / 2324 | 属性表 |
| 电气 | 5V / 2W / LED 光源 / 充电电源 / 按压开关 | 属性表 |
| 材质 | ABS+PC（属性表）；抗摔ABS+金属挂环（详情参数表） | 双出处 |
| 颜色 | 黑+白+金属灰（**单 SKU，三色拼接**） | SKU 区 |
| 规格 | 高25cm*直径4cm（= 收纳态圆整值，见 §C） | 属性表 |
| 重量 | 290 g | 包装信息 |
| 认证 | 专利：无 / 外贸出口认证：无 / 质检报告编号：无 | 属性表 |
| 卖点句 | 270°调节灯瓣 / Type-C快充防水 / 51.8cm伸缩灯杆 | 卖点区 |
| 评价 | 5.0 分 40+ 条；唯一长评：「可以立在桌子上，可以当手电筒，可以随意转换角度，亮度够用，充电续航能力挺强的」 | 评价区 |

### A.2 图片层（19 张本地核验，V1.1 新增）

| 图 | 内容 | 关键证据 |
|---|---|---|
| main1/detail02 | 手持手电模式 | 「白激光灯芯」「伸缩变焦-远近照明」；光束为**冷白** |
| main2/detail03 | 灯瓣展开 | 「**三灯瓣结构** 可270°调节」，270°/90° 弧线标注 |
| main3/detail07 | 三形态尺寸图 | 「4节伸缩灯杆 可升至51.8cm」；**25.2cm / 51.8cm** 标尺 |
| main4/detail09 | 充电口特写 | 「隐藏式充电口 Type-C快充 **防尘防水溅**」；口在**圆形端盖**上 |
| main5 | 手持近景 | 同 main1 构图变体 |
| detail01 | 三形态+卖点列表 | 露营灯/手电筒二合一、4节自由伸缩灯杆、270°、Type-C、**隐藏式挂钩**、**可拆卸灯罩** |
| detail04/05 | 暗场景暖光 | 三瓣展开为**暖黄光**（无字干净图，最佳 i2i 参考） |
| detail06 | 帐篷内吊挂+灯罩 | 「可搭配灯罩使用」暖光氛围场景 |
| detail08 | 工坊工作台场景 | 全展开立姿**无字干净图**（M1 最佳参考） |
| detail10 | 细节四宫格 | 暖光露营灯 / **双开关设计** / **金属挂环** / **可拆卸灯罩** |
| detail11 | **官方尺寸图** | 收纳 **252mm**、展开 **518mm**、身径 **42mm**、灯罩径 **100mm** |
| detail12 | **参数表** | 光源＝白激光灯芯+54*LED；手电＝强/弱/爆闪；露营灯(**暖黄光**)＝强/弱；Type-C；抗摔ABS+金属挂环；防水＝**生活级防水** |
| review1/2 | 买家实拍 | 真实使用形态佐证 |

---

## B. 图证核验修正记录（V1.0 错误清单）

> 本节是 SOP V3.1「Step 1.4 图证核验」强制门的来源案例：V1.0 仅凭文字层写提示词，4 处硬伤全部由看图发现。

| # | V1.0 写法 | 图证事实 | 修正 |
|---|----------|---------|------|
| 1 | 「four folding light panels」 | 三灯瓣结构（main2/detail03 文字+图形双重证据） | **three** panels |
| 2 | Type-C 在灯杆/机身侧面 |  recessed 于**圆形端盖**（main4/detail09） | 端盖描述 |
| 3 | 漏写底座/灯罩/挂环/按钮 | 黑色喇叭形底座、可拆黑色锥形灯罩、金属挂环、银色机身双圆按钮 | 全部补入身份锁定句 |
| 4 | 露营光写中性白 | 露营灯模式为**暖黄光**（detail04/05/10/12） | warm white；手电为冷白 |

---

## C. 尺寸口径结论（已闭环）

- 属性表「高25cm*直径4cm」＝**收纳态圆整值**；图证精确值：收纳 **252mm**、展开 **518mm**、身径 **42mm**、灯罩径 **100mm**（detail11），与 main3/detail07 的 25.2cm/51.8cm 一致。
- 上架口径：`dimensions.height = 25.2 cm`（收纳/发货态），展开高 51.8cm 只进文案与 D3 图，**不进 dimensions 字段**（体积重按发货态计）。
- 直径口径：身径 4.2cm；带灯罩最大径 10cm。D3 图四个尺寸全标。

---

## D. 卖点分层与合规闸门 V1.1

### D.1 主视觉主线（不变）

「一盏灯，三种形态」：落地灯 / 吊灯（加灯罩）/ 手电筒。评价原话佐证。

### D.2 合规闸门（逐条三态）

| 文案 | 判定 | 证据 |
|---|---|---|
| THREE ADJUSTABLE PANELS · 270° | ✅ | main2/detail03 |
| 4-SECTION TELESCOPING POLE · UP TO 51.8 CM | ✅ | main3/detail07/detail01 |
| USB-C FAST CHARGING | ✅ | detail01/main4 |
| SPLASH-RESISTANT · DUST-PROTECTED | ⚠️ **降级：定性可，定量不可** | 「防尘防水溅」main4；「生活级防水」detail12。**仅供应商自我宣称，无 IP 等级、无测试报告**。依 FTC 广告证实原则（发布前须有 reasonable basis），D6 规格表**不写此行**；如需在营销文案使用，须先取得供应商书面测试依据 |
| WHITE-LASER LED + 54 LEDs | ❌ **禁止（FDA 风险）** | detail12 参数表原文写「白激光灯芯+54LED」。**但**：含激光组件的产品进入美国受 FDA CDRH 依 21 CFR 1040.10/1040.11 强制监管，无豁免；该产品「外贸出口认证：无」「质检报告编号：无」。在商品页自我宣称 laser 等于自证受管制产品却无合规文件 → 扣货/召回/民事处罚风险。改述为 `LED LIGHT SOURCE`（属性表「光源类型：LED光源」有据） |
| FLASHLIGHT: HIGH / LOW / STROBE；LANTERN (WARM): HIGH / LOW | ✅ | detail12 |
| 290 G | ✅ | 包装信息 |
| DETACHABLE SHADE · METAL HANGING LOOP · TWIN BUTTONS | ✅ | detail01/detail10 |
| WATERPROOF / IPX4 / IPX6 / RAINPROOF | ❌ | 仅有「生活级防水/防水溅」，无 IP 等级 |
| 流明值 / 续航小时数 / 电池 mAh | ❌ | 全页面无任何数值 |
| CE / FCC / ROHS / PATENTED / 质检徽章 | ❌ | 属性表三项均「无」 |
| WARRANTY / FREE SHIPPING / RETURNS / SUPPORT 时限 | ❌（**移出产品图**） | Owner 决策 2：商城统一政策页承载 |
| SUPER BRIGHT / ULTRA BRIGHT | ❌ | 无流明依据 |

---

## E. 视觉策略：4 主图 + 6 详情图（含参考图映射）

| ID | 内容 | 参考图（本地） | 文字策略 |
|---|---|---|---|
| M1 | 黄昏营地全展开立姿 hero | detail08（无字） | 无字 |
| M2 | 手持手电模式冷白光束 | main1（含字→指令忽略） | 无字 |
| M3 | 暗场景三瓣暖光 270° | detail04（无字） | 无字 |
| M4 | 端盖充电口+双按钮+挂环+灯罩 细节拼贴 | main4（含字→指令忽略） | 无字，HTML 叠标签 |
| D1 | 三形态并列（落地/半升/全升开瓣） | main3（含字→指令忽略） | 无字 |
| D2 | 光色与模式四宫格（冷光束/暖强/暖弱/开瓣氛围） | detail04 | 无字，HTML 叠标签 |
| D3 | 尺寸双视图（无字底图） | detail11 | **无字**；尺寸文字走 HTML 叠加（公制+英制） |
| D4 | 结构与充电四宫格（ recessed USB-C/双按钮/挂环/灯罩） | main4 | 无字，HTML 叠标签 |
| D5 | 三场景（帐篷吊挂加罩/工坊工作台/夜径手持） | detail06 | 无字 |
| D6 | 产品抠图（无字底图） | detail12 | **无字**；规格表走 HTML（6 行，无激光/防水/政策文案） |

---

## F. 提示词（V1.1）

### F.0 共用身份锁定句（所有任务第 1 段原样前置）

```
Product identity lock: NUOTAO OUTDOOR telescoping camping lantern, exact replica of the reference image. Extended top-to-bottom: (1) head with exactly THREE rectangular light panels (black frames, frosted white diffusers) hinged on a central black hub, foldable from a closed column to open 270 degrees; (2) slim black four-section telescoping pole; (3) gunmetal-silver cylindrical body with exactly TWO round black buttons on its side; (4) wide black conical trumpet base it stands on. Detached flashlight head: black cylinder with a bright LED lens and silver bezel ring at the end opposite the panels. Accessories: detachable black conical lamp shade, thin metal hanging loop. USB-C charging port recessed in the round end face beside the pole joint. Colors limited to black, gunmetal silver, frosted white. Never change panel count, button count, base shape, colors or proportions. Ignore any text, watermark or logo present in the reference image.
```

### F.1 共用 negative_prompt

```
Chinese characters, any text, watermark, logo, brand name, extra light panels, four panels, extra buttons, wrong proportions, deformed pole, floating objects, extra accessories, IP rating badges, certification marks, lumen numbers, battery capacity numbers, after-sales policy statements, laser text, laser beam effects, waterproof claims, water resistance labels, price tags, barcode, QR code, human faces in close-up, mutilated hands, oversaturated glow, lens flare artifacts, plastic toy look
```

### F.2 主图

**M1 hero**（ref `detail08.jpg`）
```
<身份锁定句>
Scene: dusk campsite, lantern fully extended standing on its trumpet base on a weathered wooden table, three panels open at 120 degrees glowing warm white, soft tent bokeh and string lights behind, cool blue dusk sky balancing the warm glow, light spill on wood grain. Exactly ONE product in the whole frame: the detachable shade, the hanging loop and any other object must NOT appear as separate items on the table or anywhere in the scene. Commercial hero photography, 85mm, f/2.8, product 70% of frame, centered, no text.
```

**M2 flashlight**（ref `main1.jpg`）
```
<身份锁定句>
Scene: night forest trail, hand holding the detached flashlight head (panels folded into a column), cool white zoom beam cutting through light fog onto a rock 3 meters ahead, beam core bright with soft halo, background dark green foliage bokeh. Action product photography, 50mm, f/2.0, no text.
```

**M3 panels warm**（ref `detail04.jpg`）
```
<身份锁定句>
Scene: dark studio, head unit with three panels fully open in a 120-degree tripod fan, panels glowing warm white, black background with subtle warm reflection on a matte black surface below, rim light tracing panel frames. Studio macro product photography, no text.
```

**M4 detail collage**（ref `main4.jpg`）
```
<身份锁定句>
Layout: 2x2 macro collage on light gray studio background, equal tiles, thin white gutters. Tile 1: round end face with recessed USB-C port beside pole joint. Tile 2: gunmetal body side with the two round black buttons. Tile 3: metal hanging loop close-up. Tile 4: detached black conical lamp shade next to the head. Even soft studio light, crisp edges, no text.
```

### F.3 详情图

**D1 three forms**（ref `main3.jpg`）
```
<身份锁定句>
Layout: clean white studio, three configurations left to right on one ground line: (a) collapsed 25.2 cm standing on trumpet base with panels closed as a column; (b) mid-extended pole with panels closed; (c) fully extended 51.8 cm with three panels open 120 degrees. Same scale, soft shadows, catalog cutout style, no text, no dimension lines.
```

**D2 light modes**（ref `detail04.jpg`）
```
<身份锁定句>
Layout: 2x2 grid on dark charcoal background, equal tiles. Tile 1: detached flashlight head firing cool white beam across frame. Tile 2: lantern head, panels open, warm white at high brightness. Tile 3: same at low warm brightness, cozy dim glow. Tile 4: full lantern extended on base, panels open, warm ambient pool of light on dark ground. Consistent camera angle, no text.
```

**D3 dimensions（无字底图，尺寸文字走 HTML 叠加）**（ref `detail11.jpg`）
```
<身份锁定句>
Layout: clean technical cutout sheet, pure white background, two orthographic product views side by side with even spacing: left = collapsed state with the black conical shade attached on top, right = fully extended state with three panels open 120 degrees. Both views in the same scale, soft contact shadows only, catalog cutout style. Absolutely no text, no numbers, no dimension lines, no arrows anywhere in the image.
```

> **D3 改无字的实证依据（V1.2）**：试跑 T2 实测发现该生图后端的图内数字不可靠——把 4.2cm 写成 3.2cm、把 51.8cm 写成乱码「52:4.C(m」。因此尺寸文字一律改由描述区 HTML 承载：`<figure>` 内放无字双视图，下方以 `<ul>` 列出四项尺寸（公制+英制）。文字 100% 准确、可被屏幕阅读器读取、改文案无需重新生图。
>
> **双单位说明**：商城定位欧美 DTC，美国消费者对英寸的直觉远强于厘米，尺寸与规格文案一律「公制 + 英制」并列。换算按 1 in = 2.54 cm 四舍五入到 0.1 in。英制值仅为换算展示，**不构成新的实测宣称**。
>
> **HTML 叠加规格（D3）**：
> ```html
> <figure class="dims">
>   <img src="{{D3}}" alt="..." width="864" height="1152" loading="lazy" style="width:100%;height:auto">
>   <ul class="dim-list">
>     <li>Collapsed height: 25.2 cm (9.9 in)</li>
>     <li>Extended height: 51.8 cm (20.4 in)</li>
>     <li>Body diameter: 4.2 cm (1.7 in)</li>
>     <li>Shade diameter: 10 cm (3.9 in)</li>
>   </ul>
> </figure>
> ```

**D4 build & charging**（ref `main4.jpg`）
```
<身份锁定句>
Layout: 2x2 macro tiles on light gray background. Tile 1: recessed USB-C port in round end face, rubber flap hint, dust-protected look. Tile 2: twin round buttons with power and torch icons. Tile 3: metal hanging loop folded flush into the top cap. Tile 4: lamp shade being fitted over the head, slight gap showing detachability. Studio macro, shallow depth of field, no text.
```

**D5 scenes**（ref `detail06.jpg`）
```
<身份锁定句>
Layout: vertical triptych, three equal horizontal bands. Band 1: inside a tent at night, lantern hanging from the roof loop with shade attached, warm glow on a person reading (face in shadow, not identifiable). Band 2: workshop bench at dusk, lantern fully extended standing, warm light on tools and wood. Band 3: night trail, hand holding detached flashlight head, cool beam ahead. Cinematic lifestyle photography, consistent warm-cool palette, no text.
```

**D6 product cutout（无字底图，规格表走 HTML）**（ref `detail12.jpg`）
```
<身份锁定句>
Layout: single product cutout, seamless off-white studio background, lantern fully extended with three panels open 120 degrees standing on its trumpet base, centered, soft contact shadow, catalog packshot style. Absolutely no text, no numbers, no table, no badges anywhere in the image.
```

> **D6 改无字的依据（V1.2）**：同 D3，图内文字在该后端不可靠；且规格表是信息密度最高的文本块，必须走 HTML 才能同时保证准确、可读、可访问。描述区 HTML 规格表只含以下 6 行（**无激光措辞、无防水宣称、无政策文案**）：
> Light source: LED / Flashlight: high-low-strobe / Lantern (warm white): high-low / Charging: USB-C fast charge / Body: ABS + PC, metal hanging loop / Weight: 290 g；另加尺寸行 25.2 cm collapsed, 51.8 cm extended（9.9 in / 20.4 in）。

> **D6 文案修订说明（V1.2）**：
> - ❌ 删除 `white-laser LED + 54 LEDs`：供应商参数表虽写「白激光灯芯」，但含激光组件产品进入美国受 FDA CDRH 强制监管（21 CFR 1040.10/1040.11，无豁免），而该产品「外贸出口认证：无」「质检报告编号：无」。在商品页自我宣称 laser 属高风险。改述为 `Light source: LED`（属性表「光源类型：LED光源」有据）。
> - ❌ 删除 `Water resistance: splash-resistant, dust-protected`：仅供应商自我宣称，无 IP 等级与测试报告，依 FTC 广告证实原则发布前须有 reasonable basis。待取得书面测试依据后再议。
> - ⚠️ `impact-resistant ABS` 改为 `ABS + PC`：「抗摔」属性能宣称无测试依据，改用属性表确证的材质名。

---

## G. WC 上架配套

| 图 | 文件名 | alt（≤125 字符） |
|---|---|---|
| M1 | nuotao-telescopic-camping-lantern-hero.webp | NUOTAO telescopic camping lantern fully extended, three panels open, warm glow on a campsite table at dusk |
| M2 | nuotao-camping-lantern-flashlight-mode.webp | Detached flashlight head of the NUOTAO telescopic camping lantern casting a cool white beam on a night trail |
| M3 | nuotao-camping-lantern-270-degree-panels.webp | Three adjustable panels of the NUOTAO telescopic camping lantern opened 270 degrees, glowing warm white |
| M4 | nuotao-camping-lantern-details-usbc-buttons.webp | Details of the NUOTAO telescopic camping lantern: recessed USB-C port, twin buttons, hanging loop, detachable shade |
| D1 | nuotao-camping-lantern-three-forms.webp | NUOTAO telescopic camping lantern in three forms: collapsed 25.2 cm, mid-extended, fully extended 51.8 cm |
| D2 | nuotao-camping-lantern-light-modes.webp | Light modes of the NUOTAO camping lantern: cool white beam, warm lantern high and low, open-panel ambient glow |
| D3 | nuotao-camping-lantern-dimensions.webp | Dimension diagram: NUOTAO telescopic camping lantern, 25.2 cm collapsed, 51.8 cm extended, 4.2 cm body diameter |
| D4 | nuotao-camping-lantern-build-charging.webp | Build details: recessed USB-C port, twin buttons, metal hanging loop and detachable shade of the lantern |
| D5 | nuotao-camping-lantern-scene-triptich.webp | NUOTAO camping lantern hanging in a tent with shade, standing on a workshop bench, held as a flashlight at night |
| D6 | nuotao-camping-lantern-spec-summary.webp | Spec summary of the NUOTAO telescopic camping lantern: light source, modes, charging, materials, weight, size |

- `dimensions.height = 25.2`（收纳态）；展开高仅文案与 D3。
- 售后政策：产品页不写，链到商城统一政策页（Owner 决策 2）。

---

## H. 执行清单与阻塞项

| # | 项 | 状态 |
|---|---|---|
| B1 | **1688 开放平台 API**：已查明并处置完毕。三层问题逐一解决——① 代码方法名错误（`alibaba.product.get` 未订购 → 改用已购的 `alibaba.product.simple.get`，已修 `sourcing_1688_service.py` 并补 `API_METADATA`）；② 能力未关联 AppKey（已在控制台关联，2026-10-06 10:42:36，零费用）；③ 关联生效后接口返回业务级「由于权限受限，你不能获取该商品的信息。」——该接口语义为**只能查已购买商家的商品**，YD2324 商家未采购过，属接口数据范围限制，**非故障**。已修复假成功缺陷（业务级 errMsg 现正确返回 `success=False, error_kind=business_restricted`）。**结论：本商品取图确定走浏览器渲染通道（路径 B），API 路径留待已采购供应商的数据同步场景使用** | ✅ 已闭环 |
| B2 | 本机 `HTTP(S)_PROXY=127.0.0.1:7897` 代理进程未运行，导致 httpx 默认环境直连报 10061；`fetch_1688_images.py` 未设 `trust_env=False`，在当前环境下不可用（登记 TODO(tech-debt)） | ⚠️ 已知，绕行方案见 SOP 附录 B |
| B3 | 参考图已本地化（19 张），`reference_image` 填本地路径；若生图网关只收公网 URL，需先上传媒体库再回填 | ✅ 本地就绪 / ⚠️ 视网关而定 |
| B4 | D6 政策占位符 | ✅ 已按 Owner 决策 2 移除，无阻塞 |
| B5 | 尺寸口径 | ✅ 已闭环（§C） |

生图执行顺序：M1→M4（主图过审后再跑 D1→D6）；每图过 SOP V3.1 §8 六项 QC。

---

## I. 执行复盘（V1.2→V1.5，2026-10-06）

### I.1 成本账

| 阶段 | 张数 | 单价 | 小计 |
|------|------|------|------|
| 通道能力探测 | 4+2+3+2 | ¥0.08 | ¥0.88 |
| V1.2 首轮 10 张 | 10 | ¥0.08 | ¥0.80 |
| V1.3 重生成 7 张 | 7 | ¥0.08 | ¥0.56 |
| V1.4 单主体 16 张 | 16 | ¥0.08 | ¥1.28 |
| V1.5 批次（裁切参考+局部锁） | 15 | ¥0.08 | ¥1.20 |
| **累计** | **54** | | **≈¥4.72** |

单图成本极低（¥0.08），允许「生成→看图验收→定向重生成」的迭代闭环；真正昂贵的是**人工/AI 验收的轮次**，故 V1.5 把失败根因前置到参考图与锁定句层面解决。

### I.2 通道教训（已固化入 SOP V3.2 §4.6）

1. **negative_prompt 被 agnes 适配器静默丢弃**——禁令必须内嵌正向 prompt；
2. **3:4 小尺寸请求被降级为 864×1152**——详情图必须请求 2048×2731；
3. **文字渲染不可靠**（3/3 出乱码错值）——图内零文字，文字全部 Pillow 后处理（D3 工程图、D6 规格表）；
4. **多主体组合指令遵循率极低**——AI 只产单主体，组合程序化；
5. **I2I 会复制参考图里的文字与部件**——D6 底图曾整张复制 1688 的中文规格表；参考图必须是**已验收的无文字单主体裁切图**，无参考需求用 T2I；
6. **整产品身份锁会污染部件图**——部件图用局部锁定句（只描述该部件 + 显式 NO 其余部件）；
7. **免费额度 429**——任务间冷却 35s + 退避重试；
8. **产物下载会瞬时断连**——下载带 3 次重试。

### I.3 参考图裁切资产（已逐张验收）

`woo_images/yd2324_out/_parts/ref_*.png`：endcap（main5 下半）、hand_torch（main2 左下）、form_col / form_mid / form_ext（main4 / main1 白底三态）、shade_form（main1 左形态）、body_btn（main4 左机身）、loop_top（main1 灯罩顶）。裁切坐标经看图验收，残留尺寸线/邻位产品用背景色抹除。

### I.4 复盘四问结论

1. 三灯瓣/双按钮/喇叭底座零漂移？——**V1.5 批次已逐张验收通过**（10/10）；V1.4 及之前因整产品锁污染部件图存在漂移，已用局部锁修复策略解决。
2. 暖光/冷白区分？——D2 已过审，一眼可辨（冷白光束 vs 暖黄氛围）。
3. D3 数字一致？——程序化绘制，100% 一致（9.9/20.4/1.65/3.9 in）。
4. 中文/政策文案泄漏？——AI 图内零文字策略下无泄漏；唯一一次泄漏（D6 复制中文表）根因已定位并用 T2I 修复。

---

## J. 上架后文案整改（2026-10-06，商品 2230）

### J.1 整改项与结果

| # | 问题 | 处置 | 核验 |
|---|------|------|------|
| 1 | 标题含 `Waterproof`（无 IP 等级依据）、`High Brightness`（无流明依据）；tags 含 `waterproof`；slug 含 `high-brightness-waterproof` | 标题改为合规版，删除 `waterproof` 标签，新增 `retractable` / `telescoping`；slug 合规化见 J.2 | ✅ 公开页可见文案扫描：waterproof / high brightness / splash-resistant / laser / lumen **全部零命中** |
| 2 | RankMath SEO 评分 11/100：`rank_math_title` / `rank_math_description` / `rank_math_focus_keyword` **三项从未设置**；描述区纯文本仅 **21 词**（6 个 h2 + 图片，无正文） | 写入三项 SEO 字段；为 6 个 section 各补一段正文（**保留原 6 张详情图不动**） | ✅ `<title>`、`<meta description>`(159 字符)、og:title 均已生效；描述区可见文本 **21 → 504 词** |
| 3 | 页面源码含 31 处中文 CSS/JS 注释 | **未修改**，见 J.3 | — |

**新标题**：`Retractable LED Camping Lantern - 270° Adjustable Panels, 4-Section Telescoping Pole, USB-C Rechargeable`
**SEO title**（52 字符）：`Retractable LED Camping Lantern | USB-C Rechargeable`
**SEO description**（159 字符）：`NUOTAO retractable LED camping lantern: 270° adjustable panels, 4-section pole from 9.9 to 20.4 in, USB-C rechargeable, three modes for tent, trail, workbench.`
**Focus keyword**：`retractable camping lantern`

正文 6 段（85/96/73/75/80/74 词）全部只用 §D.2 闸门表中标记 ✅ 的事实，禁用宣称自检零命中后才写入。

### J.2 slug 与 Color 整改（2026-10-06 二次授权，已完成）

> 首版 J 曾将这两项列为「有意未改、待决策」，Owner 已授权处理，结果如下。

| 项 | 原值 | 新值 | 核验 |
|---|------|------|------|
| slug | `...high-brightness-waterproof`（含两处禁用词） | `retractable-led-camping-lantern-270-adjustable-usb-c-rechargeable` | ✅ 新 URL HTTP 200；**旧 URL 稳定 301 → 新页**（连续 3 次，即便 `x-litespeed-cache: hit` 也未退化为 200）；sitemap 旧 slug 清零、新 slug 已收录；canonical 指向新页 |
| Color 属性 | `['Black', 'White', 'Metal Gray']`（三个并列值，易被误读为可选配色） | `['Black + White + Metallic Gray (single finish)']`（单值，明确同一支灯的材质拼接） | ✅ 附加信息表已渲染新值，旧三值消失；`variation=False` 未变，不生成变体选择器 |

**301 通道结论**：RankMath Redirections REST 端点返回 404（模块未启用/无路由），实际依赖 **WordPress 核心 `_wp_old_slug` 自动 301**（`wp_old_slug_redirect()`，对 product post type 同样生效）。已实测生效，无需额外配置重定向。

**写入安全措施**：PUT attributes 提交完整 11 项数组（防丢失其他属性）；slug 写入后立即实测新 URL 可达性，不可达则自动回滚；改前完整备份商品 JSON。

### J.3 #3 中文注释定位结论（未修改）

**证据链**：
- 中文注释分布在 **5 个内联块**（4 个 `<head>` + 1 个 `<body>`），**均无 id 或任何属性**；
- `id="wp-custom-css"` 块确实存在（19729 字符），但**含中文 0 处**（内容是 `/* Nuotao Deep Green Color System Override */` 配色系统）→ **排除** Additional CSS；
- 站点 13 个插件**全部为第三方**，无 nuotao 自研插件；
- 主题为 `hello-elementor`；后台 Theme File Editor / Plugin File Editor 返回 500/403，Elementor Custom Code 页返回 403；
- REST 中 `elementor_snippet`、`custom_css`、`wpcode` 类型均不存在（404）。

**结论**：代码由某个 PHP `wp_head` / `wp_footer` hook 输出，存储位置在当前可用通道（REST + 浏览器后台）**均不可定位、不可写**。浏览器自动化曾推断其在 Additional CSS，该推断已被上述实测**推翻**，不采信。

**风险评估：低，建议暂缓**
- 全部位于 CSS 注释 `/* */` 与 JS 行注释 `//` 内，**不渲染、访客不可见、不影响 SEO 评分**（搜索引擎只索引可见内容与 meta）；
- 这 5 个块承担**站点级视觉与交互**：产品卡片正方形裁切、画廊布局、缩略图高亮、模块排序、sticky 加购栏；
- 无法先备份源码就无法安全改写，盲改会破坏整站视觉。**收益（洁癖）远低于风险（整站样式回归）**。

**建议后续**：取得服务器 SSH/SFTP 或插件文件编辑权限后，先完整备份再改写；或在下一次主题/插件维护时一并处理。已按 AGENTS.md §5 登记为 `TODO(tech-debt)`。

### J.4 本次整改成本

零生图成本。仅文案改写 + 4 次只读调查 + 1 次写入 + 1 次核验。备份文件：`.tmp_attach/_backup_p2230_before_copyfix_*.json`（含完整字段，可回滚）。

### J.5 SEO 三轮整改（RankMath 11 → 57 → 76）

**评分机制认知修正**：RankMath 分数由编辑器**前端 JS 实时计算**，**没有刷新按钮**（首轮浏览器自动化因此反复找按钮触发熔断）。API 写入后重新打开编辑页即得新分。此前我说"API 侧触发不了、需人工点 Score 刷新"是错的。

| 轮次 | 分数 | 改了什么 | 根因 |
|------|------|---------|------|
| 起点 | **11** | — | `rank_math_title/description/focus_keyword` 三项**从未设置**；描述区纯文本仅 **21 词**（只有 6 个 h2 + 图片） |
| 第一轮 | 11 → **12** | 写入三项 SEO 字段 + 6 段正文（21→504 词） | **基本无效**：focus keyword 是 `retractable camping lantern`，我却把 `LED` 插进短语中间（`Retractable LED Camping Lantern`），导致 title/desc/URL 三处**短语不连续**全部判失败 |
| 第二轮 | 12 → **57** | title/desc 改为关键词短语开头且连续；首段以短语开头；补写至 748 词 | Basic SEO 只剩「URL 无关键词」1 项失败 |
| 第三轮 | 57 → **76** | slug 缩至 `retractable-camping-lantern`（27 字符）；首图 alt 以短语开头；新增内链 section（6 个站内链接）；拆分超长段；密度 0.26%→0.47% | Basic SEO 与 Title Readability **两组全绿** |

**核心教训（已固化入 SOP §7.9.4）**：RankMath 要求 focus keyword 作为**连续短语**出现，插入任何词都判失败。第一轮白做就是这个原因——写 SEO 字段前必须先确认关键词短语在 title/desc/URL/正文开头四处**逐字连续**。

**slug 三次变更的重定向链**（均实测 301 生效，含 LiteSpeed `cache: hit` 状态下连续 3 次稳定）：

```
v1 ...led-floor-lamp-high-brightness-waterproof
v2 retractable-led-camping-lantern-270-adjustable-usb-c-rechargeable
v3 retractable-camping-lantern   ← 当前
v1 → v3 ✅ 301      v2 → v3 ✅ 301
```

教训：slug 应一次改到位。反复变更会叠加重定向链，对爬虫不友好。

**内链目标**（写入前逐个验证 HTTP 200）：`/shipping-delivery/`、`/refund-returns-policy/`、`/faq/`、`/contact-us/`、`/product-category/camping-lights/`、`/product-category/camping/`。政策页以**链接**形式出现而非复述承诺，符合 J.1 的 Owner 决策 2。

**剩余 4 项失败——判定为不再处理**：

| 失败项 | 理由 |
|--------|------|
| Keyword Density 0.47 偏低 | 追到 1%+ 需堆砌关键词，损害可读性且违反 §3.2 反堆砌原则。0.4–0.6% 对电商产品页已属自然 |
| No outbound links / DoFollow outbound | 产品页外链把权重导给外部站点，且无自然目标，对转化无益 |
| Use Content AI | RankMath 付费功能推销提示，非内容质量问题 |
| Table of Contents plugin | 商品页装目录插件不合理，且需安装插件（超出文案整改范围） |

**过程缺陷记录**（均已修复）：
1. 段落拆分函数用固定长度 `len("<h2>...</h2>\n")` 回退切片，而正则匹配的是 `\s*`，空白长度不一致会**切错位置损坏内容**。dry-run 时 section 计数 7→7（应为 8）暴露了它，改为整块匹配替换。
2. 预览打印 bug：section/img 计数两边都取了改后的值，看不出变化。改为与原始描述对比。
3. 第二轮加词到 829 词时密度反被稀释到 0.24%（低于原 0.26%），属于**引入退步**，第三轮在内链段落自然增补关键词修正到 0.47%。

**写入纪律**（每轮均遵守，见 SOP §7.9.2）：备份完整 JSON → 内链目标验证 200 → dry-run 预览 → 禁用宣称自检零命中 → 写入 → 双重核验。PUT attributes 时提交完整 11 项数组，三轮下来属性数量始终 11 未丢失。

备份文件：`_backup_p2230_before_seofix_*.json`、`_backup_p2230_before_seo3_*.json`、`_backup_p2230_before_slug_color_*.json`。

---

## K. 定价违规修复（2026-10-06，Owner 授权）

### K.1 问题：商品在亏本销售

线上 `regular_price=$6.25` / `sale_price=$5.83` / 生效价 **$5.83**，采购成本 ¥45。按项目汇率 0.14 换算采购价 = **$6.30**，即 regular_price 就等于采购价换汇、零加价，sale_price 更低。

| 口径 | regular $6.25 | sale $5.83 |
|---|---|---|
| 只扣采购价 $6.30 | −0.8% | −8.1% |
| 再扣支付费 2.9%+$0.30 | −8.5% | −16.1% |
| 再扣营销 15% | −23.5% | −31.0% |
| 再扣尾程运费 | 更亏 | 更亏 |

采购成本已高于 regular_price，连货款都收不回。且该商品 `featured=true` 挂首页推荐位、库存 1000、`on_sale=true`——曝光越高亏越多。

### K.2 根因：定价规则从未落地

- `operating_rules.md` PRICE-002 标注为 **hard + 自动**，但 `listing_gate` 只校验「有无价格」「有无成本」，**从不校验价格是否覆盖成本**；
- 根目录 `pricing_policy.py` 是**孤儿文件**，`backend/` 内无任何模块 import；
- `_batch_update_prices.py` 依赖的 `cost_prefill_service` **在代码库中不存在**，该脚本一跑即崩，从未生效；
- `cost_sync_service` 把物流字段全硬编码为 `ZERO`，`total_landed_cost` 实际只等于采购价。

### K.3 计费重判定（Owner 特别要求）

WC `dimensions=25×4×4cm` 是**产品收纳尺寸**，非包装盒尺寸。本商品含 Ø10cm 灯罩（detail11 图证），包装盒截面不可能是 4×4cm。

| 口径 | 体积重 | 计费重 |
|---|---|---|
| 产品尺寸 25×4×4（400cm³） | ÷5000→0.08kg | 实重 0.29kg |
| 含灯罩彩盒 27×11×5.5（1633cm³） | ÷5000→0.327kg | **体积重 0.327kg** |
| 同上 | ÷6000→0.272kg / ÷8000→0.204kg | 实重 0.29kg |

**结论**：临界点在除数 5000/6000 之间。走国际快递（÷5000）按体积重，走专线/小包按实重。用产品尺寸接物流商 API 会系统性低估体积重，故 `dimensions` 已改为包装盒实际尺寸。

### K.4 定价测算（净利 ≥25% 硬约束）

数据来源标注：项目内唯一费率锚点 `default_shipping_cost=$5.00`；支付费 2.9%+$0.30、营销 15%、美国 0 关税（de minimis）、汇率 0.14 取自项目配置；包装 $0.20、头程 $0.50、售后损耗 3% 为行业常规假设（ASSUMPTION，项目无实测数据）。

| 尾程情景 | 落地成本 | 达标最低价 | 建议定价 | 净利率 |
|---|---|---|---|---|
| 邮政小包 $4 | $11.00 | $20.89 | $20.99 | 25.3% |
| **项目默认 $5** | **$12.00** | **$22.74** | **$22.99** | **25.6%** |
| 专线燕文/4PX $6.5 | $13.50 | $25.51 | $25.99 | 26.0% |
| 旺季 $8 | $15.00 | $28.28 | $28.99 | 26.3% |

**采用 $22.99**：落地成本 $12.00 + 支付费 $0.97 + 营销 $3.45 + 售后 $0.69 = 总成本 $17.11，净利 $5.88，**净利率 25.6% ≥ 25% ✅**。合规：引流款价带 $10–25 ✅、尾数 .99 ✅、运费占比 21.7% ≤40% ✅。

### K.5 三项修复（均已写入 + 公开页核验通过）

| 项 | 原值 | 新值 | 核验 |
|---|---|---|---|
| regular_price | $6.25 | **$22.99** | 公开页新价出现、旧价消失、schema price=22.99 |
| sale_price | $5.83 | **清空** | on_sale=false、无 Sale! 标、无划线价 `<del>`、无 on-sale class |
| dimensions | 25×4×4cm | **27×11×5.5cm** | 含灯罩包装盒实际尺寸 |

取消促销的理由：原「原价 $6.25 → 折 $5.83」的锚点基于亏损价，属虚假折扣痕迹，必须清除而非保留。slug/status/stock/标题/描述/tags/图片全部未动。

### K.6 门禁加固（防复发）

| 交付物 | 内容 |
|---|---|
| `backend/app/core/config.py` | 新增定价配置区块：`pricing_min_net_margin=0.25`、物流默认值、变动费率、汇率（业务值入配置，AGENTS.md §1.2） |
| `backend/app/services/pricing_policy.py` | **新建**，实现 PRICE-002 公式、`evaluate_price` 净利判定、`suggested_retail_price`（.99 心理定价）、实测成本优先于估算 |
| `backend/app/services/listing_gate.py` | `evaluate_gate` + `evaluate_gate_from_dict` 两条路径接入毛利校验；`negative_margin`→HARD_BLOCK，`below_margin_target`→REVIEW_REQUIRED |
| `backend/app/api/v1/endpoints/listing_publish.py` | 新增 `_load_cost_row`（传整行成本供实测落地成本）；两处调用点接入；`_FIX_HINTS` 补两个新错误码 |
| `backend/tests/test_listing_gate_margin.py` | **新建 25 例**：亏损硬阻断、净利不足需复核、达标不误伤、无成本不误判、实测优先、CNY 换算、管线出口拦截 |

端到端验证（2230 真实数据过门禁）：修复前 $5.83 → **blocked `['negative_margin']`**；修复后 $22.99 → **passed**。

### K.7 全站排查结论

体检脚本扫描全站：当前**仅 1 个商品**（2230），无其他亏损商品。但门禁缺陷是系统性的——站点后续任何商品走此管线都可能重演，故 K.6 的加固独立于 2230 本身，必须保留。

### K.8 遗留 tech-debt

1. `price_change_log` 表文档有约定但代码不存在，调价审计目前靠 WC 修订 + 本地备份 JSON；
2. 物流成本仍是估算（`cost_sync_service` 硬编码 ZERO），落地成本 `basis=estimated`；接入实测 ProductCost 后门禁自动切 `measured`；
3. 净利 25% 与文档层级毛利率（20/35/40/45%）口径不同，已在 `operating_rules.md` PRICE-002 标注待 Owner 校准。
4. **改价只写了 WC 层，未同步生产数据库 `product.meta`**（本次通过 WC REST 直接改价）。`woocommerce_sync_service.push_product_to_woocommerce`（第 1355–1360 行）会从 DB 的 `meta.regular_price/sale_price` 读价推回 WC。若远程生产后端触发 DB→WC 推送（webhook / 定时任务 / 人工推送），会用 DB 里的旧价 6.25/5.83 **覆盖** WC 的 22.99。本地 SQLite 无此商品（生产数据在远程 PostgreSQL），无法从本地直接写 DB 修复。**需在生产后端侧同步 `product.meta` 价格**（DB 与 WC 价格源必须一致，否则每次同步都打架）。
   - **已加固（2026-10-07）**：给底层 `push_product_to_woocommerce` 加了 PRICE-002 毛利门禁——推送前用 `evaluate_price` 校验生效价（sale>regular>price），`negative_margin`（售价<落地成本）**直接阻止推送**并返回 `action="blocked"`，`below_target` 仅告警不阻断。这样即便 DB 仍是旧价 6.25（净利率 −117%），也会被门禁拦下、无法覆盖 WC 的 22.99。成本行优先取实测 `ProductCost`（basis=measured），无则按配置物流估算（basis=estimated）；缺成本数据时放行不误伤。该路径此前**完全无门禁**（gated 端点是另一条路）。测试：`test_listing_gate_margin.py` 覆盖，`test_product_factory_orchestrator.py`（mock 该 push）回归通过。
   - 遗留：门禁只是"防覆盖"兜底，**根治仍需让 DB.meta 价格 = WC 价格**（单一数据源）。当前 DB 值未知（远程 PG，本地不可读），待 Owner 在生产侧核对并同步。
5. **WC REST 读取会被 LiteSpeed 缓存污染**：本次改价后一次读取返回旧价 6.25/5.83（`x-litespeed-cache: hit`），一度误判为"被回滚"。核验价格类改动必须带 cache-buster 参数 + `Cache-Control: no-store`，连读确认 `cache=miss` 后再下结论。已补入 SOP §7.9.5。

备份文件：`_backup_p2230_before_price_*.json`（含改价前完整字段，可回滚）。
