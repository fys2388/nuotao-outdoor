import type { ModuleConfig } from './ModulePage'

// 选品管理
export const sourcingConfig: ModuleConfig = {
  key: 'sourcing',
  title: '选品管理',
  description: '管理产品选品信息，包括产品来源、供应商、评分状态等',
  apiEndpoint: '/api/v1/sourcing',
  stats: [
    { title: '总选品数', value: 48, color: '#1677ff' },
    { title: '已上架', value: 32, color: '#52c41a' },
    { title: '待评估', value: 10, color: '#faad14' },
    { title: '已淘汰', value: 6, color: '#ff4d4f' },
  ],
  fields: [
    { key: 'sku', label: 'SKU', type: 'text', required: true, width: 120 },
    { key: 'name', label: '产品名称', type: 'text', required: true, width: 200 },
    { key: 'category', label: '品类', type: 'select', options: [
      { label: '帐篷', value: 'tent' },
      { label: '睡袋', value: 'sleeping_bag' },
      { label: '户外服装', value: 'clothing' },
      { label: '登山装备', value: 'climbing' },
      { label: '露营配件', value: 'accessories' },
    ], width: 100 },
    { key: 'source', label: '来源', type: 'select', options: [
      { label: '1688', value: '1688' },
      { label: '阿里国际站', value: 'alibaba' },
      { label: '自有工厂', value: 'factory' },
      { label: '品牌代理', value: 'brand' },
    ], width: 100 },
    { key: 'supplier', label: '供应商', type: 'text', width: 120 },
    { key: 'cost_price', label: '采购价(¥)', type: 'number', width: 100 },
    { key: 'sale_price', label: '售价($)', type: 'number', width: 100 },
    { key: 'status', label: '状态', type: 'status', width: 100 },
    { key: 'score', label: '选品评分', type: 'number', width: 100 },
    { key: 'created_at', label: '创建时间', type: 'text', inForm: false, width: 160 },
  ],
  defaultData: [
    { id: 1, sku: 'NT-TENT-001', name: '双人双层防雨帐篷', category: 'tent', source: '1688', supplier: '义乌户外用品厂', cost_price: 180, sale_price: 59.99, status: 'active', score: 85, created_at: '2026-08-15' },
    { id: 2, sku: 'NT-SLEEP-002', name: '零下10度羽绒睡袋', category: 'sleeping_bag', source: 'factory', supplier: '嘉兴羽绒制品厂', cost_price: 280, sale_price: 89.99, status: 'active', score: 92, created_at: '2026-08-18' },
    { id: 3, sku: 'NT-CLOTH-003', name: '防风防水冲锋衣', category: 'clothing', source: 'alibaba', supplier: '泉州服装有限公司', cost_price: 150, sale_price: 79.99, status: 'pending', score: 78, created_at: '2026-08-20' },
    { id: 4, sku: 'NT-CLIMB-004', name: '专业登山杖套装', category: 'climbing', source: '1688', supplier: '宁波运动器材厂', cost_price: 80, sale_price: 39.99, status: 'active', score: 88, created_at: '2026-08-22' },
    { id: 5, sku: 'NT-ACC-005', name: '便携露营灯', category: 'accessories', source: 'brand', supplier: 'LED品牌代理', cost_price: 45, sale_price: 24.99, status: 'inactive', score: 65, created_at: '2026-08-25' },
  ],
}

// 成本模型
export const costConfig: ModuleConfig = {
  key: 'cost',
  title: '成本模型',
  description: '管理产品成本结构，包括采购成本、物流成本、平台费用、利润率分析',
  apiEndpoint: '/api/v1/cost-model',
  stats: [
    { title: '已建模产品', value: 32, color: '#1677ff' },
    { title: '平均毛利率', value: '65%', color: '#52c41a' },
    { title: '高利润产品', value: 18, color: '#722ed1' },
    { title: '待优化成本', value: 8, color: '#faad14' },
  ],
  fields: [
    { key: 'sku', label: 'SKU', type: 'text', required: true, width: 120 },
    { key: 'product_name', label: '产品名称', type: 'text', required: true, width: 180 },
    { key: 'purchase_cost', label: '采购成本(¥)', type: 'number', width: 110 },
    { key: 'shipping_cost', label: '物流成本($)', type: 'number', width: 110 },
    { key: 'platform_fee', label: '平台费用($)', type: 'number', width: 110 },
    { key: 'payment_fee', label: '支付手续费($)', type: 'number', width: 120 },
    { key: 'sale_price', label: '售价($)', type: 'number', width: 100 },
    { key: 'profit_margin', label: '毛利率', type: 'text', width: 100 },
    { key: 'status', label: '状态', type: 'status', width: 100 },
    { key: 'updated_at', label: '更新时间', type: 'text', inForm: false, width: 160 },
  ],
  defaultData: [
    { id: 1, sku: 'NT-TENT-001', product_name: '双人双层防雨帐篷', purchase_cost: 180, shipping_cost: 12.5, platform_fee: 4.2, payment_fee: 2.1, sale_price: 59.99, profit_margin: '62%', status: 'active', updated_at: '2026-09-01' },
    { id: 2, sku: 'NT-SLEEP-002', product_name: '零下10度羽绒睡袋', purchase_cost: 280, shipping_cost: 15.8, platform_fee: 6.3, payment_fee: 3.1, sale_price: 89.99, profit_margin: '68%', status: 'active', updated_at: '2026-09-01' },
    { id: 3, sku: 'NT-CLOTH-003', product_name: '防风防水冲锋衣', purchase_cost: 150, shipping_cost: 8.2, platform_fee: 5.6, payment_fee: 2.8, sale_price: 79.99, profit_margin: '71%', status: 'pending', updated_at: '2026-08-30' },
  ],
}

