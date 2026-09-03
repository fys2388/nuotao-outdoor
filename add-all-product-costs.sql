-- 为剩余14个产品添加成本数据
-- 成本结构：采购成本 + 国际运费 + 包装 + 支付费 + 营销摊销 + 售后损耗 = 总成本

-- NT-BAG-001 50L登山背包
INSERT INTO product_cost (
    id, workspace_id, product_id, currency,
    purchase_cost, domestic_shipping, first_leg_shipping, last_leg_shipping,
    payment_fee, marketing_amortization, after_sales_loss, total_cost,
    valid_from, notes, international_shipping, packaging, tax_estimate,
    handling, total_landed_cost, version
) VALUES (
    gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
    '035e6c35-8c8d-448f-a405-c0daa927dc74', 'USD',
    18.00, 0.50, 4.50, 1.20,
    1.20, 2.50, 0.80, 28.70,
    NOW(), '{"source": "1688", "supplier": "Yihao Outdoor", "moq": 50}',
    4.50, 1.00, 0.50, 0.30, 28.70, 'v1'
) ON CONFLICT DO NOTHING;

-- NT-BOTTLE-001 不锈钢保温水瓶
INSERT INTO product_cost (
    id, workspace_id, product_id, currency,
    purchase_cost, domestic_shipping, first_leg_shipping, last_leg_shipping,
    payment_fee, marketing_amortization, after_sales_loss, total_cost,
    valid_from, notes, international_shipping, packaging, tax_estimate,
    handling, total_landed_cost, version
) VALUES (
    gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
    'bbd05f81-bd44-445a-9d7a-5e1dd128f365', 'USD',
    6.50, 0.30, 1.80, 0.80,
    0.60, 1.20, 0.40, 11.60,
    NOW(), '{"source": "1688", "supplier": "Aohong Bottle", "moq": 100}',
    1.80, 0.40, 0.20, 0.15, 11.60, 'v1'
) ON CONFLICT DO NOTHING;

-- NT-CHAIR-001 便携折叠露营椅
INSERT INTO product_cost (
    id, workspace_id, product_id, currency,
    purchase_cost, domestic_shipping, first_leg_shipping, last_leg_shipping,
    payment_fee, marketing_amortization, after_sales_loss, total_cost,
    valid_from, notes, international_shipping, packaging, tax_estimate,
    handling, total_landed_cost, version
) VALUES (
    gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
    '8e62d506-357d-425d-bed9-aaf617e4ea81', 'USD',
    14.00, 0.40, 5.00, 1.50,
    1.00, 2.00, 0.60, 24.50,
    NOW(), '{"source": "1688", "supplier": "Tengfei Outdoor", "moq": 30}',
    5.00, 0.80, 0.40, 0.25, 24.50, 'v1'
) ON CONFLICT DO NOTHING;

-- NT-COOK-001 露营炊具套装10件
INSERT INTO product_cost (
    id, workspace_id, product_id, currency,
    purchase_cost, domestic_shipping, first_leg_shipping, last_leg_shipping,
    payment_fee, marketing_amortization, after_sales_loss, total_cost,
    valid_from, notes, international_shipping, packaging, tax_estimate,
    handling, total_landed_cost, version
) VALUES (
    gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
    '826479d1-3637-4113-979f-a81149366381', 'USD',
    16.00, 0.40, 3.50, 1.00,
    1.10, 2.20, 0.70, 24.90,
    NOW(), '{"source": "1688", "supplier": "Camping Cook Pro", "moq": 50}',
    3.50, 0.70, 0.35, 0.20, 24.90, 'v1'
) ON CONFLICT DO NOTHING;

-- NT-FILTER-001 便携净水器
INSERT INTO product_cost (
    id, workspace_id, product_id, currency,
    purchase_cost, domestic_shipping, first_leg_shipping, last_leg_shipping,
    payment_fee, marketing_amortization, after_sales_loss, total_cost,
    valid_from, notes, international_shipping, packaging, tax_estimate,
    handling, total_landed_cost, version
) VALUES (
    gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
    'db0d5dd7-5bf3-4062-92ae-08544e8a865a', 'USD',
    9.50, 0.30, 2.00, 0.80,
    0.75, 1.50, 0.50, 15.35,
    NOW(), '{"source": "1688", "supplier": "PureWater Tech", "moq": 100}',
    2.00, 0.50, 0.25, 0.15, 15.35, 'v1'
) ON CONFLICT DO NOTHING;

