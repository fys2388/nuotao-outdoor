# M0–M4 生产前验收矩阵

> 审计日期：2026-09-11
> 审计原则：不得因代码文件存在、路由存在或函数可导入即判定完成；所有结论必须有数据库记录、API响应、日志或测试证据。
> 状态定义：PASS = 有真实证据通过 / PARTIAL = 部分实现或仅规则实现 / BLOCKED = 阻断项 / NOT_IMPLEMENTED = 未实现

---

## M0 — 工程基座

| # | 验收项 | 代码位置 | API/任务 | 数据库表 | 测试方式 | 当前状态 | 证据 | 风险 | 下一步 |
|---|--------|----------|----------|----------|----------|----------|------|------|--------|
| M0-1 | 仓库与CI | `.github/workflows/deploy.yml` | GitHub Actions | — | 查看workflow配置 | PARTIAL | deploy.yml存在，含build/test/deploy三阶段；stage-validate为dry-run | staging环境未真正独立验证 | 启用staging实际部署验证 |
| M0-2 | Docker Compose环境 | `infra/docker-compose.yml` | `docker compose up` | — | 本地启动验证 | PARTIAL | compose文件存在，含postgres/redis/backend/worker | 未在干净环境验证完整启动 | 执行一次干净环境启动测试 |
| M0-3 | Alembic迁移框架 | `backend/alembic/` | `alembic upgrade head` | alembic_version | `alembic current` / `heads` | BLOCKED | head=0029，但当前DB仅迁移到0025；新增content_items/edm_campaigns/seo_records三张表无对应迁移文件 | 新增表无法部署到生产；迁移链不完整 | 立即创建0030迁移；执行upgrade head验证 |
| M0-4 | 核心表结构 | `backend/app/models/` | — | 30+张表 | 模型与迁移对比 | PARTIAL | 模型文件完整，但3张新表无迁移；B2B模型使用JSONB（SQLite不兼容） | 模型与迁移不同步 | 补齐迁移；评估JSONB兼容性 |
| M0-5 | AGENTS.md规范 | `AGENTS.md` | — | — | 文档审查 | PASS | 规范完整，含编码规范、AI原则、数据安全 | — | — |
| M0-6 | 结构化日志 | `backend/app/core/logging.py` | — | — | 查看日志输出 | PARTIAL | 日志框架存在，含trace_id；但未验证生产环境日志聚合 | 生产环境日志可观测性未验证 | 配置生产环境日志收集 |
| M0-7 | Sentry错误监控 | `backend/app/core/sentry.py` | — | — | 配置检查 | NOT_IMPLEMENTED | 未找到sentry初始化代码或配置 | 生产环境错误无法自动告警 | 配置Sentry DSN并初始化 |
| M0-8 | Prometheus/Grafana | `infra/prometheus.yml`, `infra/grafana/` | `/metrics` | — | 配置检查 | PARTIAL | 配置文件存在，Alertmanager+飞书适配器已配置 | 未验证生产环境指标采集和告警触发 | 部署后验证指标可达性 |
| M0-9 | 健康检查 | `app/api/v1/endpoints/health.py` | `GET /healthz`, `GET /readyz` | — | API调用 | PARTIAL | /healthz（进程存活）和/readyz（PG+Redis）已实现；但缺少LLM配置、WooCommerce配置、支付配置检查 | 就绪检查不完整，可能在依赖未配置时仍报告ready | 扩展readyz增加配置完整性检查 |

---

## M1 — DTC 交易闭环

