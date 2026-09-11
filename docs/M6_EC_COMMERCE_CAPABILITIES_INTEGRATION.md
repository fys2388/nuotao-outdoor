# M6 跨境电商六能力原生集成 — 架构设计与实施计划

> 状态：**已实施完成（2026-09-02），6项能力全部原生集成，图片生成已验证可出图**。
> 目标：将 6 项跨境电商能力（商品信息优化、广告&内容运营增长、选品、商品素材、活动策划、客服方案）以**原生实现**方式集成到 Nuotao Outdoor AI OS，不依赖外部黑盒系统。
> 关联：`AGENTS.md` §3（AI Agent 开发原则）、§2.3（分层约束）；`docs/project_architecture.md`；现有 5-Agent 体系。

---

## 1. 背景与现状评估

### 1.1 六项能力 vs 项目现状

| # | 能力 | 现有对应模块 | 状态 | 缺口 |
|---|---|---|---|---|
| 1 | 跨境商品信息优化 | `seo_service.py`（结构化数据/关键词/审计）+ `content_generation_service.py`（卖点/SEO 内容） | ✅ 已有 | 多语言 listing 本地化 |
| 2 | 跨境广告&内容运营增长 | `marketing.py`（campaign/创意/A-B 实验）+ `marketing_learning.py`（增长上下文/校准） | ✅ 已有 | 达人/KOL 运营子模块 |
| 3 | 电商选品 | `selection_manager_service.py`（选品推荐+审批流）+ `sourcing_service.py` + `product_intelligence.py` | ✅ 已有 | 无需新建，接线即可 |
| 4 | 电商商品素材 | `content_generation_service.py`（标题/卖点/详情文案） | ⚠️ 半覆盖 | **商品图片生成服务**（全新） |
| 5 | 电商活动策划 | 无独立模块（EDM 仅 `promotional` 类型） | ❌ 缺口 | **活动策划模块**（全新） |
| 6 | 电商客服方案 | `customer_service.py`（FAQ/AI 回复/人工工单）+ `customer_manager.py` | ✅ 已有 | 物流履约/多语言话术模板 |

### 1.2 集成原则（对齐 AGENTS.md）

1. **原生实现，不引入外部黑盒**：所有能力在 `app/services/` + `app/agents/` 内实现，通过 `llm_gateway` 统一调用 LLM，不直连单一供应商。
2. **Agent 是提议者不是执行者**（AGENTS.md §3.1）：高风险动作（活动上线、改价、批量发图）进 `approval_service` 审批队列。
3. **分层约束**（AGENTS.md §2.3）：Agent 禁止直连数据库/文件系统，所有数据走 `services` 层白名单 API；图片生成走 `integrations/` 封装。
4. **提示词版本化**（AGENTS.md §3.2）：所有新提示词入 `prompts` 表，通过 `prompt_registry` 管理，不硬编码。
5. **成本护栏**（AGENTS.md §3.3）：图片生成等付费能力设月度预算，超限自动降级到低配模型或暂停。
6. **先规划后编码**（AGENTS.md §1.2）：本文件即规划产物，评审通过后分模块实施。

---

## 2. 商品图片生成服务（能力 4，核心缺口）

### 2.1 模型选型与成本分析

> 数据来源：2026-09 市场公开价格（阿里云百炼、火山引擎、OpenAI、第三方 API 聚合）。

| 模型 | 单张成本（人民币） | 质量 | 国内访问 | 适用场景 |
|---|---|---|---|---|
| **wan2.7-image（通义万相）** | **¥0.08** | 高（电商图友好） | ✅ 稳定 | **默认首选**：商品主图、详情图 |
| Qwen-Image-3.0 Standard | ¥0.18 | 很高（Arena 国内第一） | ✅ 稳定 | 高质量场景备选 |
| Seedream 4.0 | ¥0.22 | 高 | ✅ 稳定 | 创意场景备选 |
| Seedream 5 Lite | ¥0.25 | 高 | ✅ 稳定 | 创意场景备选 |
| GPT Image 2（OpenAI） | ¥0.07 | 高 | ❌ 需代理 | 海外部署备选 |
| Flux schnell（第三方 fal.ai） | ¥0.02 | 中（快速出图） | ❌ 需代理 | 批量草稿/低质量预览 |
| Flux.2 自托管 | ¥0.05-0.12（摊销） | 很高 | 需 GPU | 未来大规模时考虑 |

