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
    print("执行2：批量同步到WooCommerce")
    print("=" * 60)
    
    print("\n正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # 步骤1: 检查WooCommerce配置
    print("\n" + "=" * 60)
    print("步骤1: 检查WooCommerce配置")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("grep -i 'woocommerce\\|WOOCOMMERCE' /opt/nuotao/backend/.env 2>/dev/null | head -10")
    print(stdout.read().decode())
    
    # 步骤2: 检查WooCommerce同步API
    print("\n" + "=" * 60)
    print("步骤2: 检查WooCommerce同步API")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("grep -rn 'sync.*woocommerce\\|woocommerce.*sync\\|批量同步' /opt/nuotao/backend/app/api/v1/endpoints/ 2>/dev/null | head -10")
    print(stdout.read().decode())
    
    # 步骤3: 查看产品API的同步端点
    print("\n" + "=" * 60)
    print("步骤3: 查看产品同步端点")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("grep -n '@router.*sync\\|@router.*woocommerce' /opt/nuotao/backend/app/api/v1/endpoints/products.py 2>/dev/null | head -10")
    print(stdout.read().decode())
    
    # 步骤4: 测试WooCommerce连接
    print("\n" + "=" * 60)
    print("步骤4: 测试WooCommerce连接")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("""
cd /opt/nuotao/backend && .venv/bin/python -c "
import os
from dotenv import load_dotenv
load_dotenv()
wc_url = os.getenv('WOOCOMMERCE_URL', '')
wc_key = os.getenv('WOOCOMMERCE_CONSUMER_KEY', '')
wc_secret = os.getenv('WOOCOMMERCE_CONSUMER_SECRET', '')
print(f'WooCommerce URL: {wc_url}')
print(f'Consumer Key: {wc_key[:10]}...' if wc_key else 'Consumer Key: 未设置')
print(f'Consumer Secret: {wc_secret[:10]}...' if wc_secret else 'Consumer Secret: 未设置')
" 2>&1
""")
    print(stdout.read().decode())
    
    # 步骤5: 查看当前产品的WooCommerce同步状态
    print("\n" + "=" * 60)
    print("步骤5: 查看产品同步状态")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao -c "
SELECT 
  COUNT(*) as total,
  COUNT(CASE WHEN meta->>'woocommerce_id' IS NOT NULL THEN 1 END) as has_wc_id,
  COUNT(CASE WHEN meta->>'woocommerce_id' IS NULL THEN 1 END) as no_wc_id
FROM products WHERE status = 'active';
"
""")
    print(stdout.read().decode())
    
    # 步骤6: 检查WooCommerce店铺产品数量
    print("\n" + "=" * 60)
    print("步骤6: 检查WooCommerce店铺产品")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("""
cd /opt/nuotao/backend && .venv/bin/python -c "
import os
import requests
from dotenv import load_dotenv
load_dotenv()
wc_url = os.getenv('WOOCOMMERCE_URL', '')
wc_key = os.getenv('WOOCOMMERCE_CONSUMER_KEY', '')
wc_secret = os.getenv('WOOCOMMERCE_CONSUMER_SECRET', '')
if wc_url and wc_key and wc_secret:
    try:
        r = requests.get(f'{wc_url}/wp-json/wc/v3/products', auth=(wc_key, wc_secret), params={'per_page': 1}, timeout=10)
        print(f'WooCommerce API状态: {r.status_code}')
        if r.status_code == 200:
            total = r.headers.get('X-WP-Total', '未知')
            print(f'店铺产品总数: {total}')
        else:
            print(f'错误: {r.text[:200]}')
    except Exception as e:
        print(f'连接失败: {e}')
else:
    print('WooCommerce配置不完整')
" 2>&1
""")
    print(stdout.read().decode())
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