| # | 验收项 | 代码位置 | API/任务 | 数据库表 | 测试方式 | 当前状态 | 证据 | 风险 | 下一步 |
|---|--------|----------|----------|----------|----------|----------|------|------|--------|
| M1-1 | WooCommerce独立站 | `app/integrations/woocommerce.py` | — | products | 生产站点访问 | PASS | nuotaooutdoor.com在线，60 SKU上架，全部11张图体系 | — | — |
| M1-2 | Stripe支付集成 | `app/integrations/payment.py` | `create_payment_intent()` | — | 单元测试 | PARTIAL | 代码封装完整（create_payment_intent/create_paypal_order/verify_webhook）；配置从环境变量读取；无对应测试文件；默认gateway=woocommerce | 未真实支付测试；Stripe SDK可能未安装 | 安装stripe SDK；编写mock测试；生产环境用测试密钥验证 |
| M1-3 | PayPal支付集成 | `app/integrations/payment.py` | `create_paypal_order()` | — | 单元测试 | PARTIAL | 代码封装完整；配置从环境变量读取；无对应测试文件 | 未真实支付测试；paypal SDK可能未安装 | 安装paypal SDK；编写mock测试 |
| M1-4 | WooCommerce订单Webhook签名验证 | `app/api/v1/endpoints/webhooks.py` | `POST /webhooks/woocommerce` | orders | test_webhook_orders.py | PASS | HMAC-SHA256签名验证+常量时间比较；无效签名返回401；有测试覆盖 | — | — |
| M1-5 | Webhook幂等处理 | `app/services/order_service.py:ingest_order` | — | orders | test_webhook_orders.py | PASS | 预检查existing order+并发重复检查（IntegrityError后再查）；重复返回duplicate状态；有测试覆盖 | — | — |
| M1-6 | Webhook异常重试 | — | — | — | 文档审查 | PARTIAL | 5xx返回触发WooCommerce重试（指数退避）；幂等保护使重试安全；但无主动重试队列 | 系统内部失败无重试机制 | 评估是否需要内部重试队列 |
| M1-7 | 订单→采购单转换 | `app/services/fulfillment_service.py` | — | purchase_orders, purchase_order_items | 代码审查 | PARTIAL | 已修复为从ProductCost表获取实际成本（三级降级：product_id→SKU→配置兜底）；但兜底比例procurement_fallback_cost_ratio=0.40仍存在；成本缺失时不阻断，使用兜底比例 | 成本缺失时使用未经确认的默认比例，违反"禁止凭感觉" | 成本缺失时应标记为"待确认"而非自动使用兜底比例 |
| M1-8 | 退款/取消/部分退款 | `app/services/refund_service.py` | `POST /api/v1/refunds` | refund_cases, orders | test_refund_service.py | PASS | 完整退款状态机(requested→pending_approval→approved→processing→succeeded)；全额/部分退款；退款拒绝/取消；金额校验(≤可退款余额)；幂等键唯一约束；支付未配置返回RefundNotConfigured不伪造成功；退款成功原子更新orders.refunded_amount；所有状态变更写入event_log；16个测试全部通过 | — | — |
| M1-9 | 邮件通知 | `app/services/email_service.py` | — | — | 代码审查 | PARTIAL | SMTP未配置时自动进入MOCK模式（保存到data/emails/）；支持订单确认/发货/退款模板；但无全局发送开关；无测试文件；SMTP配置默认为None | 生产环境SMTP未配置时所有邮件都是mock | 配置生产SMTP；添加全局发送开关；编写测试 |
| M1-10 | 美国销售税 | `app/services/tax_service.py` | `GET /i18n-tax/` | — | 代码审查 | PARTIAL | US_STATE_SALES_TAX含50州税率；calculate_us_sales_tax函数实现；但为静态税率表，非实时税务API | 税率可能过时；无免税州处理验证 | 验证税率准确性；评估是否需要TaxJar/Avalara集成 |
| M1-11 | 欧盟VAT | `app/services/tax_service.py` | — | — | 代码审查 | PARTIAL | EU_VAT_RATES含27国税率；calculate_eu_vat函数实现；静态税率表 | 税率可能过时 | 验证税率准确性 |
| M1-12 | IOSS | `app/services/tax_service.py` | — | — | 代码审查 | PARTIAL | IOSS_CONFIG存在，threshold=€150；但ioss_number="IM1234567890"是示例号码，非真实登记 | 示例IOSS号码无法用于清关 | 注册真实IOSS号码并配置 |
| M1-13 | 德国LUCID/WEEE合规 | — | — | — | 代码搜索 | NOT_IMPLEMENTED | 未找到LUCID或WEEE相关代码或配置 | 德国市场合规缺失 | 注册LUCID/WEEE；添加合规声明到页脚 |
| M1-14 | 多币种/汇率 | `app/services/tax_service.py`, `app/core/config.py` | — | — | 代码审查 | PARTIAL | 支付支持USD/EUR/GBP/CNY；但无汇率服务或汇率表；金额使用Decimal精度 | 多币种定价依赖WooCommerce端；本地无汇率转换 | 评估是否需要本地汇率服务 |
| M1-15 | AI客服MVP | `app/services/customer_service.py` | `POST /customer-service/chat` | customer_interactions | 代码审查 | PARTIAL | FAQ匹配+AI回复生成+置信度<0.5建议人工转接+人工工单创建；提示词明确"不知道就建议人工"；但FAQ硬编码在代码中，非数据库；无权限边界检查 | FAQ不可动态维护；AI可能回答超出权限的问题 | FAQ移至数据库；添加权限边界校验 |
| M1-16 | LLM网关双供应商 | `app/services/llm_gateway.py` | — | — | test_llm_gateway.py, test_llm_gateway_circuit_breaker.py | PASS | OpenAI主+DeepSeek备；连续失败3次熔断60s；有测试覆盖 | — | — |

