# CURRENT_PIPELINE_MAP — P0-2 只读架构审计

> PHASE 1 — READ ONLY ARCHITECTURE AUDIT  
> 审计日期：2026-07-01  
> 审计范围：SOP-A / V3 / Decision / Creative / Listing / WooCommerce 全链路  
> 约束：不修改任何业务代码，仅读取实际代码并输出架构映射

---

## 0. 结论摘要

| 问题 | 答案 |
|------|------|
| 当前是否已有 pipeline/orchestrator | **是**，`pipeline_orchestrator.py`（P2-2 时代，内存态 8 步骤，不可用）+ `product_pipeline_service.run_pipeline()`（内联长函数） |
| 哪些阶段已有可调用 service | 全部 13 个 stage 均有可调用 service（见 §2 详表） |
| 哪些阶段只能 HTTP 调用 | `list_to_woocommerce`（同步 `requests`）、`push_product_to_woocommerce`（async 但内部用 `requests`） |
| 当前状态从哪里读取 | `Product.candidate_status` / `Product.status` / `Product.funnel_stage` / `Product.data_integrity_status` / `Product.mastered_at` / `Product.reject_reasons` |
| 哪些状态可以自动推进 | Data Readiness→V3（gate pass 时）、V3→Hard Rules（集成）、Creative Brief→Generate→QC（自动链）、Listing Gate passed→WC Sync（自动） |
| 哪些状态必须等待人工 | Decision（APPROVE/REJECT）、Creative Human Review、Listing Gate needs_review、Approval |
| 哪些失败已有 retry | `retry_engine.py`（通用）、`list_to_woocommerce`（3 次 1s/3s/9s 内联重试）、`pipeline_orchestrator.retry_step`（内存态） |
| 哪些失败目前直接结束 | V3 hard veto blocked→停止、Listing Gate blocked→停止、WC sync 异常→返回失败 dict、Data Integrity gate failed→跳过评分 |

---

## 1. 已有编排器分析

### 1.1 `pipeline_orchestrator.py`（P2-2 时代）

```
位置: backend/app/services/pipeline_orchestrator.py
状态: 内存态 (_pipeline_runs dict)
步骤: 8 步 (sourcing→analysis→copywriting→images→pricing→review→listing→seo)
持久化: 无（进程重启丢失）
DB 绑定: 无 workflow_run_id / execution_status 表
幂等性: 无（按 run_id 字符串，不按 product_id）
异常队列: 无
Resume: 不支持（无 WAITING_APPROVAL 持久化）
```

**结论：与 P0-2 要求的 13-stage DB-backed orchestrator 差距巨大，不可直接复用。**  
但它的 `_safe_call` 动态导入模式可作为"服务不可用时降级"的参考。

### 1.2 `product_pipeline_service.run_pipeline()`

```
位置: backend/app/services/product_pipeline_service.py:792
类型: 内联长 async 函数（1958 行文件的 ~1000 行）
流程: input→analysis→images→listing_data→V3 gate→auto_list
事务: 单 session，flush 多次
V3 集成: run_v3_gate() 落库候选 + evaluate_product() + evaluate_v3_gate()
上架: auto_list 直接调 list_to_woocommerce() 或 confirm_and_list()
```

**结论：SOP-A 主流程已存在，但它是"一次性直推"模式，不是 13-stage 编排。  
P0-2 需要的是"分阶段推进 + 可暂停/恢复 + 可重试"的编排层。**

---

## 2. 13 个 Stage 的可调用 Service 映射

