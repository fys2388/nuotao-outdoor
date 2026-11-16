# GitHub Ecommerce Skills 选型与集成审计

> **版本**：v1.0 ｜ **日期**：2026-11-01 ｜ **性质**：READ / AUDIT / PLAN（只读审计与方案，未改任何业务代码）
> **审计人**：Nuotao AI OS Agent（DSH，商量 / SensenNova）
> **范围**：5 个候选 GitHub 仓库，针对美国户外市场 6 项业务能力的复用评估；仅选出最小试点并给出集成设计，不安装、不替换现有 Product Factory、不新增第二套商品状态机。

---

## 0. 结论速览（TL;DR）

| 决策点 | 结论 |
|---|---|
| 是否值得实施 | **是，但分两步**：先做「数据优先的运营分析 Skill」最小试点（mardab96），再评估「Listing/生图 Brief Skill」（mianbaofang）。**
| 首选仓库 | **mardab96/ecommerce-claude-skills**（MIT，20 Skill + 9 脚本，数据优先 + Human-in-the-loop，脚本自测全过） |
| 次选仓库 | **mianbaofang/ai-ecommerce-workflow**（MIT，生产级单 Skill，公开研究 + 证据账本 + 平台文案 + 生图 Brief） |
| 方法学参考 | **nexscope-ai/eCommerce-Skills**（MIT，157 个纯提示词模板，零依赖、零 API Key，可作为方法论/框架参考，不承载真实数据） |
| **排除** | **noique/cross-border-ecommerce-skills** —— **CC BY-NC 4.0 非商业许可，禁止并入商业项目**（尽管含 Trustpilot/Reddit VOC、Listing 文案等强相关内容） |
| 高风险/不建议直连 | **Rayyyyy1202/eec-agent** —— MIT 但为**完整独立应用**（需 OpenAI Key + Claude 专属 Skill 链 + 自带 DB/Web），与现有 Product Factory 重复度高、违反 LiteLLM 单网关原则 |
| 最大真实数据缺口 | Nuotao 的 `market_data.py`（Google Trends/Amazon/TikTok）当前为 **stub 启发式**；`competitor_analysis_service` 无数据时**生成示例竞品**；`weekly_report_service` 复购率 56.41 为**硬编码占位**；**无 LTV/cohort 模型、无物流回收分段分析** |
| 最小试点 | **5 个 Skill**：`ltv-cohort-read`、`repeat-purchase-flow-review`、`shipping-economics-review`（mardab96 脚本）+ `market-gap-analysis`（nexscope 方法学）+ `ai-ecommerce-workflow`（mianbaofang 文案/生图），应用于 **Car Camping Organization / Outdoor Repair & Replacement** 场景 |
| 试点前置事实 | Nuotao **已有** `research/car_camping_niche_findings.md`（2026-10-08，含 ASIN/价格/评论、证据标签、大量 UNKNOWN 评论数、1688 链接）——试点应**在其上继续**而非另起炉灶 |

---

## 1. 环境能力检查（第一步）

> 目的：确认 DSH 与 Claude Code / Codex 安装方式是否相同，避免凭假设集成。

### 1.1 DSH 支持的 Skill 格式与发现机制

| 检查项 | 结果 | 证据 |
|---|---|---|
| DSH 是否支持 SKILL.md | **是** | 本地 `skills/product-listing-automation/SKILL.md` 有效（frontmatter `name`+`description` + `scripts/` + `references/` + `assets/`）；会话 `available_skills` 目录含 `wc-product-upload`、`amazon-product-research`、`sealeap-amazon-acos-diagnostics` 等 SKILL.md 型 skill |
| Skill 自动发现目录 | 项目级 `.claude/skills/` + `skills/`；`skills-lock.json` 记录 github 源安装；另有 OpenViking（`viking://~/skills`）与 DSH 内置 | `.claude/skills/` 含 `amazon-product-research`、`sealeap-amazon-acos-diagnostics`；`skills/` 含 `product-listing-automation`；`skills-lock.json` 源为 `nexscope-ai/amazon-skills`、`coolqoo/1click-ecom-detailpage` |
| 能否运行其中的脚本 | **是**（Python 3.12.10，脚本可执行） | mardab96 `scripts/selftest.py` 运行 **exit 0**，7 个脚本全部通过自测；本地 `product-listing-automation/scripts/*.pyc` 已编译运行 |
| 是否等价于 Claude Code 安装 | **不完全等价** | DSH 发现目录是 `.claude/skills/` + `skills/`（非 `~/.claude/`）；Rayyyyy1202 的 Skill 依赖 `~/.claude/skills/eec-shared/`、`$ARGUMENTS`、`/eec-*` 斜杠命令与 Agent tool —— **DSH 不原生支持，需移植** |

### 1.2 当前已有 Skills（与本任务相关）

| Skill | 来源 | 与本任务关系 |
|---|---|---|
| `product-listing-automation` | 本地 `skills/` | 已有 WooCommerce 上架 + Rank Math SEO 4 步流程（`extract/upload/associate/configure_seo/full_listing/verify` 6 脚本）——**已覆盖「产品图片与 Listing」一部分** |
| `wc-product-upload` | DSH 目录 | WooCommerce 字段映射/API 推送指南——**已覆盖 WC 上架规则** |
| `amazon-product-research` | `.claude/skills/`（nexscope-ai/amazon-skills） | 亚马逊选品研究（提示词类） |
| `sealeap-amazon-acos-diagnostics` | `.claude/skills/` | Amazon Ads ACOS 诊断（脚本 + 证据契约）——**与 Nuotao marketing 分析同域，可借鉴「证据契约」模式** |
| `ecom-pdp` | `skills-lock.json`（coolqoo/1click-ecom-detailpage） | 详情页 Skill（`ECOM_PDP_SKILL_V1` 提示词）——与 mianbaofang Listing 能力部分重叠 |

