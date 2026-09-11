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
    
    # 1. 检查前端批量同步按钮调用的API
    print("\n=== 1. 检查前端批量同步按钮 ===")
    stdin, stdout, stderr = ssh.exec_command("grep -n '批量同步\\|sync.*wc\\|syncWooCommerce\\|handleSync' /opt/nuotao/frontend/src/pages/Products.tsx | head -20")
    print(stdout.read().decode())
    
    # 2. 检查是否有推送到WooCommerce的API
    print("\n=== 2. 检查推送到WooCommerce的API ===")
    stdin, stdout, stderr = ssh.exec_command("grep -rn 'push.*woocommerce\\|update.*woocommerce\\|create.*product.*wc\\|woocommerce.*create' /opt/nuotao/backend/app/services/ 2>/dev/null | head -10")
    print(stdout.read().decode())
    
    # 3. 查看woocommerce_sync_service的功能
    print("\n=== 3. 查看WooCommerce同步服务 ===")
    stdin, stdout, stderr = ssh.exec_command("grep -n 'def \\|async def ' /opt/nuotao/backend/app/services/woocommerce_sync_service.py | head -20")
    print(stdout.read().decode())
    
    # 4. 执行从WooCommerce同步（拉取最新数据）
    print("\n=== 4. 执行从WooCommerce同步（拉取最新数据） ===")
    stdin, stdout, stderr = ssh.exec_command("""
curl -s -X POST http://127.0.0.1:8000/api/v1/products/sync-woocommerce \
  -H "Content-Type: application/json" \
  -d '{}' 2>&1 | head -50
""")
    print(stdout.read().decode())
    
    # 5. 同步后检查产品数量
    print("\n=== 5. 同步后检查产品数量 ===")
    stdin, stdout, stderr = ssh.exec_command("""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao -c "
SELECT COUNT(*) as total, COUNT(CASE WHEN status='active' THEN 1 END) as active 
FROM products;
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
