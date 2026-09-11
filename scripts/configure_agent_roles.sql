-- ============================================================
-- AI Agent 职责与权限配置
-- 按照 AGENTS.md 3.1 原则配置各Agent的职责、权限和工具范围
-- ============================================================

-- ============================================================
-- 1. 产品经理Agent（product-manager）
-- 职责：选品分析、产品导入、图片合规检查、WooCommerce上架
-- 权限：L2（提议），上架发布需L3人工审批
-- ============================================================
UPDATE agents SET
  description = '产品经理AI：负责1688选品分析、产品导入系统、图片合规性检查、WooCommerce产品创建与上架。高风险操作（发布产品）必须进入人工审批队列。',
  permission_level = 'L2',
  model_name = 'deepseek-chat',
  prompt_version = 'v2',
  status = 'active'
WHERE agent_id = 'product-manager';

-- ============================================================
-- 2. 营销经理Agent（marketing-manager）
-- 职责：AI文案生成、文案合规检查、AI生图（主图+详情图）、生图质量检查
-- 权限：L2（提议），文案和图片保存需人工确认
-- ============================================================
UPDATE agents SET
  description = '营销经理AI：负责产品文案生成（标题/描述/卖点/SEO）、文案合规检查、AI生图（主图3套方向+详情页6板块）、生图质量检查。严格按照生图SOP流程执行，主图和详情图逻辑不得混用。',
  permission_level = 'L2',
  model_name = 'deepseek-chat',
  prompt_version = 'v2',
  status = 'active'
WHERE agent_id = 'marketing-manager';

-- ============================================================
-- 3. 供应链经理Agent（supply-chain-manager）
-- 职责：库存同步、采购单创建、1688下单、采购物流追踪、物流信息同步
-- 权限：L2（提议），1688实际下单需L3人工审批
-- ============================================================
UPDATE agents SET
  description = '供应链经理AI：负责1688库存定期同步、采购单创建（半自动模式）、1688订单提交（需人工审批）、采购物流追踪、物流信息同步到WooCommerce订单。支持一件代发模式。',
  permission_level = 'L2',
  model_name = 'deepseek-chat',
  prompt_version = 'v2',
  status = 'active'
WHERE agent_id = 'supply-chain-manager';

-- ============================================================
-- 4. 客户经理Agent（customer-manager）
-- 职责：客户服务、订单查询、售后处理
-- 权限：L1（内部读），回复需规则校验
-- ============================================================
UPDATE agents SET
  description = '客户经理AI：负责客户咨询回复、订单状态查询、售后问题处理、客户学习记录。所有对外文案必须通过禁词/敏感词/品牌口径规则校验，回复不了时降级到人工。',
  permission_level = 'L1',
  model_name = 'deepseek-chat',
  prompt_version = 'v2',
  status = 'active'
WHERE agent_id = 'customer-manager';

-- ============================================================
-- 5. 商业分析师Agent（business-analyst）
-- 职责：经营数据分析、成本模型、AI周报、选品模型评估
-- 权限：L3（高风险执行），可执行数据分析和报表生成
-- ============================================================
UPDATE agents SET
  description = '商业分析师AI：负责经营数据分析、成本模型计算、AI经营周报生成、选品模型评估与校准、营销效果分析。所有数据基于真实API，禁止模拟数据。',
  permission_level = 'L3',
  model_name = 'deepseek-chat',
  prompt_version = 'v2',
  status = 'active'
WHERE agent_id = 'business-analyst';

-- ============================================================
-- 验证：查询所有Agent配置
-- ============================================================
SELECT agent_id, name, domain, status, permission_level, model_name, prompt_version
FROM agents
WHERE workspace_id = '00000000-0000-0000-0000-000000000001'::uuid
ORDER BY domain;
