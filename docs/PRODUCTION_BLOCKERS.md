# M0–M4.1 Production Blocker Remediation 报告

> 修复日期：2026-09-11
> 修复范围：P1–P7 全部生产阻断项
> 原则：不伪造数据、不输出密钥、高风险动作保留人工审批、所有修改有迁移+测试+审计+回滚

---

## 修复总览

| 优先级 | 模块 | 修复内容 | 状态 | 测试数 |
|--------|------|----------|------|--------|
| P1 | M1退款流程 | 完整退款状态机+审批+执行+幂等+金额校验 | ✅ 完成 | 16 |
| P2 | 成本缺失阻断 | 成本缺失时PO进入pending_cost_confirmation，禁止执行 | ✅ 完成 | 10 |
| P3 | M3内容/EDM/SEO数据库化 | CRUD+审核状态机+版本控制+乐观锁+审计 | ✅ 完成 | 17 |
| P4 | EDM安全与GDPR | email_subscriptions表+发送前6项检查+默认关闭+dry-run | ✅ 完成 | 13 |
| P5 | M4 Dashboard和告警数据库化 | 8项指标实时聚合+持久化告警表+5类告警+去重恢复 | ✅ 完成 | 25 |
| P6 | 安全清理和版本治理 | 删除token文件+移除feishu_config+更新.gitignore+敏感扫描 | ✅ 完成 | — |
| P7 | 生产验收重跑 | 迁移测试+全部682测试通过+文档更新 | ✅ 完成 | 682 |

---

## P1：M1退款流程

### 修复内容
- 扩展 `RefundCase` 模型（20+字段：状态机、审批、执行、重试、幂等键、唯一约束）
- 创建 `refund_service.py`（完整退款流程服务）
- 创建 `refund.py` Schema、`refunds.py` API端点（10个端点）
- 创建迁移 `0031_refund_lifecycle.py`（已验证可回滚）

### 核心实现
- 状态机：`requested → pending_approval → approved → processing → succeeded`
- 异常状态：`rejected` / `failed` / `cancelled`
- 金额校验：退款金额 ≤ 订单总额 - 已退款 - 活跃退款预留
- 幂等：`workspace_id + order_id + idempotency_key` 唯一约束
- 支付平台未配置时返回 `RefundNotConfigured`，绝不伪造成功
- 退款成功后原子更新 `orders.refunded_amount`
- 所有状态变更写入 `event_log`
- `approved_by`/`rejected_by` 来自认证上下文，客户端无法传入绕过

### 测试结果
- 16个单元测试全部通过
- 覆盖：全额退款、部分退款、退款拒绝、退款取消、金额超限拦截、重复退款拦截、幂等、支付未配置安全返回

---

## P2：成本缺失阻断

### 修复内容
- `PO_STATUSES` 添加 `pending_cost_confirmation` 状态
- `PO_TRANSITIONS` 更新：`pending_cost_confirmation` 只能 → `draft` 或 `cancelled`，禁止直接 → `approved`/`ordered`
- `PurchaseOrder` 模型添加成本确认字段（`cost_confirmed`/`cost_source`/`cost_confidence`/`cost_confirmed_at`/`cost_confirmed_by`/`cost_block_reason`）
- 创建迁移 `0032_purchase_order_cost_confirmation.py`（已验证可回滚）
- `fulfillment_service.py` 添加 `_get_product_cost_detailed`（返回成本来源+置信度）
- `create_purchase_order_from_order` 成本缺失时自动进入 `pending_cost_confirmation`
- 新增 `confirm_purchase_order_cost` 函数（成本补齐后 → `draft`，幂等）

### 核心规则
- 无 `ProductCost` → PO 进入 `pending_cost_confirmation`
- `fallback` 比例标记 `source="fallback"`, `confidence<0.5`，仅用于估算不得用于执行
- 成本补齐后 `confirm_purchase_order_cost` 验证所有 item 有真实成本然后 → `draft`
- `pending_cost_confirmation` 状态禁止直接进入 `approved`/`ordered`/执行状态

### 测试结果
- 10个单元测试全部通过
- 覆盖：无ProductCost时采购被阻断、只有purchase_cost没有完整落地成本时被阻断、fallback只用于估算、成本补齐后可以重新进入审批、重复补齐成本不会产生重复采购单

---

## P3：M3内容/EDM/SEO数据库化

