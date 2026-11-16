# 主图 03 · 促销转化主图

> **对应 SOP**：`wc-ai-content-sop-v1.0.md` Phase ④
> **工具**：Seedream 5.0 Pro (I2I 图生图)
> **规格**：1:1 正方形，2048×2048

---

## 用途

突出核心卖点，提升点击率和转化率。这是独立站首屏 hero 图的关键素材。

## 构图规范

- **构图**：产品偏左或偏右，另一侧放置卖点文字
- **背景**：渐变背景或浅色场景背景
- **文字**：2-3 个核心卖点，大号粗体英文
- **注意**：所有文字必须为英文，无中文

---

## Prompt 模板（Seedream I2I）

```
参考[img0]作为产品外观参考，保持产品的形状、颜色、材质、结构100%不变。
产品位于画面左侧，占画面约45%，右侧留白区域放置英文卖点文字。
背景采用浅灰色到白色的渐变背景，干净现代。
右侧文字区域包含：
- 主标题："[核心卖点1]"（大号粗体无衬线字体，深灰色）
- 副标题："[核心卖点2]"（中号字体，中灰色）
- 小标签："[核心卖点3]"（小号字体，品牌色背景白色文字）
整体采用现代电商促销海报风格，文字清晰可读，排版简洁有力，
产品和文字之间有明确的视觉层次。关键主体与文字完整置于安全边界内。
```

---

## 卖点文案库（按品类）

| 品类 | 核心卖点 1 | 核心卖点 2 | 核心卖点 3 |
|---|---|---|---|
| 露营家具 | ULTRA LIGHTWEIGHT | EASY FOLDING | HEAVY DUTY |
| 露营照明 | SUPER BRIGHT | LONG BATTERY LIFE | IPX6 WATERPROOF |
| 水具/Hydration | FOOD GRADE MATERIAL | LEAK PROOF | KEEPS COLD 24H |
| 露营炊具 | FAST BOILING | WINDPROOF DESIGN | COMPACT & PORTABLE |
| 户外收纳 | LARGE CAPACITY | WATERPROOF | DURABLE MATERIAL |
| 帐篷/庇护所 | EASY SETUP | UV PROTECTION | WATERPROOF |
| 户外配件 | MULTI-FUNCTIONAL | PREMIUM QUALITY | LIGHTWEIGHT |

---

## I2I 参考图选择

**首选**：1688 产品正面图或 45 度图
**次选**：1688 白底图（Prompt 要求添加文字和渐变背景）

---

## 负面提示词

```
no chinese characters, no misspelled english,
no garbled text, no fake brand logo,
keep product shape and color identical,
no blur on text, no low quality,
no watermark, no oversaturated colors
```

---

## 验收 Checklist

- [ ] 产品外观与 1688 原图 100% 一致
- [ ] 卖点文字为英文，拼写正确
- [ ] 3 个卖点层次清晰（主/副/小标签）
- [ ] 产品占画面 45% 左右
- [ ] 背景渐变干净现代
- [ ] 排版简洁有力
- [ ] 分辨率 2048×2048
- [ ] 文字无乱码

**⚠️ 关键**：如果文字生成出现乱码，改用后处理方式：
1. Seedream 生成无字底图
2. Canva / Photoshop 后添加文字
3. 或使用 Ideogram 2.0 专门生成文字排版图

---

## 版本记录

- v1.0 (2026-09-27)：从 `docs/ai_image_prompt_template_library.md` §2.3 拆分升级
