# Nuotao AI OS · 独立站 WC 产品页 AI 生图 + 文案 SOP

> **定位**：从 1688 链接到 WooCommerce 前台可发布的**端到端内容作业标准**。
> **对应工作流**：`docs/selection_to_woocommerce_operation_workflow.md`（阶段 C：内容与图片）
> **对应生图规范**：`docs/ai_image_prompt_template_library.md`（V1.0，Seedream I2I）
> **对应字段契约**：`wc-product-upload` skill 中的 `push_product_to_woocommerce` API 契约
> **本文档定位**：把上述分散的规范**整合为一份可执行的作业手册**，供 Agent 与运营直接调用。

---

## 目录

```
docs/sop/
├── README.md                              # 本文件，总索引
├── wc-ai-content-sop-v1.0.md              # 主 SOP 文档（9 个 Phase）
├── prompts/
│   ├── seedream-i2i/                      # Seedream 5.0 Pro I2I 主工具（对齐既有规范）
│   │   ├── 01-white-background.md         # 主图01：白底清爽主图
│   │   ├── 02-camping-scene.md            # 主图02：真实露营场景
│   │   ├── 03-promotion-conversion.md     # 主图03：促销转化主图
│   │   ├── 04-product-structure.md        # 主图04：产品结构细节
│   │   ├── 05-multi-color.md              # 主图05：多色/多规格展示
│   │   ├── 06-brand-hero.md               # 详情06：品牌主视觉
│   │   ├── 07-core-features.md            # 详情07：核心卖点
│   │   ├── 08-function-structure.md       # 详情08：功能结构
│   │   ├── 09-use-scenes.md               # 详情09：使用场景
│   │   ├── 10-product-details.md          # 详情10：产品细节
│   │   └── 11-quality-assurance.md        # 详情11：品质保障
│   └── flux-kontext/                      # Flux Kontext 备用工具
│       ├── background-replace.md          # 换背景保真
│       └── scene-injection.md             # 场景注入保真
├── copywriting/                           # 文案 Prompt 库
│   ├── wc-product-title.md                # 产品标题
│   ├── wc-short-description.md            # 短描述
│   ├── wc-full-description-html.md        # HTML 详细描述（7 模块）
│   ├── wc-seo-meta.md                     # SEO Meta
│   └── wc-multilingual-localization.md    # 多语言本地化
├── audit/
│   └── compliance-audit-prompt.md         # 合规审核 Prompt（L1 自动）
├── checklists/
│   ├── image-generation-checklist.md      # 生图验收
│   ├── copywriting-checklist.md           # 文案验收
│   └── pre-push-checklist.md              # 推送前拦截
├── wc-fields/
│   └── content-packet-schema.md           # WC 字段契约（对齐 wc-product-upload）
└── examples/
    └── yoga-mat-complete.json             # 完整示例（瑜伽垫）
```

---

## 使用方式

### 场景 1：Agent 自动化（端到端）

```
① 选品闸门 → ② 采集清洗 → ③ 品牌定位 → ④ AI 生图 → ⑤ AI 文案
        ↓
⑥ 三层合规审核 → ⑦ 字段组装 → ⑧ 推送验证 → ⑨ 数据回流
```

Agent 应按主文档 `wc-ai-content-sop-v1.0.md` 的 Phase 顺序执行，
每个 Phase 调用本目录下的对应 Prompt / Checklist 文件。

### 场景 2：运营手工执行（单点）

运营可按需调用：
- 只出图：读 `prompts/seedream-i2i/` 下的模板
- 只出文案：读 `copywriting/` 下的模板
- 只审核：读 `audit/compliance-audit-prompt.md`
- 只校验：读 `checklists/` 下的清单

### 场景 3：Prompt 版本管理

每次成功出图，必须把 Prompt 记录到 `examples/` 目录下（参考 `yoga-mat-complete.json` 结构），
包含 prompt_id、tool、parameters、seed、output_url、iteration log、review_status。

---

## 与既有文档的关系

| 既有文档 | 本 SOP 的关系 |
|---|---|
| `docs/ai_image_prompt_template_library.md` | 本 SOP `prompts/seedream-i2i/` 是从中拆分 + 升级 |
| `docs/selection_to_woocommerce_operation_workflow.md` | 本 SOP 覆盖其阶段 C（内容与图片）+ 阶段 D（推送） |
| `docs/product_selection_logic_v2.0.md` | 本 SOP Phase 1 调用其选品评分模型 |
| `docs/cross_border_compliance_knowledge_base.md` | 本 SOP Phase 6 调用其合规知识库 |
| `AGENTS.md` §3.1 Agent 是提议者 | 本 SOP 4 道闸口严格执行 Human-in-the-loop |

---

## 版本

- **v1.0** (2026-09-27)：初版，覆盖 9 个 Phase + 11 张图 Prompt + 5 类文案 Prompt + 3 类 Checklist + WC 字段契约

---

*下一步 v1.1（预留）*：加入视频素材 SOP、A/B 测试自动化、多市场本地化扩展。