-- NT-KNIFE-002 户外多功能刀15功能
INSERT INTO product_cost (
    id, workspace_id, product_id, currency,
    purchase_cost, domestic_shipping, first_leg_shipping, last_leg_shipping,
    payment_fee, marketing_amortization, after_sales_loss, total_cost,
    valid_from, notes, international_shipping, packaging, tax_estimate,
    handling, total_landed_cost, version
) VALUES (
    gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
    '4c6aa7be-1219-47fe-a382-35716e756422', 'USD',
    7.50, 0.25, 1.50, 0.60,
    0.55, 1.10, 0.35, 11.85,
    NOW(), '{"source": "1688", "supplier": "SharpTool Factory", "moq": 200}',
    1.50, 0.35, 0.15, 0.10, 11.85, 'v1'
) ON CONFLICT DO NOTHING;

-- NT-LANTERN-001 可充电露营灯1000LM
INSERT INTO product_cost (
    id, workspace_id, product_id, currency,
    purchase_cost, domestic_shipping, first_leg_shipping, last_leg_shipping,
    payment_fee, marketing_amortization, after_sales_loss, total_cost,
    valid_from, notes, international_shipping, packaging, tax_estimate,
    handling, total_landed_cost, version
) VALUES (
    gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
    '849f3ddc-98b5-4992-8b15-4b0b9740127a', 'USD',
    8.00, 0.30, 2.20, 0.80,
    0.65, 1.30, 0.45, 13.70,
    NOW(), '{"source": "1688", "supplier": "BrightLantern Co", "moq": 100}',
    2.20, 0.45, 0.20, 0.15, 13.70, 'v1'
) ON CONFLICT DO NOTHING;

-- NT-LIGHT-001 可充电LED头灯1000流明
INSERT INTO product_cost (
    id, workspace_id, product_id, currency,
    purchase_cost, domestic_shipping, first_leg_shipping, last_leg_shipping,
    payment_fee, marketing_amortization, after_sales_loss, total_cost,
    valid_from, notes, international_shipping, packaging, tax_estimate,
    handling, total_landed_cost, version
) VALUES (
    gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
    '91149b07-5d37-432f-b2d8-c839d9063408', 'USD',
    5.50, 0.25, 1.50, 0.60,
    0.45, 0.90, 0.30, 9.50,
    NOW(), '{"source": "1688", "supplier": "HeadLight Pro", "moq": 200}',
    1.50, 0.30, 0.15, 0.10, 9.50, 'v1'
) ON CONFLICT DO NOTHING;

-- NT-PAD-001 充气露营睡垫
INSERT INTO product_cost (
    id, workspace_id, product_id, currency,
    purchase_cost, domestic_shipping, first_leg_shipping, last_leg_shipping,
    payment_fee, marketing_amortization, after_sales_loss, total_cost,
    valid_from, notes, international_shipping, packaging, tax_estimate,
    handling, total_landed_cost, version
) VALUES (
    gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
    '018c9783-f778-4f42-afcd-cf5a4b17bde4', 'USD',
    11.00, 0.35, 3.00, 1.00,
    0.85, 1.60, 0.55, 18.35,
    NOW(), '{"source": "1688", "supplier": "SleepWell Outdoor", "moq": 100}',
    3.00, 0.55, 0.25, 0.15, 18.35, 'v1'
) ON CONFLICT DO NOTHING;

-- NT-POLE-001 碳纤维登山杖一对
INSERT INTO product_cost (
    id, workspace_id, product_id, currency,
    purchase_cost, domestic_shipping, first_leg_shipping, last_leg_shipping,
    payment_fee, marketing_amortization, after_sales_loss, total_cost,
    valid_from, notes, international_shipping, packaging, tax_estimate,
    handling, total_landed_cost, version
) VALUES (
    gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
    '2f491e4b-5097-4d83-9f98-bf33dd9a665f', 'USD',
    22.00, 0.50, 4.00, 1.20,
    1.50, 3.00, 0.90, 33.10,
    NOW(), '{"source": "1688", "supplier": "CarbonPole Tech", "moq": 50}',
    4.00, 0.90, 0.40, 0.20, 33.10, 'v1'
) ON CONFLICT DO NOTHING;