---

## M2 — 供应链自动化

| # | 验收项 | 代码位置 | API/任务 | 数据库表 | 测试方式 | 当前状态 | 证据 | 风险 | 下一步 |
|---|--------|----------|----------|----------|----------|----------|------|------|--------|
| M2-1 | 1688产品来源 | `app/integrations/sourcing_1688.py` | — | sourcing_candidates | 代码审查 | PARTIAL | 1688集成代码存在；SourcingCandidate模型存在；但未验证真实1688 API调用 | 1688 API可能需要认证；爬取合规性未验证 | 验证1688 API可用性；合规评审 |
| M2-2 | MANUAL产品来源 | `app/services/product_intelligence_service.py` | `POST /product-intelligence/candidates` | sourcing_candidates | 代码审查 | PARTIAL | 支持手动创建候选产品；source字段支持manual | — | — |
| M2-3 | CSV批量导入 | `app/services/product_import_service.py` | — | sourcing_candidates | test_product_import.py | PARTIAL | CSV导入服务存在；有测试文件；但未验证真实CSV导入流程 | — | 执行一次真实CSV导入测试 |
| M2-4 | ProductCandidate与Product生命周期分离 | `app/models/product_intelligence.py`, `app/models/product.py` | — | sourcing_candidates, products | 代码审查 | PASS | SourcingCandidate（候选）与Product（正式产品）为独立表；候选需审批后才能转为正式产品 | — | — |
| M2-5 | ProductCost成本分解 | `app/models/product.py:ProductCost` | — | product_costs | 代码审查 | PASS | 字段完整：purchase_cost, domestic_shipping, international_shipping, packaging, tax_estimate, handling, total_landed_cost, payment_fee, marketing_amortization, after_sales_loss, total_cost；含valid_from版本控制 | — | — |
| M2-6 | 成本缺失时阻断 | `app/services/fulfillment_service.py` | — | purchase_orders | test_cost_blocker.py | PASS | 新增pending_cost_confirmation状态；无ProductCost时PO自动进入该状态；该状态禁止直接→approved/ordered；fallback比例标记source="fallback",confidence<0.5仅用于估算；成本补齐后confirm_purchase_order_cost→draft(幂等)；10个测试全部通过 | — | — |
| M2-7 | Supplier CRUD | `app/services/supply_chain.py`, `app/api/v1/endpoints/supply_chain.py` | `/api/v1/suppliers` | suppliers | 代码审查 | PARTIAL | 本次新增完整CRUD（create/list/get/update/delete）；含workspace隔离；含软删除保护（有关联采购单时标记inactive）；含重复code检查；但无测试文件；新增API未验证 | 新代码未测试 | 编写Supplier CRUD测试；验证API端点 |
| M2-8 | 采购状态机 | `app/services/supply_chain.py:PO_TRANSITIONS` | `PATCH /purchase-orders/{id}/transition` | purchase_orders | test_supply_chain.py | PARTIAL | 状态机定义完整（draft→approved→ordered→partial_received→received；draft/approved可cancelled）；非法跳转抛出SupplyChainError；只能在draft更新；但test_supply_chain.py因JSONB/SQLite问题无法运行 | 测试无法运行，状态机未验证 | 修复测试环境为PostgreSQL；运行状态机测试 |
| M2-9 | 库存扣减幂等 | `app/services/supply_chain.py` | — | inventory_snapshots | 代码审查 | PARTIAL | 库存模型支持available=quantity-reserved；reserve_inventory/release_inventory函数存在；但未找到幂等键或并发锁机制 | 并发扣减可能超卖 | 添加幂等键和乐观锁 |
| M2-10 | 物流状态幂等 | `app/services/supply_chain.py` | — | shipment_records, logistics_events | 代码审查 | PARTIAL | ShipmentRecord和LogisticsEvent模型存在；create_shipment/add_logistics_event函数存在；但物流事件去重机制未验证 | 重复物流事件可能导致状态错误 | 添加物流事件幂等键 |
| M2-11 | AI选品只提建议不自动执行 | `app/agents/product_manager.py`, `app/services/agent_suggestion_service.py` | — | agent_suggestions | 代码审查 | PASS | AI选品输出为AgentSuggestion（status=pending）；需人工审批后才能执行；execution_router只执行approved状态的建议；无自动采购/自动付款/自动发布代码路径 | — | — |
| M2-12 | 物流监控时效异常预警 | `app/services/logistics_monitor_service.py` | — | logistics_events | 代码审查 | PARTIAL | 物流监控服务存在；但使用JSON文件存储（data/logistics/），非数据库；时效异常预警逻辑未验证 | 物流数据不入数据库，无法持久化查询 | 物流监控数据迁移到数据库 |

