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
    print("产品-供应商关联脚本")
    print("=" * 60)
    
    print("\n正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # 1. 在products表添加supplier_id字段
    print("\n" + "=" * 60)
    print("步骤1: 在products表添加supplier_id字段")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao -c "
ALTER TABLE products ADD COLUMN IF NOT EXISTS supplier_id UUID;
ALTER TABLE products ADD COLUMN IF NOT EXISTS supplier_code VARCHAR(64);
"
""")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 2. 查看suppliers表的ID映射
    print("\n" + "=" * 60)
    print("步骤2: 查看供应商ID映射")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao -c "
SELECT id, code, name FROM suppliers ORDER BY code;
"
""")
    print(stdout.read().decode())
    
    # 3. 根据品类更新产品的supplier_id和supplier_code
    print("\n" + "=" * 60)
    print("步骤3: 根据品类匹配供应商")
    print("=" * 60)
    
    # 品类-供应商匹配规则
    # SUP-YIHAO: 义乌市浩宇户外用品有限公司 - 背包、收纳、水瓶、配件
    # SUP-TENGFEI: 深圳市腾飞露营装备厂 - 帐篷、家具、椅子
    # SUP-BRIGHT: 宁波市明亮照明电器有限公司 - 照明、头灯、灯笼
    # SUP-WARMSLEEP: 南通市暖睡家纺制品厂 - 睡眠装备
    # SUP-CAMPCOOK: 永康市野营炊具制造有限公司 - 炊具
    # DEFAULT-SUPPLIER: 默认供应商 - 其他
    
    update_sql = """
-- 炊具类 → 永康市野营炊具制造有限公司
UPDATE products SET supplier_id = (SELECT id FROM suppliers WHERE code = 'SUP-CAMPCOOK'), 
                    supplier_code = 'SUP-CAMPCOOK'
WHERE category = 'Cookware & Picnic' AND status = 'active';

-- 收纳类 → 义乌市浩宇户外用品有限公司
UPDATE products SET supplier_id = (SELECT id FROM suppliers WHERE code = 'SUP-YIHAO'), 
                    supplier_code = 'SUP-YIHAO'
WHERE category = 'Storage & Organizers' AND status = 'active';

-- 背包类 → 义乌市浩宇户外用品有限公司
UPDATE products SET supplier_id = (SELECT id FROM suppliers WHERE code = 'SUP-YIHAO'), 
                    supplier_code = 'SUP-YIHAO'
WHERE category = 'Backpacks & Hiking Gear' AND status = 'active';

-- 水瓶类 → 义乌市浩宇户外用品有限公司
UPDATE products SET supplier_id = (SELECT id FROM suppliers WHERE code = 'SUP-YIHAO'), 
                    supplier_code = 'SUP-YIHAO'
WHERE category = 'Sports Bottles' AND status = 'active';

-- 配件类 → 义乌市浩宇户外用品有限公司
UPDATE products SET supplier_id = (SELECT id FROM suppliers WHERE code = 'SUP-YIHAO'), 
                    supplier_code = 'SUP-YIHAO'
WHERE category = 'Outdoor Accessories' AND status = 'active';

-- 照明类 → 宁波市明亮照明电器有限公司
UPDATE products SET supplier_id = (SELECT id FROM suppliers WHERE code = 'SUP-BRIGHT'), 
                    supplier_code = 'SUP-BRIGHT'
WHERE category = 'Lighting & Power' AND status = 'active';

-- 头灯类 → 宁波市明亮照明电器有限公司
UPDATE products SET supplier_id = (SELECT id FROM suppliers WHERE code = 'SUP-BRIGHT'), 
                    supplier_code = 'SUP-BRIGHT'
WHERE category = 'Headlamps' AND status = 'active';

-- 灯笼类 → 宁波市明亮照明电器有限公司
UPDATE products SET supplier_id = (SELECT id FROM suppliers WHERE code = 'SUP-BRIGHT'), 
                    supplier_code = 'SUP-BRIGHT'
WHERE category = 'Camping Lanterns' AND status = 'active';

-- 帐篷类 → 深圳市腾飞露营装备厂
UPDATE products SET supplier_id = (SELECT id FROM suppliers WHERE code = 'SUP-TENGFEI'), 
                    supplier_code = 'SUP-TENGFEI'
WHERE category = 'Tents & Shelters' AND status = 'active';

-- 家具类 → 深圳市腾飞露营装备厂
UPDATE products SET supplier_id = (SELECT id FROM suppliers WHERE code = 'SUP-TENGFEI'), 
                    supplier_code = 'SUP-TENGFEI'
WHERE category = 'Camping Furniture' AND status = 'active';

-- 椅子类 → 深圳市腾飞露营装备厂
UPDATE products SET supplier_id = (SELECT id FROM suppliers WHERE code = 'SUP-TENGFEI'), 
                    supplier_code = 'SUP-TENGFEI'
WHERE category = 'Camping Chairs' AND status = 'active';

-- 睡眠类 → 南通市暖睡家纺制品厂
UPDATE products SET supplier_id = (SELECT id FROM suppliers WHERE code = 'SUP-WARMSLEEP'), 
                    supplier_code = 'SUP-WARMSLEEP'
WHERE category = 'Sleeping Gear & Mattress' AND status = 'active';

-- Outlet类 → 默认供应商
UPDATE products SET supplier_id = (SELECT id FROM suppliers WHERE code = 'DEFAULT-SUPPLIER'), 
                    supplier_code = 'DEFAULT-SUPPLIER'
WHERE category = 'Outlet' AND status = 'active';
"""
    
    # 执行更新
    stdin, stdout, stderr = ssh.exec_command(f"""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao << 'EOF'
{update_sql}
EOF
""")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 4. 验证关联结果
    print("\n" + "=" * 60)
    print("步骤4: 验证关联结果")
    print("=" * 60)
    
    # 按供应商统计产品数量
    stdin, stdout, stderr = ssh.exec_command("""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao -c "
SELECT s.code as supplier_code, s.name as supplier_name, COUNT(p.id) as product_count
FROM suppliers s
LEFT JOIN products p ON p.supplier_id = s.id AND p.status = 'active'
GROUP BY s.code, s.name
ORDER BY product_count DESC;
"
""")
    print("按供应商统计产品数量:")
    print(stdout.read().decode())
    
    # 按品类+供应商查看
    stdin, stdout, stderr = ssh.exec_command("""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao -c "
SELECT p.category, p.supplier_code, s.name as supplier_name, COUNT(*) as count
FROM products p
LEFT JOIN suppliers s ON s.code = p.supplier_code
WHERE p.status = 'active'
GROUP BY p.category, p.supplier_code, s.name
ORDER BY p.category;
"
""")
    print("按品类+供应商查看:")
    print(stdout.read().decode())
    
    # 检查是否有未关联的产品
    stdin, stdout, stderr = ssh.exec_command("""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao -c "
SELECT COUNT(*) as unlinked_count FROM products WHERE status = 'active' AND supplier_id IS NULL;
"
""")
    print("未关联产品数量:")
    print(stdout.read().decode())
    
    print("\n" + "=" * 60)
    print("产品-供应商关联完成！")
    print("=" * 60)
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