**选型结论（2026-09-02 最终确认）**：
- **默认模型**：`doubao-seedream-4-0-250828`（火山引擎 Seedream 4.0，¥0.20/张）—— **新用户 200 张免费额度**，成本低，质量高（SOTA 级多模态图像创作模型，支持 4K 输出、多图融合、组图生成）。已开通并验证可正常出图。
- **高质量备选**：`doubao-seedream-5-0-pro-260628`（¥0.30/张，输入图首张免费）—— 字节跳动最新模型，支持精准图像编辑、图层分离，用于关键场景。
- **中质量备选**：`doubao-seedream-4-5-251128`（¥0.25/张，200张免费）—— 需在控制台开通后使用。
- **降级链**：Seedream 4.0（200免费）→ Seedream 4.5（200免费）→ Seedream 5.0 Pro → qwen-image-3.0 → mock（本地占位）。
- **阿里云备选**：wan2.7-image（¥0.08/张）、qwen-image 系列—— 因阿里云账户状态异常（欠费/未开通）暂不可用，保留为降级链备选，账户恢复后可重新启用。
- **自托管**：暂不实施（需 GPU 服务器，前期投入大），预留接口，日均 >500 张时再评估。

### 2.2 架构设计

```
app/
  integrations/image_gen.py      # 唯一封装：多后端适配器（wan2.7/qwen/seedream）、超时、重试、降级
  services/image_generation_service.py  # 业务服务层：任务编排、成本核算、落库、审批、审计
  models/image_gen.py             # 图片生成任务表
  api/v1/endpoints/image_gen.py   # API 端点
```

**核心流程**：
1. 前端/Agent 提交图片生成请求（prompt + 商品 ID + 用途 + 模型选择）
2. `image_generation_service` 校验预算（`agent_budget`）→ 创建任务记录（status=pending）
3. 调用 `integrations/image_gen.py` → 适配器路由到指定模型后端
4. 生成成功 → 保存图片到本地存储/对象存储 → 更新任务（status=completed，记录 cost）
5. 生成失败 → 重试（最多 2 次）→ 降级到低配模型 → 仍失败则标记 failed
6. 所有动作写 `event_log`，全量可审计

**图片用途分类**（对应电商场景）：
- `main_image`：商品主图（白底/场景）
- `detail_image`：详情页配图
- `lifestyle_image`：生活方式/场景图
- `marketing_image`：营销/广告素材
- `variant_image`：变体/颜色图

### 2.3 成本护栏

- 每 workspace 设月度图片生成预算（默认 ¥100/月，约 1250 张 wan2.7）
- 单次生成前检查预算余额，超限自动降级或拒绝
- 高成本模型（>¥0.15/张）需人工审批后才能使用
- 成本记录到 `agent_budget` + `image_generation_tasks.cost`，支持月度报表

---

## 3. 电商活动策划模块（能力 5，核心缺口）

### 3.1 定位

生成、改写、优化专业电商活动策划方案，覆盖：
- 大促活动（黑五、网一、圣诞、夏季促销等）
- 新品发布活动
- 清仓/库存清理活动
- 节日营销活动
- 会员专属活动

**Agent 角色归属**：Marketing Manager（营销经理）的子能力，复用现有 `marketing.py` 的 campaign/experiment 框架。

### 3.2 架构设计

```
app/
  services/activity_planner_service.py  # 活动策划服务：方案生成、改写、优化、审批
  models/activity_plan.py                # 活动策划方案表
  api/v1/endpoints/activity_planner.py   # API 端点
```