// AI选品建议
export const selectionConfig: ModuleConfig = {
  key: 'selection',
  title: 'AI选品建议',
  description: 'AI基于市场趋势、竞争分析、利润空间生成的选品建议列表',
  apiEndpoint: '/api/v1/ai-selection',
  stats: [
    { title: 'AI建议总数', value: 25, color: '#1677ff' },
    { title: '高潜力建议', value: 8, color: '#52c41a' },
    { title: '已采纳', value: 12, color: '#722ed1' },
    { title: '待评估', value: 5, color: '#faad14' },
  ],
  fields: [
    { key: 'product_name', label: '建议产品', type: 'text', required: true, width: 180 },
    { key: 'category', label: '品类', type: 'select', options: [
      { label: '帐篷', value: 'tent' },
      { label: '睡袋', value: 'sleeping_bag' },
      { label: '户外服装', value: 'clothing' },
      { label: '登山装备', value: 'climbing' },
      { label: '露营配件', value: 'accessories' },
    ], width: 100 },
    { key: 'market_trend', label: '市场趋势', type: 'select', options: [
      { label: '上升', value: 'rising' },
      { label: '稳定', value: 'stable' },
      { label: '下降', value: 'declining' },
    ], width: 100 },
    { key: 'competition', label: '竞争程度', type: 'select', options: [
      { label: '低', value: 'low' },
      { label: '中', value: 'medium' },
      { label: '高', value: 'high' },
    ], width: 100 },
    { key: 'estimated_profit', label: '预估利润($)', type: 'number', width: 110 },
    { key: 'ai_score', label: 'AI评分', type: 'number', width: 90 },
    { key: 'status', label: '状态', type: 'status', width: 100 },
    { key: 'suggestion', label: 'AI建议说明', type: 'textarea', inTable: false },
    { key: 'created_at', label: '生成时间', type: 'text', inForm: false, width: 160 },
  ],
  defaultData: [
    { id: 1, product_name: '便携式太阳能充电板', category: 'accessories', market_trend: 'rising', competition: 'medium', estimated_profit: 25.5, ai_score: 91, status: 'pending', suggestion: '户外露营市场对清洁能源需求增长，太阳能充电板搜索量月增35%，竞争中等，建议快速切入', created_at: '2026-09-01' },
    { id: 2, product_name: '超轻量钛合金炊具', category: 'climbing', market_trend: 'rising', competition: 'low', estimated_profit: 35.0, ai_score: 88, status: 'active', suggestion: '轻量化徒步趋势明显，钛合金炊具溢价能力强，目前竞争者少，建议开发自有品牌', created_at: '2026-08-30' },
    { id: 3, product_name: '智能温控睡袋', category: 'sleeping_bag', market_trend: 'stable', competition: 'high', estimated_profit: 45.0, ai_score: 76, status: 'inactive', suggestion: '智能温控概念新颖但技术门槛高，当前市场接受度有限，建议观望', created_at: '2026-08-28' },
  ],
}

// 采购自动化
export const purchaseConfig: ModuleConfig = {
  key: 'purchase',
  title: '采购自动化',
  description: '管理采购订单，包括供应商、采购数量、到货状态、付款状态',
  apiEndpoint: '/api/v1/purchase',
  stats: [
    { title: '采购订单总数', value: 56, color: '#1677ff' },
    { title: '进行中', value: 8, color: '#1890ff' },
    { title: '待付款', value: 3, color: '#faad14' },
    { title: '本月采购额', value: '¥85,600', color: '#52c41a' },
  ],
  fields: [
    { key: 'po_number', label: '采购单号', type: 'text', required: true, width: 130 },
    { key: 'supplier', label: '供应商', type: 'text', required: true, width: 140 },
    { key: 'product_name', label: '产品名称', type: 'text', width: 160 },
    { key: 'quantity', label: '数量', type: 'number', width: 80 },
    { key: 'unit_price', label: '单价(¥)', type: 'number', width: 100 },
    { key: 'total_amount', label: '总金额(¥)', type: 'number', width: 110 },
    { key: 'status', label: '状态', type: 'status', width: 100 },
    { key: 'payment_status', label: '付款状态', type: 'select', options: [
      { label: '未付款', value: 'unpaid' },
      { label: '部分付款', value: 'partial' },
      { label: '已付款', value: 'paid' },
    ], width: 100 },
    { key: 'expected_date', label: '预计到货', type: 'text', width: 120 },
    { key: 'created_at', label: '创建时间', type: 'text', inForm: false, width: 160 },
  ],
  defaultData: [
    { id: 1, po_number: 'PO-2026-001', supplier: '义乌户外用品厂', product_name: '双人双层防雨帐篷', quantity: 100, unit_price: 180, total_amount: 18000, status: 'completed', payment_status: 'paid', expected_date: '2026-08-20', created_at: '2026-08-01' },
    { id: 2, po_number: 'PO-2026-002', supplier: '嘉兴羽绒制品厂', product_name: '零下10度羽绒睡袋', quantity: 50, unit_price: 280, total_amount: 14000, status: 'processing', payment_status: 'partial', expected_date: '2026-09-10', created_at: '2026-08-25' },
    { id: 3, po_number: 'PO-2026-003', supplier: '宁波运动器材厂', product_name: '专业登山杖套装', quantity: 200, unit_price: 80, total_amount: 16000, status: 'pending', payment_status: 'unpaid', expected_date: '2026-09-15', created_at: '2026-09-01' },
  ],
}