### 1.3 Nuotao 项目现有能力（关键盘点，用于 Gap Matrix 的「已有能力」列）

> 依据 `backend/app/services/`、`backend/app/integrations/`、`backend/app/agents/` 与 `docs/`。

| 能力域 | 现有实现 | 真实度评估 |
|---|---|---|
| 市场情报 | `market_data.py`（Google Trends / Amazon BSR / TikTok 适配器） | **stub 启发式**（"MVP: returns stub data based on category heuristics"，生产需接 API/Scrapling） |
| 竞品分析 | `competitor_analysis_service.py`（价格对比、销量估算、`analyze_reviews`、`_extract_pain_points`） | 数据源为 WC 产品 + 1688 + 手动录入；**无数据时 `_generate_sample_competitors()` 生成示例竞品** —— 有编造风险 |
| 产品分析/情报 | `product_analysis_service.py`、`product_intelligence.py`、`product_context.py` | 存在 |
| 选品评分 | `nuotao_score_v3.py`、`selection_rules.py`、`selection_scorecard.py`、`nuotao_selection_service.py`、`selection_pipeline.py` | 存在（V3 评分 + 硬规则） |
| 成本/利润 | `cost_model_service.py`、`profit_engine.py`、`pricing_policy.py`、`cost_sync_service.py` | 存在（含 VAT/运费/退货成本） |
| 供应链/1688 | `sourcing_1688_service.py`、`scrape_1688.py`、`supply_chain.py`、`procurement_service.py`、`integrations/supplier.py` | 存在（1688 抓取服务 + 供应商集成） |
| Listing / 内容 | `product_content_service.py`、`product_copy_service.py`、`creative_service.py`、`seo_service.py`、`listing_gate.py`、`product_listing_service.py`、`wc_product_link_service.py` | 存在（含 WC Listing Gate 硬门槛） |
| 评论/痛点 | `competitor_analysis_service.analyze_reviews`、`customer.py`（create/update/list_reviews）、`customer_learning.py`、`feedback_loop.py`、`marketing.py`（feedback） | 存在（内部评论管理 + 竞品评论分析；**无外部平台评论自动抓取**） |
| 复购/留存/LTV | `weekly_report_service.py`（`"repeat_purchase_rate": 56.41` 硬编码占位） | **缺口**：无 cohort/LTV 模型，复购率为硬编码占位（违反 AGENTS.md §1.2「禁止硬编码业务经验值」） |
| 物流经济 | `integrations/logistics.py`、`logistics_monitor_service.py`、`cost_model_service`（含运费）、`fulfillment_service.py` | **缺口**：无「运费收取 vs 实际成本」的分段回收（banded recovery）分析 |
| 退货/退款 | `refund_service.py`、`alert_system_service`（退款率阈值） | 存在（退款率监控） |
| 数据分析/看板 | `dashboard_metrics_service.py`、`channel_analytics_service.py`、`business_alert_service.py` | 存在 |
| 产品工厂 | `product_factory_orchestrator.py`（13 阶段：Candidate→Data→V3→Decision→Master→Creative→Listing→WC→Verify→Learning） | 存在（**仅控制流程，不改 V3/硬规则/Listing Gate/WC**） |
| 审批/RBAC | `agent_approval_service.py`、`approval_rbac.py`、`approval_service.py`、`agent_suggestion_service.py`、`feishu_approval_service.py` | 存在（Human-in-the-loop + 审批队列） |

### 1.4 数据源实际可用性（试点必须基于真实接口，不得虚构）

| 数据源 | 可用性 | 证据 |
|---|---|---|
| WooCommerce API | **已配置** | `.env`：`WOOCOMMERCE_BASE_URL` / `CONSUMER_KEY` / `CONSUMER_SECRET` / `WEBHOOK_SECRET`；`integrations/woocommerce.py` 存在 |
| WP Media / RankMath | 已配置 | `.env`：`WP_USERNAME` / `WP_APPLICATION_PASSWORD` / `WP_MEDIA_UPLOAD_ENABLED` |
| 1688 | **服务存在** | `scrape_1688.py`、`sourcing_1688_service.py`、`integrations/supplier.py`；`docs/1688_*.md` 说明 |
| 浏览器抓取 | 可用 | 会话有 `browser-skill`（bsk_* 工具）+ `scrapling-official` skill；`integrations/scrapling.py` 存在 |
| 网络搜索 | 可用 | `web_search` / `web_fetch`（本会话可用）；`autoglm-websearch` skill |
| LLM 网关 | 已配置 | `.env`：`LLM_PROVIDER` / `SENSENOVA_API_KEY` / `DEEPSEEK_API_KEY`；`services/llm_gateway.py`（LiteLLM，**业务代码禁直连单一模型**） |
| 真实销量/搜索量/复购率/LTV | **当前不可得（需新增数据源）** | 无 Amazon 销量 API、无 Google Trends API、无 cohort 表；现有 market_data 为 stub |

> **重要合规提示**：Amazon 评论正文/星级/评论数在匿名 HTTP 下被登录墙阻挡（见 `research/car_camping_niche_findings.md` 数据质量披露）。任何「真实销量、搜索量、复购率、LTV」在无对应接口前**一律标 UNKNOWN / 待核验**，禁止用常识补事实。

---

## 2. 逐仓库审计（第二步）

### 2.1 候选仓库比较总表