### 修复内容
- 模型已存在（迁移 `0030_content_marketing.py`：ContentItem/EDMCampaign/SEORecord）
- 创建 `content_marketing_service.py`（CRUD+审核状态机+版本控制+乐观锁+event_log审计+workspace隔离）
- 创建 `content_marketing.py` API端点（ContentItem 9个+EDM 5个+SEO 4个）

### 核心实现
- 内容状态机：`draft → pending_review → approved → published`，`pending_review → rejected → draft`
- 未经 `approved` 不得 `published`
- `approved`/`published` 内容不得直接编辑
- 版本控制：每次更新 `version+1`；`expected_version` 不匹配抛 `ContentVersionConflict`（并发保护）
- 所有状态变更写入 `event_log`
- workspace隔离：所有查询强制 `workspace_id` 过滤

### 测试结果
- 17个单元测试全部通过
- 覆盖：CRUD、审核状态机流转、非法状态跳转拦截、版本控制、并发更新冲突、workspace隔离、审计日志

---

## P4：EDM安全与GDPR

### 修复内容
- 创建 `edm_subscription.py` 模型（`EmailSubscription` + `EDMSendLog`）
- 创建迁移 `0033_edm_subscription_and_send_log.py`（已验证可回滚）
- `config.py` 添加 EDM 安全配置（`edm_send_enabled=false` 默认关闭、`edm_dry_run_default=true`、`edm_dedup_window_hours=24`、`edm_max_retries=3`）
- 创建 `edm_send_service.py`（订阅管理+发送前6项检查+幂等键+dry-run默认+失败重试+发送日志）

### 发送前6项检查（必须全部满足）
1. `edm_send_enabled=true`
2. 用户存在有效订阅同意
3. 用户未退订
4. 当前活动已批准（non-draft）
5. 当前收件人未被24小时去重规则拦截
6. 发送内容已审核通过

### 核心实现
- 默认禁止发送营销邮件（`EDM_SEND_ENABLED=false`）
- 默认只运行 dry-run
- 发送幂等键：`workspace_id + campaign_id + email + send_date`
- 失败重试：指数退避，最多3次
- 记录发送成功、失败、退订和跳过原因
- 真实发送必须有明确人工或配置开关

### 测试结果
- 13个单元测试全部通过
- 覆盖：默认不发送、未同意用户不发送、已退订用户不发送、未审核内容不发送、24小时内重复发送被拦截、发送失败可以重试、重试不会重复发送成功邮件

---

## P5：M4 Dashboard和业务告警数据库化

### 修复内容
- 创建 `business_alert.py` 模型（持久化告警表，唯一约束 `workspace_id + alert_type + resource_type + resource_id + status`）
- 创建迁移 `0034_business_alerts.py`（已验证可回滚）
- 创建 `dashboard_metrics_service.py`（8项指标从PostgreSQL实时聚合）
- 创建 `persistent_alert_service.py`（5类告警评估+去重+恢复+确认+重启后状态保留）

### Dashboard 8项指标（全部从PostgreSQL实时聚合）
- `revenue`：已支付订单总额
- `order_count`：订单数
- `AOV`：平均订单价值（空数据返回NULL，不除零）
- `gross_profit`：收入 - 退款金额
- `margin_rate`：毛利率（空数据返回NULL）
- `refund_rate`：退款率（空数据返回NULL）
- `inventory_available`：可用库存
- `stockout_risk`：缺货风险产品数

每项指标标明：`source` / `calculation_window` / `timezone` / `currency` / `generated_at`

### 5类业务告警（持久化）
- `margin_decline`：毛利率低于阈值
- `refund_spike`：退款率高于阈值
- `revenue_decline`：收入环比下降超过阈值
- `aov_decline`：AOV环比下降超过阈值
- `stockout_risk`：缺货风险产品数达到阈值

### 告警核心特性
- 去重：相同活跃告警更新 `detection_count`，不创建重复
- 恢复：`status → resolved`，设置 `resolved_at`
- 重启后状态保留：告警存储在PostgreSQL
- 恢复事件审计：所有状态变更写入 `event_log`
- 重复执行不重复创建告警
- 空数据安全：不除零、不误报

### 测试结果
- 25个单元测试全部通过
- 覆盖：Dashboard指标计算、空数据安全、5类告警触发、告警去重、告警恢复、重启后状态保留、重复执行不重复创建、告警确认、按状态查询

---

## P6：安全清理和版本治理