| Stage | 可调用 Service | 函数签名 | 位置 | 可持久化 | 可异步 |
|-------|---------------|----------|------|---------|--------|
| **S1** CANDIDATE_READY | `sourcing_service.create_product_candidate` | `(session, product_data, source_type, source_url, workspace_id, trace_id) → (Product, ProductSource)` | `sourcing_service.py:51` | ✅ | ✅ |
| S1 幂等建档 | `product_source_identity.get_or_create_by_source` | `(session, workspace_id, source_offer_id, build, fallback_sku) → (Product, bool)` | `product_source_identity.py:161` | ✅ | ✅ |
| S1 1688 搜索 | `sourcing_1688_service.search_products` | `(keyword, page, page_size, sort) → dict` | `sourcing_1688_service.py:142` | ❌ mock | ❌ sync |
| S1 1688 详情 | `sourcing_1688_service.get_product_detail` | `(product_id) → dict` | `sourcing_1688_service.py:193` | ❌ mock | ❌ sync |
| S1 Newton 找品 | `newton_agent_service.newton_agent_search` | `(message, ...) → dict` | `newton_agent_service.py:517` | ❌ mock | ❌ sync |
| **S2** DATA_READINESS | `data_integrity_gate.check_integrity` | `(facts: ScoreFacts) → GateResult` | `data_integrity_gate.py:87` | ❌ 纯函数 | ✅ |
| S2 V3 评分入口 | `nuotao_selection_service.evaluate_product` | `(session, product_id, workspace_id, trace_id, ai_assessment) → dict` | `nuotao_selection_service.py:201` | ✅ | ✅ |
| S2 评分闸门 | `product_pipeline_service.evaluate_v3_gate` | `(evaluation: dict) → dict` | `product_pipeline_service.py:454` | ❌ 纯函数 | ✅ |
| S2 数据完整性 | `data_integrity_gate.check_integrity` (同上) | | | | |
| S2 Backfill | `backfill_1688_service.backfill_1688_products` | `(session, workspace_id, product_ids, candidate_only, batch_limit, dry_run) → dict` | `backfill_1688_service.py` | ✅ | ✅ |
| **S3** V3_EVALUATION | `nuotao_selection_service.evaluate_product` (同上) | | | | |
| S3 评分映射 | `nuotao_score_mapper.map_dimensions` | `(facts: ScoreFacts) → (dict, dict)` | `nuotao_score_mapper.py:128` | ❌ 纯函数 | ✅ |
| S3 严格映射 | `nuotao_score_mapper.map_dimensions_strict` | `(facts: ScoreFacts) → (dict, dict)` | `nuotao_score_mapper.py:251` | ❌ 纯函数 | ✅ |
| **S4** HARD_RULES | 集成在 `evaluate_product` 中（V1-V12 veto） | | | | |
| S4 评分器 | `product_pipeline_service.run_v3_gate` | `(session, product_info, listing_data, workspace_id, trace_id) → dict` | `product_pipeline_service.py:604` | ✅ | ✅ |
| **S5** PRODUCT_DECISION | `decision_service.get_product_decision_view` | `(session, workspace_id, product_id, trace_id) → ProductDecisionView` | `decision_service.py:458` | ✅ | ✅ |
| S5 应用决策 | `decision_service.apply_product_decision` | `(session, workspace_id, product_id, request: ProductDecisionRequest, actor, trace_id) → ProductDecisionResult` | `decision_service.py:863` | ✅ | ✅ |
| S5 审批 | `approval_service.ensure_approval` / `approve_approval` / `reject_approval` | | `approval_service.py:78` | ✅ | ✅ |
| **S6** PRODUCT_MASTER | `decision_service.apply_product_decision` (decision=APPROVE 时设置 mastered_at) | | | | |
| S6 状态推进 | `decision_service._get_next_candidate_status` | `(current) → str` | `decision_service.py:775` | ❌ | ✅ |
| **S7** CREATIVE | `creative_service.create_brief_from_product` | `(session, product_id, workspace_id, objective, channel, target_market, visual_style, created_by, trace_id) → CreativeBrief` | `creative_service.py:1163` | ✅ | ✅ |
| S7 生成 | `creative_service.execute_generation` | `(session, run_id, workspace_id, prompt, model, width, height, reference_image, negative_prompt, trace_id) → CreativeGenerationRun` | `creative_service.py:331` | ✅ | ✅ |
| S7 批量生成 | `creative_service.generate_brief_assets` | `(session, brief_id, workspace_id, trace_id) → list[CreativeGenerationRun]` | `creative_service.py:1653` | ✅ | ✅ |
| S7 创意网关 | `creative_gateway.execute_creative_operation` | `(request: CreativeRequest) → CreativeResult` | `creative_gateway.py` | ❌ 外部 | ✅ |
| **S8** CREATIVE_QC | `creative_service.run_quality_check` | `(session, asset_id, workspace_id, trace_id) → dict` | `creative_service.py:653` | ✅ | ✅ |
| S8 人工审核 | `creative_service.review_asset` | `(session, asset_id, result, reasons, reviewer_id, workspace_id, trace_id) → CreativeStudioAsset` | `creative_service.py:743` | ✅ | ✅ |
| **S9** LISTING_BUILD | `product_listing_service._generate_listing_data` | `(product_info: dict) → dict` | `product_pipeline_service.py:176` | ❌ 纯函数 | ✅ |
| S9 本地化 | `listing_localization_service` | | `listing_localization_service.py` | ✅ | ✅ |
| S9 工单 | `product_listing_service.create_listing_queue` | `(products: list, status) → dict` | `product_listing_service.py:190` | ✅ | ✅ |
| S9 Gate(dict) | `listing_gate.evaluate_gate_from_dict` | `(listing_data: dict) → dict` | `listing_gate.py:239` | ❌ 纯函数 | ✅ |
| S9 Gate(Product) | `listing_gate.evaluate_gate` | `(product, prices, en_copy, purchase_cost) → dict` | `listing_gate.py:144` | ❌ 纯函数 | ✅ |
| **S10** LISTING_GATE | 集成在 `list_to_woocommerce` 中（gate 在前） | | | | |
| **S11** WC_SYNC | `woocommerce_sync_service.push_product_to_woocommerce` | `(product_id: str, db_session=None) → dict` | `woocommerce_sync_service.py:1239` | ✅ | ✅ |
| S11 批量 | `woocommerce_sync_service.batch_push_products_to_woocommerce` | `(product_ids: list, db_session=None) → dict` | `woocommerce_sync_service.py:1463` | ✅ | ✅ |
| S11 传统 | `product_listing_service.list_to_woocommerce` | `(product: dict, status="publish") → dict` | `product_listing_service.py:278` | ✅ | ❌ sync |
| S11 WC 关联 | `wc_product_link_service.resolve_wc_product_id` | `(product, auth, headers, budget) → (int, bool)` | `wc_product_link_service.py:39` | ✅ | ❌ sync |
| S11 WC 记忆 | `wc_product_link_service.remember_wc_product` | `(session, product, wc_id, slug) → None` | `wc_product_link_service.py:75` | ✅ | ✅ |
| **S12** WC_VERIFY | 集成在 `push_product_to_woocommerce` 中（回读验证） | | | | |
| **S13** LEARNING | `event_service.create_event` | `(session, workspace_id, event_type, entity_type, entity_id, payload, trace_id, commit) → EventLog` | `event_service.py:12` | ✅ | ✅ |

