-- ============================================================
-- AI Agent 工具白名单注册
-- 按照 AGENTS.md 3.1 原则：Agent 只能调用注册过的工具函数
-- 权限级别：L0(公开读) / L1(内部读) / L2(提议) / L3(高风险执行)
-- ============================================================

-- 清理旧数据（保留workspace_id约束）
DELETE FROM agent_tools WHERE workspace_id = '00000000-0000-0000-0000-000000000001'::uuid;

-- ============================================================
-- 1. 选品类工具（产品经理Agent - L1/L2）
-- ============================================================
INSERT INTO agent_tools (id, workspace_id, tool_name, description, permission_level, enabled, category, handler_name, args_schema, created_at, updated_at)
VALUES
(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'search_1688_products', '1688商品搜索，按关键词/品类检索商品列表', 'L1', true, 'sourcing', 'sourcing_1688_service.search_products', '{"keyword":"string","category":"string","page":"integer","page_size":"integer"}', NOW(), NOW()),

(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'get_1688_product_detail', '获取1688商品详情（价格、SKU、图片、属性、供应商）', 'L1', true, 'sourcing', 'sourcing_1688_service.get_product_detail', '{"offer_id":"string"}', NOW(), NOW()),

(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'analyze_product_selection', '选品分析（市场需求、竞争度、利润空间、风险评估）', 'L2', true, 'selection', 'selection_manager_service.analyze_product', '{"product_data":"object","market_data":"object"}', NOW(), NOW()),

(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'import_product_to_system', '将选品导入Nuotao系统（创建candidate状态产品）', 'L2', true, 'selection', 'product_service.create_product', '{"sku":"string","name":"string","source_url":"string","source":"string","cost_price":"decimal"}', NOW(), NOW()),

-- ============================================================
-- 2. 文案生成类工具（营销经理Agent - L1/L2）
-- ============================================================
(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'generate_product_copy', 'AI生成产品文案（标题、描述、卖点、SEO关键词）', 'L1', true, 'copywriting', 'product_copy_service.generate_copy', '{"product_id":"uuid","language":"string","tone":"string"}', NOW(), NOW()),

(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'check_copy_compliance', '文案合规检查（禁词、敏感词、品牌口径、事实核对）', 'L1', true, 'copywriting', 'content_generation_service.check_compliance', '{"content":"string","rules":"array"}', NOW(), NOW()),

(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'save_product_copy', '保存AI生成的文案到产品记录', 'L2', true, 'copywriting', 'product_service.update_copy', '{"product_id":"uuid","title":"string","description":"string","bullets":"array","seo_keywords":"array"}', NOW(), NOW()),

-- ============================================================
-- 3. 图片合规检查类工具（产品经理Agent - L1）
-- ============================================================
(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'check_image_compliance', '图片合规检查（白底、无文字、无水印、无促销标签、产品清晰度）', 'L1', true, 'image', 'image_generation_service.check_compliance', '{"image_url":"string","rules":"array"}', NOW(), NOW()),

(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'download_1688_images', '下载1688商品图片到本地（用于I2I图生图参考）', 'L1', true, 'image', 'sourcing_1688_service.download_images', '{"offer_id":"string","output_dir":"string"}', NOW(), NOW()),

-- ============================================================
-- 4. AI生图类工具（营销经理Agent - L1/L2）
-- ============================================================
(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'generate_main_images', '生成产品主图（3套方向：白底清爽/真实场景/促销转化）', 'L1', true, 'image_generation', 'main_image_service.generate_main_images', '{"product_id":"uuid","reference_image":"string","directions":"array","prompt_template":"string"}', NOW(), NOW()),

(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'generate_detail_images', '生成产品详情页长图（6个板块：品牌主视觉/核心卖点/功能结构/使用场景/产品细节/品质保障）', 'L1', true, 'image_generation', 'image_generation_service.generate_detail_images', '{"product_id":"uuid","reference_image":"string","sections":"array","prompt_template":"string"}', NOW(), NOW()),

(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'check_image_quality', '生图质量检查（产品外观一致性、文字清晰度、构图合理性）', 'L1', true, 'image_generation', 'image_generation_service.check_quality', '{"generated_images":"array","reference_image":"string","checklist":"array"}', NOW(), NOW()),