### 修复内容
1. ✅ 删除 `admin_token.txt` 和 `admin_token_new.txt`（确认未被git跟踪过）
2. ✅ 从git跟踪移除 `feishu_config.txt`（`git rm --cached`），文件含518字符敏感信息
3. ✅ 删除 `infra/gen_admin_token*.py`（含SSH连接凭据）
4. ✅ 更新 `.gitignore`：
   - 添加 `feishu_config.txt`、`admin_token*.txt`、`*token*.txt`
   - 添加 `backend/app/data/`（内容/EDM/SEO已迁移到数据库）
   - 添加 `*.backup`、`*.bak`
   - 添加临时脚本：`check_*.py`、`debug_*.py`、`_*.py`、`cloudflare_*.py` 等
   - 添加 `.rivet/`、`backup/`
   - 添加证书文件：`*.der`、`*.crt`、`*.cert`
5. ✅ 敏感信息扫描：检查代码中硬编码密钥（GitHub Actions workflow中的secrets引用为正常配置）
6. ✅ git历史检查：`feishu_config.txt` 曾在commit 51aff92中，未匹配到敏感关键词
7. ✅ 未跟踪文件从374个减少到274个

### git历史清理方案（如需执行）
如果确认历史提交中包含敏感信息，可使用 `git filter-repo` 清理：
```bash
# 安装 git-filter-repo
pip install git-filter-repo

# 从所有历史提交中删除 feishu_config.txt
git filter-repo --path feishu_config.txt --invert-paths

# 强制推送到远程（会重写历史，需团队协调）
git push --force --all
```
> 注意：重写远程历史需要团队协调，已克隆的仓库需要重新克隆。当前未执行此操作。

---

## P7：生产验收重新执行

### 迁移测试
- ✅ `alembic upgrade head` → 0034 (head)
- ✅ `alembic downgrade -1` → 0033
- ✅ `alembic upgrade head` → 0034 (head)
- ✅ 迁移可重复执行、可回滚

### 测试结果
- **测试总数：682**
- **通过：682**
- **失败：0**
- **错误：0**
- **跳过：0**
- **执行时间：245.5秒**

### 新增测试统计
| 模块 | 测试数 | 状态 |
|------|--------|------|
| P1 退款流程 | 16 | ✅ 全部通过 |
| P2 成本阻断 | 10 | ✅ 全部通过 |
| P3 内容营销 | 17 | ✅ 全部通过 |
| P4 EDM发送 | 13 | ✅ 全部通过 |
| P5 Dashboard和告警 | 25 | ✅ 全部通过 |
| **新增合计** | **81** | ✅ 全部通过 |

### API健康检查
- ✅ `GET /healthz`：存活检查（不访问外部服务）
- ✅ `GET /readyz`：就绪检查（PostgreSQL + Redis）
- ⚠️ 后续改进：扩展readyz增加LLM配置、WooCommerce配置、支付配置完整性检查

### 外部服务配置状态
| 服务 | 状态 | 说明 |
|------|------|------|
| PostgreSQL | ✅ 已配置 | 本地开发环境，迁移到0034 |
| Redis | ✅ 已配置 | 本地开发环境 |
| Stripe | ⚠️ 未配置真实密钥 | 代码封装完整，未配置时安全返回NOT_CONFIGURED |
| PayPal | ⚠️ 未配置真实密钥 | 代码封装完整，未配置时安全返回NOT_CONFIGURED |
| WooCommerce | ⚠️ 需生产环境配置 | 集成代码完整，生产站点nuotaooutdoor.com在线 |
| SMTP/EDM | ✅ 默认关闭 | EDM_SEND_ENABLED=false，默认dry-run |
| LLM Gateway | ✅ 已配置 | OpenAI主+DeepSeek备，熔断机制 |

---

## 数据库迁移版本

| 版本 | 名称 | 状态 |
|------|------|------|
| 0030 | content_marketing | ✅ 已应用 |
| 0031 | refund_lifecycle | ✅ 已应用 |
| 0032 | purchase_order_cost_confirmation | ✅ 已应用 |
| 0033 | edm_subscription_and_send_log | ✅ 已应用 |
| 0034 | business_alerts | ✅ 已应用 (head) |

---

## 修改文件清单