---

## 3. 当前状态字段映射

### 3.1 Product 状态字段

| 字段 | 类型 | 取值 | 用途 |
|------|------|------|------|
| `status` | String(24) | `draft`, `active`, ... | 商务/执行状态 |
| `candidate_status` | String(16) nullable | `candidate`, `approved`, `testing`, `winner`, `rejected`, NULL | M5.13 候选生命周期。NULL = 下游商务品（如 WC 同步品） |
| `funnel_stage` | String(24) nullable | V3 funnel stage | V3 选品漏斗 |
| `data_integrity_status` | String(16) nullable | `complete`, `partial`, `missing`, NULL | 数据完整性闸门 |
| `data_integrity_score` | Numeric(5,2) nullable | 0-100 | 数据完整度评分 |
| `data_integrity_missing` | JSON list | 字段名列表 | 缺失字段列表 |
| `mastered_at` | DateTime nullable | timestamp | Product Master 创建时间（NULL=非 Master） |
| `mastered_by` | String(128) nullable | 审批人 | 审批人 |
| `mastered_trace_id` | String(64) nullable | trace id | 追踪 ID |
| `reject_reasons` | JSON list | 规则 ID/备注 | V1-V12 否决快照 |
| `deleted_at` | DateTime nullable | timestamp | 软删除 |

### 3.2 Creative 状态字段

| 模型 | 字段 | 取值 |
|------|------|------|
| `CreativeGenerationRun` | `status` | `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED` |
| `CreativeStudioAsset` | `status` | `QC_PASSED`, `REJECTED`, ... |
| `CreativeBrief` | `status` | `draft`, `active`, ... |
| `CreativeApprovalRequest` | `status` | `pending`, `approved`, `rejected`, ... |

