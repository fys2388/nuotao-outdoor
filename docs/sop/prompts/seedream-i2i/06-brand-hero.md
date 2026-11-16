# 详情 06 · 品牌主视觉

> **对应 SOP**：`wc-ai-content-sop-v1.0.md` Phase ④
> **工具**：Seedream 5.0 Pro (I2I 图生图)
> **规格**：3:4 竖版，1536×2048

---

## 用途

详情页首屏，建立品牌认知和产品第一印象。这是独立站详情页的第一张图，决定买家是否继续浏览。

## 构图规范

- **构图**：3:4 竖版，上方品牌名，中间大场景+产品，下方 slogan
- **背景**：户外大场景（山脉/森林/湖边）
- **文字**：品牌名 + 产品系列名 + slogan

---

## Prompt 模板（Seedream I2I）

```
参考[img0]作为产品外观参考，保持产品的形状、颜色、材质、结构100%不变。
竖版3:4构图，画面上方是"NUOTAO OUTDOOR"品牌名（大号粗体无衬线字体，白色），
中间是壮丽的户外山脉风景，产品放置在前景的岩石上，
产品占画面约30%，背景是远处的雪山和蓝天。
画面下方是产品系列名"[系列名]"和slogan"[品牌slogan]"。
整体采用户外品牌大片摄影风格，自然光，温暖色调，氛围感强烈，
品牌名和产品形成清晰的视觉层次。关键主体与文字完整置于安全边界内。
```

---

## 品牌 slogan 库

- "Explore Beyond Limits"
- "Your Adventure Companion"
- "Gear Up, Go Out"
- "Built for the Wild"
- "Outdoor Excellence"
- "Built for the Elements"
- "Wherever You Go"

---

## I2I 参考图选择

**首选**：1688 场景图（户外使用）
**次选**：1688 白底图（Prompt 要求生成品牌场景）

---

## 负面提示词

```
no chinese characters, no misspelled english,
no fake brand name, no wrong typography,
keep product shape and color identical,
no garbled text, no fake slogan,
no overexposed sky, no underexposed product
```

---

## 验收 Checklist

- [ ] 产品外观与 1688 原图 100% 一致
- [ ] 品牌名拼写正确（NUOTAO OUTDOOR）
- [ ] slogan 拼写正确
- [ ] 3:4 竖版构图
- [ ] 品牌名+场景+产品层次清晰
- [ ] 分辨率 1536×2048
- [ ] 文字无乱码
- [ ] 氛围感强烈，有品牌大片感

**⚠️ 关键**：品牌名和 slogan 如果生成乱码，用后处理方式：
1. Seedream 生成无字场景底图
2. Photoshop / Canva 后添加品牌名和 slogan
3. 或使用品牌官方字库确保字体正确

---

## 版本记录

- v1.0 (2026-09-27)：从 `docs/ai_image_prompt_template_library.md` §3.1 拆分升级