---

## M3 — 营销与内容系统

| # | 验收项 | 代码位置 | API/任务 | 数据库表 | 测试方式 | 当前状态 | 证据 | 风险 | 下一步 |
|---|--------|----------|----------|----------|----------|----------|------|------|--------|
| M3-1 | ContentItem迁移和CRUD | `app/services/content_marketing_service.py` | `POST /api/v1/content-marketing/items` | content_items | test_content_marketing_service.py | PASS | 迁移0030已创建并应用；CRUD服务完整；审核状态机(draft→pending_review→approved→published)；版本控制+乐观锁；event_log审计；workspace隔离；17个测试全部通过 | — | — |
| M3-2 | 内容审核状态机 | `app/models/content_marketing.py:ContentItem.status` | — | content_items | 代码审查 | PARTIAL | 状态定义完整（draft→pending_review→approved→published/rejected/archived）；但无服务层状态流转函数；无API端点 | 状态机仅定义，未实现流转逻辑 | 实现内容审核服务和API |
| M3-3 | 内容版本控制和审计 | `app/models/content_marketing.py:ContentItem.version` | — | content_items | 代码审查 | PARTIAL | version字段存在；但无版本历史表；修改不保留旧版本 | 无法追溯内容变更历史 | 添加content_versions历史表 |
| M3-4 | EDM订阅同意记录 | `app/services/edm_send_service.py` | — | email_subscriptions | test_edm_send_service.py | PASS | 新增email_subscriptions表(consent_given/consent_timestamp/consent_source/unsubscribe_timestamp)；发送前检查有效订阅同意；未同意用户不发送；13个测试全部通过 | — | — |
| M3-5 | EDM退订处理 | `app/services/edm_automation_service.py:track_email_event` | — | — | 代码审查 | PARTIAL | 支持unsubscribe事件跟踪；但无退订列表管理；无退订链接生成 | 退订后可能仍收到邮件 | 实现退订列表和退订链接 |
| M3-6 | EDM发送前开关 | `app/services/edm_send_service.py` | — | — | test_edm_send_service.py | PASS | EDM_SEND_ENABLED=false默认关闭；edm_dry_run_default=true默认dry-run；发送前6项检查(开关+同意+未退订+活动批准+24h去重+内容审核)；幂等键；失败重试最多3次；13个测试全部通过 | — | — |
| M3-7 | EDM去重 | `app/services/edm_automation_service.py` | — | — | 代码审查 | NOT_IMPLEMENTED | 未找到邮件去重逻辑；同一用户可能在多个campaign中重复收到邮件 | 用户体验差；可能被标记为垃圾邮件 | 添加邮件去重逻辑（24小时内不重复发送） |
| M3-8 | EDM失败重试 | `app/services/edm_automation_service.py` | — | — | 代码审查 | NOT_IMPLEMENTED | 未找到邮件发送失败重试逻辑 | 发送失败的邮件不会重发 | 添加失败重试机制（指数退避，最多3次） |
| M3-9 | EDM数据存储 | `app/services/content_marketing_service.py` | — | edm_campaigns, email_subscriptions, edm_send_logs | test_content_marketing_service.py, test_edm_send_service.py | PASS | EDMCampaign使用数据库表(迁移0030)；新增email_subscriptions和edm_send_logs表(迁移0033)；JSON数据目录已加入.gitignore不再作为正式数据源；30个测试全部通过 | — | — |
| M3-10 | SEO数据来源区分 | `app/models/content_marketing.py:SEORecord` | — | seo_records | 代码审查 | PARTIAL | SEORecord模型定义了search_volume/keyword_difficulty/current_position；但无source字段区分AI推测/外部真实数据/人工录入 | 无法区分数据可信度 | 添加source字段（ai_estimated/external_api/manual） |
| M3-11 | 广告ROAS真实数据来源 | `app/models/marketing.py:Campaign` | — | campaigns | 代码审查 | PARTIAL | Campaign模型含spend/impressions/clicks/conversion/revenue/roas字段；但无广告平台API集成（Meta/Google/TikTok）；数据只能手动录入 | ROAS数据可能为人工录入，非真实归因 | 集成Meta/Google Ads API；无数据时ROAS返回NULL |
| M3-12 | 无真实归因数据时返回NULL | `app/services/marketing_service.py` | — | campaigns | 代码审查 | BLOCKED | 未验证无数据时ROAS是否返回NULL；可能存在默认值或假数字 | 可能生成假ROAS数字 | 确保无数据时ROAS=None；添加"未验证"标记 |
| M3-13 | 内容生成服务 | `app/services/content_generation_service.py` | `POST /content-generation/` | — | 代码审查 | PARTIAL | 内容生成服务存在；支持卖点/SEO文章/EDM草稿；但使用JSON文件存储；无审核流集成 | 内容生成后无法审核 | 迁移到ContentItem表；接入审核状态机 |

