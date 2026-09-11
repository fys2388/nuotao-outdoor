"""在服务器上探查 WooCommerce 状态和位置"""
import paramiko

HOST = "95.217.218.178"
PORT = 22
USERNAME = "root"
PRIVATE_KEY = r"C:\Users\神魂之人\.ssh\id_ed25519_nuotao"

WC_KEY = "ck_bb60e1dba9bd459b751b2ab6845c707aaf5945ca"
WC_SECRET = "cs_6814a9474b9ecab87e0fbfd57dae11bf47071f5c"

def ssh_run(client, cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    return out, err

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=HOST, port=PORT, username=USERNAME, key_filename=PRIVATE_KEY, timeout=30)
    print("SSH 连接成功!\n")
    
    # 1. 通过 curl 获取 WooCommerce 系统状态
    print("=" * 60)
    print("1. WooCommerce 系统状态 (通过服务器 curl)")
    print("=" * 60)
    out, err = ssh_run(client, f"""
    curl -s -u "{WC_KEY}:{WC_SECRET}" "https://nuotaooutdoor.com/wp-json/wc/v3/system_status" 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
print('WooCommerce 版本:', data.get('version', 'N/A'))
print('WordPress 版本:', data.get('wp_version', 'N/A'))
print('PHP 版本:', data.get('php_version', 'N/A'))
theme = data.get('theme', {{}})
print('当前主题:', theme.get('name', 'N/A'), 'v' + str(theme.get('version', 'N/A')))
print('主题模板:', theme.get('template', 'N/A'))
print('是否子主题:', theme.get('is_child_theme', 'N/A'))
plugins = data.get('active_plugins', [])
print(f'\\n已激活插件 ({{len(plugins)}}):')
for p in plugins:
    print(f'  - {{p.get(\"plugin\", \"N/A\")}}: {{p.get(\"name\", \"N/A\")}} v{{p.get(\"version\", \"N/A\")}}')
" 2>&1 || echo "解析失败，原始输出:" && curl -s -u "{WC_KEY}:{WC_SECRET}" "https://nuotaooutdoor.com/wp-json/wc/v3/system_status" 2>/dev/null | head -c 2000
    """, timeout=30)
    print(out)
    if err:
        print(f"错误: {err[:500]}")
    
    # 2. 检查 WooCommerce 站点的真实源站 IP (通过 Cloudflare)
    print("\n" + "=" * 60)
    print("2. 检查 Cloudflare 后面的真实源站")
    print("=" * 60)
    out, _ = ssh_run(client, """
    # 检查是否有 cloudflared 隧道
    which cloudflared 2>/dev/null && cloudflared tunnel list 2>/dev/null || echo "cloudflared 未安装"
    echo "---"
    # 检查是否有 Cloudflare 相关配置
    grep -r "cloudflare\\|CF_\\|origin" /etc/nginx/ 2>/dev/null | grep -v '.bak' | head -10
    echo "---"
    # 检查 hosts 文件
    cat /etc/hosts | grep -i nuotao
    """)
    print(out)
    
    # 3. 检查服务器上是否有 WordPress 相关的备份或文件
    print("\n" + "=" * 60)
    print("3. 搜索 WordPress 相关文件")
    print("=" * 60)
    out, _ = ssh_run(client, """
    find / -name "wp-config.php" -o -name "wp-load.php" 2>/dev/null | head -10
    echo "---"
    # 检查 backups 目录
    ls /opt/nuotao/backups/ 2>/dev/null | head -20
    echo "---"
    # 检查是否有数据库备份包含 wordpress
    find /opt/nuotao/backups -name "*.sql" -o -name "*.gz" 2>/dev/null | head -10
    """, timeout=30)
    print(out)
    
    # 4. 获取 WordPress 站点的 HTTP 响应头（从服务器）
    print("\n" + "=" * 60)
    print("4. WooCommerce 站点 HTTP 响应头")
    print("=" * 60)
    out, _ = ssh_run(client, """
    curl -sI "https://nuotaooutdoor.com" 2>/dev/null | head -30
    echo "---"
    curl -sI "https://nuotaooutdoor.com/wp-admin" 2>/dev/null | head -10
    """)
    print(out)
    
    # 5. 检查是否可以通过 WordPress API 安装插件（需要先确认是否有管理员权限）
    print("\n" + "=" * 60)
    print("5. WordPress 用户和权限检查")
    print("=" * 60)
    out, _ = ssh_run(client, f"""
    # 尝试通过 WooCommerce API 获取当前用户信息
    curl -s -u "{WC_KEY}:{WC_SECRET}" "https://nuotaooutdoor.com/wp-json/wp/v2/users/me" 2>/dev/null | python3 -m json.tool 2>/dev/null | head -20 || echo "无法获取用户信息"
    echo "---"
    # 检查 WooCommerce API 权限范围
    curl -s -u "{WC_KEY}:{WC_SECRET}" "https://nuotaooutdoor.com/wp-json/" 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
print('站点名称:', data.get('name', 'N/A'))
print('URL:', data.get('url', 'N/A'))
routes = list(data.get('routes', {{}}).keys())
wp_routes = [r for r in routes if r.startswith('/wp/')]
wc_routes = [r for r in routes if r.startswith('/wc/')]
print(f'WP 路由数: {{len(wp_routes)}}')
print(f'WC 路由数: {{len(wc_routes)}}')
# 检查是否有插件相关路由
plugin_routes = [r for r in routes if 'plugin' in r.lower()]
print(f'插件相关路由: {{plugin_routes[:5]}}')
" 2>&1 || echo "API 调用失败"
    """, timeout=30)
    print(out)
    
    client.close()
    print("\n探查完成!")

if __name__ == "__main__":
    main()