// 物流监控
export const logisticsConfig: ModuleConfig = {
  key: 'logistics',
  title: '物流监控',
  description: '实时监控订单物流状态，包括发货、运输、清关、派送各环节',
  apiEndpoint: '/api/v1/logistics',
  stats: [
    { title: '运输中订单', value: 23, color: '#1677ff' },
    { title: '清关中', value: 5, color: '#faad14' },
    { title: '已签收', value: 156, color: '#52c41a' },
    { title: '异常件', value: 2, color: '#ff4d4f' },
  ],
  fields: [
    { key: 'tracking_number', label: '运单号', type: 'text', required: true, width: 150 },
    { key: 'order_id', label: '订单号', type: 'text', width: 130 },
    { key: 'carrier', label: '物流商', type: 'select', options: [
      { label: '中国邮政', value: 'china_post' },
      { label: '顺丰国际', value: 'sf_express' },
      { label: 'DHL', value: 'dhl' },
      { label: 'UPS', value: 'ups' },
      { label: 'FedEx', value: 'fedex' },
      { label: '西班牙邮政', value: 'correos' },
    ], width: 110 },
    { key: 'destination', label: '目的国', type: 'text', width: 100 },
    { key: 'status', label: '物流状态', type: 'status', width: 100 },
    { key: 'current_location', label: '当前位置', type: 'text', width: 140 },
    { key: 'estimated_delivery', label: '预计送达', type: 'text', width: 120 },
    { key: 'weight', label: '重量(kg)', type: 'number', width: 90 },
    { key: 'shipping_cost', label: '运费($)', type: 'number', width: 90 },
    { key: 'updated_at', label: '更新时间', type: 'text', inForm: false, width: 160 },
  ],
  defaultData: [
    { id: 1, tracking_number: 'CP123456789CN', order_id: 'ORD-1001', carrier: 'china_post', destination: '美国', status: 'processing', current_location: '上海转运中心', estimated_delivery: '2026-09-10', weight: 2.5, shipping_cost: 18.5, updated_at: '2026-09-02 08:30' },
    { id: 2, tracking_number: 'SF987654321', order_id: 'ORD-1002', carrier: 'sf_express', destination: '德国', status: 'pending', current_location: '深圳仓库', estimated_delivery: '2026-09-12', weight: 1.8, shipping_cost: 22.0, updated_at: '2026-09-02 09:15' },
    { id: 3, tracking_number: 'COR555666777', order_id: 'ORD-1003', carrier: 'correos', destination: '西班牙', status: 'completed', current_location: '已签收', estimated_delivery: '2026-08-28', weight: 3.2, shipping_cost: 15.8, updated_at: '2026-08-28 14:20' },
  ],
}

// 内容生成
export const contentConfig: ModuleConfig = {
  key: 'content',
  title: '内容生成系统',
  description: 'AI生成的营销内容，包括产品描述、广告文案、社交媒体帖子、博客文章',
  apiEndpoint: '/api/v1/content',
  stats: [
    { title: '生成内容总数', value: 128, color: '#1677ff' },
    { title: '已发布', value: 85, color: '#52c41a' },
    { title: '待审核', value: 12, color: '#faad14' },
    { title: '本月生成', value: 35, color: '#722ed1' },
  ],
  fields: [
    { key: 'title', label: '内容标题', type: 'text', required: true, width: 200 },
    { key: 'content_type', label: '内容类型', type: 'select', options: [
      { label: '产品描述', value: 'product_description' },
      { label: '广告文案', value: 'ad_copy' },
      { label: '社交媒体', value: 'social_media' },
      { label: '博客文章', value: 'blog_post' },
      { label: '邮件营销', value: 'email' },
    ], width: 110 },
    { key: 'product', label: '关联产品', type: 'text', width: 140 },
    { key: 'language', label: '语言', type: 'select', options: [
      { label: '英文', value: 'en' },
      { label: '中文', value: 'zh' },
      { label: '西班牙语', value: 'es' },
      { label: '德语', value: 'de' },
      { label: '法语', value: 'fr' },
    ], width: 90 },
    { key: 'word_count', label: '字数', type: 'number', width: 80 },
    { key: 'status', label: '状态', type: 'status', width: 100 },
    { key: 'ai_model', label: 'AI模型', type: 'text', width: 120 },
    { key: 'content_body', label: '内容正文', type: 'textarea', inTable: false },
    { key: 'created_at', label: '创建时间', type: 'text', inForm: false, width: 160 },
  ],
  defaultData: [
    { id: 1, title: '双人双层防雨帐篷 - 产品描述', content_type: 'product_description', product: 'NT-TENT-001', language: 'en', word_count: 320, status: 'published', ai_model: 'gpt-4o-mini', content_body: 'Experience the ultimate outdoor adventure with our premium 2-person double-layer rainproof tent...', created_at: '2026-09-01' },
    { id: 2, title: '秋季露营促销 - Facebook广告文案', content_type: 'ad_copy', product: '全品类', language: 'en', word_count: 85, status: 'pending', ai_model: 'gpt-4o-mini', content_body: '🍂 Fall Camping Sale! Up to 40% OFF on premium outdoor gear...', created_at: '2026-09-02' },
    { id: 3, title: '如何选择适合你的睡袋 - 博客文章', content_type: 'blog_post', product: '睡袋系列', language: 'en', word_count: 1200, status: 'draft', ai_model: 'gpt-4o-mini', content_body: 'Choosing the right sleeping bag is crucial for a comfortable camping experience...', created_at: '2026-08-30' },
  ],
}

