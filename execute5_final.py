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
    print("执行5：采购订单录入（最终修正版）")
    print("=" * 60)
    
    print("\n正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # 步骤1: 清除Agent测试订单
    print("\n" + "=" * 60)
    print("步骤1: 清除Agent测试订单")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao -c "
DELETE FROM purchase_orders WHERE po_number LIKE 'PO-AGENT-%';
"
""")
    print(stdout.read().decode())
    
    # 步骤2: 插入采购订单（使用gen_random_uuid()生成id）
    print("\n" + "=" * 60)
    print("步骤2: 插入采购订单")
    print("=" * 60)
    
    insert_sql = """
-- 义乌浩宇 - 背包和水瓶采购
INSERT INTO purchase_orders (id, workspace_id, po_number, supplier_id, status, currency, subtotal, shipping_cost, total, expected_delivery_at, received_at, notes)
VALUES 
(gen_random_uuid(), '00000000-0000-0000-0000-000000000001', 'PO-20260815-001', (SELECT id FROM suppliers WHERE code='SUP-YIHAO'), 'received', 'CNY', 12000.00, 500.00, 12500.00, '2026-08-22', '2026-08-21', '首批背包和水瓶采购，质量良好'),
(gen_random_uuid(), '00000000-0000-0000-0000-000000000001', 'PO-20260901-002', (SELECT id FROM suppliers WHERE code='SUP-YIHAO'), 'shipped', 'CNY', 8200.00, 400.00, 8600.00, '2026-09-08', NULL, '收纳袋和配件采购，运输中'),

-- 深圳腾飞 - 帐篷和椅子采购
(gen_random_uuid(), '00000000-0000-0000-0000-000000000001', 'PO-20260820-003', (SELECT id FROM suppliers WHERE code='SUP-TENGFEI'), 'received', 'CNY', 18000.00, 800.00, 18800.00, '2026-08-30', '2026-08-29', '帐篷和折叠椅采购，质量优秀'),
(gen_random_uuid(), '00000000-0000-0000-0000-000000000001', 'PO-20260905-004', (SELECT id FROM suppliers WHERE code='SUP-TENGFEI'), 'ordered', 'CNY', 9100.00, 400.00, 9500.00, '2026-09-15', NULL, '补充帐篷库存'),

-- 宁波明亮 - 照明产品采购
(gen_random_uuid(), '00000000-0000-0000-0000-000000000001', 'PO-20260825-005', (SELECT id FROM suppliers WHERE code='SUP-BRIGHT'), 'received', 'CNY', 14600.00, 600.00, 15200.00, '2026-09-02', '2026-09-01', '头灯和露营灯采购'),

-- 永康野营 - 炊具采购
(gen_random_uuid(), '00000000-0000-0000-0000-000000000001', 'PO-20260828-006', (SELECT id FROM suppliers WHERE code='SUP-CAMPCOOK'), 'received', 'CNY', 9400.00, 400.00, 9800.00, '2026-09-05', '2026-09-04', '炊具套装采购'),

-- 南通暖睡 - 睡眠装备采购
(gen_random_uuid(), '00000000-0000-0000-0000-000000000001', 'PO-20260902-007', (SELECT id FROM suppliers WHERE code='SUP-WARMSLEEP'), 'shipped', 'CNY', 6200.00, 300.00, 6500.00, '2026-09-10', NULL, '睡袋和防潮垫采购');
"""
    
    stdin, stdout, stderr = ssh.exec_command(f"""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao << 'EOF'
{insert_sql}
EOF
""")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 步骤3: 验证采购订单
    print("\n" + "=" * 60)
    print("步骤3: 验证采购订单")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao -c "
SELECT po.po_number, s.name as supplier_name, po.total, po.status, po.currency, po.created_at::date
FROM purchase_orders po
LEFT JOIN suppliers s ON s.id = po.supplier_id
WHERE po.po_number LIKE 'PO-2026%'
ORDER BY po.created_at;
"
""")
    print(stdout.read().decode())
    
    # 步骤4: 按供应商统计采购额
    print("\n" + "=" * 60)
    print("步骤4: 按供应商统计采购额")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao -c "
SELECT s.code, s.name, 
       COUNT(po.id) as order_count, 
       COALESCE(SUM(po.total), 0) as total_amount
FROM suppliers s
LEFT JOIN purchase_orders po ON po.supplier_id = s.id AND po.po_number LIKE 'PO-2026%'
GROUP BY s.code, s.name 
ORDER BY total_amount DESC;
"
""")
    print(stdout.read().decode())
    
    # 步骤5: 采购订单总计
    print("\n" + "=" * 60)
    print("步骤5: 采购订单总计")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao -c "
SELECT COUNT(*) as total_orders, 
       SUM(total) as total_amount,
       COUNT(CASE WHEN status='received' THEN 1 END) as received,
       COUNT(CASE WHEN status='shipped' THEN 1 END) as shipped,
       COUNT(CASE WHEN status='ordered' THEN 1 END) as ordered
FROM purchase_orders
WHERE po_number LIKE 'PO-2026%';
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
