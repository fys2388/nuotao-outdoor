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
    
    # 1. 检查后端服务状态
    print("\n=== 后端服务状态 ===")
    stdin, stdout, stderr = ssh.exec_command("systemctl is-active nuotao-backend && curl -s http://127.0.0.1:8000/health | head -5")
    print(stdout.read().decode())
    
    # 2. 检查产品API路径
    print("\n=== 产品API路径检查 ===")
    stdin, stdout, stderr = ssh.exec_command("curl -s http://127.0.0.1:8000/api/v1/products/ 2>&1 | head -20")
    print(f"带斜杠: {stdout.read().decode()[:200]}")
    
    stdin, stdout, stderr = ssh.exec_command("curl -s http://127.0.0.1:8000/api/v1/products 2>&1 | head -20")
    print(f"不带斜杠: {stdout.read().decode()[:200]}")
    
    # 3. 检查WooCommerce配置
    print("\n=== WooCommerce配置 ===")
    stdin, stdout, stderr = ssh.exec_command("grep -i 'woocommerce\\|WOOCOMMERCE' /opt/nuotao/backend/.env 2>/dev/null | head -10")
    print(stdout.read().decode())
    
    # 4. 检查采购订单API
    print("\n=== 采购订单API测试 ===")
    stdin, stdout, stderr = ssh.exec_command("curl -s http://127.0.0.1:8000/api/v1/supply-chain/purchase-orders 2>&1 | python3 -c 'import sys,json; data=json.load(sys.stdin); print(f\"采购订单数量: {len(data)}\") if isinstance(data,list) else print(data)' 2>&1")
    print(stdout.read().decode())
    
    # 5. 检查采购订单统计API
    print("\n=== 采购订单统计API测试 ===")
    stdin, stdout, stderr = ssh.exec_command("curl -s http://127.0.0.1:8000/api/v1/supply-chain/purchase-orders/stats 2>&1 | python3 -m json.tool 2>&1 | head -20")
    print(stdout.read().decode())
    
    # 6. 检查前端构建是否成功
    print("\n=== 前端构建文件检查 ===")
    stdin, stdout, stderr = ssh.exec_command("ls -la /var/www/nuotao/assets/ | grep -i 'purchase\\|Products' | head -5")
    print(stdout.read().decode())
    
    stdin, stdout, stderr = ssh.exec_command("ls -la /var/www/nuotao/index.html")
    print(stdout.read().decode())
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