### 3.3 Listing / WC 状态字段

| 模型 | 字段 | 取值 |
|------|------|------|
| `ListingJob` | `status` | `pending`, `approved`, `processing`, `rejected`, `published`, `failed` |
| `ListingJob` | `wc_verify_status` | `verified`, `failed`, NULL |
| `ProductMapping` | `sync_status` | `synced`, `pending`, `error`, ... |

### 3.4 Approval 状态字段

| 模型 | 字段 | 取值 |
|------|------|------|
| `AgentApproval` | `status` | `pending`, `approved`, `rejected`, `expired`, `warning` |

---

## 4. 现有重试机制

### 4.1 `retry_engine.py`（通用重试引擎）

```
位置: backend/app/services/retry_engine.py
函数: classify_error, should_retry, backoff_seconds, record_attempt
错误分类: timeout / network / llm / transient → retryable
         auth / invalid / budget / unknown → terminal
模型: AgentRetryPolicy (versioned policy), AgentTaskAttempt (immutable audit)
适用: Agent 任务运行时（AgentTask 体系）
```

**与 P0-2 的关系：可复用其 error classification 和 backoff 逻辑，但 P0-2 需要的是 workflow 级别的重试（stage retry），而非 agent task 级别。**

### 4.2 `list_to_woocommerce` 内联重试

```
位置: product_listing_service.py:357
策略: 3 次尝试，延迟 1s / 3s / 9s
重试条件: 429 / 5xx / ConnectionError / Timeout
不重试: 400 / 422（业务错误）
通知: 重试耗尽后发飞书通知
```

### 4.3 `pipeline_orchestrator.retry_step`

```
位置: pipeline_orchestrator.py:280
策略: 内存态重试，每次 bump retry_count
限制: 无 DB 持久化，进程重启丢失
```

---

## 5. 现有事件/审计基础设施

### 5.1 `event_service.py`

```
位置: backend/app/services/event_service.py
模型: EventLog (event_log 表)
字段: event_type, entity_type, entity_id, payload, trace_id, created_at
函数: create_event (append-only, commit 可控), query_events (分页查询)
索引: ix_event_log_workspace_created, ix_event_log_entity
```

**已使用的 event_type（从代码扫描）：**
- `agent.approval.created`
- `creative.generation_completed`
- `product.decision.applied`
- `listing.published`
- `wc.product.synced`
- `selection.scored`
- ...（更多）

### 5.2 已有审计追踪

- `Product.mastered_trace_id` — 审批链路追踪
- `Product.data_integrity_trace_id` — 数据完整性检查追踪
- `ListingJob.trace_id` — 上架工单追踪
- `EventLog.trace_id` — 全局事件追踪
- `CreativeGenerationRun.trace_id` — 创意生成追踪
- `AgentApproval.trace_id` — 审批追踪

---

## 6. 现有审批基础设施

### 6.1 `approval_service.py`

```
位置: backend/app/services/approval_service.py
模型: AgentApproval
状态: pending → approved / rejected / expired / warning
函数: ensure_approval (幂等创建), sync_approval (同步决策), 
     approve_approval, reject_approval, list_approvals
特性: 幂等（同 type+entity 只有一条 pending）、事件记录、飞书通知
```

### 6.2 Decision 审批

```
位置: backend/app/services/decision_service.py
函数: apply_product_decision (幂等，idempotency_key)
决策类型: APPROVE, REJECT, SUPPLEMENT_DATA, HOLD
前置检查: candidate_status 不能是 terminal (winner/rejected)
Hard Rules: _check_hard_rules 检查否决规则
```

---

## 7. 关键约束与契约不匹配

### 7.1 STOP RULE 触发的 contract mismatch