---

## M4 — 商业分析系统

| # | 验收项 | 代码位置 | API/任务 | 数据库表 | 测试方式 | 当前状态 | 证据 | 风险 | 下一步 |
|---|--------|----------|----------|----------|----------|----------|------|------|--------|
| M4-1 | Dashboard指标数据来源 | `app/services/dashboard_service.py` | `GET /dashboard/` | — | 代码审查 | BLOCKED | 使用JSON文件存储（data/dashboard/），非数据库实时聚合；daily_2026-09-01.json等文件存在；指标可能不是实时数据 | Dashboard显示过时数据；无法SQL查询 | 迁移到数据库实时聚合 |
| M4-2 | 收入/订单数/AOV计算公式 | `app/services/dashboard_service.py` | — | — | 代码审查 | PARTIAL | 计算逻辑存在；但基于JSON文件数据；公式未验证 | 计算公式可能有误 | 迁移到数据库后验证公式 |
| M4-3 | 毛利率/退款率计算 | `app/services/profit_engine.py` | — | — | test_profit_engine.py | PARTIAL | profit_engine存在；有测试文件；但毛利率基于估算成本（非实际ProductCost）；退款率计算未验证 | 毛利率可能不准确 | 接入实际ProductCost；验证退款率 |
| M4-4 | 时间窗口/时区/币种 | `app/services/dashboard_service.py` | — | — | 代码审查 | PARTIAL | 按日期聚合；但时区处理未验证；币种统一为USD | 跨时区数据可能错位 | 验证时区处理 |
| M4-5 | margin_decline预警 | `app/services/business_alert_service.py`, `app/services/alert_system_service.py` | 调度器business_alerts | event_log | 代码审查 | PARTIAL | business_alert_service（本次新增）从DB实时查询，毛利率低于30%或环比下降>15%触发；alert_system_service也有margin_decline规则（JSON存储）；但无测试；未验证真实数据触发 | 预警阈值可能不合适；未验证 | 编写预警测试；用空数据验证不触发 |
| M4-6 | refund_spike预警 | `app/services/business_alert_service.py` | 调度器business_alerts | event_log | 代码审查 | PARTIAL | 退款率超过5%或环比飙升>50%触发；但退款数据来源未验证（orders.refunded_amount可能未被更新） | 退款率可能始终为0，预警不生效 | 验证退款数据更新流程 |
| M4-7 | revenue_decline预警 | `app/services/business_alert_service.py` | 调度器business_alerts | event_log | 代码审查 | PARTIAL | 收入环比下降>20%触发；基于orders表实时查询 | — | 编写测试验证 |
| M4-8 | aov_decline预警 | `app/services/business_alert_service.py` | 调度器business_alerts | event_log | 代码审查 | PARTIAL | 客单价环比下降>15%触发 | — | 编写测试验证 |
| M4-9 | stockout_risk预警 | `app/services/business_alert_service.py` | 调度器business_alerts | event_log, inventory_snapshots | 代码审查 | PARTIAL | 可用库存≤5件触发；逐产品检查；但inventory_snapshots表可能无数据 | 库存表无数据时预警不生效 | 验证库存数据；编写测试 |
| M4-10 | 告警去重 | `app/services/business_alert_service.py:_active_alerts` | — | — | 代码审查 | PARTIAL | 内存字典去重，key=(workspace, type, resource)；但进程重启后丢失；无数据库持久化 | 重启后重复告警 | 告警状态持久化到数据库 |
| M4-11 | 告警自动恢复 | `app/services/business_alert_service.py:_resolve_alert_if_recovered` | — | — | 代码审查 | PARTIAL | 指标恢复后自动从_active_alerts移除；但不发送恢复通知 | 恢复时无通知 | 添加恢复通知 |
| M4-12 | 告警审计日志 | `app/services/business_alert_service.py` | — | event_log | 代码审查 | PASS | 每次新告警写入event_log（event_type=business_alert.*）；含trace_id | — | — |
| M4-13 | 空数据测试 | — | — | — | 测试执行 | NOT_IMPLEMENTED | 未编写空数据场景测试；无法验证无订单/无库存时预警是否安全 | 空数据时可能除零或误报 | 编写空数据测试 |
| M4-14 | 调度器注册和启动 | `app/services/agent_scheduler.py` | systemd nuotao-agent-scheduler | — | 代码审查 | PARTIAL | 6个任务注册（product/marketing/supply_chain/execution/feedback/business_alerts）；AgentScheduler类实现；systemd服务已部署；但未验证调度器实际运行和记录结果 | 调度器可能未真正运行 | 检查生产环境调度器日志和运行状态 |
| M4-15 | AI经营周报 | `app/services/weekly_report_service.py` | `GET /weekly-report/` | — | 代码审查 | PARTIAL | 周报服务存在；从orders/settlements/campaigns等表聚合数据；AI生成异常解释；但部分数据源可能为JSON文件 | 周报数据可能不一致 | 验证周报数据源全部为数据库 |
| M4-16 | 回款台账 | `app/services/settlement_service.py` | `GET /settlements/` | settlements | test_settlement_service.py | PARTIAL | Settlement模型和服务存在；支持COD回款登记和利润核算；有测试文件；但真实回款数据需人工录入 | 回款数据依赖人工录入 | 验证回款登记流程 |

