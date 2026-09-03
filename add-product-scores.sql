-- 为候选产品创建 product_scores 评分记录
-- 评分维度：profit(30%), logistics(20%), demand(15%), competition(10%), differentiation(15%), compliance(10%)

-- CAND-002 太阳能LED露营灯（总分80.2）
INSERT INTO product_scores (
    id, workspace_id, product_id,
    profit, logistics, demand, competition, differentiation, compliance,
    total, model_version, rule_version, scored_at, created_at
) VALUES (
    gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
    '9da474bb-29da-4008-b1a2-864a62fef6ba',
    85.0, 78.0, 82.0, 70.0, 80.0, 90.0,
    80.2, 'v1.0', 'v1.0', NOW(), NOW()
) ON CONFLICT DO NOTHING;

-- CAND-001 便携露营吊床带蚊帐（总分74.5）
INSERT INTO product_scores (
    id, workspace_id, product_id,
    profit, logistics, demand, competition, differentiation, compliance,
    total, model_version, rule_version, scored_at, created_at
) VALUES (
    gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
    '05df0da4-19e7-46d4-8ecb-9c4240699f4e',
    80.0, 72.0, 75.0, 60.0, 75.0, 85.0,
    74.5, 'v1.0', 'v1.0', NOW(), NOW()
) ON CONFLICT DO NOTHING;

-- CAND-003 可折叠硅胶炊具套装（总分66.8）
INSERT INTO product_scores (
    id, workspace_id, product_id,
    profit, logistics, demand, competition, differentiation, compliance,
    total, model_version, rule_version, scored_at, created_at
) VALUES (
    gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
    '107eb029-b32c-4b4a-b658-4bef54d75cf0',
    72.0, 65.0, 68.0, 55.0, 70.0, 80.0,
    66.8, 'v1.0', 'v1.0', NOW(), NOW()
) ON CONFLICT DO NOTHING;

-- 验证评分记录
SELECT p.sku, p.name, ps.profit, ps.logistics, ps.demand, ps.competition, ps.differentiation, ps.compliance, ps.total
FROM product_scores ps
JOIN products p ON ps.product_id = p.id
ORDER BY ps.total DESC;
