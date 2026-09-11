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
    print("正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # 使用LIKE匹配，避免HTML实体问题
    print("\n=== 使用LIKE匹配更新供应商 ===")
    update_sql = """
-- 炊具类 → 永康市野营炊具制造有限公司
UPDATE products SET supplier_id = (SELECT id FROM suppliers WHERE code = 'SUP-CAMPCOOK'), 
                    supplier_code = 'SUP-CAMPCOOK'
WHERE category LIKE 'Cookware%' AND status = 'active' AND supplier_id IS NULL;

-- 收纳类 → 义乌市浩宇户外用品有限公司
UPDATE products SET supplier_id = (SELECT id FROM suppliers WHERE code = 'SUP-YIHAO'), 
                    supplier_code = 'SUP-YIHAO'
WHERE category LIKE 'Storage%' AND status = 'active' AND supplier_id IS NULL;

-- 背包类 → 义乌市浩宇户外用品有限公司
UPDATE products SET supplier_id = (SELECT id FROM suppliers WHERE code = 'SUP-YIHAO'), 
                    supplier_code = 'SUP-YIHAO'
WHERE category LIKE 'Backpacks%' AND status = 'active' AND supplier_id IS NULL;

-- 照明类 → 宁波市明亮照明电器有限公司
UPDATE products SET supplier_id = (SELECT id FROM suppliers WHERE code = 'SUP-BRIGHT'), 
                    supplier_code = 'SUP-BRIGHT'
WHERE category LIKE 'Lighting%' AND status = 'active' AND supplier_id IS NULL;

-- 帐篷类 → 深圳市腾飞露营装备厂
UPDATE products SET supplier_id = (SELECT id FROM suppliers WHERE code = 'SUP-TENGFEI'), 
                    supplier_code = 'SUP-TENGFEI'
WHERE category LIKE 'Tents%' AND status = 'active' AND supplier_id IS NULL;

-- 睡眠类 → 南通市暖睡家纺制品厂
UPDATE products SET supplier_id = (SELECT id FROM suppliers WHERE code = 'SUP-WARMSLEEP'), 
                    supplier_code = 'SUP-WARMSLEEP'
WHERE category LIKE 'Sleeping%' AND status = 'active' AND supplier_id IS NULL;
"""
    
    stdin, stdout, stderr = ssh.exec_command(f"""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao << 'EOF'
{update_sql}
EOF
""")
    print(stdout.read().decode())
    
    # 验证最终结果
    print("\n=== 最终验证：按供应商统计产品数量 ===")
    stdin, stdout, stderr = ssh.exec_command("""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao -c "
SELECT s.code as supplier_code, s.name as supplier_name, COUNT(p.id) as product_count
FROM suppliers s
LEFT JOIN products p ON p.supplier_id = s.id AND p.status = 'active'
GROUP BY s.code, s.name
ORDER BY product_count DESC;
"
""")
    print(stdout.read().decode())
    
    # 检查未关联产品
    print("\n=== 未关联产品 ===")
    stdin, stdout, stderr = ssh.exec_command("""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao -c "
SELECT sku, name, category FROM products WHERE status = 'active' AND supplier_id IS NULL;
"
""")
    print(stdout.read().decode())
    
    # 总产品数
    print("\n=== 总产品数 ===")
    stdin, stdout, stderr = ssh.exec_command("""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao -c "
SELECT COUNT(*) as total, COUNT(supplier_id) as linked, COUNT(*) - COUNT(supplier_id) as unlinked
FROM products WHERE status = 'active';
"
""")
    print(stdout.read().decode())
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
