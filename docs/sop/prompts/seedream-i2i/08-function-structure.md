# 详情 08 · 功能结构

> **对应 SOP**：`wc-ai-content-sop-v1.0.md` Phase ④
> **工具**：Seedream 5.0 Pro (I2I 图生图)
> **规格**：3:4 竖版，1536×2048

---

## 用途

详细标注产品各部位的功能和特点。让客户快速理解产品构造。

## 构图规范

- **构图**：3:4 竖版，产品大图居中，周围有标注线指向各部位
- **背景**：纯白或浅色背景
- **文字**：部位名称 + 功能说明（英文）

---

## Prompt 模板（Seedream I2I）

```
参考[img0]作为产品外观参考，保持产品的形状、颜色、材质、结构100%不变。
竖版3:4构图，产品大图位于画面中央，占画面约55%，
采用45度视角展示产品全貌。
从产品的不同部位引出4条标注线，每条线末端有文字说明：
- 标注1指向[部位1]："[部位1名称] - [功能说明1]"
- 标注2指向[部位2]："[部位2名称] - [功能说明2]"
- 标注3指向[部位3]："[部位3名称] - [功能说明3]"
- 标注4指向[部位4]："[部位4名称] - [功能说明4]"
标注线使用细灰色线条，文字使用小号无衬线字体，深灰色。
背景采用纯白色背景，干净简洁。
整体采用专业产品结构图风格，标注清晰，信息准确。
关键主体与文字完整置于安全边界内。
```

---

## 部位库（按品类）

| 品类 | 部位 1 | 部位 2 | 部位 3 | 部位 4 |
|---|---|---|---|---|
| 折叠椅 | FOLDING JOINT | X-FRAME | FABRIC | FOOT CAP |
| 头灯 | LED ARRAY | SWITCH | RECHARGE PORT | HEAT SINK |
| 保温瓶 | SEAL CAP | HANDLE | MATERIAL | VACUUM LAYER |
| 露营炉 | STOVE HEAD | WIND SHIELD | IGNITER | FUEL VALVE |
| 收纳箱 | ZIPPER | FABRIC | HANDLE | COMPARTMENTS |
| 帐篷 | FABRIC COATING | POLE | STAKES | VENT |
| 多功能工具 | TOOL HEAD | FRAME | HANDLE | STORAGE |

---

## I2I 参考图选择

**首选**：1688 45 度全貌图
**次选**：1688 白底图

---

## 负面提示词

```
no chinese characters, no misspelled english,
no garbled text, no wrong label placement,
keep product shape and color identical,
no crossing annotation lines,
no low quality, no cartoon style
```

---

## 验收 Checklist

- [ ] 产品外观与 1688 原图 100% 一致
- [ ] 4 条标注线指向正确部位
- [ ] 部位名称+功能说明正确（英文，无乱码）
- [ ] 标注线清晰不交叉
- [ ] 产品占画面约 55%
- [ ] 3:4 竖版构图
- [ ] 分辨率 1536×2048

**⚠️ 关键**：标注图对文字位置要求极高。推荐流程：
1. Seedream 生成产品大图（无标注）
2. Photoshop / Canva 后添加标注线和文字
3. 使用矢量标注工具确保标注精准

---

## 版本记录

- v1.0 (2026-09-27)：从 `docs/ai_image_prompt_template_library.md` §3.3 拆分升级