**活动方案数据结构**：
```json
{
  "activity_name": "Black Friday 2026 Outdoor Gear Sale",
  "activity_type": "big_promotion",
  "start_date": "2026-11-24",
  "end_date": "2026-11-30",
  "target_audience": "outdoor enthusiasts, 25-45, US/EU",
  "budget": {"total": 5000, "currency": "USD"},
  "objectives": {"target_revenue": 50000, "target_orders": 500, "target_roas": 4.0},
  "discount_strategy": {"type": "tiered", "tiers": [{"min_qty": 1, "discount_pct": 20}, {"min_qty": 3, "discount_pct": 30}]},
  "product_selection": ["product_id_1", "product_id_2"],
  "marketing_channels": ["edm", "social_media", "paid_ads", "seo"],
  "content_plan": [{"channel": "edm", "send_date": "2026-11-20", "subject": "Early Access..."}],
  "creative_assets": [{"type": "banner", "spec": "1920x1080", "prompt": "..."}],
  "timeline": [{"phase": "preheat", "start": "2026-11-17", "actions": [...]}],
  "risk_mitigation": ["库存不足风险：提前备货 top 20 SKU", "物流延迟风险：提前与承运商沟通"],
  "kpi_tracking": {"metrics": ["revenue", "orders", "conversion_rate", "roas", "aov"]}
}
```

**核心功能**：
1. `generate_activity_plan`：基于活动类型+时间+预算+目标商品，AI 生成完整方案
2. `rewrite_activity_plan`：基于人工反馈/历史数据，改写优化方案
3. `optimize_activity_plan`：基于历史活动效果数据，优化折扣策略/渠道分配/预算分配
4. 审批流：方案生成后进入 `approval_service` 队列，人工审批后才能执行
5. 与现有模块联动：方案中的 EDM 内容 → `edm_automation_service`；创意素材 → `image_generation_service`；商品选择 → `selection_manager_service`

### 3.3 提示词设计

入 `prompts` 表，名称 `ACTIVITY_PLANNER_V1`，变量：
- `activity_type`：活动类型
- `context_json`：业务上下文（历史活动数据、商品数据、预算约束）
- `output_schema`：输出 JSON Schema

---

## 4. 达人/KOL 运营子模块（能力 2，补强）

### 4.1 定位

挂在 Marketing Manager 下，补充现有 marketing 模块缺失的达人运营能力：
- 达人筛选与匹配（基于品类、粉丝量、互动率、地域）
- 达人合作方案生成（寄样、佣金、内容要求）
- 达人内容效果追踪（曝光、点击、转化、ROI）
- 达人关系管理（合作历史、评分、续约建议）

### 4.2 架构设计

```
app/
  services/influencer_service.py  # 达人运营服务
  models/influencer.py             # 达人档案 + 合作记录表
  api/v1/endpoints/influencer.py   # API 端点
```

**注意**：达人数据来源为人工录入/CSV 导入（Phase 1），不做爬虫（合规风险）。未来可探索合规的达人平台 API 集成。

---

## 5. 多语言 Listing 本地化（能力 1，补强）

### 5.1 定位

挂在 `seo_service` + `content_generation_service` 下，补充多语言商品 listing 生成与优化能力：
- 支持语言：英语（默认）、德语、法语、西班牙语、意大利语（覆盖主要欧洲市场）
- 翻译 + 本地化（不是直译，而是符合目标市场消费习惯的文案）
- 多语言 SEO 关键词优化
- 与 WooCommerce 多语言插件（WPML/Polylang）对接

### 5.2 实现方式

- 在 `content_generation_service.py` 新增 `generate_localized_listing(product_id, target_lang)` 函数
- 复用 `llm_gateway`，提示词入 `prompts` 表（`LISTING_LOCALIZATION_V1`）
- 翻译结果经 `i18n_service` 校验后存储
- 不新建独立模块，在现有服务上扩展

---

## 6. 客服话术模板（能力 6，补强）

### 6.1 定位

