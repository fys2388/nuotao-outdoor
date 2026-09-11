"""通过 WooCommerce REST API 获取站点信息，同时检查服务器其他配置"""
import paramiko
import requests
import json

# SSH 配置
HOST = "95.217.218.178"
PORT = 22
USERNAME = "root"
PRIVATE_KEY = r"C:\Users\神魂之人\.ssh\id_ed25519_nuotao"

# WooCommerce API 配置
WC_BASE_URL = "https://nuotaooutdoor.com"
WC_CONSUMER_KEY = "ck_bb60e1dba9bd459b751b2ab6845c707aaf5945ca"
WC_CONSUMER_SECRET = "cs_6814a9474b9ecab87e0fbfd57dae11bf47071f5c"

def ssh_run(client, cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    return out, err

def wc_get(endpoint, params=None):
    """WooCommerce REST API GET"""
    url = f"{WC_BASE_URL}/wp-json/wc/v3/{endpoint}"
    try:
        r = requests.get(url, auth=(WC_CONSUMER_KEY, WC_CONSUMER_SECRET), params=params, timeout=15)
        return r.status_code, r.json() if r.headers.get('content-type','').startswith('application/json') else r.text
    except Exception as e:
        return None, str(e)

def wp_get(endpoint):
    """WordPress REST API GET (不需要 wc 权限的)"""
    url = f"{WC_BASE_URL}/wp-json/{endpoint}"
    try:
        r = requests.get(url, timeout=15)
        return r.status_code, r.json() if r.headers.get('content-type','').startswith('application/json') else r.text[:500]
    except Exception as e:
        return None, str(e)

def main():
    # 1. 通过 WordPress API 获取站点信息
    print("=" * 60)
    print("1. WordPress 站点信息")
    print("=" * 60)
    code, data = wp_get("")
    print(f"状态码: {code}")
    if isinstance(data, dict):
        print(f"名称: {data.get('name', 'N/A')}")
        print(f"描述: {data.get('description', 'N/A')}")
        print(f"URL: {data.get('url', 'N/A')}")
        print(f"命名空间: {data.get('namespaces', [])}")
    else:
        print(data)
    
    # 2. WooCommerce 系统状态
    print("\n" + "=" * 60)
    print("2. WooCommerce 系统状态")
    print("=" * 60)
    code, data = wc_get("system_status")
    if code == 200 and isinstance(data, dict):
        print(f"WooCommerce 版本: {data.get('version', 'N/A')}")
        print(f"WordPress 版本: {data.get('wp_version', 'N/A')}")
        print(f"PHP 版本: {data.get('php_version', 'N/A')}")
        print(f"当前主题: {data.get('theme', {}).get('name', 'N/A')}")
        print(f"主题版本: {data.get('theme', {}).get('version', 'N/A')}")
        print(f"主题模板: {data.get('theme', {}).get('template', 'N/A')}")
        # 插件列表
        plugins = data.get('active_plugins', [])
        print(f"\n已激活插件 ({len(plugins)}):")
        for p in plugins:
            print(f"  - {p.get('plugin', 'N/A')}: {p.get('name', 'N/A')} v{p.get('version', 'N/A')}")
    else:
        print(f"状态码: {code}")
        print(data)
    
    # 3. 检查服务器上的其他 nginx 配置
    print("\n" + "=" * 60)
    print("3. 服务器上其他 nginx 配置 (8081/8082)")
    print("=" * 60)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=HOST, port=PORT, username=USERNAME, key_filename=PRIVATE_KEY, timeout=30)
    
    out, _ = ssh_run(client, "cat /etc/nginx/sites-available/nuotao.bak 2>/dev/null | head -80")
    print("--- nuotao.bak (前80行) ---")
    print(out)
    
    # 检查 nginx 主配置中的其他 server
    out, _ = ssh_run(client, "grep -r 'listen 8081\\|listen 8082\\|listen.*8081\\|listen.*8082' /etc/nginx/ 2>/dev/null")
    print("\n--- 8081/8082 端口配置 ---")
    print(out)
    
    # 检查所有 nginx 配置中的 server_name
    out, _ = ssh_run(client, "grep -r 'server_name' /etc/nginx/ 2>/dev/null | grep -v '#' | grep -v '.bak'")
    print("\n--- 所有 server_name ---")
    print(out)
    
    # 检查 /opt/nuotao 目录
    out, _ = ssh_run(client, "ls -la /opt/nuotao/")
    print("\n--- /opt/nuotao 目录 ---")
    print(out)
    
    # 检查是否有 wordpress 相关目录
    out, _ = ssh_run(client, "find /opt /var/www /srv /home -type d -name 'wp-admin' -o -type d -name 'wp-includes' 2>/dev/null | head -10")
    print("\n--- WordPress 目录搜索 ---")
    print(out)
    
    client.close()
    
    # 4. 检查 WooCommerce 站点的 HTTP 响应头（判断服务器）
    print("\n" + "=" * 60)
    print("4. WooCommerce 站点 HTTP 响应头")
    print("=" * 60)
    try:
        r = requests.get(WC_BASE_URL, timeout=15, allow_redirects=True)
        print(f"最终 URL: {r.url}")
        print(f"状态码: {r.status_code}")
        for k, v in r.headers.items():
            if k.lower() in ['server', 'x-powered-by', 'x-cache', 'cf-ray', 'link', 'set-cookie']:
                print(f"  {k}: {v[:100]}")
    except Exception as e:
        print(f"错误: {e}")

if __name__ == "__main__":
    main()