| 项目 | 状态 | 说明 |
|------|------|------|
| 现有状态机能否支持 13-stage | ⚠️ 部分支持 | Product.candidate_status / funnel_stage 支持 V3 漏斗，但无 workflow_run 概念 |
| Creative API 一致性 | ✅ 一致 | create_brief_from_product → execute_generation → run_quality_check 链路完整 |
| Listing API 一致性 | ⚠️ 部分一致 | `list_to_woocommerce`（dict, sync）vs `push_product_to_woocommerce`（product_id, async）双轨制 |
| WC Gate 一致性 | ✅ 一致 | `evaluate_gate_from_dict` 集成在 `list_to_woocommerce` 中；`evaluate_gate` 用于 Product 行 |
| Approval Service 一致性 | ✅ 一致 | `ensure_approval` + `approve_approval` 链路完整 |
| Retry 一致性 | ⚠️ 部分 | `retry_engine.py` 是 Agent Task 级别，不是 workflow 级别 |

### 7.2 双轨制问题

**Listing/WC 推送存在两条并行路径：**

| 路径 | 入口 | 特性 |
|------|------|------|
| 路径 A | `product_listing_service.list_to_woocommerce(dict)` | sync, 内联 retry, gate 集成, 无 DB session |
| 路径 B | `woocommerce_sync_service.push_product_to_woocommerce(product_id, session)` | async, 无内联 retry, 有 DB session, 有 row lock, 有 WC verify |

**P0-2 应使用路径 B（async + DB session + row lock + verify），因为它更符合编排器的控制需求。**

---

## 8. 编排器设计要求（基于审计结论）

### 8.1 必须新建

1. **`workflow_run` 表** — 独立的编排执行元数据表（不覆盖 Product Lifecycle）
2. **`workflow_exception` 表** — 统一异常队列
3. **`product_factory_orchestrator.py`** — 13-stage 编排器（DB-backed, 可持久化）
4. **`GET /workflow/status`** — 可观测性查询端点

### 8.2 可以复用

| 组件 | 复用方式 |
|------|----------|
| `product_source_identity` | S1 幂等建档 |
| `data_integrity_gate` | S2 数据完整性检查 |
| `nuotao_selection_service` | S3 V3 评估 |
| `decision_service` | S5 决策 + S6 Product Master |
| `approval_service` | S5 审批 |
| `creative_service` | S7 创意 + S8 QC |
| `listing_gate` | S9/S10 上架闸门 |
| `woocommerce_sync_service.push_product_to_woocommerce` | S11 WC 同步 |
| `wc_product_link_service` | S11/S12 WC 关联 + 验证 |
| `event_service` | S13 事件 + 全链路审计 |
| `retry_engine.classify_error` / `backoff_seconds` | Retry 策略 |

### 8.3 禁止修改

| 组件 | 原因 |
|------|------|
| V3 评分规则 | STOP RULE |
| Hard Rules | STOP RULE |
| Creative 核心逻辑 | STOP RULE |
| Listing Gate | STOP RULE |
| WooCommerce sync 核心 | STOP RULE |
| 批量 Product Master | STOP RULE |
| Production 自动发布 | STOP RULE |
| 第二套 Lifecycle State Machine | STOP RULE |

---

## 9. 状态推进决策矩阵（初步）

| Stage | 自动推进条件 | 人工介入条件 | 停止条件 |
|-------|------------|------------|---------|
| S1 CANDIDATE_READY | candidate_status == "candidate" | — | 无候选 |
| S2 DATA_READINESS | gate.passed == True | — | gate 失败 3 次 → EXCEPTION |
| S3 V3_EVALUATION | gate verdict == passed | — | veto failed → STOP |
| S4 HARD_RULES | 无一票否决 | — | veto failed → STOP |
| S5 PRODUCT_DECISION | 有明确自动通过条件 | UNKNOWN/REVIEW_REQUIRED/borderline | — |
| S6 PRODUCT_MASTER | decision == APPROVE | 需人工批准 | decision == REJECT → END |
| S7 CREATIVE | brief → generate → assets | — | generation failed → RETRY |
| S8 CREATIVE_QC | QC passed | QC failed → RETRY | — |
| S9 LISTING_BUILD | listing_data 就绪 | — | — |
| S10 LISTING_GATE | gate passed | needs_review → HUMAN | blocked → HARD_STOP |
| S11 WC_SYNC | gate passed | — | WC error → RETRY |
| S12 WC_VERIFY | verify passed | — | verify failed → EXCEPTION |
| S13 LEARNING | 自动 | — | — |
