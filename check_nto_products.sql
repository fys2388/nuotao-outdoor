SELECT id, sku, name, source_url, category, created_at FROM products WHERE sku LIKE 'NTO-%' ORDER BY created_at DESC LIMIT 5;
