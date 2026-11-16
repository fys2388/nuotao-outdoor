# Flux Kontext · 背景替换（保真）

> **对应 SOP**：`wc-ai-content-sop-v1.0.md` Phase ④
> **工具**：Flux 1.1 Pro / Flux Kontext
> **规格**：1:1 或 3:4（按目标图）
> **用途**：Seedream I2I 产品变形时的保真补强

---

## 用途

当 Seedream I2I 出现产品变形时，切换到 Flux Kontext。Kontext 的核心能力是**保留产品、替换环境**，保真度极高。

## 适用场景

- 产品轮廓被 AI 改形
- 需要精准保留产品 logo/细节
- Seedream 多次迭代仍无法保真

---

## Prompt 模板

```
Keep the [PRODUCT] exactly as shown in the reference image,
preserve all details, textures, logos, colors and proportions.
Replace the background with a [NEW SCENE: minimalist studio /
sunlit loft / zen garden].
Add natural soft shadows under the product.
Match lighting direction from [DIRECTION: top-left].
Photorealistic, commercial quality.
```

---

## 具体示例

### 示例 1：白底场景替换

```
Keep the camping chair exactly as shown in the reference image,
preserve all details: 600D Oxford fabric texture, aluminum frame, 
folding joints, foot caps. Keep the olive green color exactly.
Replace the background with a minimalist outdoor camping scene,
grass ground, distant forest, soft morning light from top-left.
Add natural soft shadows under the chair.
Photorealistic, commercial e-commerce quality.
```

### 示例 2：场景注入

```
Keep the product exactly as shown in the reference image,
preserve all details, textures, logos, colors and proportions.
Inject the product into a sunset camping scene,
tent in background, warm golden hour lighting,
fireflies in the air, cinematic atmosphere.
Natural shadows under product.
Match lighting direction from right side.
Photorealistic, editorial outdoor lifestyle quality.
```

---

## 工作流

```
1. 抠出真实产品图（透明 PNG）
         ↓
2. Flux Kontext prompt 描述新场景
         ↓
3. 输出带新背景的成品图
         ↓
4. 人工精修（如有需要）
```

---

## 负面提示词

```
no text, no chinese characters, no other brand logo,
no product distortion, no color shift on product,
no fake product details, no cartoon style,
no blur, no overexposed areas, no underexposed areas,
keep product shape and color 100% identical
```

---

## 验收 Checklist

- [ ] 产品外观与 1688 原图 100% 一致
- [ ] 新背景自然融合
- [ ] 光影方向一致
- [ ] 产品下方有自然阴影
- [ ] 无 AI 崩坏
- [ ] 无文字、水印
- [ ] 分辨率达标（2048×2048 或 1536×2048）

---

## 与 Seedream 的对比

| 维度 | Seedream I2I | Flux Kontext |
|---|---|---|
| 产品保真度 | 中（可能变形） | 极高 |
| 场景创造力 | 强 | 中等 |
| 价格 | 相对便宜 | $0.04/张 |
| 推荐场景 | 首选用 | 保真补强 |
| 速度 | 快 | 快 |

---

## 版本记录

- v1.0 (2026-09-27)：初版