// SEO基建
export const seoConfig: ModuleConfig = {
  key: 'seo',
  title: 'SEO基建',
  description: '搜索引擎优化管理，包括关键词、Meta标签、站点地图、结构化数据',
  apiEndpoint: '/api/v1/seo',
  stats: [
    { title: '已优化页面', value: 45, color: '#1677ff' },
    { title: '关键词总数', value: 280, color: '#722ed1' },
    { title: '排名前10', value: 32, color: '#52c41a' },
    { title: '待优化', value: 15, color: '#faad14' },
  ],
  fields: [
    { key: 'page_url', label: '页面URL', type: 'text', required: true, width: 200 },
    { key: 'page_title', label: '页面标题', type: 'text', required: true, width: 180 },
    { key: 'meta_description', label: 'Meta描述', type: 'textarea', width: 200 },
    { key: 'target_keyword', label: '目标关键词', type: 'text', width: 140 },
    { key: 'keyword_difficulty', label: '关键词难度', type: 'select', options: [
      { label: '低', value: 'low' },
      { label: '中', value: 'medium' },
      { label: '高', value: 'high' },
    ], width: 100 },
    { key: 'search_volume', label: '月搜索量', type: 'number', width: 100 },
    { key: 'current_rank', label: '当前排名', type: 'number', width: 90 },
    { key: 'status', label: '优化状态', type: 'status', width: 100 },
    { key: 'last_optimized', label: '上次优化', type: 'text', inForm: false, width: 120 },
  ],
  defaultData: [
    { id: 1, page_url: '/products/camping-tents', page_title: 'Best Camping Tents 2026 | Nuotao Outdoor', meta_description: 'Shop premium camping tents for every adventure. Waterproof, lightweight, and affordable. Free shipping on orders over $50.', target_keyword: 'camping tents', keyword_difficulty: 'high', search_volume: 12000, current_rank: 8, status: 'active', last_optimized: '2026-08-25' },
    { id: 2, page_url: '/products/sleeping-bags', page_title: 'Sleeping Bags for Camping | Nuotao Outdoor', meta_description: 'Find the perfect sleeping bag for your next trip. From summer to winter, we have you covered.', target_keyword: 'sleeping bags', keyword_difficulty: 'medium', search_volume: 8500, current_rank: 15, status: 'pending', last_optimized: '2026-08-20' },
    { id: 3, page_url: '/blog/camping-tips', page_title: 'Camping Tips & Guides | Nuotao Outdoor Blog', meta_description: 'Expert camping tips, gear guides, and outdoor adventure inspiration.', target_keyword: 'camping tips', keyword_difficulty: 'low', search_volume: 3200, current_rank: 3, status: 'active', last_optimized: '2026-09-01' },
  ],
}

// EDM营销
export const edmConfig: ModuleConfig = {
  key: 'edm',
  title: 'EDM营销自动化',
  description: '邮件营销活动管理，包括邮件模板、发送计划、打开率/点击率追踪',
  apiEndpoint: '/api/v1/edm',
  stats: [
    { title: '邮件活动总数', value: 32, color: '#1677ff' },
    { title: '订阅用户', value: 2850, color: '#722ed1' },
    { title: '平均打开率', value: '28.5%', color: '#52c41a' },
    { title: '平均点击率', value: '5.2%', color: '#faad14' },
  ],
  fields: [
    { key: 'campaign_name', label: '活动名称', type: 'text', required: true, width: 180 },
    { key: 'email_type', label: '邮件类型', type: 'select', options: [
      { label: '欢迎邮件', value: 'welcome' },
      { label: '促销活动', value: 'promotion' },
      { label: '新品发布', value: 'new_product' },
      { label: '弃购挽回', value: 'abandoned_cart' },
      { label: '节日营销', value: 'holiday' },
      { label: '周报', value: 'weekly' },
    ], width: 110 },
    { key: 'subject', label: '邮件主题', type: 'text', width: 200 },
    { key: 'recipients', label: '收件人数', type: 'number', width: 100 },
    { key: 'open_rate', label: '打开率', type: 'text', width: 90 },
    { key: 'click_rate', label: '点击率', type: 'text', width: 90 },
    { key: 'status', label: '状态', type: 'status', width: 100 },
    { key: 'scheduled_at', label: '计划发送', type: 'text', width: 120 },
    { key: 'email_content', label: '邮件内容', type: 'textarea', inTable: false },
    { key: 'created_at', label: '创建时间', type: 'text', inForm: false, width: 160 },
  ],
  defaultData: [
    { id: 1, campaign_name: '秋季露营促销 - 第一轮', email_type: 'promotion', subject: '🍂 Fall Camping Sale: Up to 40% OFF!', recipients: 2850, open_rate: '32.1%', click_rate: '6.8%', status: 'completed', scheduled_at: '2026-09-01 09:00', email_content: 'Hi [Name],\n\nFall is here and so is our biggest sale of the season...', created_at: '2026-08-28' },
    { id: 2, campaign_name: '新品发布 - 钛合金炊具', email_type: 'new_product', subject: '🔥 New Arrival: Titanium Cookware Set', recipients: 1200, open_rate: '28.5%', click_rate: '5.2%', status: 'scheduled', scheduled_at: '2026-09-05 10:00', email_content: 'Introducing our latest innovation...', created_at: '2026-09-01' },
    { id: 3, campaign_name: '弃购挽回 - 自动触发', email_type: 'abandoned_cart', subject: 'You left something in your cart 🛒', recipients: 85, open_rate: '45.2%', click_rate: '12.5%', status: 'active', scheduled_at: '自动触发', email_content: 'Hi [Name],\n\nYou forgot something...', created_at: '2026-08-15' },
  ],
}

