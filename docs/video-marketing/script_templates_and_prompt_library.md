# Nuotao Outdoor 短视频脚本模板与 AI 提示词库

> 版本：v1.0  
> 更新日期：2026-09-10  
> 适用：2C 为主，2B 轻量并行  
> 工具：ChatGPT/Claude（脚本）、Copilot/DALL-E（图片）、Pika/Luma（视频）、ElevenLabs（配音）

---

## 目录

1. [脚本模板（2C）](#1-脚本模板2c)
2. [脚本模板（2B）](#2-脚本模板2b)
3. [AI 脚本生成提示词](#3-ai-脚本生成提示词)
4. [AI 图片生成提示词](#4-ai-图片生成提示词)
5. [AI 视频生成提示词](#5-ai-视频生成提示词)
6. [AI 配音参数与提示词](#6-ai-配音参数与提示词)
7. [标题/描述/标签生成提示词](#7-标题描述标签生成提示词)
8. [多语言翻译提示词](#8-多语言翻译提示词)

---

## 1. 脚本模板（2C）

### 1.1 场景实测型（占比30%）

**适用产品**：帐篷、背包、睡袋、炉具等可在场景中展示的产品

**结构模板**：
```
[0-3s 钩子] 场景冲突 + 提问
  旁白："[冲突场景]。[提问]？"
  画面：[冲突场景的视觉冲击]

[3-8s 问题] 放大痛点
  旁白："[痛点描述]。[后果]。"
  画面：[痛点场景，可用对比/夸张]

[8-20s 解决方案] 产品出场 + 3个卖点
  旁白："直到我试了 [产品名]。[卖点1]。[卖点2]。[卖点3]。"
  画面：[产品特写 + 使用场景 + 细节展示]

[20-25s 社会证明] 效果验证
  旁白："[使用效果/数据/评价]。"
  画面：[使用效果展示/评价截图]

[25-30s CTA] 行动号召
  旁白："[CTA]。"
  画面：[产品+品牌logo+网站链接]
```

**示例（帐篷暴雨测试）**：
```
[0-3s] 旁白："It started pouring. This is what happened to my $80 tent."
       画面：乌云密布 → 大雨倾盆 → 帐篷在雨中

[3-8s] 旁白："Most cheap tents leak after 10 minutes. You wake up soaking wet."
       画面：普通帐篷漏水 → 睡袋湿透

[8-20s] 旁白："But this Nuotao tent? 3000mm waterproof rating. 
       Set up in 60 seconds. And it survived this storm all night."
       画面：帐篷特写 → 快速搭建延时 → 雨中帐篷内部干燥

[20-25s] 旁白："Over 500 five-star reviews. People love it."
       画面：评价截图滚动 + 五星图标

[25-30s] 旁白："Link in bio to grab yours before they sell out!"
       画面：产品展示 + Nuotao Outdoor logo + nuotaooutdoor.com
```

---

### 1.2 开箱/组装型（占比20%）

**适用产品**：所有产品，尤其是组装类（帐篷、炉具、桌椅）

**结构模板**：
```
[0-3s 钩子] 快递/开箱 + 期待
  旁白："[提问/感叹]。"
  画面：快递盒特写 → 拆箱

[3-10s 开箱] 产品出场 + 第一印象
  旁白："[包装/配件描述]。[第一印象]。"
  画面：产品取出 → 配件展示 → 细节特写

[10-25s 组装/使用] 全过程展示
  旁白："[组装步骤/使用方法]。"
  画面：延时/快进组装过程 → 完成效果

[25-30s CTA]
  旁白："[CTA]。"
  画面：成品展示 + 品牌信息
```

**示例（帐篷60秒搭建）**：
```
[0-3s] 旁白："Can you set up a tent in 60 seconds? Watch this."
       画面：计时器开始 → 帐篷包在地上

[3-10s] 旁白："Unzip the bag. Take out the tent. Poles are already attached."
       画面：快进拆箱 → 帐篷展开 → 杆子展示

[10-25s] 旁白："Just lift, click, and stake. That's it. 
       No complicated poles. No fighting with instructions."
       画面：延时搭建（60秒压缩到15秒）→ 完成的帐篷

[25-30s] 旁白："60 seconds. Done. Link in bio to get yours!"
       画面：成品帐篷360度展示 + 计时器显示60秒
```

---

### 1.3 装备清单型（占比20%）

**适用**：引流爆款，植入多个产品

**结构模板**：
```
[0-3s 钩子] 数字 + 场景
  旁白："[数字] things you need for [场景]。"
  画面：场景全景 → 数字弹出

[3-25s 清单] 逐个展示（每个3-5秒）
  旁白："Number [N]: [产品名]。[为什么需要]。"
  画面：产品特写 + 使用场景

[25-30s CTA]
  旁白："[CTA]。"
  画面：所有产品合集 + 品牌信息
```

**示例（露营新手5件装备）**：
```
[0-3s] 旁白："5 things every camping beginner needs. Number 3 will surprise you."
       画面：营地全景 → 数字5弹出

[3-8s] 旁白："Number 1: A lightweight tent. This one sets up in 60 seconds."
       画面：帐篷特写 → 搭建场景

[8-13s] 旁白："Number 2: A warm sleeping bag. Rated for 3 seasons."
       画面：睡袋展开 → 人在睡袋中

[13-18s] 旁白："Number 3: A portable stove. Boil water in 3 minutes."
       画面：炉具点火 → 水烧开

[18-23s] 旁白："Number 4: A durable backpack. 50L, fits everything."
       画面：背包展示 → 装东西

[23-25s] 旁白："Number 5: A headlamp. Hands-free light at night."
       画面：头灯展示 → 夜晚使用

[25-30s] 旁白："All available at nuotaooutdoor.com. Link in bio!"
       画面：5件产品合集 + Nuotao Outdoor logo
```

---

### 1.4 ASMR/满足感型（占比15%）

**适用**：所有产品，尤其是有 satisfying 声音/动作的

**结构模板**：
```
[0-3s] 视觉/声音钩子
  旁白：无 或 一句话
  画面：特写动作 + 清晰声音

[3-25s] 连续 satisfying 动作
  旁白：无 或 极简旁白
  画面：多个满足感镜头拼接

[25-30s] 品牌露出 + CTA
  旁白："[品牌/CTA]。"
  画面：产品 + 品牌信息
```

**关键**：声音要清晰（拉链声、搭建声、点火声、折叠声），画面要特写、慢动作

**示例（帐篷搭建ASMR）**：
```
[0-3s] 画面：拉链拉开特写 + 清晰拉链声
[3-8s] 画面：帐篷展开慢动作 + 布料摩擦声
[8-13s] 画面：杆子扣入特写 + "咔哒"声
[13-18s] 画面：地钉敲入特写 + 敲击声
[18-23s] 画面：完成的帐篷360度旋转 + 环境音
[23-30s] 旁白："Nuotao Outdoor. Gear that just works. Link in bio."
       画面：产品 + Nuotao Outdoor logo
```

---

### 1.5 教程/技巧型（占比10%）

**适用**：建立专业形象，软植入产品

**结构模板**：
```
[0-3s 钩子] 痛点/误区
  旁白："[常见错误/痛点]。"
  画面：错误示范

[3-25s 教程] 步骤讲解
  旁白："[步骤1]。[步骤2]。[步骤3]。"
  画面：正确示范 + 文字标注

[25-30s 产品植入 + CTA]
  旁白："[推荐产品]。[CTA]。"
  画面：产品展示
```

**示例（帐篷防风绳正确打法）**：
```
[0-3s] 旁白："90% of people tie their tent guylines wrong. Here's the right way."
       画面：错误的防风绳 → 帐篷被风吹歪

[3-10s] 旁白："Step 1: Pull the line tight, not loose."
       画面：拉紧防风绳特写

[10-17s] 旁白："Step 2: Use the tensioner, not a knot. It's faster and stronger."
       画面：调节扣使用特写

[17-24s] 旁白："Step 3: Angle at 45 degrees. This gives the best stability."
       画面：45度角示意图 + 稳定的帐篷

[24-30s] 旁白："Our tents come with premium guylines and tensioners. 
       Link in bio to upgrade your setup!"
       画面：Nuotao 帐篷防风绳特写 + 品牌信息
```

---

### 1.6 品牌/故事型（占比5%）

**适用**：建立品牌认知，不追求直接转化

**结构模板**：
```
[0-3s] 品牌愿景/场景
  旁白："[品牌理念]。"
  画面：户外美景/人物

[3-20s] 品牌故事/产品理念
  旁白："[故事/理念]。"
  画面：工厂/团队/产品细节

[20-30s] 品牌口号 + CTA
  旁白："[口号]。[CTA]。"
  画面：品牌logo + 产品合集
```

---

## 2. 脚本模板（2B）

### 2.1 产品详解型（3-5分钟）

**适用**：经销商/批发商了解产品细节

**结构模板**：
```
[0-10s] 产品出场 + 定位
  旁白："[产品名]，[定位]，专为[市场]设计。"
  画面：产品360度展示

[10-60s] 核心参数
  旁白："[参数1]。[参数2]。[参数3]。"
  画面：参数标注 + 细节特写

[60-180s] 材质工艺 + 质检
  旁白："[材质描述]。[工艺]。[质检流程]。"
  画面：材质特写 + 生产流程 + 质检环节

[180-240s] 包装规格 + MOQ
  旁白："[包装规格]。[MOQ]。[交货期]。"
  画面：包装展示 + 装箱过程

[240-300s] 利润空间 + 合作政策
  旁白："[建议零售价]。[批发价]。[利润空间]。[合作政策]。"
  画面：价格表 + 合作流程

[300-310s] CTA
  旁白："[联系方式]。[CTA]。"
  画面：联系方式 + 品牌信息
```

### 2.2 工厂/供应链展示型（5-10分钟）

**结构模板**：
```
[0-30s] 工厂概览
  旁白："[工厂规模]。[历史]。[产能]。"
  画面：工厂外景 + 车间全景

[30-180s] 生产流程
  旁白："[工序1]。[工序2]。..."
  画面：各工序实拍

[180-300s] 质检流程
  旁白："[质检标准]。[质检环节]。[合格率]。"
  画面：质检实拍 + 检测设备

[300-420s] 仓储物流
  旁白："[仓储面积]。[发货流程]。[物流合作]。"
  画面：仓库 + 打包 + 发货

[420-480s] 合作优势 + CTA
  旁白："[优势1]。[优势2]。[CTA]。"
  画面：合作流程 + 联系方式
```

### 2.3 行业洞察型（图文+短视频）

**结构模板**：
```
[0-5s] 行业问题/趋势
  旁白："[行业洞察]。"
  画面：数据图表 + 市场场景

[5-25s] 分析 + 建议
  旁白："[分析]。[建议]。"
  画面：分析图表 + 产品场景

[25-30s] 品牌专业形象 + CTA
  旁白："[品牌定位]。[CTA]。"
  画面：品牌信息
```

---

## 3. AI 脚本生成提示词

### 3.1 通用脚本生成提示词（2C）

```
Role: You are a senior TikTok/Reels content strategist for Nuotao Outdoor, 
an outdoor gear DTC brand targeting 18-35 year old outdoor enthusiasts in 
North America and Europe.

Task: Write a [DURATION]-second short video script for the following topic.

Topic: [填入选题]
Product: [产品名 + 核心卖点 + 价格]
Content type: [场景实测/开箱/装备清单/ASMR/教程/品牌故事]

Requirements:
1. Hook in the first 3 seconds (question, conflict, visual shock, or surprising fact)
2. Structure: Hook(0-3s) → Problem(3-8s) → Solution(8-20s) → Social proof(20-25s) → CTA(25-30s)
3. For each segment, include:
   - [timestamp] Voiceover: "..." (casual, conversational English, like talking to a friend)
   - Visual: "..." (specific, detailed, easy to generate with AI or match with footage)
4. Voiceover word count: [75-90 words for 30s, 150-180 for 60s]
5. Include 3 key product benefits, specific and tangible
6. CTA must be clear: "Link in bio to [action]!"
7. No false claims, no exaggeration
8. Output only the script, no extra explanation

Output format:
[0-3s] Voiceover: "..."
       Visual: "..."
[3-8s] ...
```

### 3.2 批量脚本生成提示词

```
Generate [N] different [DURATION]-second TikTok scripts for [产品名].

Each script must:
- Use a different hook style (question, conflict, fact, challenge, comparison)
- Focus on a different product benefit
- Target a slightly different audience angle (beginner, budget, pro, gift)
- Follow the structure: Hook → Problem → Solution → Social proof → CTA

Product info: [产品详情]

Output each script numbered 1-[N], in the format:
[N] Title: [video title]
[timestamp] Voiceover: "..."
            Visual: "..."
```

### 3.3 2B 脚本生成提示词

```
Role: You are a B2B marketing content specialist for Nuotao Outdoor, 
an outdoor gear manufacturer and wholesaler.

Task: Write a [DURATION]-minute product showcase video script for wholesale buyers.

Product: [产品名 + 完整参数]
Target audience: Outdoor gear retailers, distributors, and procurement managers

Requirements:
1. Professional, factual, data-driven tone
2. Include: product positioning, core specs, materials & craftsmanship, 
   quality control, packaging & MOQ, pricing & profit margin, cooperation policy
3. For each segment:
   - [timestamp] Voiceover: "..." (professional English)
   - Visual: "..." (factory footage, product close-up, charts, packaging)
4. Include specific numbers (specs, MOQ, delivery time, profit margin)
5. End with clear CTA: contact info + next steps
6. Duration: [DURATION] minutes, approximately [WORDS] words

Output format:
[0:00-0:30] Voiceover: "..."
              Visual: "..."
```

### 3.4 钩子生成提示词

```
Generate [N] different 3-second hooks for a TikTok video about [产品/话题].

Each hook must:
- Be 1-2 sentences, under 20 words
- Stop the scroll (curiosity, conflict, surprise, relatability)
- Be specific to [产品/话题]
- Use different hook types: question, statement, fact, challenge, comparison, story

Output only the hooks, numbered 1-[N].
```

---

## 4. AI 图片生成提示词

### 4.1 通用场景背景图提示词模板

```
[场景描述], [时间/光线], [天气/氛围], [摄影风格], [镜头], [画质], 
no people, no text, no logo, no watermark
```

### 4.2 常用场景提示词库

#### 森林营地
```
A cozy campsite in a dense pine forest at golden hour, warm sunlight filtering 
through tree canopy, orange tent in the background, camping gear on a wooden 
table, soft bokeh, cinematic photography, shallow depth of field, 4k, 
no people, no text, no logo
```

#### 山顶日出
```
A hiker's view from a mountain summit at sunrise, orange and pink sky, 
sea of clouds below, backpack and camping gear in foreground, 
epic landscape photography, wide angle, 4k, no people, no text, no logo
```

#### 湖边露营
```
Camping by a calm mountain lake at dusk, reflection of mountains in water, 
tent and campfire on the shore, warm firelight, peaceful atmosphere, 
cinematic photography, 4k, no people, no text, no logo
```

#### 森林徒步
```
A winding hiking trail through a misty forest, tall trees, soft morning light, 
backpack and hiking poles leaning against a tree, adventure atmosphere, 
cinematic photography, shallow depth of field, 4k, no people, no text, no logo
```

#### 星空营地
```
Campsite under a starry night sky, Milky Way visible, tent with warm light 
from inside, long exposure photography, dark blue and purple tones, 
epic night photography, wide angle, 4k, no people, no text, no logo
```

#### 秋日营地
```
Campsite in an autumn forest, golden and orange leaves, tent among trees, 
warm afternoon light, cozy fall atmosphere, cinematic photography, 
shallow depth of field, 4k, no people, no text, no logo
```

#### 雪地露营
```
Winter camping in a snow-covered forest, white tent among pine trees, 
snow falling, cold blue tones, crisp winter air, cinematic photography, 
4k, no people, no text, no logo
```

#### 沙漠露营
```
Camping in a desert at sunset, orange tent on sand dunes, warm golden light, 
vast empty landscape, adventure atmosphere, cinematic photography, 
wide angle, 4k, no people, no text, no logo
```

### 4.3 产品氛围图提示词（产品图+场景合成用）

> 注意：不要让 AI 直接生成产品（会和实际产品不符）。AI 只生成场景背景，产品用真实图抠图叠加。

#### 帐篷场景
```
Empty campsite with a flat spot for a tent, pine forest background, 
golden hour light, soft shadows, ready for product placement, 
cinematic photography, 4k, no tent, no people, no text
```

#### 背包场景
```
Rocky mountain trail with a flat rock in foreground, mountain view in background, 
morning light, ready for backpack placement, adventure photography, 
4k, no backpack, no people, no text
```

#### 炉具场景
```
Camping table with empty spot for a stove, forest background, 
warm afternoon light, cooking atmosphere, close-up shot, 
4k, no stove, no people, no text
```

### 4.4 图片生成参数建议

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| 比例 | 9:16（竖版）或 16:9（横版） | 短视频用9:16 |
| 风格 | cinematic photography | 电影感，适合户外 |
| 光线 | golden hour / soft natural light | 黄金时刻最有氛围 |
| 画质 | 4k, high detail, sharp focus | 高清 |
| 负向提示 | no people, no text, no logo, no watermark, blurry, low quality | 避免不需要的元素 |

### 4.5 图片生成工具选择

| 工具 | 优势 | 适用场景 |
|------|------|----------|
| Microsoft Copilot (DALL-E 3) | 免费，质量高，英文提示词效果好 | 场景背景图首选 |
| 豆包 | 免费，中文提示词友好，国内访问稳定 | 备用，或需要中文提示词时 |
| Midjourney ($10) | 质量最高，艺术感强 | 重要视频的关键帧（预算充足时） |
| Leonardo AI | 免费额度，可控制风格 | 需要特定风格时 |

---

## 5. AI 视频生成提示词

### 5.1 图生视频提示词模板（推荐）

```
[运动描述], [镜头运动], [光线变化], [氛围], [画质], 
smooth motion, no camera shake, no people, no text
```

### 5.2 常用视频片段提示词库

#### 营地慢摇
```
Slow pan across a cozy campsite in a pine forest, gentle wind moving 
tree leaves, warm golden hour light, soft shadows, cinematic, 
smooth motion, 4k, no people
```

#### 帐篷特写
```
Slow zoom in on a tent in a forest, sunlight filtering through trees, 
subtle movement of tent fabric in wind, peaceful atmosphere, 
cinematic, smooth motion, 4k
```

#### 森林步道
```
Tracking shot along a hiking trail through a misty forest, 
soft morning light, leaves gently falling, adventure atmosphere, 
cinematic, smooth motion, 4k, no people
```

#### 营火
```
Close-up of a campfire burning, flames dancing, sparks rising, 
warm orange light, dark forest background, cozy atmosphere, 
cinematic, slow motion, 4k
```

#### 湖面倒影
```
Slow pan across a calm mountain lake at dusk, reflection of mountains 
and sky, gentle ripples on water, peaceful atmosphere, 
cinematic, smooth motion, 4k
```

#### 云海日出
```
Time-lapse of sunrise over a sea of clouds from a mountain summit, 
sky changing from dark blue to orange and pink, epic landscape, 
cinematic, smooth motion, 4k
```

#### 树叶光影
```
Close-up of sunlight filtering through moving tree leaves, 
dappled light, bokeh background, peaceful forest atmosphere, 
cinematic, slow motion, 4k
```

#### 雨滴帐篷
```
Close-up of rain falling on a tent rainfly, water droplets running down, 
soft focus forest background, cozy rainy day atmosphere, 
cinematic, 4k
```

### 5.3 视频生成参数建议

| 参数 | Pika | Luma |
|------|------|------|
| 比例 | 9:16 或 16:9 | 9:16 或 16:9 |
| Motion（运动强度） | 0.5-0.7（避免过度运动） | 默认 |
| 时长 | 3-4秒 | 5秒 |
| 负向提示 | blurry, distorted, watermark, text, people | 同左 |

### 5.4 视频生成技巧

1. **图生视频优先**：上传一张高质量场景图，生成动态效果，比文生视频更可控
2. **短片段拼接**：生成多个3-5秒片段，在 CapCut 中拼接成完整视频
3. **运动要慢**：Motion 参数调低，避免 AI 生成的诡异运动
4. **固定镜头**：优先用 slow pan / slow zoom，避免复杂镜头运动
5. **空镜为主**：AI 生成人物容易出错，优先生成无人场景空镜

---

## 6. AI 配音参数与提示词

### 6.1 ElevenLabs 推荐参数

| 参数 | 2C 推荐 | 2B 推荐 | 说明 |
|------|---------|---------|------|
| 音色（男） | Adam / Antoni | Adam | Adam 沉稳通用，Antoni 年轻活力 |
| 音色（女） | Rachel / Domi | Rachel | Rachel 自然亲切 |
| Stability | 0.5-0.7 | 0.7-0.8 | 2C可稍低增加感情，2B要稳定 |
| Similarity | 0.8-0.9 | 0.9 | 越高越接近音色原型 |
| Style Exaggeration | 0.3-0.5 | 0.1-0.2 | 2C可夸张，2B要克制 |

### 6.2 配音脚本处理提示词

```
Convert this script into natural-sounding voiceover text:
[粘贴脚本旁白]

Requirements:
- Remove stage directions, timestamps, and visual descriptions
- Keep only the spoken words
- Make it sound natural when spoken aloud (not written)
- Add natural pauses with commas and periods
- Keep it casual and conversational
- Output only the voiceover text, ready to paste into ElevenLabs
```

### 6.3 多语言配音提示词

```
Translate and adapt this English voiceover into [目标语言]:
[英文旁白]

Requirements:
- Natural, native-sounding [目标语言]
- Adapt cultural references and idioms for [目标市场]
- Keep the same tone (casual/adventurous/professional)
- Keep the same length and pacing
- Output only the translated voiceover text
```

---

## 7. 标题/描述/标签生成提示词

### 7.1 TikTok 标题+描述+标签

```
Generate a TikTok title, description, and hashtags for this video:

Video content: [简要描述视频内容]
Product: [产品名]
Key benefit: [核心卖点]
Target audience: 18-35 year old outdoor enthusiasts in North America

Requirements:
- Title: 1 short sentence, under 50 characters, curiosity-inducing, includes keyword
- Description: 2-3 sentences, includes CTA "Link in bio", natural tone
- Hashtags: 5-7 relevant hashtags, mix of big (#camping 10M+), 
  medium (#campinggear 1M+), and niche (#lightweighttent 100K+)
- Include brand hashtag #NuotaoOutdoor
- All in English

Output format:
Title: [title]
Description: [description]
Hashtags: [#tag1 #tag2 #tag3 ...]
```

### 7.2 Instagram Reels 标题+描述+标签

```
Generate an Instagram Reels caption and hashtags for this video:

Video content: [视频内容描述]
Product: [产品名]

Requirements:
- Caption: 2-4 sentences, engaging, includes emojis (2-3), 
  includes CTA "Link in bio", ask a question to encourage comments
- Hashtags: 10-15 relevant hashtags, mix of big/medium/niche, 
  include #NuotaoOutdoor #outdoorgear #campinglife
- English, casual adventurous tone

Output format:
Caption: [caption]
Hashtags: [#tag1 #tag2 ...]
```

### 7.3 YouTube Shorts 标题+描述+标签（SEO 优化）

```
Generate a YouTube Shorts title, description, and tags for this video:

Video content: [视频内容描述]
Product: [产品名]
Target keyword: [目标关键词，如 "best lightweight tent"]

Requirements:
- Title: Under 60 characters, includes target keyword, click-worthy, 
  format like "Best [Product] Under $[Price]? (Honest Review)" or "[Number] [Product] Hacks You Need"
- Description: 2-3 paragraphs, includes target keyword in first sentence, 
  includes product link, timestamps (if applicable), CTA to subscribe
- Tags: 8-12 specific keywords, include target keyword and related searches
- English, SEO-optimized

Output format:
Title: [title]
Description: [description]
Tags: [tag1, tag2, tag3, ...]
```

### 7.4 常用标签库（户外装备）

#### 大标签（10M+ 播放）
- #camping #hiking #outdoor #outdoors #nature #travel #adventure #backpacking #campinglife #hikingadventures

#### 中标签（1M-10M）
- #campinggear #hikinggear #outdoorgear #camp #tent #backpack #sleepingbag #bushcraft #solocamping #campingvibes #outdoorlife #wildcamping

#### 小标签（100K-1M）
- #lightweighttent #campingtents #hikingbackpack #campingstove #outdoorcooking #campingessentials #hikingessentials #budgetcamping #campingforbeginners #NuotaoOutdoor

#### 2B 标签
- #outdoorindustry #wholesale #outdoorgearmanufacturer #campinggearsupplier #outdoorretail #b2b #privatelabel #oem

---

## 8. 多语言翻译提示词

### 8.1 脚本翻译（适配本地文化）

```
Translate and localize this English TikTok script into [目标语言]:

[英文脚本]

Requirements:
- Natural, native-sounding [目标语言], not literal translation
- Adapt cultural references, idioms, and humor for [目标市场]
- Keep the same structure: Hook → Problem → Solution → Social proof → CTA
- Keep the same tone: casual, adventurous, conversational
- Keep product names and brand name (Nuotao Outdoor) in English
- Adapt units (imperial to metric if needed: lbs→kg, ft→m, °F→°C)
- Adapt prices to local currency if mentioned
- Output in the same format as the original script
```

### 8.2 标题/描述翻译

```
Translate and localize this social media content into [目标语言]:

Title: [英文标题]
Description: [英文描述]
Hashtags: [英文标签]

Requirements:
- Natural, native-sounding [目标语言]
- Adapt cultural references and idioms
- Keep hashtags in English (hashtags work better in English globally) 
  OR translate to [目标语言] if targeting local market only
- Keep brand name Nuotao Outdoor
- Output format same as input
```

### 8.3 主要市场语言

| 市场 | 语言 | 备注 |
|------|------|------|
| 美国/加拿大 | English (US) | 主市场，优先 |
| 英国/澳大利亚 | English (UK/AU) | 可共用美式英语，微调拼写 |
| 德国 | Deutsch | 户外装备大市场 |
| 法国 | Français | |
| 西班牙/墨西哥 | Español | |
| 日本 | 日本語 | 高端户外市场 |
| 韩国 | 한국어 | |

---

## 附录：使用建议

1. **提示词要具体**：越具体的提示词，AI 生成质量越高。包含场景、光线、风格、镜头、画质、负向元素。
2. **迭代优化**：第一次生成不满意，调整提示词重新生成，不要一次就放弃。
3. **建立自己的提示词库**：把生成效果好的提示词保存下来，分类整理，重复使用。
4. **人工审核是必须的**：AI 生成的脚本、图片、视频、配音都需要人工审核，确保产品信息准确、无虚假宣传、英文地道。
5. **A/B 测试**：同一产品用不同提示词生成2版，对比数据，找到效果最好的提示词风格。

---

## 相关文档

- [AI 工具链配置指南](./ai_toolchain_setup_guide.md)
- [内容生产工作流 SOP](./content_production_sop.md)
- [4周内容日历](./content_calendar_4weeks.md)
- [2C+2B 内容策略](./b2c_b2b_content_strategy.md)
