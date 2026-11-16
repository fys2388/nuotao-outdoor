# 详情 07 · 核心卖点

> **对应 SOP**：`wc-ai-content-sop-v1.0.md` Phase ④
> **工具**：Seedream 5.0 Pro (I2I 图生图)
> **规格**：3:4 竖版，1536×2048

---

## 用途

快速传达产品的 3-4 个核心价值点。这是详情页信息密度最高的图。

## 构图规范

- **构图**：3:4 竖版，上方标题，中间 3-4 个卖点图标+文字，下方产品图
- **背景**：浅色背景或品牌色渐变
- **文字**：标题 + 3-4 个卖点（图标+标题+简短说明）

---

## Prompt 模板（Seedream I2I）

```
参考[img0]作为产品外观参考，保持产品的形状、颜色、材质、结构100%不变。
竖版3:4构图，画面上方是标题"WHY CHOOSE US"（大号粗体字体，深灰色），
中间是3列核心卖点展示，每列包含：
- 一个简洁的线性图标（如闪电/水滴/盾牌/重量图标）
- 卖点标题（中号粗体字体）
- 简短说明文字（小号字体）
3个卖点分别是："[卖点1]"、"[卖点2]"、"[卖点3]"。
画面下方是产品的侧面展示图，占画面约35%。
背景采用浅灰色到白色的渐变背景，干净现代。
整体采用现代电商详情页设计风格，排版整齐，信息层次清晰。
关键主体与文字完整置于安全边界内。
```

---

## 卖点库（按品类）

| 品类 | 卖点 1 | 卖点 2 | 卖点 3 |
|---|---|---|---|
| 露营家具 | ULTRA LIGHTWEIGHT / 4.5LB | EASY FOLDING / 3-SEC SETUP | HEAVY DUTY / 300LB CAPACITY |
| 露营照明 | SUPER BRIGHT / 1000LM | LONG BATTERY / 40H RUNTIME | IPX6 WATERPROOF / ALL WEATHER |
| 水具/Hydration | FOOD GRADE / BPA FREE | LEAK PROOF / 24H SEALED | KEEPS COLD 24H |
| 露营炊具 | FAST BOILING / 3.5MIN | WINDPROOF / 4-SIDE SHIELD | COMPACT / 1L CAPACITY |
| 户外收纳 | LARGE CAPACITY / 50L | WATERPROOF / IPX5 | DURABLE / RIPSTOP FABRIC |
| 帐篷/庇护所 | EASY SETUP / 60SEC | UV PROTECTION / UPF50 | WATERPROOF / 3000MM |
| 户外配件 | MULTI-FUNCTIONAL / 10-IN-1 | PREMIUM STEEL / 420 HV | LIGHTWEIGHT / 320G |

---

## I2I 参考图选择

**首选**：1688 产品侧面图
**次选**：1688 白底图

---

## 负面提示词

```
no chinese characters, no misspelled english,
no garbled text, no fake icons,
keep product shape and color identical,
no oversaturated colors, no cartoon style,
no text overlap, no text cutoff
```

---

## 验收 Checklist

- [ ] 产品外观与 1688 原图 100% 一致
- [ ] 3 个卖点文案正确（英文，无乱码）
- [ ] 图标简洁清晰
- [ ] 排版整齐，信息层次清晰
- [ ] 3:4 竖版构图
- [ ] 分辨率 1536×2048
- [ ] 产品占画面约 35%
- [ ] 文字无重叠、无裁切

**⚠️ 关键**：卖点图文字量大，容易乱码。推荐流程：
1. Seedream 生成产品+图标底图
2. Photoshop / Canva 后添加文字（使用品牌官方字体）
3. 或使用 Ideogram 2.0 专门生成文字排版图

---

## 版本记录

- v1.0 (2026-09-27)：从 `docs/ai_image_prompt_template_library.md` §3.2 拆分升级