// AI经营周报
export const weeklyReportConfig: ModuleConfig = {
  key: 'weekly-report',
  title: 'AI经营周报',
  description: 'AI自动生成的经营分析周报，包括销售数据、趋势分析、风险预警、改进建议',
  apiEndpoint: '/api/v1/weekly-report',
  stats: [
    { title: '已生成周报', value: 12, color: '#1677ff' },
    { title: '本周销售额', value: '$12,580', color: '#52c41a' },
    { title: '订单数', value: 156, color: '#722ed1' },
    { title: '客单价', value: '$80.64', color: '#faad14' },
  ],
  fields: [
    { key: 'week_number', label: '周次', type: 'text', required: true, width: 100 },
    { key: 'period', label: '统计周期', type: 'text', width: 180 },
    { key: 'total_revenue', label: '总销售额($)', type: 'number', width: 120 },
    { key: 'order_count', label: '订单数', type: 'number', width: 90 },
    { key: 'avg_order_value', label: '客单价($)', type: 'number', width: 110 },
    { key: 'top_product', label: '畅销产品', type: 'text', width: 150 },
    { key: 'growth_rate', label: '环比增长', type: 'text', width: 100 },
    { key: 'status', label: '状态', type: 'status', width: 100 },
    { key: 'ai_summary', label: 'AI总结', type: 'textarea', inTable: false },
    { key: 'recommendations', label: 'AI建议', type: 'textarea', inTable: false },
    { key: 'generated_at', label: '生成时间', type: 'text', inForm: false, width: 160 },
  ],
  defaultData: [
    { id: 1, week_number: 'W36', period: '2026-08-26 ~ 2026-09-01', total_revenue: 12580, order_count: 156, avg_order_value: 80.64, top_product: '双人双层防雨帐篷', growth_rate: '+15.2%', status: 'completed', ai_summary: '本周销售额稳步增长，主要得益于秋季促销活动和新品发布。帐篷品类表现突出，占总销售额的42%。', recommendations: '1. 继续加大帐篷品类广告投放\n2. 考虑增加睡袋品类促销\n3. 优化弃购挽回邮件流程', generated_at: '2026-09-02 08:00' },
    { id: 2, week_number: 'W35', period: '2026-08-19 ~ 2026-08-25', total_revenue: 10920, order_count: 142, avg_order_value: 76.90, top_product: '零下10度羽绒睡袋', growth_rate: '+8.5%', status: 'completed', ai_summary: '本周销售额平稳增长，睡袋品类表现优异。物流时效有所改善，客户满意度提升。', recommendations: '1. 维持当前广告策略\n2. 关注库存周转\n3. 准备秋季大促', generated_at: '2026-08-26 08:00' },
    { id: 3, week_number: 'W37', period: '2026-09-02 ~ 2026-09-08', total_revenue: 0, order_count: 0, avg_order_value: 0, top_product: '-', growth_rate: '-', status: 'pending', ai_summary: '本周数据统计中...', recommendations: '待生成', generated_at: '待生成' },
  ],
}

// 海外仓对接
export const overseasConfig: ModuleConfig = {
  key: 'overseas',
  title: '海外仓对接',
  description: '管理海外仓库信息，包括仓库位置、库存、入库/出库记录、物流时效',
  apiEndpoint: '/api/v1/overseas-warehouse',
  stats: [
    { title: '海外仓数量', value: 3, color: '#1677ff' },
    { title: '在库SKU', value: 45, color: '#722ed1' },
    { title: '库存总值', value: '$28,500', color: '#52c41a' },
    { title: '本月出库', value: 320, color: '#faad14' },
  ],
  fields: [
    { key: 'warehouse_code', label: '仓库编码', type: 'text', required: true, width: 120 },
    { key: 'warehouse_name', label: '仓库名称', type: 'text', required: true, width: 160 },
    { key: 'country', label: '国家', type: 'text', width: 100 },
    { key: 'city', label: '城市', type: 'text', width: 100 },
    { key: 'provider', label: '服务商', type: 'select', options: [
      { label: 'ShipBob', value: 'shipbob' },
      { label: 'ShipHero', value: 'shiphero' },
      { label: 'Flexport', value: 'flexport' },
      { label: '自有仓', value: 'self_owned' },
    ], width: 110 },
    { key: 'total_sku', label: 'SKU数量', type: 'number', width: 90 },
    { key: 'total_inventory', label: '库存总量', type: 'number', width: 100 },
    { key: 'monthly_fee', label: '月费($)', type: 'number', width: 100 },
    { key: 'status', label: '状态', type: 'status', width: 100 },
    { key: 'api_connected', label: 'API对接', type: 'text', width: 90 },
    { key: 'created_at', label: '创建时间', type: 'text', inForm: false, width: 160 },
  ],
  defaultData: [
    { id: 1, warehouse_code: 'US-LA-01', warehouse_name: '洛杉矶海外仓', country: '美国', city: '洛杉矶', provider: 'shipbob', total_sku: 25, total_inventory: 1250, monthly_fee: 850, status: 'active', api_connected: '已对接', created_at: '2026-06-15' },
    { id: 2, warehouse_code: 'DE-BER-01', warehouse_name: '柏林海外仓', country: '德国', city: '柏林', provider: 'flexport', total_sku: 15, total_inventory: 680, monthly_fee: 720, status: 'active', api_connected: '已对接', created_at: '2026-07-20' },
    { id: 3, warehouse_code: 'ES-MAD-01', warehouse_name: '马德里海外仓', country: '西班牙', city: '马德里', provider: 'self_owned', total_sku: 5, total_inventory: 120, monthly_fee: 350, status: 'pending', api_connected: '待对接', created_at: '2026-08-10' },
  ],
}

