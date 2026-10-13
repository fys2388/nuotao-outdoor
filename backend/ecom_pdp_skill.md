---
name: ecom-pdp
description: Build high-converting cross-border ecommerce PDP, hero image, product image stack, and AI image prompt strategy by resolving minimum inputs in priority order from user input, attachments, context, web research, logic inference, and explicit assumptions/defaults; then diagnose the conversion driver, produce an English (US) baseline, optionally localize while preserving intent, and generate executable image prompts or images through the bundled OpenAI-compatible image script.
---

# Ecom PDP Skill

当用户需要跨境电商商品主图、PDP 详情页、Amazon / Shopify / TikTok Shop 图片、A+ content、广告图、商品图文案、转化优化、英文基准文案、本地化适配，或直接 AI 生图时，使用这个 Skill。

## Trigger Signals

- "Amazon listing", "Shopify PDP", "TikTok Shop", "A+ content", "product image stack"
- "hero image copy", "detail page", "PDP structure", "main image", "lifestyle image"
- "improve CTR", "improve CVR", "boost add-to-cart", "increase AOV", "weak trust"
- "offer + CTA", "bundle strategy", "guarantee", "risk reversal"
- "localize copy", "multilingual listing", "adapt for US / EU / JP / DE market"
- "生图", "生成商品图", "生成详情页图片", "出图"

## Core Principle

先做 **Conversion Driver Diagnosis**，再决定图片和文案结构：

1. **Visual-Driven**：靠"看见"成交，适合外观、质感、礼品感、前后对比明显的产品。
2. **Pain-Driven**：靠"问题紧迫 + 解决方案"成交，适合反复烦恼、风险、低效、损失明确的产品。
3. **Emotion-Value-Driven**：靠"身份、向往、情绪价值"成交，适合自我表达、关怀、冲动、新奇和社交属性强的产品。

所有主图、PDP 模块、图内文案和 Prompt 都必须服务所选转化驱动力。

## Workflow

1. 先执行 **Minimum Input Resolution Gate**：按信息权重补齐最小输入
2. 收集最小输入；非关键缺失可标注 Assumption / Default 后继续
3. 诊断 1 个主转化驱动力，必要时补 1 个次级驱动力
4. 生成 **Buyer Reason Card**，锁定买家为什么现在会买
5. 输出 **English (US) Baseline**
6. 如用户要求本地化，再做 **Localization Layer**
7. 为多图任务建立 **Campaign Style Lock**
8. 如果是真实实物产品且用户提供了参考图，先执行 **Product Angle Sheet Pipeline**
9. 通过 **Image Copy Gate**：每张图先确定图内短文案，再写独立 Prompt
10. 输出主图序列、PDP 详情页序列、可执行 Prompt
11. 用 **Self-review Scorecard** 自审

## Minimum Inputs

跨境电商任务优先收集：
- Product name + category + price band
- Audience segment + purchase context
- Target market and channel constraints
- Top differentiators
- Proof assets
- Review and recommendation assets
- Current weak points
- Offer assets
- Compliance preference
- Output need