挂在 `customer_service.py` 下，补充标准化客服话术模板：
- 物流履约类：发货通知、物流延迟、清关问题、配送失败
- 退换货类：退货流程、换货流程、退款进度
- 质量问题类：产品缺陷、使用问题、保修
- 售前咨询类：尺码、材质、发货时间、支付方式
- 多语言支持：英/德/法/西/意

### 6.2 实现方式

- 在 `customer_service.py` 新增话术模板管理（JSON 配置 + AI 个性化生成）
- 模板入 `knowledge/` 目录，Agent 只读访问
- `generate_ai_response` 优先匹配模板，再 AI 个性化
- 不新建独立模块

---

## 7. 选品能力接线（能力 3，无需新建）

现有 `selection_manager_service.py` 已完整实现选品推荐+审批流，只需：
- 在前端「营销增长」菜单下新增「AI 选品」入口（已有 `selection` 菜单，确认可见性）
- 确认 Agent 工具注册中包含选品相关工具
- 无需新建代码

---

## 8. 数据库设计

### 8.1 新增表

| 表名 | 用途 | 关键字段 |
|---|---|---|
| `image_generation_tasks` | 图片生成任务 | id, workspace_id, product_id, prompt, use_case, model, status, image_url, cost, created_at, completed_at |
| `activity_plans` | 活动策划方案 | id, workspace_id, name, type, start_date, end_date, budget, plan_json, status, approval_status, created_by |
| `influencers` | 达人档案 | id, workspace_id, name, platform, followers, engagement_rate, category, region, contact_info, rating |
| `influencer_collaborations` | 达人合作记录 | id, influencer_id, activity_id, type, compensation, content_url, metrics_json, status |

### 8.2 迁移编号

- `0025_image_generation_tasks.py`
- `0026_activity_plans.py`
- `0027_influencers.py`

---

## 9. API 端点设计

| 端点 | 方法 | 用途 |
|---|---|---|
| `/api/v1/image-gen/tasks` | POST | 提交图片生成任务 |
| `/api/v1/image-gen/tasks` | GET | 列出图片生成任务 |
| `/api/v1/image-gen/tasks/{id}` | GET | 获取单个任务详情 |
| `/api/v1/image-gen/models` | GET | 列出可用模型及价格 |
| `/api/v1/activity-planner/generate` | POST | 生成活动策划方案 |
| `/api/v1/activity-planner/{id}/rewrite` | POST | 改写活动方案 |
| `/api/v1/activity-planner/{id}/optimize` | POST | 优化活动方案 |
| `/api/v1/activity-planner` | GET | 列出活动方案 |
| `/api/v1/influencers` | GET/POST | 达人档案管理 |
| `/api/v1/influencers/{id}/collaborations` | GET/POST | 达人合作记录 |
| `/api/v1/content/localize` | POST | 多语言 listing 本地化 |
| `/api/v1/customer/templates` | GET | 客服话术模板列表 |

---

## 10. Agent 工具注册

通过 `tool_gateway.register_handler` 注册以下白名单工具：

| 工具名 | 所属 Agent | 权限级别 | 用途 |
|---|---|---|---|
| `generate_product_image` | Product Analyst / Marketing Manager | L2（需审批高成本模型） | 生成商品图片 |
| `generate_activity_plan` | Marketing Manager | L2（需审批） | 生成活动策划方案 |
| `rewrite_activity_plan` | Marketing Manager | L1 | 改写活动方案 |
| `match_influencers` | Marketing Manager | L1 | 达人匹配推荐 |
| `localize_listing` | Product Analyst | L1 | 多语言 listing 本地化 |
| `generate_customer_reply` | Customer Manager | L1 | 客服回复生成（已有，补模板） |

所有工具调用写 `agent_executions` 审计表，L2 工具进入审批队列。

---

## 11. 前端集成

在 `frontend/src/App.tsx` 菜单中新增/调整：

**营销增长组**（已有）：
- 内容生成（已有）
- SEO 基建（已有）
- EDM 营销（已有）
- **商品图片生成**（新增）
- **活动策划**（新增）
- **达人运营**（新增）

**供应链组**（已有）：
- AI 选品建议（已有，确认可见）

