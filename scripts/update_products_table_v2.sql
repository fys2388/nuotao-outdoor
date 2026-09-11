-- ============================================================
-- Nuotao AI OS 产品表结构升级 V2.0
-- 新增5个选品评分字段 + 1个综合评分字段
-- 执行日期：2026-09-06
-- ============================================================

-- 1. 新增选品评分字段
ALTER TABLE products ADD COLUMN IF NOT EXISTS supplier_score INTEGER DEFAULT 0;
ALTER TABLE products ADD COLUMN IF NOT EXISTS sales_score INTEGER DEFAULT 0;
ALTER TABLE products ADD COLUMN IF NOT EXISTS profit_score INTEGER DEFAULT 0;
ALTER TABLE products ADD COLUMN IF NOT EXISTS quality_score INTEGER DEFAULT 0;
ALTER TABLE products ADD COLUMN IF NOT EXISTS logistics_score INTEGER DEFAULT 0;
ALTER TABLE products ADD COLUMN IF NOT EXISTS differentiation_score INTEGER DEFAULT 0;
ALTER TABLE products ADD COLUMN IF NOT EXISTS market_heat_score INTEGER DEFAULT 0;
ALTER TABLE products ADD COLUMN IF NOT EXISTS amazon_competition_score INTEGER DEFAULT 0;
ALTER TABLE products ADD COLUMN IF NOT EXISTS seasonality_score INTEGER DEFAULT 0;
ALTER TABLE products ADD COLUMN IF NOT EXISTS ai_image_difficulty_score INTEGER DEFAULT 0;
ALTER TABLE products ADD COLUMN IF NOT EXISTS compliance_risk_score INTEGER DEFAULT 0;

-- 2. 新增综合评分和等级字段
ALTER TABLE products ADD COLUMN IF NOT EXISTS selection_total_score NUMERIC(5,2) DEFAULT 0;
ALTER TABLE products ADD COLUMN IF NOT EXISTS selection_grade VARCHAR(10) DEFAULT 'D';

-- 3. 新增全成本利润相关字段
ALTER TABLE products ADD COLUMN IF NOT EXISTS full_cost_profit_rate NUMERIC(5,2) DEFAULT 0;
ALTER TABLE products ADD COLUMN IF NOT EXISTS international_shipping_cost NUMERIC(10,2) DEFAULT 0;
ALTER TABLE products ADD COLUMN IF NOT EXISTS platform_fee NUMERIC(10,2) DEFAULT 0;
ALTER TABLE products ADD COLUMN IF NOT EXISTS marketing_cost NUMERIC(10,2) DEFAULT 0;

-- 4. 新增季节性和合规字段
ALTER TABLE products ADD COLUMN IF NOT EXISTS peak_season VARCHAR(50) DEFAULT '';
ALTER TABLE products ADD COLUMN IF NOT EXISTS compliance_notes TEXT DEFAULT '';

-- 5. 验证字段添加成功
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'products' 
AND column_name IN (
    'supplier_score', 'sales_score', 'profit_score', 'quality_score', 
    'logistics_score', 'differentiation_score', 'market_heat_score',
    'amazon_competition_score', 'seasonality_score', 'ai_image_difficulty_score',
    'compliance_risk_score', 'selection_total_score', 'selection_grade',
    'full_cost_profit_rate', 'international_shipping_cost', 'platform_fee',
    'marketing_cost', 'peak_season', 'compliance_notes'
)
ORDER BY column_name;

-- 6. 更新已有产品的评分（示例：水袋背包）
UPDATE products 
SET 
    supplier_score = 80,
    sales_score = 85,
    profit_score = 75,
    quality_score = 80,
    logistics_score = 85,
    differentiation_score = 90,
    market_heat_score = 85,
    amazon_competition_score = 70,
    seasonality_score = 90,
    ai_image_difficulty_score = 80,
    compliance_risk_score = 85,
    selection_total_score = 86.75,
    selection_grade = 'A',
    full_cost_profit_rate = 45.0,
    peak_season = '全年热销',
    compliance_notes = 'FDA食品级EVA材质，供应商可提供认证'
WHERE sku = 'NTO-WATER-BAG-001';

-- 7. 更新已有产品的评分（示例：折叠月亮椅）
UPDATE products 
SET 
    supplier_score = 90,
    sales_score = 85,
    profit_score = 65,
    quality_score = 85,
    logistics_score = 80,
    differentiation_score = 90,
    market_heat_score = 90,
    amazon_competition_score = 65,
    seasonality_score = 85,
    ai_image_difficulty_score = 80,
    compliance_risk_score = 85,
    selection_total_score = 80.75,
    selection_grade = 'B',
    full_cost_profit_rate = 25.5,
    peak_season = '春夏秋热销',
    compliance_notes = '无专利风险，碳钢+牛津布材质，无特殊认证'
WHERE sku = 'NTO-FOLDING-CHAIR-001';

-- 8. 验证更新结果
SELECT sku, name, selection_total_score, selection_grade, full_cost_profit_rate
FROM products 
WHERE sku IN ('NTO-WATER-BAG-001', 'NTO-FOLDING-CHAIR-001')
ORDER BY selection_total_score DESC;
