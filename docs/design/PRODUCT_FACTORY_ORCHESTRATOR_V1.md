# Product Factory Orchestrator V1 — 设计文档

> P0-2: 把 SOP-A/SOP-B/SOP-C 串成自动化 Product Factory  
> 约束：不修改现有业务服务，仅编排调用

---

## 1. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Product Factory Orchestrator               │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ Workflow │  │ Stage    │  │ Policy   │  │ Retry    │    │
│  │ Run      │──│ Engine   │──│ Engine   │──│ Engine   │    │
│  │ Metadata │  │ (13 Stg) │  │ (A/H/S)  │  │ (Backoff)│    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │
│       │              │              │              │          │
│       ▼              ▼              ▼              ▼          │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Existing Business Services                │    │
│  │  candidate│data_ready│V3│decision│creative│listing│WC│   │    │
│  └─────────────────────────────────────────────────────┘    │
│       │              │              │              │          │
│       ▼              ▼              ▼              ▼          │
│  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐             │
│  │Product │  │Event   │  │Exception│  │Approval │             │
│  │Model   │  │Log     │  │Queue    │  │Service  │             │
│  └────────┘  └────────┘  └────────┘  └────────┘             │
└─────────────────────────────────────────────────────────────┘
```

## 2. Stage Matrix

| Stage | Name | Auto/Human | Retry | 条件 |
|-------|------|-----------|-------|------|
| S1 | CANDIDATE_READY | AUTO | NO | candidate_status == "candidate" |
| S2 | DATA_READINESS | AUTO_WITH_RETRY | YES (3) | gate.passed; NEEDS_DATA → backfill |
| S3 | V3_EVALUATION | AUTO | NO | grade != reject |
| S4 | HARD_RULES | AUTO | NO | no veto |
| S5 | PRODUCT_DECISION | POLICY | NO | APPROVE→auto; UNKNOWN→HUMAN |
| S6 | PRODUCT_MASTER | AUTO_AFTER_APPROVAL | NO | decision==APPROVE |
| S7 | CREATIVE | AUTO | YES (2) | brief→generate→assets |
| S8 | CREATIVE_QC | AUTO_WITH_RETRY | YES (2) | QC passed |
| S9 | LISTING_BUILD | AUTO | NO | listing_data ready |
| S10 | LISTING_GATE | AUTO | NO | gate passed |
| S11 | WC_SYNC | AUTO_WITH_RETRY | YES (3) | WC sync success |
| S12 | WC_VERIFY | AUTO | NO | verify passed |
| S13 | LEARNING | AUTO | NO | event logged |

## 3. Auto/Human Matrix

| Stage | AUTO | HUMAN_REQUIRED | HARD_STOP |
|-------|------|----------------|-----------|
| S1 | candidate_status=="candidate" | — | — |
| S2 | gate.passed | backfill exhausted | — |
| S3 | verdict=="passed" | — | veto failed |
| S4 | no veto | — | veto failed |
| S5 | decision==APPROVE | UNKNOWN/REVIEW_REQUIRED/borderline | — |
| S6 | decision==APPROVE | needs approval | decision==REJECT |
| S7 | brief→generate→assets | — | generation exhausted |
| S8 | QC passed | — | — |
| S9 | listing_data ready | — | — |
| S10 | gate passed | needs_review | blocked |
| S11 | sync success | — | retry exhausted |
| S12 | verify passed | — | verify mismatch |
| S13 | auto | — | — |

## 4. Retry Policy

- 默认 3 次重试
- 可重试错误: timeout, 429, 5xx, temporary provider failure
- 不可重试: 400, 422, hard rule fail, permission denied, data missing after enrichment
- 退避: 指数退避，base=1s, multiplier=2, max=30s
- 使用 `retry_engine.classify_error` 和 `backoff_seconds`

## 5. Exception Policy

统一异常结构:
- exception_id, workflow_run_id, product_id, stage
- error_code, error_message, retryable, retry_count
- next_action, trace_id, created_at

异常进入 EXCEPTION_QUEUE，不写日志了事。

## 6. Idempotency

- 同一 product_id + workflow_type 重复触发: 复用现有 run
- 已有 Product Master: 不重复创建
- 已有 WC product_id: 走 update 不重复创建
- 使用 existing product state + existing external ID 决定 RESUME 或 COMPLETE

## 7. Event Model

复用 event_log，新增事件类型:
- workflow.started, workflow.stage_completed, workflow.stage_failed
- workflow.completed, workflow.failed, workflow.exception
- workflow.waiting_approval, workflow.resumed

## 8. Resume Model

- WAITING_APPROVAL: 审批后从当前 stage 继续
- 禁止从头重新跑
- 使用 existing run + current_stage 恢复

## 9. Security

- workspace 隔离
- trace_id 传播
- 不泄露 PII 到事件 payload

## 10. Audit

- 每 stage 完成记录 event_log
- 每 retry 记录 event_log
- 每 exception 记录 event_log + exception_queue
- 每 resume 记录 event_log

## 11. Test Coverage

18 项测试覆盖:
1. candidate → workflow auto start
2. data ready → V3
3. missing data → auto backfill
4. backfill failure → retry
5. retry exhausted → exception
6. V3 reject → stop
7. decision approval → resume
8. Product Master idempotent
9. Creative failure → retry
10. Listing Gate blocked → stop
11. WC 429 → retry
12. WC 5xx → retry
13. WC duplicate → update
14. WC verify failure → exception
15. duplicate workflow → resume existing
16. cross workspace isolation
17. trace_id propagation
18. no fake success