实现方式：复用 `ModulePage` + `moduleConfigs` 通用页面模式，新增配置项即可，无需新建页面组件。

---

## 12. 实施计划与优先级

| 阶段 | 模块 | 优先级 | 预估工作量 | 依赖 |
|---|---|---|---|---|
| P0 | 商品图片生成服务（integrations + service + model + API） | 🔴 最高 | 中 | 无 |
| P0 | 电商活动策划模块（service + model + API + 审批流） | 🔴 最高 | 中 | 无 |
| P1 | 达人/KOL 运营子模块 | 🟡 中 | 小 | 无 |
| P1 | 多语言 listing 本地化 | 🟡 中 | 小 | content_generation_service |
| P2 | 客服话术模板 | 🟢 低 | 小 | customer_service |
| P2 | 前端菜单 + 页面接线 | 🟢 低 | 小 | 后端 API |
| P2 | 数据库迁移 + 测试 | 🟢 低 | 中 | 所有模块 |

**验收标准**：
1. 每个新模块有单元测试（覆盖率 ≥ 80%）
2. API 端点可通过 `/docs` 访问并测试
3. Agent 工具可通过 `tool_gateway` 调用并审计
4. 图片生成实际可出图（wan2.7 后端）
5. 活动策划方案可生成并进入审批流
6. 成本护栏生效（超预算拒绝/降级）
7. `ruff check` + `pytest` 全绿

---

## 13. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| 图片生成 API 密钥泄露 | 财务损失 | 密钥仅存 `.env` / Secrets，不入库不入日志；`gitignore` 已覆盖 |
| 图片生成质量不达标 | 业务效果差 | 多后端可切换；人工审核后才使用；支持重新生成 |
| 活动方案 AI 幻觉（错误折扣/日期） | 业务损失 | 方案必须人工审批后执行；关键字段（折扣率、日期）做规则校验 |
| 达人数据合规风险 | 法律风险 | Phase 1 仅人工录入，不爬虫；数据来源标注 |
| 多语言翻译质量 | 品牌形象 | 翻译结果人工审核；关键文案（品牌名、规格）不翻译 |
| 成本超支 | 财务损失 | 月度预算硬上限；高成本模型需审批；实时成本报表 |

---

## 14. 决策记录（ADR）

- **ADR-M6-001（2026-09-02 最终更新）**：图片生成默认模型最终确定为 `doubao-seedream-4-0-250828`（火山引擎 Seedream 4.0，¥0.20/张，**新用户 200 张免费额度**）。决策过程：① 最初选 wan2.7-image（¥0.08/张），但阿里云账户状态异常（欠费/未开通）无法使用；② 切换到 Seedream-5.0-pro（¥0.30/张），质量最高但成本较高；③ 发现 Seedream-4.0/4.5 各有 200 张免费额度，且 Seedream-4.0 仅 ¥0.20/张，性价比最优；④ 开通 Seedream-4.0 并验证可正常出图，确定为默认模型。高质量场景可手动切换到 Seedream-5.0-pro（¥0.30/张）。阿里云模型保留为降级链备选，账户恢复后可重新启用。
- **ADR-M6-002**：不实施自托管图片生成（Flux/SDXL），理由：需 GPU 服务器，前期投入大，当前规模（日均 <100 张）下 API 更划算。预留接口，日均 >500 张时再评估。
- **ADR-M6-003**：活动策划作为 Marketing Manager 子能力，不新建独立 Agent，理由：复用现有 marketing 框架和审批流，减少架构复杂度。
- **ADR-M6-004**：达人数据 Phase 1 仅人工录入，不做爬虫，理由：合规风险（AGENTS.md §4.4），达人平台数据使用条款限制。

---

*文档版本：v1.1（2026-09-02）*
*实施状态：已完成 — 6项能力全部原生集成，53个单元测试全通过，图片生成已验证可出图（Seedream 5.0 Pro），数据库迁移0025已执行，前端5个菜单项已添加，5个Agent工具已注册，3个提示词已入库。*