### 新增文件（20个）
- `backend/app/services/refund_service.py`
- `backend/app/schemas/refund.py`
- `backend/app/api/v1/endpoints/refunds.py`
- `backend/alembic/versions/0031_refund_lifecycle.py`
- `backend/tests/test_refund_service.py`
- `backend/alembic/versions/0032_purchase_order_cost_confirmation.py`
- `backend/tests/test_cost_blocker.py`
- `backend/app/services/content_marketing_service.py`
- `backend/app/api/v1/endpoints/content_marketing.py`
- `backend/tests/test_content_marketing_service.py`
- `backend/app/models/edm_subscription.py`
- `backend/app/services/edm_send_service.py`
- `backend/alembic/versions/0033_edm_subscription_and_send_log.py`
- `backend/tests/test_edm_send_service.py`
- `backend/app/models/business_alert.py`
- `backend/app/services/dashboard_metrics_service.py`
- `backend/app/services/persistent_alert_service.py`
- `backend/alembic/versions/0034_business_alerts.py`
- `backend/tests/test_dashboard_and_alerts.py`
- `docs/PRODUCTION_BLOCKERS.md`

### 修改文件（12个）
- `backend/app/models/customer.py`（RefundCase扩展）
- `backend/app/api/v1/router.py`（注册新路由）
- `backend/app/models/supply_chain.py`（PO成本确认字段）
- `backend/app/services/supply_chain.py`（PO_TRANSITIONS更新）
- `backend/app/services/fulfillment_service.py`（成本阻断逻辑）
- `backend/app/models/__init__.py`（注册新模型）
- `backend/app/core/config.py`（EDM安全配置）
- `.gitignore`（安全清理规则）
- `docs/M0_M4_ACCEPTANCE_MATRIX.md`（更新验收状态）
- `docs/development_roadmap.md`（更新路线图）

### 删除文件（5个）
- `admin_token.txt`
- `admin_token_new.txt`
- `infra/gen_admin_token.py`
- `infra/gen_admin_token2.py`
- `infra/gen_admin_token3.py`

---

## 最终结论

### M0–M4 验收状态

| 模块 | 状态 | 说明 |
|------|------|------|
| M0 工程基座 | PARTIAL | 核心基座完成；Sentry未配置；readyz可扩展 |
| M1 DTC交易闭环 | PARTIAL | 退款流程已实现；支付真实密钥未配置；税务为规则实现 |
| M2 供应链自动化 | PARTIAL | 成本缺失阻断已实现；Supplier CRUD需补充测试；库存幂等需加强 |
| M3 营销与内容系统 | PARTIAL | 内容/EDM/SEO已数据库化；EDM安全已实现；真实发送provider未配置 |
| M4 商业分析 | PARTIAL | Dashboard已数据库化；告警已持久化；真实广告数据未接入 |

### 是否允许进入生产
**有条件允许**：
- ✅ 核心业务逻辑有真实测试证据（682测试全部通过）
- ✅ 高风险动作保留人工审批（退款、采购、EDM发送）
- ✅ 成本缺失会阻断正式采购
- ✅ EDM默认关闭，不会误发送
- ✅ 支付平台未配置时安全返回，不伪造成功
- ⚠️ 生产环境部署需配置：Stripe/PayPal密钥、WooCommerce API、SMTP、Sentry
- ⚠️ 生产环境需执行一次干净部署验证

### 是否允许进入M5（海外仓）
**暂不建议**：
- M0–M4核心功能已实现并通过测试，但部分模块仍为PARTIAL
- 建议先在生产环境运行M0–M4至少2周，收集真实业务数据
- 修复生产环境发现的问题后，再进入M5海外仓开发
- M5需要海外仓供应商、物流商、税务等真实业务对接，准备工作较多

### 仍然BLOCKED的项目
1. **生产环境真实部署验证**：需在Hetzner VPS执行干净部署，验证API/Worker/Scheduler启动
2. **Stripe/PayPal真实支付测试**：需配置测试密钥，执行真实支付流程验证
3. **WooCommerce生产环境集成验证**：需验证订单Webhook在生产环境正常工作
4. **SMTP真实发送验证**：需配置SMTP提供商，验证EDM真实发送（默认关闭）
5. **Sentry错误监控配置**：需配置Sentry DSN，验证生产环境错误告警
6. **德国LUCID/WEEE合规**：需注册合规号码，添加到网站页脚

### 修复优先级（后续）
1. **P0**：生产环境部署验证 + 健康检查扩展
2. **P1**：Stripe/PayPal真实支付测试 + WooCommerce生产集成验证
3. **P2**：SMTP配置 + EDM真实发送验证（保持默认关闭）
4. **P3**：Sentry配置 + 生产环境日志聚合
5. **P4**：德国LUCID/WEEE合规注册
6. **P5**：Supplier CRUD测试补充 + 库存幂等加强
