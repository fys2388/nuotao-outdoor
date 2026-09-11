import paramiko
import json

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
    print("任务5：WooCommerce推送功能测试")
    print("=" * 60)
    
    print("\n正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # 步骤1: 获取产品列表，选择1-2个产品测试
    print("\n" + "=" * 60)
    print("步骤1: 获取产品列表")
    print("=" * 60)
    
    stdin, stdout, stderr = ssh.exec_command("""
curl -s http://127.0.0.1:8000/api/v1/products?limit=5 | python3 -c '
import sys, json
data = json.load(sys.stdin)
products = data.get("items", data.get("products", data if isinstance(data, list) else []))
print(f"产品数量: {len(products)}")
for p in products[:3]:
    print(f"  - ID: {p.get(\"id\")}, SKU: {p.get(\"sku\")}, 名称: {p.get(\"name\")[:30]}, WC_ID: {p.get(\"woocommerce_id\", \"无\")}")
' 2>&1
""")
    print(stdout.read().decode())
    
    # 步骤2: 测试单个产品推送
    print("\n" + "=" * 60)
    print("步骤2: 测试单个产品推送")
    print("=" * 60)
    
    # 先获取一个产品ID
    stdin, stdout, stderr = ssh.exec_command("""
curl -s http://127.0.0.1:8000/api/v1/products?limit=1 | python3 -c '
import sys, json
data = json.load(sys.stdin)
products = data.get("items", data.get("products", data if isinstance(data, list) else []))
if products:
    print(products[0].get("id"))
' 2>&1
""")
    product_id = stdout.read().decode().strip()
    print(f"测试产品ID: {product_id}")
    
    if product_id and product_id != "None":
        # 调用推送API
        print(f"\n正在推送产品 {product_id} 到WooCommerce...")
        stdin, stdout, stderr = ssh.exec_command(f"""
curl -s -X POST http://127.0.0.1:8000/api/v1/products/{product_id}/push-woocommerce \
  -H "Content-Type: application/json" 2>&1
""")
        result = stdout.read().decode()
        print(f"推送结果: {result[:500]}")
        
        try:
            result_json = json.loads(result)
            if result_json.get("success"):
                print(f"\n✅ 推送成功！")
                print(f"   动作: {result_json.get('action')}")
                print(f"   产品: {result_json.get('name')}")
                print(f"   WooCommerce ID: {result_json.get('woocommerce_id')}")
                print(f"   验证通过: {result_json.get('verified')}")
            else:
                print(f"\n❌ 推送失败: {result_json.get('error')}")
        except:
            print("\n⚠️ 无法解析推送结果")
    else:
        print("⚠️ 未获取到产品ID，跳过单个推送测试")
    
    # 步骤3: 验证WooCommerce中的产品
    print("\n" + "=" * 60)
    print("步骤3: 验证WooCommerce连接")
    print("=" * 60)
    
    stdin, stdout, stderr = ssh.exec_command("""
curl -s "https://nuotaooutdoor.com/wp-json/wc/v3/products?per_page=1" \
  -u "ck_3f24b7b9a4e0c5e6d7f8a9b0c1d2e3f4:cs_1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d" 2>&1 | python3 -c '
import sys, json
try:
    data = json.load(sys.stdin)
    if isinstance(data, list) and len(data) > 0:
        print(f"✅ WooCommerce API连接正常")
        print(f"   产品数量: {len(data)}")
        print(f"   第一个产品: {data[0].get(\"name\", \"\")[:40]}")
    elif isinstance(data, dict):
        print(f"⚠️ API返回错误: {data.get(\"message\", str(data)[:100])}")
    else:
        print(f"⚠️ 未知响应格式")
except Exception as e:
    print(f"❌ 解析失败: {e}")
' 2>&1
""")
    print(stdout.read().decode())
    
    # 步骤4: 查看后端日志确认推送
    print("\n" + "=" * 60)
    print("步骤4: 查看后端日志")
    print("=" * 60)
    
    stdin, stdout, stderr = ssh.exec_command("journalctl -u nuotao-backend --no-pager -n 30 | grep -i 'push\\|woocommerce\\|sync' | tail -10")
    log_output = stdout.read().decode()
    if log_output:
        print(log_output)
    else:
        print("（未找到相关日志，可能推送功能未被调用或日志级别不同）")
    
    print("\n" + "=" * 60)
    print("任务5完成：WooCommerce推送功能测试结束")
    print("=" * 60)
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
