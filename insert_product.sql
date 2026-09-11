INSERT INTO products (id, workspace_id, sku, name, category, source, source_url, status, candidate_status, target_market, weight_kg, created_at, updated_at)
VALUES (
  gen_random_uuid(),
  '00000000-0000-0000-0000-000000000001',
  'NTO-WATER-BAG-001',
  '户外运动骑行水袋包带3L食品级材质水囊战术水袋包战术背包',
  '户外装备',
  '1688',
  'https://detail.1688.com/offer/550102787449.html',
  'candidate',
  'candidate',
  'US',
  '0.5',
  NOW(),
  NOW()
)
RETURNING id, sku, name;