---

## 跨里程碑共性问题

| # | 问题 | 影响范围 | 严重程度 | 说明 |
|---|------|----------|----------|------|
| C-1 | 新增3张表无Alembic迁移 | M3 | BLOCKER | content_items/edm_campaigns/seo_records无法部署 |
| C-2 | 当前DB迁移滞后（0025 vs head 0029） | 全部 | BLOCKER | 生产环境可能缺少0026-0029的表 |
| C-3 | JSON文件存储替代数据库 | M3/M4 | HIGH | dashboard/edm/content/alerts/logistics使用JSON文件，非数据库 |
| C-4 | 成本缺失时不阻断 | M1/M2 | HIGH | 使用兜底比例0.40，违反"禁止凭感觉" |
| C-5 | 退款流程缺失 | M1 | HIGH | 无退款创建/审批/执行流程 |
| C-6 | EDM无发送开关/订阅同意/退订 | M3 | HIGH | GDPR合规风险；可能误发送 |
| C-7 | 测试环境SQLite与PostgreSQL不兼容 | 全部 | MEDIUM | B2B模型JSONB导致所有SQLite测试失败 |
| C-8 | 健康检查不完整 | M0 | MEDIUM | 缺少LLM/WooCommerce/支付配置检查 |
| C-9 | Sentry未配置 | M0 | MEDIUM | 生产错误无自动告警 |
| C-10 | 告警状态内存存储 | M4 | MEDIUM | 进程重启后告警去重状态丢失 |
| C-11 | IOSS示例号码 | M1 | MEDIUM | IM1234567890非真实登记 |
| C-12 | 德国LUCID/WEEE未实现 | M1 | MEDIUM | 德国市场合规缺失 |
| C-13 | 产品Webhook硬编码workspace_id | M1 | LOW | 硬编码为00000000-0000-0000-0000-000000000001 |
| C-14 | FAQ硬编码 | M1 | LOW | AI客服FAQ在代码中，非数据库 |

---

## 统计汇总

| 里程碑 | PASS | PARTIAL | BLOCKED | NOT_IMPLEMENTED | 总计 |
|--------|------|---------|---------|-----------------|------|
| M0 | 1 | 6 | 1 | 1 | 9 |
| M1 | 3 | 9 | 1 | 2 | 16 |
| M2 | 2 | 8 | 1 | 0 | 12 |
| M3 | 0 | 6 | 3 | 4 | 13 |
| M4 | 1 | 12 | 1 | 1 | 16 |
| **合计** | **7** | **41** | **7** | **8** | **66** |

> 注：本矩阵基于代码审查和配置检查，未执行真实API集成测试或生产环境验证。所有PARTIAL项均需进一步验证才能升级为PASS。