// B2B代理商
export const b2bConfig: ModuleConfig = {
  key: 'b2b',
  title: 'B2B代理商管理',
  description: '管理B2B代理商信息，包括代理等级、折扣政策、订单量、结算状态',
  apiEndpoint: '/api/v1/b2b',
  stats: [
    { title: '代理商总数', value: 12, color: '#1677ff' },
    { title: '活跃代理商', value: 8, color: '#52c41a' },
    { title: '本月B2B销售额', value: '$8,200', color: '#722ed1' },
    { title: '待结算金额', value: '$2,400', color: '#faad14' },
  ],
  fields: [
    { key: 'agent_code', label: '代理编码', type: 'text', required: true, width: 110 },
    { key: 'company_name', label: '公司名称', type: 'text', required: true, width: 180 },
    { key: 'contact_person', label: '联系人', type: 'text', width: 100 },
    { key: 'country', label: '国家', type: 'text', width: 100 },
    { key: 'agent_level', label: '代理等级', type: 'select', options: [
      { label: '金牌代理', value: 'gold' },
      { label: '银牌代理', value: 'silver' },
      { label: '铜牌代理', value: 'bronze' },
      { label: '普通代理', value: 'regular' },
    ], width: 100 },
    { key: 'discount_rate', label: '折扣率', type: 'text', width: 90 },
    { key: 'total_orders', label: '累计订单', type: 'number', width: 90 },
    { key: 'total_revenue', label: '累计销售额($)', type: 'number', width: 120 },
    { key: 'status', label: '状态', type: 'status', width: 100 },
    { key: 'settlement_status', label: '结算状态', type: 'select', options: [
      { label: '已结清', value: 'settled' },
      { label: '待结算', value: 'pending' },
      { label: '部分结算', value: 'partial' },
    ], width: 100 },
    { key: 'created_at', label: '合作时间', type: 'text', inForm: false, width: 120 },
  ],
  defaultData: [
    { id: 1, agent_code: 'B2B-001', company_name: 'Outdoor Adventure GmbH', contact_person: 'Hans Mueller', country: '德国', agent_level: 'gold', discount_rate: '35%', total_orders: 45, total_revenue: 28500, status: 'active', settlement_status: 'settled', created_at: '2026-03-15' },
    { id: 2, agent_code: 'B2B-002', company_name: 'Camping World LLC', contact_person: 'John Smith', country: '美国', agent_level: 'silver', discount_rate: '25%', total_orders: 28, total_revenue: 15600, status: 'active', settlement_status: 'pending', created_at: '2026-04-20' },
    { id: 3, agent_code: 'B2B-003', company_name: 'Aventura Outdoor SL', contact_person: 'Maria Garcia', country: '西班牙', agent_level: 'bronze', discount_rate: '15%', total_orders: 12, total_revenue: 5800, status: 'active', settlement_status: 'partial', created_at: '2026-06-10' },
    { id: 4, agent_code: 'B2B-004', company_name: 'Nordic Outdoor AB', contact_person: 'Erik Johansson', country: '瑞典', agent_level: 'regular', discount_rate: '10%', total_orders: 5, total_revenue: 2100, status: 'inactive', settlement_status: 'settled', created_at: '2026-07-25' },
  ],
}

