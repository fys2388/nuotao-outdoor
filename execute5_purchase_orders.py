import paramiko

# SSH连接配置
hostname = "95.217.218.178"
port = 22
username = "root"
password = "4SqwD8k@vuXWYUE%!bkfyf1b"

# 创建SSH客户端
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    print("=" * 60)
    print("执行5：采购订单录入")
    print("=" * 60)
    
    print("\n正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # 步骤1: 检查采购订单相关表
    print("\n" + "=" * 60)
    print("步骤1: 检查采购订单相关表")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao -c "
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema='public' 
AND (table_name LIKE '%purchase%' OR table_name LIKE '%po%')
ORDER BY table_name;
"
""")
    print(stdout.read().decode())
    
    # 步骤2: 查看purchase_orders表结构
    print("\n" + "=" * 60)
    print("步骤2: 查看采购订单表结构")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao -c "
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name='purchase_orders' 
ORDER BY ordinal_position;
" 2>&1 | head -30
""")
    print(stdout.read().decode())
    
    # 步骤3: 创建示例采购订单
    print("\n" + "=" * 60)
    print("步骤3: 创建示例采购订单")
    print("=" * 60)
    
    # 先检查是否有purchase_orders表，如果没有就创建
    create_table_sql = """
CREATE TABLE IF NOT EXISTS purchase_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    po_number VARCHAR(64) NOT NULL,
    supplier_id UUID,
    supplier_code VARCHAR(64),
    supplier_name VARCHAR(255),
    order_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expected_delivery TIMESTAMP WITH TIME ZONE,
    actual_delivery TIMESTAMP WITH TIME ZONE,
    total_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    items_count INTEGER NOT NULL DEFAULT 0,
    quality_rating NUMERIC(3,1),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
"""
    
    stdin, stdout, stderr = ssh.exec_command(f"""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao << 'EOF'
{create_table_sql}
EOF
""")
    print(stdout.read().decode())
    
    # 插入示例采购订单
    insert_sql = """
-- 义乌浩宇 - 背包和水瓶采购
INSERT INTO purchase_orders (workspace_id, po_number, supplier_id, supplier_code, supplier_name, order_date, expected_delivery, actual_delivery, total_amount, status, items_count, quality_rating, notes)
VALUES 
('00000000-0000-0000-0000-000000000001', 'PO-20260815-001', (SELECT id FROM suppliers WHERE code='SUP-YIHAO'), 'SUP-YIHAO', '义乌市浩宇户外用品有限公司', '2026-08-15', '2026-08-22', '2026-08-21', 12500.00, 'completed', 200, 4.8, '首批背包和水瓶采购，质量良好'),
('00000000-0000-0000-0000-000000000001', 'PO-20260901-002', (SELECT id FROM suppliers WHERE code='SUP-YIHAO'), 'SUP-YIHAO', '义乌市浩宇户外用品有限公司', '2026-09-01', '2026-09-08', NULL, 8600.00, 'shipped', 150, NULL, '收纳袋和配件采购，运输中'),

-- 深圳腾飞 - 帐篷和椅子采购
('00000000-0000-0000-0000-000000000001', 'PO-20260820-003', (SELECT id FROM suppliers WHERE code='SUP-TENGFEI'), 'SUP-TENGFEI', '深圳市腾飞露营装备厂', '2026-08-20', '2026-08-30', '2026-08-29', 18800.00, 'completed', 80, 4.9, '帐篷和折叠椅采购，质量优秀'),
('00000000-0000-0000-0000-000000000001', 'PO-20260905-004', (SELECT id FROM suppliers WHERE code='SUP-TENGFEI'), 'SUP-TENGFEI', '深圳市腾飞露营装备厂', '2026-09-05', '2026-09-15', NULL, 9500.00, 'ordered', 50, NULL, '补充帐篷库存'),

-- 宁波明亮 - 照明产品采购
('00000000-0000-0000-0000-000000000001', 'PO-20260825-005', (SELECT id FROM suppliers WHERE code='SUP-BRIGHT'), 'SUP-BRIGHT', '宁波市明亮照明电器有限公司', '2026-08-25', '2026-09-02', '2026-09-01', 15200.00, 'completed', 300, 4.7, '头灯和露营灯采购'),

-- 永康野营 - 炊具采购
('00000000-0000-0000-0000-000000000001', 'PO-20260828-006', (SELECT id FROM suppliers WHERE code='SUP-CAMPCOOK'), 'SUP-CAMPCOOK', '永康市野营炊具制造有限公司', '2026-08-28', '2026-09-05', '2026-09-04', 9800.00, 'completed', 120, 4.5, '炊具套装采购'),

-- 南通暖睡 - 睡眠装备采购
('00000000-0000-0000-0000-000000000001', 'PO-20260902-007', (SELECT id FROM suppliers WHERE code='SUP-WARMSLEEP'), 'SUP-WARMSLEEP', '南通市暖睡家纺制品厂', '2026-09-02', '2026-09-10', NULL, 6500.00, 'shipped', 80, NULL, '睡袋和防潮垫采购');
"""
    
    stdin, stdout, stderr = ssh.exec_command(f"""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao << 'EOF'
{insert_sql}
EOF
""")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 步骤4: 验证采购订单
    print("\n" + "=" * 60)
    print("步骤4: 验证采购订单")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao -c "
SELECT po_number, supplier_name, total_amount, status, items_count, order_date 
FROM purchase_orders 
ORDER BY order_date;
"
""")
    print(stdout.read().decode())
    
    # 步骤5: 按供应商统计采购额
    print("\n" + "=" * 60)
    print("步骤5: 按供应商统计采购额")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao -c "
SELECT supplier_code, supplier_name, 
       COUNT(*) as order_count, 
       SUM(total_amount) as total_amount,
       AVG(quality_rating) as avg_rating
FROM purchase_orders 
GROUP BY supplier_code, supplier_name 
ORDER BY total_amount DESC;
"
""")
    print(stdout.read().decode())
    
    print("\n" + "=" * 60)
    print("执行5完成：采购订单已录入！")
    print("=" * 60)
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