| 仓库 | 最近提交 | LICENSE | 许可证 | Skill 数量/形态 | 真实脚本 | 依赖/Key | 真实数据能力 | 测试/安全 | 与 Nuotao 重复度 |
|---|---|---|---|---|---|---|---|---|---|
| [nexscope-ai/eCommerce-Skills](https://github.com/nexscope-ai/eCommerce-Skills) | 2026-08-26 | MIT | **可商用** | **157** 个单文件 SKILL.md（纯提示词模板） | 目标 6 Skill **无脚本**（个别其他 Skill 带 scripts/ + agents/openai.yaml 元数据） | **无 API Key**，仅 `npx skills add` | **无**：靠 LLM 现有知识与用户提供数据；不含真实检索器 | 无独立测试 | 低（方法学层面） |
| [mardab96/ecommerce-claude-skills](https://github.com/mardab96/ecommerce-claude-skills) | 2026-08-03 | MIT | **可商用** | **20** 个 Skill（`SKILL.md` + `scripts/` + `references/` + `examples/` + `playbooks/`） | **9 个脚本**（7 个确定性计算 + `selftest.py` + `validate-skills.py`） | 无（标准库，纯 Python） | **数据优先**：读导出/截图/URL/粘贴文本；缺数据标 `hypothesis`/`needs_data` | `selftest.py` **exit 0**（7 脚本全过） | 中（利润/评分部分重叠；LTV/复购/物流为补缺） |
| [mianbaofang/ai-ecommerce-workflow](https://github.com/mianbaofang/ai-ecommerce-workflow) | 2026-08-17 | MIT | **可商用** | **1** 个生产级 Skill（`SKILL.md` + 8 `references/` + `evals/` + `reports/` + `security/` + `tests/` + `scripts/`） | 打包/校验脚本（`validate_package.py`、`package_skill.py`）；Skill 本体为提示词+参考文档 | 无 Key（公开搜索用 LLM 现有能力） | 公开市场研究（搜索/单页读取）+ 证据账本；**不强求真实成交/销量** | `validate.yml` workflow + 自测 | **高**（与 product_content/creative/listing_gate 重叠） |
| [noique/cross-border-ecommerce-skills](https://github.com/noique/cross-border-ecommerce-skills) | 2026-08-01 | **CC BY-NC 4.0** | **禁止商用** | **58** Skill（53 单文件 + 5 多文件）+ **7** 工具（browser-fetch、fetchlib、trustpilot、api-pacer、backlink-kol、linktree-expander、contact-extractor） | 有（Python 工具） | 部分工具需 Semrush/代理（`brand-market-scan` 提及 Semrush） | 有（Trustpilot 抓取、Reddit VOC、SERP 拆解） | 有 `skill-lint.yml`、`secret-scan.yml` | 低-中（但因**许可**不可用） |
| [Rayyyyy1202/eec-agent](https://github.com/Rayyyyy1202/eec-agent) | 2026-05-06 | MIT | **可商用** | **15** 个 `eec-0N` Skill 链 + **完整应用**（`agent/server` hono+better-sqlite3+openai@4.76；`agent/web` Next.js） | 有（TypeScript 服务端 + 执行器 + ajv schema 校验） | **需 OpenAI API Key**；依赖 `~/.claude/skills/eec-shared/` | 有（契约化 JSON+MD；全部 claim 带源+置信度） | 有 preflight/validate/ajv | **极高**（完整独立站流水线，重复 Candidate/工厂/listing） |

### 2.2 逐仓库细节审计

#### A. nexscope-ai/eCommerce-Skills（MIT，可商用，方法学参考）

- **定位**：157 个免费 AI agent skills，覆盖 Amazon/Shopify/eBay/Etsy/TikTok/Walmart。"No binaries, no API keys, no setup friction — just markdown that any LLM can read."（README）
- **形态**：目标 6 个 Skill（market-gap-analysis / dropshipping-product-research / ecommerce-keyword-research / product-review-analysis / ecommerce-competitor-analysis / ecommerce-customer-retention）**均为单文件 SKILL.md，无脚本、无 API Key、无专有工具依赖**。`agents/openai.yaml`（仅 price-optimization-tool 等个别 Skill 有）只是 `display_name / short_description / default_prompt` 元数据，**非专有工具**。
- **工作流**：收集信息 → 一次多选追问 → 用内置框架研究分析 → 输出结构化建议，估算项标 `⚠️`。**本身不检索真实数据**，依赖宿主 Agent 的 web 工具与用户提供的数据。
- **真实数据能力**：**无**。适合作为「方法论/框架」参考（如 market-gap-analysis 的「搜索需求 vs 供给、价格空档、特征缺口、未被服务细分」框架），以及作为「先给一页结论、再逐步深入」的输出风格参考。
- **关键区分（用户特别要求）**：本仓库（GitHub，MIT）是**指令集合**；Nexscope 的**专有工具集合**（需 API 凭据）是 nexscope.ai SaaS，**不在本仓库内**。本仓库可安全复制/引用（保留 MIT 声明）。
- **重复度**：低（Nuotao 已有 V3 评分与选品；nexscope 提供的是通用电商方法学，非 Nuotao 状态机）。

#### B. mardab96/ecommerce-claude-skills（MIT，可商用，**首选**）

- **定位**：20 个 Claude Skills for e-commerce owners，"designed to run **without live platform integrations**. They work from exports, screenshots, URLs, pasted reports, reviews, tickets, and store documentation."（README）
- **AGENTS.md 三条硬约束（与 Nuotao 哲学完全一致）**：
  1. **数据优先**：读你提供的数据；缺数据就标 `hypothesis`/`needs_data`，**绝不编一个数字**（"This is the pack's one hard rule"）。
  2. **Human-in-the-loop**：Skills 诊断与建议，**不登录任何后台、不改任何线上内容**，"Every skill in this pack stops at approval-ready."
  3. **诚实面对局限**：阈值是起点启发式而非平台规则；外部标准需具名+日期。
- **脚本**：7 个确定性计算脚本（`margin_stack.py`、`cohort_read.py`、`catalog_scan.py`、`promo_impact.py`、`shipping_recovery.py`、`subscription_survival.py`、`dispute_rate.py`）+ `selftest.py` + `validate-skills.py`。**实测 `selftest.py` exit 0**，例如 `cohort_read.py` 保证「未到的 horizon 输出 null 而非 0」「成熟 segment 不被新客户清空」「cohort 大小随数字一起打印」；`shipping_recovery.py` 保证「退款行从总数中排除」。
- **与户外品类的契合**：AGENTS.md 明示「**Considered one-off purchases**（furniture, electronics, tools）——长研究周期、重/超大件导致 **shipping economics 主导毛利**，复购可能非增长杠杆」。**户外露营装备即属此类** → `shipping-economics-review`、`ltv-cohort-read`、`repeat-purchase-flow-review` 是最对症的。
- **真实数据能力**：**有（数据优先）**——从订单导出/COGS/物流发票/评论/工单读真实值；缺则如实标注。
- **重复度**：中（`contribution-margin-check`、`promo-discount-impact-review` 与 Nuotao `cost_model_service`/`profit_engine` 重叠；**LTV/cohort、repeat-purchase-flow、shipping-economics、product-feed-qa、returns-reason-miner 为 Nuotao 真实缺口**）。
- **风险**：需人工装配输入文件（`references/getting-your-data.md` 说明）；部分 Skill 靠相对路径引用 `../scripts/` 与 `../references/`，**复制 Skill 文件夹时须连同 scripts/references 一起**（README 明示"a skills-only copy installs the skills and quietly breaks their helpers"）。

#### C. mianbaofang/ai-ecommerce-workflow（MIT，可商用，**次选 / 文案生图**）

- **定位**：单一生**产级** Skill（v1.1.1，`maturity_tier: production`、`review_cadence: monthly`、`target_platforms: openai/claude/generic/agent-skills-compatible/vscode`）。
- **覆盖**：识别商品 → 公开市场研究（搜索 3-6 组词、去重、5-8 个公开链接）→ **证据账本**（`research-evidence-ledger.md`，区分「仅发现/已读公开正文/用户提供/读取失败」）→ **先交付一页结论** → 用户选平台后出「平台文案包」（3 标题、3-5 卖点、描述、5 FAQ、关键词/禁用词）→ 可选**生图 Brief**（比例/尺寸/数量/文字安全区，要求保持产品结构/颜色/Logo/材质一致）。
- **反编造硬约束**（SKILL.md）："不负责：真实成交价、销量或搜索量证明；登录态/受保护页面；批量抓取；绕过反爬/验证码；自动发布；虚假评论、资质或功效；保证排名/转化/销售结果。" 每条约外部结论带 `[来源: URL/搜索工具 + 关键词 + 时间 + 观察口径]`；来源不支持的内容只标「推断/待核验」。
- **参考资料**：`public-search-policy.md`、`research-evidence-ledger.md`、`asset-output-contract.md`、`platform-image-specs.md`、`product-copy-framework.md`、`listing-compliance-review.md`、`copy-research-basis.md`、`compliance-terms.md`。
- **真实数据能力**：**有（公开研究，不强求成交/销量）**——公开页面观察价、竞品链接、痛点/卖点，但明确**不声称**真实销量/搜索量。
- **重复度**：**高**——与 Nuotao `product_content_service`（文案）、`creative_service`（生图）、`seo_service`、`listing_gate`（硬规则）、本地 `product-listing-automation`（WC 上架）、`ecom-pdp` Skill 部分重叠。但它的「**证据账本 + 一页结论 + 合规复审 + 生图一致性约束**」是 Nuotao 目前较弱的部分，可作为 **Listing/生图 Brief 的合规与事实护栏参考**。
- **风险**：需把 `references/` 8 个文件与 `evals/` 一起迁移；强依赖宿主搜索能力（无则标「未完成公开核验」，不补事实）。

#### D. noique/cross-border-ecommerce-skills（CC BY-NC 4.0，**禁止商用**）

- **定位**：58 个 AI agent skills（53 单文件 + 5 多文件）+ 7 个独立工具，覆盖品牌策略（含 `brand-market-scan`）、Amazon 链（含 `amazon-listing-copywriter`、`amazon-main-image-prompt`、`amazon-aplus-image-prompt`、`amazon-keyword-research`、`amazon-compliance-review`）、DTC、金融资本、红人、外联、**Trustpilot VOC**、**Reddit pre-purchase VOC**、SERP 内容拆解（`serp-content-teardown`）。
- **许可证**：`LICENSE` 首行为 **Creative Commons Attribution-NonCommercial 4.0 International License (CC BY-NC 4.0)**（Copyright 2026 Alex / 黄子阳）。**NonCommercial 限制** → **未经商业授权，不得复制、改编或并入 Nuotao 商业项目**（用户明确提醒）。`brand-market-scan` 提及 Semrush，可能涉及第三方付费数据。
- **真实数据能力**：强（Trustpilot 抓取、Reddit VOC、SERP/关键词拆解）——**但许可禁止商用**，故**排除**。
- **结论**：**不采用**。若未来取得书面商业授权或仅作个人学习参考，可再评估 `trustpilot`/`reddit-voc` 的「真实用户评论挖掘」价值；当前不列入试点。

#### E. Rayyyyy1202/eec-agent（MIT，可商用，但**高风险不建议直连**）

- **定位**：完整「独立站全链路 Agent」——15 个 `eec-0N` Skill（01-research → 02-product-selection → 03-brand-identity → 03b-legal-pack → 04-creative-factory → 04b-social-proof → 05-site-build → 05b-merchant-console → 06-tracking → 07a-tech-seo → 07b-content-marketing → 08-paid-ads → 09-optimization → 11b-customer-service → 13-data-model）+ `shared/` + `agent/`（server + web）+ `examples/`。
- **Skill 强项**：`eec-01-research`（6 大模块：市场趋势/需求量化/用户洞察/竞品分析/广告情报/供应信号，**全部 claim 必须带源 + 置信度**，单源只能 medium/low，`ajv` schema 自校验）；`eec-02-product-selection`（4 模块：候选生成/SKU 评分/定价/供应链评估，**强制上游门**（01 output 存在 + ajv 校验），`margin_pct ≥ 50%`，10 个 Phase 2 钩子全填）。
- **依赖/冲突**：`agent/server/package.json` 依赖 `openai@4.76`（**需 OpenAI API Key**，违反 Nuotao「业务代码直连单一模型供应商」禁令，应走 LiteLLM）；Skill 依赖 `~/.claude/skills/eec-shared/{conventions,data-contracts,phase2-hooks}.md` + `schemas/*.json` 与 Claude 专属 `$ARGUMENTS`、`/eec-0N` 斜杠命令、Agent tool —— **非 DSH 原生，需移植**；自带 `better-sqlite3` + Next.js，**与 Nuotao 的 Product Factory / PostgreSQL 完全两套体系**。
- **真实数据能力**：有（契约化 JSON+MD，免费数据源，claim 带源+置信度）。
- **重复度**：**极高**——`eec-01`/`eec-02` 与 Nuotao `market_data`+`competitor_analysis`+`nuotao_score_v3`+`sourcing_1688` 职能重叠；`eec-04-creative-factory` 与 `creative_service` 重叠；`eec-05b-merchant-console` 与 `listing_gate`/WC 重叠。
- **结论**：**不建议整体集成**（引入第二套状态机/第二套数据模型/自有 LLM 直连）。**可借鉴其「契约 schema + 上游门 + 置信度追溯」设计模式**，但以 Nuotao 现有服务为唯一事实源。

---

## 3. License 审计（重点）

| 仓库 | LICENSE | 商用 | 复制/并入 Nuotao | 说明 |
|---|---|---|---|---|
| nexscope-ai/eCommerce-Skills | MIT | ✅ 允许 | ✅ 允许（保留 MIT 声明） | 指令集合与 nexscope.ai SaaS 专有工具**分离**；本仓库无专有工具 |
| mardab96/ecommerce-claude-skills | MIT | ✅ 允许 | ✅ 允许（保留 MIT 声明） | 含脚本；复制需连同 `scripts/`/`references/` |
| mianbaofang/ai-ecommerce-workflow | MIT | ✅ 允许 | ✅ 允许（保留 MIT 声明） | 生产级，`manifest.json` 声明 MIT |
| **noique/cross-border-ecommerce-skills** | **CC BY-NC 4.0** | ❌ **禁止** | ❌ **禁止（未经商业授权）** | 含 Trustpilot/Reddit VOC 等强内容，但许可阻断 |
| Rayyyyy1202/eec-agent | MIT | ✅ 允许 | ✅ 允许（但需移植 + 去 OpenAI 直连） | 应用依赖需评估；Skill 需移植 Claude 约定 |

> **审计结论**：可商用的许可为 **MIT × 4**；**noique 因 CC BY-NC 4.0 排除**。所有纳入的 Skill 均需在 Nuotao 仓库保留原 LICENSE 与版权声明。

---

## 4. Skill Gap Matrix（第三步）

> 列：「业务能力 → 候选 Skill（是否存在已核验）/ 已有 Nuotao 能力 / 数据依赖 / License / 重复度 / 建议」。
> **仅列已核验存在的 Skill；不存在者明确标注「❌ 不存在（凭名称不得假设）」**。

| 业务能力 | 候选 Skill | 已有 Nuotao 能力 | 数据依赖 | License | 重复度 | 建议 |
|---|---|---|---|---|---|---|
| 美国户外市场调查 | nexscope `market-gap-analysis`（✅存在，纯模板） | `market_data.py`（**stub**）+ `us-outdoor-market-research-2026.md` | 需宿主 web 工具 + 用户数据；**无真实检索器** | MIT | 低 | ✅ 选为**方法学参考**，接入真实数据源（见 §6.1） |
| 细分品类机会发现 | nexscope `market-gap-analysis` / `dropshipping-product-research`（✅存在）；mianbaofang `ai-ecommerce-workflow`（✅存在） | `selection_rules`/`selection_pipeline` + `research/car_camping_niche_findings.md` | 公开搜索 + 证据账本 | MIT | 低-中 | ✅ 试点：用 mardab96/nexscope 框架在**已有 Car Camping 研究**上补足机会点 |
| 产品选品与 1688 供应链研究 | nexscope `dropshipping-product-research`（✅存在，纯模板）；Rayyyyy1202 `eec-02-product-selection`（✅存在，需移植） | `nuotao_score_v3`+`sourcing_1688_service`+`scrape_1688`+`selection_pipeline` | 1688 抓取 + 成本/物流 | MIT | **高** | ⚠️ 不引入（Nuotao V3+1688 已覆盖）；仅参考 eec-02 的「上游门/schema」设计 |
| 真实竞品与用户评论分析 | nexscope `product-review-analysis`（✅14KB，纯模板）；mardab96 `review-objection-miner`/`returns-reason-miner`（✅）；noique `trustpilot`/`reddit-voc`（✅但 NC）；mianbaofang（✅公开研究） | `competitor_analysis_service.analyze_reviews`+`_extract_pain_points`（**无数据生成示例**） | 外部评论需抓取/导出；`shipping_invoice`/`review` 导出 | MIT / **NC** | 中 | ✅ 用 mardab96 `review-objection-miner` 补「真实评论→痛点/异议」；**noique 排除**；Nuotao 需修 `_generate_sample_competitors` |
| 产品图片与 WooCommerce Listing | mianbaofang `ai-ecommerce-workflow`（✅文案+生图Brief+合规）；nexscope `product-description-generator`/`product-title-optimization`（✅模板）；本地 `product-listing-automation`（✅已有）；Rayyyyy1202 `eec-04-creative-factory`（✅需移植） | `product_content_service`+`creative_service`+`seo_service`+`listing_gate`+`product-listing-automation` | 公开研究 + 平台规则 + 生图工具 | MIT | **高** | ⚠️ 不重复造轮子：**仅借鉴 mianbaofang 的「证据账本 + 一页结论 + 合规复审 + 生图一致性」护栏**，落地在现有 listing/creative 服务内，不新增第二套 Listing |
| 上线后复购/退货/毛利/LTV | mardab96 `ltv-cohort-read`（✅）/`repeat-purchase-flow-review`（✅）/`shipping-economics-review`（✅）/`contribution-margin-check`（✅）/`promo-discount-impact-review`（✅） | `profit_engine`+`cost_model`+`refund_service`+`business_alert`；**无 cohort/LTV**；复购率硬编码 56.41 | 订单导出/COGS/物流发票/评论/工单 | MIT | **中（毛利）/低（LTV、物流）** | ✅ **优先试点**：`ltv-cohort-read`、`repeat-purchase-flow-review`、`shipping-economics-review`（真实缺口） |
| 关键词研究 | nexscope `ecommerce-keyword-research`（✅纯模板）；noique `amazon-keyword-research`（✅NC） | `seo_service`/`product_category_planning`/`docs/phase1a-product-titles-keywords.md` | 需关键词 API（无） | MIT / NC | 中 | ⚠️ 暂缓：无真实搜索量接口前只能做模板级；noique 排除 |
| 物流成本分段回收 | mardab96 `shipping-economics-review`（✅，`shipping_recovery.py`） | `logistics`+`cost_model`（含运费）+`logistics_monitor` | 承运商发票 + 订单(目的地/运费) + 当前规则 | MIT | **低** | ✅ **优先试点**（户外大件/超大件毛利被物流侵蚀的典型场景） |
| 产品 Feed 质量 | mardab96 `product-feed-qa`（✅） | `product_data_extractor`+`product_readiness_gate`+`wc_product_link_service` | 目录/Feed 导出 | MIT | 中 | ⚠️ 试点后可评（与 WC 同步/内容完整性部分重叠） |
| AI Listing / 图片 Brief | mianbaofang `ai-ecommerce-workflow`（✅） | `product_content_service`/`creative_service`/`main_image_service`/`image_generation_service` | 公开搜索 + 平台图片规格 | MIT | **高** | ✅ **借鉴其护栏**（证据账本/合规复审/生图一致性），不新建第二套 |
| LTV 数据模型 | — | ❌ 无（`models` 无 Cohort/LTV 类） | 订单 + 客户身份 | — | — | ❌ **需新增**：`cohort` 表/服务（见 §6.1） |

> **说明**：`ecommerce-customer-retention`（nexscope）仅为 36 行小模板，覆盖度低，作为方法学参考即可；`ltv-cohort-read` / `repeat-purchase-flow-review` / `shipping-economics-review` 为 mardab96 独有、**Nuotao 真实缺口**，为试点首选。

---

## 5. 最小试点方案（第四步）

### 5.1 试点场景与已有基础

- **场景**：Car Camping Organization / Outdoor Repair & Replacement（美国户外）。
- **已有基础**：`research/car_camping_niche_findings.md`（2026-10-08）已含：NICHE 1 Car organization（ASIN B071F82CYJ $19.60 / 4.7★ / 27,529 评等）、生态位机会（无多品类组合套件）、替换/维修痛点（卡扣带失效 190 人赞、刚性丧失、调节行程不足、不防水、无锁定）、1688 链接（DIRECT_EVIDENCE）。
- **数据缺口（已有披露）**：多数评论数/星级为 **UNKNOWN**（Amazon 登录墙）；价格可恢复；销量/搜索量/复购率/LTV 无接口。

### 5.2 试点选择（5 个 Skill，全部 MIT 可商用）

| # | Skill | 来源 | 角色 | 产出契约 |
|---|---|---|---|---|
| 1 | `ltv-cohort-read-ecommerce` | mardab96 | 补 LTV/cohort 缺口 | cohort 表（30/60/90/180/365）、二次下单窗口、分群对比、**未到 horizon 输出 null 而非 0** |
| 2 | `repeat-purchase-flow-review-ecommerce` | mardab96 | 补复购/留存缺口 | 流程表（welcome/browse/cart/post-purchase/education/replenishment/cross-sell/win-back）+ 下次 3 个测试 |
| 3 | `shipping-economics-review-ecommerce` | mardab96 | 补物流经济缺口 | 分段回收表（zone/金额段）、免邮门槛 vs AOV 分布、2-3 个阈值场景、配送承诺核对 |
| 4 | `market-gap-analysis` | nexscope | Car Camping 机会框架 | 覆盖缺口、评论痛点→机会、搜索需求 vs 供给、价格空档、特征缺口；估算标 ⚠️ |
| 5 | `ai-ecommerce-workflow` | mianbaofang | Listing 文案 + 生图 Brief + 合规 | 一页结论 → 平台文案包（3 标题/3-5 卖点/描述/5 FAQ/关键词）→ 生图 Brief；来源带 `[来源: URL+关键词+时间+口径]` |

> **不选**：`dropshipping-product-research`/`eec-02-product-selection`（与 V3/1688 重复）；`eec-04-creative-factory`（需移植+OpenAI）；noique 全部（NC）；`product-description-generator` 等（重复）。

### 5.3 试点必须输出的证据清单（用户要求）

对 Car Camping Organization 试点，每个结论必须输出：

1. **真实来源 URL** + **采集日期**（如 `https://www.amazon.com/dp/B071F82CYJ` @ 2026-10-08，本次浏览器复核 @ 审计日）。
2. **价格与评价数的原始页面证据**（价格来自搜索片段为 `DIRECT_EVIDENCE`；评价数被登录墙阻挡 → 用浏览器会话复核，仍不可得则 `UNKNOWN`）。
3. **用户痛点证据**（带原文引用 + 有用票数，如卡扣带失效 190 人 helpful）。
4. **已知数据缺口**（哪些 horizon/评论数/搜索量未达，`needs_data`）。
5. **1688 候选与来源 ID**（如 `detail.1688.com/offer/1086968286278.html`）。
6. **采购价、重量、尺寸、物流成本**：真实值或 **UNKNOWN**（无接口前不得编造）。
7. **独立标签**：`DIRECT_EVIDENCE` / `INFERENCE`（说明依据）/ `THIRD_PARTY_ESTIMATE` / `UNKNOWN`。

> **硬约束**：无实际数据接口，**不得声称获得真实销量、搜索量、复购率或 LTV**；一律标 `UNKNOWN`/`needs_data` 并列入「已知数据缺口」。

### 5.4 试点执行步骤（仅读/分析，dry-run）

1. 用 `market-gap-analysis`（nexscope 框架）对 Car Camping Organization 做一次机会缺口分析，输入用现有 `car_camping_niche_findings.md` 数据。
2. 对已列 ASIN 做**浏览器复核**（bsk/scrapling），尽可能补评论数/星级/正文（Amazon 登录墙允许时），否则标 UNKNOWN。
3. 用 `ltv-cohort-read`（mardab96 脚本 `cohort_read.py`）对**现有订单导出**跑 cohort（若 WC 有订单历史）；无导出 → 标 `needs_data`，不编 LTV。
4. 用 `shipping-economics-review`（`shipping_recovery.py`）对物流发票/订单导出跑分段回收；无数据 → `needs_data`。
5. 用 `repeat-purchase-flow-review` 对现有 email/SMS 流程做缺口分析（截图/导出）。
6. 用 `ai-ecommerce-workflow` 产出 Car Camping 商品的**一页结论 + 平台文案草案 + 生图 Brief**（含证据账本与合规复审），**仅草案，不发布**。
7. 输出统一 JSON + 证据清单，落盘 `docs/research/car_camping_skill_pilot_<date>.md`（只读/分析，dry-run）。

---

## 6. 集成设计（第五步，最小方案）

### 6.1 需要新增的真实数据源

| 数据源 | 用途 | 建议接入层 | 成本/风险 |
|---|---|---|---|
| 订单/客户历史（WC → 本地） | cohort/LTV/复购 | `backend/app/services` 新增 `customer_cohort_service` + `models` 新增 cohort 表（或复用 `order`/`customer` 表聚合，**不加第二套状态机**） | 低；需先确认订单/客户身份字段完整性（guest checkout 碎片化风险） |
| 承运商发票/运费数据 | 物流回收 | `integrations/logistics` 扩展（发票解析 + zone/段聚合） | 中；发票行含燃油/住宅/超大附加费 |
| 评论抓取（Amazon/Trustpilot/Reddit） | 痛点/异议 | `integrations/scrapling`（合规、robots.txt、公开字段）；**noique 排除** | 中；需合规评审（AGENTS.md §4.4），Amazon 登录墙需浏览器会话 |
| 关键词/搜索量 | 需求量化 | 可选：Google Trends API / 付费数据（**需成本上限与降级**） | 中-高；无接口前不声称搜索量 |
| 1688 报价/成本 | 采购价/重量/尺寸 | 已有 `sourcing_1688_service`；补重量/尺寸抓取 | 低；已有 |
| LLM | 分析/文案 | **LiteLLM 网关**（已有，禁止直连单一模型） | 低；已有 |

### 6.2 边界与护栏（必须保留）

1. **保留** Nuotao **V3 评分**与**硬规则**（`nuotao_score_v3`、`selection_rules`、`data_integrity_gate`）。
2. **保留** **Candidate / Product Master / Listing / WooCommerce** 边界与状态机（`product_lifecycle_service`、`product_listing_service`、`wc_product_link_service`）——**不新增第二套商品状态机**。
3. **保留** **Product Factory Orchestrator**（`product_factory_orchestrator.py` 13 阶段仅控制流程，不改业务服务）。
4. **Skill 输出结构化 JSON + 证据清单**（`source_url` / `collected_at` / `evidence_tag` / `confidence` / `needs_data`）。
5. **关键状态变化仍由现有服务执行**：Skill 只产建议/草案，**不得**直接改 Candidate/Master/Listing/WC 状态。
6. **禁止 Skill 绕过**：审批（`approval_rbac`/`agent_approval_service`）、规则（`rule_engine`）、租户隔离（`workspace_identity`/多租户）、WC Listing Gate（`listing_gate`）。
7. **写入类默认 dry-run**：任何 WC 写入/发布/改价/删除须经现有授权 + 人工批准，默认 dry-run（`--dry-run` 全链路）。

### 6.3 最小集成落地（建议顺序，仅方案，不执行）

1. **复制** mardab96 相关 Skill 到 `skills/`（连同 `scripts/` + `references/` + `examples/` + `playbooks/`，保留 LICENSE）。
2. **复制** mianbaofang `ai-ecommerce-workflow`（连同 `references/`、`evals/`，保留 LICENSE）到 `skills/`。
3. **复制** nexscope 目标 6 Skill 到 `skills/`（纯模板，作为方法学参考）。
4. **注册** 到 `skills-lock.json`（`sourceType: github` + `computedHash`）。
5. **新增** 适配层：`backend/app/agents/skill_adapters/`（或集成到现有 `m6_tool_registry`/`tool_gateway`）——把 Skill 输出**映射**为现有服务的**结构化 JSON**，并做：
   - 事实/推断/未知三态标注；
   - 证据清单校验（无证据不得进决策）；
   - dry-run 守卫（写入前检查审批 + 授权 + 租户 + Listing Gate）。
6. **新增** `customer_cohort_service`（仅读聚合，不改订单模型），供 `ltv-cohort-read` 消费。
7. **修正** `competitor_analysis_service` 的 `_generate_sample_competitors`（无数据应标 `needs_data`，不生成示例）。
8. **修正** `weekly_report_service` 的硬编码 `repeat_purchase_rate`（改为读真实聚合或标 `needs_data`）。

---

## 7. 风险与未决问题

| 风险/问题 | 等级 | 说明 |
|---|---|---|
| noique 许可阻断 | 🔴 高 | CC BY-NC 4.0 禁止商用；即使其 Trustpilot/Reddit VOC 极匹配，**未经书面商业授权不得使用** |
| Rayyyyy1202 整体集成 | 🔴 高 | 引入第二套状态机/数据模型 + OpenAI 直连（违反 LiteLLM 单网关）+ Claude 专属 Skill 链需移植 |
| Amazon 登录墙 | 🟠 中 | 评论正文/星级/评论数匿名不可得；需浏览器会话，仍可能受限 → 标 UNKNOWN |
| 真实销量/搜索量/LTV 无接口 | 🟠 中 | 无 Amazon 销量 API、无 Trends API、无 cohort 表；**不声称**，标 `needs_data` |
| mardab96 相对路径引用 | 🟡 低-中 | 复制 Skill 必须连带 `scripts/`/`references/`，否则 helper 静默失效 |
| mianbaofang 与现有 Listing 重复 | 🟡 低-中 | 只借鉴护栏，不新建第二套 Listing；需明确 boundary |
| guest checkout 身份碎片化 | 🟠 中 | 影响 cohort/复购准确性；分析前须确认身份标识 |
| 数据隐私/合规 | 🟠 中 | 评论/工单/订单导出含 PII（L4），须脱敏；爬取先过合规评审（AGENTS.md §4.4） |
| DSH 与 Claude 差异 | 🟡 低 | DSH 发现目录为 `.claude/skills/`+`skills/`，非 `~/.claude/`；Rayyyyy1202/部分 Skill 需移植 |

---

## 8. 最终结论

1. **值得实施**（分两步）：
   - **第一步（推荐先做）**：接入 **mardab96/ecommerce-claude-skills** 的 `ltv-cohort-read` / `repeat-purchase-flow-review` / `shipping-economics-review` 三个**数据优先** Skill（MIT，脚本自测全过），补齐 Nuotao 在 **LTV/复购/物流回收**上的真实缺口；同时以 **nexscope** `market-gap-analysis` 做 Car Camping 机会方法学。
   - **第二步（评估后）**：以 **mianbaofang** `ai-ecommerce-workflow` 的**证据账本 + 一页结论 + 合规复审 + 生图一致性**护栏增强现有 Listing/生图服务（不新建第二套 Listing）。
2. **排除**：noique（CC BY-NC 4.0 禁止商用）；Rayyyyy1202（完整应用 + OpenAI 直连 + Claude 约定，仅借鉴设计模式）。
3. **关键前提**：任何「真实销量/搜索量/复购率/LTV」在接入真实数据源前**一律标 UNKNOWN / 待核验**；写入类操作默认 **dry-run** + 现有授权 + 人工批准；**不改** V3 评分、硬规则、Candidate/Product Master/Listing/WooCommerce 边界、Product Factory Orchestrator。
4. **本次审计仅 READ/AUDIT/PLAN**：未修改任何业务代码、未安装仓库、未替换 Product Factory、未新增第二套商品状态机。

---

## 附录 A：候选仓库 URL

- https://github.com/nexscope-ai/eCommerce-Skills
- https://github.com/mianbaofang/ai-ecommerce-workflow
- https://github.com/mardab96/ecommerce-claude-skills
- https://github.com/noique/cross-border-ecommerce-skills
- https://github.com/Rayyyyy1202/eec-agent

## 附录 B：核验方法与日期

- 全部仓库于审计日通过 `git clone --depth 1` 克隆至 `.tmp/skills-audit/` 复核（TLS 偶发需重试）。
- License / 最近提交：`git log -1` + 读取 `LICENSE` 首段。
- 脚本可运行性：`python scripts/selftest.py`（exit 0）。
- 目标 Skill 存在性：按目录名 + SKILL.md 逐一核验，不存在者明确标注。
- 现有 Nuotao 能力：`backend/app/services|integrations|agents`、`docs/`、`research/` 目录与 `grep` 核验。