// 系统设置
export const settingsConfig: ModuleConfig = {
  key: 'settings',
  title: '系统设置',
  description: '管理系统配置，包括店铺信息、API密钥、通知设置、安全策略',
  apiEndpoint: '/api/v1/settings',
  stats: [
    { title: '已配置项', value: 28, color: '#1677ff' },
    { title: 'API集成', value: 6, color: '#722ed1' },
    { title: '通知渠道', value: 3, color: '#52c41a' },
    { title: '待配置', value: 4, color: '#faad14' },
  ],
  fields: [
    { key: 'config_key', label: '配置项', type: 'text', required: true, width: 180 },
    { key: 'config_name', label: '配置名称', type: 'text', required: true, width: 160 },
    { key: 'category', label: '分类', type: 'select', options: [
      { label: '店铺设置', value: 'store' },
      { label: 'API集成', value: 'api' },
      { label: '通知设置', value: 'notification' },
      { label: '安全设置', value: 'security' },
      { label: '物流设置', value: 'logistics' },
    ], width: 110 },
    { key: 'config_value', label: '配置值', type: 'text', width: 200 },
    { key: 'description', label: '说明', type: 'textarea', inTable: false },
    { key: 'status', label: '状态', type: 'status', width: 100 },
    { key: 'updated_at', label: '更新时间', type: 'text', inForm: false, width: 160 },
  ],
  defaultData: [
    { id: 1, config_key: 'store_name', config_name: '店铺名称', category: 'store', config_value: 'Nuotao Outdoor', description: '店铺显示名称', status: 'active', updated_at: '2026-08-01' },
    { id: 2, config_key: 'woocommerce_api', config_name: 'WooCommerce API', category: 'api', config_value: '已配置', description: 'WooCommerce REST API 集成', status: 'active', updated_at: '2026-08-15' },
    { id: 3, config_key: 'feishu_webhook', config_name: '飞书通知', category: 'notification', config_value: '已配置', description: '飞书机器人 Webhook 通知', status: 'active', updated_at: '2026-08-20' },
    { id: 4, config_key: 'deepseek_api', config_name: 'DeepSeek API', category: 'api', config_value: '已配置', description: 'DeepSeek LLM API 集成', status: 'active', updated_at: '2026-08-25' },
    { id: 5, config_key: 'ssl_certificate', config_name: 'SSL证书', category: 'security', config_value: '待配置', description: 'HTTPS SSL 证书配置', status: 'pending', updated_at: '-' },
  ],
}

// 商品图片生成
export const imageGenConfig: ModuleConfig = {
  key: 'image-gen',
  title: '商品图片生成',
  description: 'AI 驱动的商品图片生成，支持多模型可插拔网关，月度成本护栏与审批流',
  apiEndpoint: '/api/v1/image-gen',
  stats: [
    { title: '默认模型', value: 'wan2.7', color: '#1677ff' },
    { title: '单张成本', value: '¥0.08', color: '#52c41a' },
    { title: '月度预算', value: '¥100', color: '#722ed1' },
    { title: '可用模型', value: 4, color: '#faad14' },
  ],
  fields: [
    { key: 'id', label: '任务ID', type: 'text', inForm: false, width: 200 },
    { key: 'prompt', label: '生成提示词', type: 'textarea', required: true, width: 250 },
    { key: 'use_case', label: '用途', type: 'select', options: [
      { label: '主图', value: 'main_image' },
      { label: '详情图', value: 'detail_image' },
      { label: '营销图', value: 'marketing_image' },
      { label: '社交媒体', value: 'social_media' },
      { label: '广告素材', value: 'ad_creative' },
    ], width: 120 },
    { key: 'requested_model', label: '请求模型', type: 'select', options: [
      { label: 'wan2.7-image (¥0.08)', value: 'wan2.7-image' },
      { label: 'qwen-image-3.0 (¥0.18)', value: 'qwen-image-3.0' },
      { label: 'seedream-4.0 (¥0.22)', value: 'seedream-4.0' },
      { label: 'mock (开发用)', value: 'mock' },
    ], width: 160 },
    { key: 'status', label: '状态', type: 'status', width: 100 },
    { key: 'cost_cny', label: '成本(¥)', type: 'number', inForm: false, width: 80 },
    { key: 'created_at', label: '创建时间', type: 'text', inForm: false, width: 160 },
  ],
  defaultData: [],
}

// 电商活动策划
export const activityPlannerConfig: ModuleConfig = {
  key: 'activity-planner',
  title: '电商活动策划',
  description: 'AI 生成电商营销活动方案，支持版本链管理与人工审批流',
  apiEndpoint: '/api/v1/activity-planner',
  stats: [
    { title: '活动类型', value: 8, color: '#1677ff' },
    { title: '待审批', value: 0, color: '#faad14' },
    { title: '已通过', value: 0, color: '#52c41a' },
    { title: '已执行', value: 0, color: '#722ed1' },
  ],
  fields: [
    { key: 'id', label: '方案ID', type: 'text', inForm: false, width: 200 },
    { key: 'name', label: '活动名称', type: 'text', required: true, width: 200 },
    { key: 'activity_type', label: '活动类型', type: 'select', options: [
      { label: '大促活动', value: 'big_promotion' },
      { label: '新品发布', value: 'new_launch' },
      { label: '清仓促销', value: 'clearance' },
      { label: '季节性活动', value: 'seasonal' },
      { label: '会员专享', value: 'member_exclusive' },
      { label: '节日营销', value: 'holiday' },
      { label: '捆绑销售', value: 'bundle' },
      { label: '其他', value: 'other' },
    ], width: 120 },
    { key: 'budget_total', label: '总预算($)', type: 'number', width: 100 },
    { key: 'start_date', label: '开始日期', type: 'text', width: 120 },
    { key: 'end_date', label: '结束日期', type: 'text', width: 120 },
    { key: 'approval_status', label: '审批状态', type: 'status', width: 100 },
    { key: 'version', label: '版本', type: 'number', inForm: false, width: 60 },
  ],
  defaultData: [],
}

