# 详情 09 · 使用场景

> **对应 SOP**：`wc-ai-content-sop-v1.0.md` Phase ④
> **工具**：Seedream 5.0 Pro (I2I 图生图)
> **规格**：3:4 竖版，1536×2048

---

## 用途

展示产品在不同场景下的使用，激发购买欲望。这是详情页最有代入感的图。

## 构图规范

- **构图**：3:4 竖版，2×2 四格拼图，每格一个使用场景
- **背景**：每格独立的场景照片
- **文字**：每格底部有场景名称标签

---

## Prompt 模板（Seedream I2I）

```
参考[img0]作为产品外观参考，保持产品的形状、颜色、材质、结构100%不变。
竖版3:4构图，采用2×2四格拼图布局，每格展示一个不同的使用场景：
- 左上格：产品在[场景1]中使用，如露营帐篷内，温暖灯光
- 右上格：产品在[场景2]中使用，如户外野餐，阳光明媚
- 左下格：产品在[场景3]中使用，如钓鱼场景，湖边日落
- 右下格：产品在[场景4]中使用，如徒步背包上，山间小径
每格底部有半透明黑色条，上面有白色英文场景名称标签。
四格之间有细微的白色分隔线。
整体采用户外生活方式摄影风格，每个场景都有产品的真实使用展示，
自然真实的光线，温暖的色调。关键主体与文字完整置于安全边界内。
```

---

## 场景库（按品类）

| 品类 | 场景 1 | 场景 2 | 场景 3 | 场景 4 |
|---|---|---|---|---|
| 露营家具 | CAMPING | PICNIC | FISHING | BACKYARD |
| 露营照明 | NIGHT CAMP | HIKING | FISHING | EMERGENCY |
| 水具/Hydration | HIKING | CYCLING | CAMPING | TRAVEL |
| 露营炊具 | CAMPING COOK | PICNIC | BACKPACKING | FISHING |
| 户外收纳 | CAR TRUNK | CAMPING | TRAVEL | HOME |
| 帐篷/庇护所 | CAMPING | BEACH | BACKPACKING | FESTIVAL |
| 户外配件 | HIKING | CAMPING | FISHING | DAILY USE |

---

## I2I 参考图选择

**首选**：1688 场景图（多角度）
**次选**：1688 白底图（Prompt 要求生成 4 个场景）

**⚠️ 关键**：4 个场景必须视觉差异化明显，避免重复。

---

## 负面提示词

```
no chinese characters, no misspelled english,
no garbled text, no fake scenes,
keep product shape and color identical across all 4 scenes,
no blur, no cartoon style,
no text overlap, no scene repetition
```

---

## 验收 Checklist

- [ ] 产品外观在 4 格中 100% 一致
- [ ] 4 个场景视觉差异化明显
- [ ] 场景名称正确（英文，无乱码）
- [ ] 每格底部半透明黑色条+白色文字
- [ ] 四格之间有白色分隔线
- [ ] 3:4 竖版构图
- [ ] 分辨率 1536×2048
- [ ] 自然光，无过度后期

---

## 版本记录

- v1.0 (2026-09-27)：从 `docs/ai_image_prompt_template_library.md` §3.4 拆分升级
