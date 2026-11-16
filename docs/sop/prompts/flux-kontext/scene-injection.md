# Flux Kontext · 场景注入（保真）

> **对应 SOP**：`wc-ai-content-sop-v1.0.md` Phase ④
> **工具**：Flux 1.1 Pro / Flux Kontext
> **用途**：把产品注入到复杂场景中，同时保留产品原貌

---

## 用途

比"背景替换"更复杂，适用于：
- 产品需要融入复杂场景（不是简单换背景）
- 产品与场景有交互（如产品在使用中）
- 需要精准控制产品位置和大小

## 适用场景

- 露营场景图（产品+帐篷+背景）
- 使用场景图（产品在背包上、在炉子上）
- 多人场景图（产品+模特+背景）

---

## Prompt 模板

```
[PRODUCT] as the main subject, placed in [SCENE DESCRIPTION].
Keep the product EXACTLY as shown in the reference image:
preserve all details, textures, logos, colors, proportions.
The product occupies [PERCENTAGE]% of the frame, positioned [POSITION].
[CONTEXT ELEMENTS: tent, table, etc.] around the product.
[LIGHTING: natural golden hour / studio soft light / etc.]
[CAMERA: 35mm lens / 50mm / wide angle].
Photorealistic, editorial lifestyle photography.
Natural shadows and lighting integration.
```

---

## 具体示例

### 示例 1：露营场景注入

```
A folding camping chair as the main subject, placed in a sunset 
camping scene with a tent in the background.
Keep the chair EXACTLY as shown in the reference image:
preserve 600D Oxford fabric texture, aluminum frame, folding joints,
olive green color, Nuotao logo.
The chair occupies 50% of the frame, positioned center-left.
A camping tent and cooking stove visible in background.
Warm golden hour lighting from right side, natural shadows under chair.
50mm lens, shallow depth of field.
Photorealistic, editorial outdoor lifestyle photography.
```

### 示例 2：使用场景注入

```
A portable camping stove as the main subject, actively boiling water 
in a camping pot, placed on a folding table in a forest campsite.
Keep the stove EXACTLY as shown in the reference image:
preserve all details: stove head, wind shield, fuel valve, ignition,
black color, Nuotao branding.
The stove occupies 60% of the frame, positioned center.
Wooden table surface, forest background slightly blurred.
Natural daylight, soft shadows.
Macro photography style, showing flame and boiling water.
Photorealistic, commercial quality.
```

---

## 工作流

```
1. 抠出真实产品图（透明 PNG）
         ↓
2. 确定场景描述和交互方式
         ↓
3. Flux Kontext prompt（含位置、光影、相机）
         ↓
4. 输出成品图
         ↓
5. 精修（光影融合、细节调整）
```

---

## 负面提示词

```
no text, no chinese characters, no other brand logo,
no product distortion, no color shift on product,
no fake product details, no cartoon style,
no blur on product, no overexposed areas,
no unrealistic lighting, no harsh shadows,
keep product shape, color, texture 100% identical
```

---

## 验收 Checklist

- [ ] 产品外观与 1688 原图 100% 一致
- [ ] 产品与场景自然融合
- [ ] 光影方向一致
- [ ] 产品位置和大小符合 Prompt
- [ ] 无 AI 崩坏
- [ ] 无文字、水印
- [ ] 分辨率达标
- [ ] 场景真实自然

---

## 版本记录

- v1.0 (2026-09-27)：初版
