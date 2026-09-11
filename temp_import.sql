INSERT INTO products (id, workspace_id, sku, name, description, category, brand, status, source, source_url, tags, attributes, meta, created_at, updated_at, weight_kg, dimensions, target_market, candidate_status)
VALUES (
    gen_random_uuid(),
    '00000000-0000-0000-0000-000000000001',
    'NTO-CAMPING-TABLE-001',
    'Portable Folding Camping Table - Lightweight Aluminum Alloy, 120cm',
    'Portable folding camping table made of lightweight aluminum alloy. 120cm size, perfect for outdoor camping, picnics, fishing, and backyard gatherings. Quick fold design for easy transport and storage.',
    'Camp Furniture',
    'Nuotao Outdoor',
    'draft',
    '1688',
    'https://detail.1688.com/offer/911748269930.html',
    '["camping table", "folding table", "aluminum table", "outdoor furniture", "portable table", "picnic table"]'::jsonb,
    '{"material": "Aluminum Alloy", "size": "120cm", "color": "White/Blue", "foldable": true, "weight": "3.5kg"}'::jsonb,
    jsonb_build_object(
        '1688_offer_id', '911748269930',
        '1688_offer_url', 'https://detail.1688.com/offer/911748269930.html',
        'supplier_name', '霸州市鏖战户外用品有限公司',
        'supplier_rating', '超级工厂, 入驻7年, 回头率43%, 品质达标率99%',
        'cost_price_cny', 50.00,
        'cost_price_usd', 6.85,
        'profit_margin', '83%',
        'sourcing_method', '1688_dropshipping',
        'i2i_reference_url', 'https://aka.doubaocdn.com/s/Rp1tvAQs9L'
    ),
    NOW(),
    NOW(),
    3.5,
    '{"length": 120, "width": 60, "height": 70}'::jsonb,
    'US/EU',
    'selected'
)
RETURNING id, sku, name, status;