// 达人/KOL运营
export const influencerConfig: ModuleConfig = {
  key: 'influencer',
  title: '达人/KOL运营',
  description: '达人档案管理、AI 智能匹配与合作记录追踪',
  apiEndpoint: '/api/v1/influencer',
  stats: [
    { title: '达人总数', value: 0, color: '#1677ff' },
    { title: '活跃合作', value: 0, color: '#52c41a' },
    { title: '平台覆盖', value: 5, color: '#722ed1' },
    { title: '合作类型', value: 6, color: '#faad14' },
  ],
  fields: [
    { key: 'id', label: '达人ID', type: 'text', inForm: false, width: 200 },
    { key: 'name', label: '达人名称', type: 'text', required: true, width: 150 },
    { key: 'platform', label: '平台', type: 'select', options: [
      { label: 'Instagram', value: 'instagram' },
      { label: 'TikTok', value: 'tiktok' },
      { label: 'YouTube', value: 'youtube' },
      { label: 'Facebook', value: 'facebook' },
      { label: 'Pinterest', value: 'pinterest' },
    ], width: 110 },
    { key: 'handle', label: '账号', type: 'text', width: 130 },
    { key: 'followers', label: '粉丝数', type: 'number', width: 100 },
    { key: 'engagement_rate', label: '互动率(%)', type: 'number', width: 90 },
    { key: 'category', label: '品类', type: 'text', width: 100 },
    { key: 'region', label: '地区', type: 'text', width: 80 },
    { key: 'status', label: '状态', type: 'status', width: 80 },
  ],
  defaultData: [],
}

// 多语言Listing本地化
export const listingLocalizationConfig: ModuleConfig = {
  key: 'listing-localization',
  title: '多语言Listing本地化',
  description: 'AI 驱动的多语言产品 Listing 本地化，支持英/德/法/西/意 5 种语言',
  apiEndpoint: '/api/v1/m6-extras/listing-localization',
  stats: [
    { title: '支持语言', value: 5, color: '#1677ff' },
    { title: '默认源语言', value: 'EN', color: '#52c41a' },
    { title: '目标市场', value: 'EU/US', color: '#722ed1' },
    { title: '本地化维度', value: 8, color: '#faad14' },
  ],
  fields: [
    { key: 'product_name', label: '产品名称', type: 'text', required: true, width: 180 },
    { key: 'target_language', label: '目标语言', type: 'select', options: [
      { label: 'English', value: 'en' },
      { label: 'Deutsch', value: 'de' },
      { label: 'Français', value: 'fr' },
      { label: 'Español', value: 'es' },
      { label: 'Italiano', value: 'it' },
    ], width: 120 },
    { key: 'target_market', label: '目标市场', type: 'text', width: 100 },
    { key: 'product_category', label: '产品品类', type: 'text', width: 120 },
    { key: 'confidence_score', label: '置信度', type: 'number', inForm: false, width: 80 },
  ],
  defaultData: [],
}

// 客服话术模板
export const customerTemplatesConfig: ModuleConfig = {
  key: 'customer-templates',
  title: '客服话术模板',
  description: '15 类客服场景 × 6 语言确定性话术模板，零成本即时响应',
  apiEndpoint: '/api/v1/m6-extras/customer-templates',
  stats: [
    { title: '场景模板', value: 15, color: '#1677ff' },
    { title: '支持语言', value: 6, color: '#52c41a' },
    { title: '英文全覆盖', value: '100%', color: '#722ed1' },
    { title: '德语模板', value: 2, color: '#faad14' },
  ],
  fields: [
    { key: 'category', label: '场景分类', type: 'select', required: true, options: [
      { label: '物流延迟', value: 'shipping_delay' },
      { label: '物流更新', value: 'shipping_update' },
      { label: '退货申请', value: 'return_request' },
      { label: '退款处理', value: 'refund_processing' },
      { label: '产品咨询', value: 'product_question' },
      { label: '尺码指南', value: 'size_guide' },
      { label: '订单确认', value: 'order_confirmation' },
      { label: '送达确认', value: 'delivery_confirmation' },
      { label: '商品损坏', value: 'damaged_item' },
      { label: '发错商品', value: 'wrong_item' },
      { label: '支付问题', value: 'payment_issue' },
      { label: '账户帮助', value: 'account_help' },
      { label: '一般咨询', value: 'general_inquiry' },
      { label: '致歉', value: 'apology' },
      { label: '跟进', value: 'follow_up' },
    ], width: 130 },
    { key: 'language', label: '语言', type: 'select', options: [
      { label: 'English', value: 'en' },
      { label: 'Deutsch', value: 'de' },
      { label: 'Français', value: 'fr' },
      { label: 'Español', value: 'es' },
      { label: 'Italiano', value: 'it' },
      { label: '中文', value: 'zh' },
    ], width: 110 },
    { key: 'subject', label: '邮件主题', type: 'text', inForm: false, width: 200 },
    { key: 'is_fallback', label: '英文回退', type: 'status', inForm: false, width: 80 },
  ],
  defaultData: [],
}

export const moduleConfigs: Record<string, ModuleConfig> = {
  sourcing: sourcingConfig,
  cost: costConfig,
  selection: selectionConfig,
  purchase: purchaseConfig,
  logistics: logisticsConfig,
  content: contentConfig,
  seo: seoConfig,
  edm: edmConfig,
  'weekly-report': weeklyReportConfig,
  overseas: overseasConfig,
  b2b: b2bConfig,
  settings: settingsConfig,
  'image-gen': imageGenConfig,
  'activity-planner': activityPlannerConfig,
  influencer: influencerConfig,
  'listing-localization': listingLocalizationConfig,
  'customer-templates': customerTemplatesConfig,
}
