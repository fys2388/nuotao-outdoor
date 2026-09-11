-- 创建选品候选产品
INSERT INTO products (
    id, workspace_id, sku, name, description, category,
    status, source, tags, attributes, meta,
    target_market, candidate_status,
    created_at, updated_at
) VALUES
(
    gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
    'CAND-001', 'Portable Camping Hammock with Mosquito Net',
    'Lightweight portable hammock with integrated mosquito net, perfect for outdoor camping',
    'camping', 'draft', '1688',
    '["candidate","outdoor","camping"]',
    '{"estimated_cost": 8.50, "estimated_price": 29.99, "estimated_margin": 0.55, "demand_score": 75, "competition_score": 60, "profit_score": 80, "selection_score": 74.5}',
    '{}', 'US', 'candidate', NOW(), NOW()
),
(
    gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
    'CAND-002', 'Solar Powered LED Camping Lantern',
    'Rechargeable solar LED lantern with 3 brightness modes, waterproof for outdoor use',
    'lighting', 'draft', '1688',
    '["candidate","outdoor","lighting"]',
    '{"estimated_cost": 6.80, "estimated_price": 24.99, "estimated_margin": 0.60, "demand_score": 82, "competition_score": 70, "profit_score": 85, "selection_score": 80.2}',
    '{}', 'US', 'candidate', NOW(), NOW()
),
(
    gen_random_uuid(), '00000000-0000-0000-0000-000000000001',
    'CAND-003', 'Collapsible Silicone Camping Cookware Set',
    'Food-grade silicone collapsible cookware set, lightweight and space-saving for backpacking',
    'cooking', 'draft', '1688',
    '["candidate","outdoor","cooking"]',
    '{"estimated_cost": 12.00, "estimated_price": 39.99, "estimated_margin": 0.58, "demand_score": 68, "competition_score": 55, "profit_score": 72, "selection_score": 66.8}',
    '{}', 'US', 'candidate', NOW(), NOW()
)
ON CONFLICT DO NOTHING;

-- 验证候选产品
SELECT sku, name, category, candidate_status,
       attributes->>'selection_score' as selection_score
FROM products
WHERE candidate_status = 'candidate';

-- 统计
SELECT
    COUNT(*) as total_products,
    COUNT(*) FILTER (WHERE status = 'active') as active_products,
    COUNT(*) FILTER (WHERE candidate_status = 'candidate') as candidate_products
FROM products;
