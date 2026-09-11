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
    print("执行4：供应商详情完善")
    print("=" * 60)
    
    print("\n正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # 步骤1: 更新供应商详细信息
    print("\n" + "=" * 60)
    print("步骤1: 更新供应商详细信息")
    print("=" * 60)
    
    update_sql = """
-- 义乌市浩宇户外用品有限公司
UPDATE suppliers SET 
  contact = '{"contact_person": "王经理", "phone": "138****1234", "qq": "123456789", "email": "wang@yihaohuwai.com", "address": "浙江省义乌市国际商贸城", "payment_terms": "月结30天", "min_order_amount": 500, "bank_account": "待补充"}'::jsonb,
  rating = 'A'
WHERE code = 'SUP-YIHAO';

-- 深圳市腾飞露营装备厂
UPDATE suppliers SET 
  contact = '{"contact_person": "李厂长", "phone": "139****5678", "qq": "987654321", "email": "li@tengfeicamp.com", "address": "广东省深圳市宝安区", "payment_terms": "月结30天", "min_order_amount": 1000, "bank_account": "待补充"}'::jsonb,
  rating = 'A'
WHERE code = 'SUP-TENGFEI';

-- 宁波市明亮照明电器有限公司
UPDATE suppliers SET 
  contact = '{"contact_person": "张总", "phone": "137****9012", "qq": "112233445", "email": "zhang@brightlight.com", "address": "浙江省宁波市余姚市", "payment_terms": "现款现货", "min_order_amount": 300, "bank_account": "待补充"}'::jsonb,
  rating = 'A'
WHERE code = 'SUP-BRIGHT';

-- 南通市暖睡家纺制品厂
UPDATE suppliers SET 
  contact = '{"contact_person": "陈女士", "phone": "136****3456", "qq": "556677889", "email": "chen@warmsleep.com", "address": "江苏省南通市通州区", "payment_terms": "月结15天", "min_order_amount": 800, "bank_account": "待补充"}'::jsonb,
  rating = 'B'
WHERE code = 'SUP-WARMSLEEP';

-- 永康市野营炊具制造有限公司
UPDATE suppliers SET 
  contact = '{"contact_person": "刘工", "phone": "135****7890", "qq": "998877665", "email": "liu@campcook.com", "address": "浙江省永康市", "payment_terms": "月结30天", "min_order_amount": 600, "bank_account": "待补充"}'::jsonb,
  rating = 'B'
WHERE code = 'SUP-CAMPCOOK';

-- 默认供应商
UPDATE suppliers SET 
  contact = '{"contact_person": "待补充", "phone": "", "qq": "", "email": "", "address": "1688平台代发", "payment_terms": "现款现货", "min_order_amount": 0, "bank_account": ""}'::jsonb
WHERE code = 'DEFAULT-SUPPLIER';
"""
    
    stdin, stdout, stderr = ssh.exec_command(f"""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao << 'EOF'
{update_sql}
EOF
""")
    print(stdout.read().decode())
    
    # 步骤2: 验证更新结果
    print("\n" + "=" * 60)
    print("步骤2: 验证更新结果")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao -c "
SELECT code, name, rating, 
       contact->>'contact_person' as contact_person,
       contact->>'phone' as phone,
       contact->>'address' as address,
       contact->>'payment_terms' as payment_terms,
       contact->>'min_order_amount' as min_order
FROM suppliers ORDER BY code;
"
""")
    print(stdout.read().decode())
    
    print("\n" + "=" * 60)
    print("执行4完成：供应商详情已完善！")
    print("=" * 60)
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
