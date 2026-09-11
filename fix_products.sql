-- 修复头灯产品（NTO-E38B998F57）
UPDATE products 
SET name = '跨境感应头灯强光长续航多功能便携头戴灯户外防水钓鱼迷你小头灯',
    category = '照明设备',
    source_url = 'https://detail.1688.com/offer/781946278349.html'
WHERE sku = 'NTO-E38B998F57';

-- 修复另一个LED产品（NTO-2A4F1775D1）- 暂时用英文名称
UPDATE products 
SET name = 'LED Rechargeable Headlamp - Waterproof Outdoor Headlight',
    category = '照明设备',
    source_url = 'https://detail.1688.com/offer/1078487117828.html'
WHERE sku = 'NTO-2A4F1775D1';

-- 验证修复结果
SELECT id, sku, name, source_url, category FROM products WHERE sku LIKE 'NTO-%';