-- NT-SLEEP-001 高级户外睡袋-15°F
INSERT INTO product_cost (
    id, workspace_id, product_id, currency,
    purchase_cost, domestic_shipping, first_leg_shipping, last_leg_shipping,
    payment_fee, marketing_amortization, after_sales_loss, total_cost,
    valid_from, notes, international_shipping, packaging, tax_estimate,
    handling, total_landed_cost, version
) VALUES (
    gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
    '985a42fa-ac56-4956-ab5d-a7b1b62110fd', 'USD',
    28.00, 0.60, 6.00, 1.80,
    1.80, 3.50, 1.00, 42.70,
    NOW(), '{"source": "1688", "supplier": "WarmSleep Factory", "moq": 30}',
    6.00, 1.00, 0.50, 0.30, 42.70, 'v1'
) ON CONFLICT DO NOTHING;

-- NT-TENT-001 高级户外露营帐篷4人
INSERT INTO product_cost (
    id, workspace_id, product_id, currency,
    purchase_cost, domestic_shipping, first_leg_shipping, last_leg_shipping,
    payment_fee, marketing_amortization, after_sales_loss, total_cost,
    valid_from, notes, international_shipping, packaging, tax_estimate,
    handling, total_landed_cost, version
) VALUES (
    gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
    '335c7390-bf91-4b20-ba70-cb96b33546d0', 'USD',
    45.00, 0.80, 12.00, 3.00,
    2.80, 5.50, 1.50, 70.60,
    NOW(), '{"source": "1688", "supplier": "TentPro Outdoor", "moq": 20}',
    12.00, 1.50, 0.80, 0.50, 70.60, 'v1'
) ON CONFLICT DO NOTHING;

-- NT-TENT-002 家庭露营帐篷6人
INSERT INTO product_cost (
    id, workspace_id, product_id, currency,
    purchase_cost, domestic_shipping, first_leg_shipping, last_leg_shipping,
    payment_fee, marketing_amortization, after_sales_loss, total_cost,
    valid_from, notes, international_shipping, packaging, tax_estimate,
    handling, total_landed_cost, version
) VALUES (
    gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
    '7f9c833a-f71b-484a-b5c4-9d6f5459ee42', 'USD',
    55.00, 1.00, 15.00, 3.50,
    3.50, 6.50, 1.80, 86.30,
    NOW(), '{"source": "1688", "supplier": "FamilyTent Co", "moq": 15}',
    15.00, 1.80, 0.90, 0.60, 86.30, 'v1'
) ON CONFLICT DO NOTHING;

-- NT-TOOL-001 多功能露营刀15功能
INSERT INTO product_cost (
    id, workspace_id, product_id, currency,
    purchase_cost, domestic_shipping, first_leg_shipping, last_leg_shipping,
    payment_fee, marketing_amortization, after_sales_loss, total_cost,
    valid_from, notes, international_shipping, packaging, tax_estimate,
    handling, total_landed_cost, version
) VALUES (
    gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
    'a7317349-5abc-4842-9ec5-473b95b0b9a8', 'USD',
    7.00, 0.25, 1.40, 0.60,
    0.50, 1.00, 0.35, 11.10,
    NOW(), '{"source": "1688", "supplier": "MultiTool Factory", "moq": 200}',
    1.40, 0.35, 0.15, 0.10, 11.10, 'v1'
) ON CONFLICT DO NOTHING;

-- 验证：所有产品成本统计
SELECT
    COUNT(*) as total_cost_records,
    COUNT(DISTINCT product_id) as products_with_cost,
    ROUND(AVG(purchase_cost), 2) as avg_purchase_cost,
    ROUND(AVG(total_cost), 2) as avg_total_cost,
    ROUND(MIN(total_cost), 2) as min_total_cost,
    ROUND(MAX(total_cost), 2) as max_total_cost
FROM product_cost;

-- 验证：按产品列出成本
SELECT p.sku, p.name, pc.purchase_cost, pc.international_shipping, pc.total_cost
FROM product_cost pc
JOIN products p ON pc.product_id = p.id
ORDER BY pc.total_cost DESC;
