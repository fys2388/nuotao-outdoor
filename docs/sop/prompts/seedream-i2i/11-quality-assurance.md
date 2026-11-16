# 详情 11 · 品质保障

> **对应 SOP**：`wc-ai-content-sop-v1.0.md` Phase ④
> **工具**：Seedream 5.0 Pro (I2I 图生图)
> **规格**：3:4 竖版，1536×2048

---

## 用途

建立信任，降低购买顾虑，促进转化。这是详情页的"临门一脚"。

## 构图规范

- **构图**：3:4 竖版，上方标题，中间 4 格服务承诺，下方品牌标语
- **背景**：浅色背景或品牌色渐变
- **文字**：标题 + 4 个服务承诺 + 品牌标语

---

## Prompt 模板（Seedream I2I）

```
参考[img0]作为产品外观参考，保持产品的形状、颜色、材质、结构100%不变。
竖版3:4构图，画面上方是标题"QUALITY ASSURANCE"（大号粗体字体，深灰色），
中间是2×2四格服务承诺展示，每格包含：
- 一个简洁的线性图标（如盾牌/卡车/退换/客服图标）
- 服务承诺标题（中号粗体字体）
- 简短说明文字（小号字体）
4个承诺分别是：
- "30-DAY MONEY BACK" - "Hassle-free returns"
- "2-YEAR WARRANTY" - "Quality guaranteed"
- "FREE SHIPPING" - "On orders over $50"
- "24/7 CUSTOMER SUPPORT" - "Always here to help"
画面下方是品牌标语"NUOTAO OUTDOOR - Your Adventure Companion"（中号字体，品牌色）。
背景采用浅灰色到白色的渐变背景，干净现代，带有轻微的品牌色点缀。
整体采用现代电商详情页设计风格，排版整齐，信任感强。
关键主体与文字完整置于安全边界内。
```

---

## 服务承诺库（按市场）

| 市场 | 承诺 1 | 承诺 2 | 承诺 3 | 承诺 4 |
|---|---|---|---|---|
| US | 30-DAY MONEY BACK | 2-YEAR WARRANTY | FREE SHIPPING >$50 | 24/7 SUPPORT |
| UK | 30-DAY RETURNS | 1-YEAR WARRANTY | FREE SHIPPING >£50 | EMAIL SUPPORT |
| DE | 14-TAGE RÜCKGABE | 2-JAHRE GARANTIE | KOSTENLOSER VERSAND | KUNDENSERVICE |
| AU | 30-DAY RETURNS | 2-YEAR WARRANTY | FREE SHIPPING >$50 | EMAIL SUPPORT |

---

## I2I 参考图选择

**首选**：1688 产品正面小图
**次选**：1688 白底图

---

## 负面提示词

```
no chinese characters, no misspelled english,
no garbled text, no fake warranty claims,
keep product shape and color identical,
no oversaturated colors, no cartoon style,
no text overlap, no text cutoff,
no false promises (e.g. "lifetime warranty" if not true)
```

---

## 验收 Checklist

- [ ] 服务承诺与实际情况一致（不夸大）
- [ ] 4 个承诺文案正确（英文，无乱码）
- [ ] 图标简洁清晰
- [ ] 品牌标语正确
- [ ] 3:4 竖版构图
- [ ] 分辨率 1536×2048
- [ ] 排版整齐，信任感强

**⚠️ 合规关键**：
- 服务承诺必须与网站实际政策一致
- "Warranty" 时长必须与售后政策一致
- 禁止夸大（如 "lifetime warranty" 如果不是真的）
- 涉及退款/退货承诺必须符合目标市场法律（US: FTC, EU: Consumer Rights Directive）

---

## 版本记录

- v1.0 (2026-09-27)：从 `docs/ai_image_prompt_template_library.md` §3.6 拆分升级
