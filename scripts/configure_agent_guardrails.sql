-- ============================================================
-- AI Agent 成本护栏与系统配置
-- 使用 system_settings.extra_config JSON 字段存储
-- ============================================================

-- 直接构造完整的Agent配置JSON并更新
UPDATE system_settings
SET extra_config = json_build_object(
  'agent_config', json_build_object(
    'version', 'v1.0',
    'updated_at', NOW()::text,
    
    -- 月度成本预算（美元）
    'monthly_budgets', json_build_object(
      'product-manager', 50.00,
      'marketing-manager', 100.00,
      'supply-chain-manager', 30.00,
      'customer-manager', 20.00,
      'business-analyst', 30.00
    ),
    
    -- 成本告警阈值（%）
    'alert_thresholds', json_build_object(
      'warning', 80,
      'downgrade', 95,
      'pause', 100
    ),
    
    -- 单次运行限制
    'run_limits', json_build_object(
      'max_tokens', 10000,
      'max_tool_calls', 20,
      'max_latency_seconds', 120
    ),
    
    -- 降级链配置
    'degradation', json_build_object(
      'llm_primary', 'deepseek-chat',
      'llm_fallback', 'gpt-3.5-turbo',
      'image_max_retries', 2,
      'customer_service_strategy', 'rule_engine_then_human'
    ),
    
    -- 生图SOP配置
    'image_generation', json_build_object(
      'method', 'i2i_only',
      'description', '仅允许I2I图生图，禁止纯文字T2I',
      'main_image_directions', json_build_array('white_background', 'real_scene', 'promotion'),
      'detail_image_sections', json_build_array('brand_hero', 'core_selling_points', 'functional_structure', 'use_scenes', 'product_details', 'quality_assurance'),
      'strict_rules', json_build_array('main_detail_separated', 'i2i_reference_required', 'english_only', 'per_image_quality_check')
    ),
    
    -- 审批SLA配置（小时）
    'approval_sla', json_build_object(
      'selection', 24,
      'copy', 12,
      'images', 12,
      'publish', 24,
      'purchase', 4
    ),
    
    -- 审计日志保留期（天）
    'audit_retention', json_build_object(
      'agent_runs', 365,
      'executions', 365,
      'approvals', 730
    ),
    
    -- 人审规则
    'human_in_the_loop', json_build_object(
      'required_approvals', json_build_array('PRODUCT_SELECTION', 'PRODUCT_COPY', 'PRODUCT_IMAGES', 'PRODUCT_PUBLISH', 'PURCHASE_ORDER'),
      'high_risk_tools', json_build_array('publish_woocommerce_product', 'submit_1688_order'),
      'principle', 'Agent是提议者不是执行者，高风险操作必须人工确认'
    )
  )
)
WHERE id = 1;

-- 验证：查询配置
SELECT id, site_name, 
       extra_config->'agent_config'->>'version' as config_version,
       extra_config->'agent_config'->'monthly_budgets' as budgets,
       extra_config->'agent_config'->'image_generation'->>'method' as image_method,
       extra_config->'agent_config'->'human_in_the_loop'->'required_approvals' as required_approvals
FROM system_settings
WHERE id = 1;