(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'save_product_images', '保存生成的图片到产品记录', 'L2', true, 'image_generation', 'product_service.update_images', '{"product_id":"uuid","main_image":"string","gallery_images":"array","detail_images":"array"}', NOW(), NOW()),

-- ============================================================
-- 5. WooCommerce上架类工具（产品经理Agent - L2/L3）
-- ============================================================
(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'create_woocommerce_product', '创建WooCommerce产品（草稿状态，不直接发布）', 'L2', true, 'woocommerce', 'woocommerce_sync_service.create_product', '{"product_id":"uuid","name":"string","sku":"string","price":"decimal","description":"string","category":"string"}', NOW(), NOW()),

(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'upload_woocommerce_images', '上传图片到WooCommerce媒体库', 'L2', true, 'woocommerce', 'woocommerce_sync_service.upload_images', '{"product_id":"uuid","images":"array"}', NOW(), NOW()),

(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'publish_woocommerce_product', '发布WooCommerce产品（高风险操作，必须人工审批）', 'L3', true, 'woocommerce', 'woocommerce_sync_service.publish_product', '{"woocommerce_product_id":"integer"}', NOW(), NOW()),

-- ============================================================
-- 6. 采购类工具（供应链经理Agent - L2/L3）
-- ============================================================
(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'create_purchase_order', '创建采购单（1688下单，半自动模式）', 'L2', true, 'procurement', 'purchase_order_service.create_order', '{"order_id":"uuid","product_id":"uuid","supplier_id":"string","quantity":"integer","unit_price":"decimal"}', NOW(), NOW()),

(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'submit_1688_order', '提交1688订单（高风险操作，必须人工审批）', 'L3', true, 'procurement', 'purchase_automation_service.submit_order', '{"purchase_order_id":"uuid","1688_offer_id":"string","sku_id":"string","quantity":"integer"}', NOW(), NOW()),

(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'track_purchase_order', '追踪采购单物流状态', 'L1', true, 'procurement', 'purchase_order_service.track_order', '{"purchase_order_id":"uuid"}', NOW(), NOW()),

(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'sync_logistics_to_woocommerce', '同步物流信息到WooCommerce订单', 'L2', true, 'procurement', 'fulfillment_service.sync_tracking', '{"order_id":"uuid","tracking_number":"string","carrier":"string"}', NOW(), NOW()),

-- ============================================================
-- 7. 库存同步类工具（供应链经理Agent - L1/L2）
-- ============================================================
(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'sync_inventory_from_1688', '从1688同步库存信息', 'L1', true, 'inventory', 'inventory_service.sync_from_1688', '{"offer_id":"string","sku_id":"string"}', NOW(), NOW()),

(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'update_woocommerce_inventory', '更新WooCommerce产品库存', 'L2', true, 'inventory', 'inventory_service.update_woocommerce', '{"product_id":"uuid","quantity":"integer"}', NOW(), NOW()),

-- ============================================================
-- 8. 通用工具（所有Agent - L0/L1）
-- ============================================================
(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'get_product_data', '读取产品数据', 'L0', true, 'common', 'product_service.get_product', '{"product_id":"uuid"}', NOW(), NOW()),

(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'list_products', '列出产品列表', 'L0', true, 'common', 'product_service.list_products', '{"status":"string","page":"integer","page_size":"integer"}', NOW(), NOW()),

(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'create_approval_request', '创建人工审批请求', 'L2', true, 'common', 'approval_service.ensure_approval', '{"approval_type":"string","entity_type":"string","entity_id":"string","metadata":"object"}', NOW(), NOW()),

(gen_random_uuid(), '00000000-0000-0000-0000-000000000001'::uuid, 'log_agent_run', '记录Agent运行审计日志', 'L0', true, 'common', 'agent_runtime.log_execution', '{"agent_id":"uuid","input":"object","output":"object","tool_calls":"array","cost":"decimal","status":"string"}', NOW(), NOW());

-- ============================================================
-- 验证：统计注册的工具数量
-- ============================================================
SELECT category, COUNT(*) as tool_count, 
       SUM(CASE WHEN permission_level = 'L3' THEN 1 ELSE 0 END) as high_risk_count
FROM agent_tools 
WHERE workspace_id = '00000000-0000-0000-0000-000000000001'::uuid
GROUP BY category 
ORDER BY category;
