"""SSH 探查生产服务器 WooCommerce 状态"""
import paramiko
import sys

HOST = "95.217.218.178"
PORT = 22
USERNAME = "root"
PRIVATE_KEY = r"C:\Users\神魂之人\.ssh\id_ed25519_nuotao"

def ssh_run(client, cmd, timeout=30):
    """执行命令并返回输出"""
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    return out, err

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    print(f"正在连接 {HOST}:{PORT} (使用密钥 {PRIVATE_KEY})...")
    client.connect(hostname=HOST, port=PORT, username=USERNAME, key_filename=PRIVATE_KEY, timeout=30)
    print("SSH 连接成功!\n")
    
    # 1. 查找 WordPress/WooCommerce 安装路径
    print("=" * 60)
    print("1. 查找 WordPress/WooCommerce 安装路径")
    print("=" * 60)
    out, err = ssh_run(client, "find /var/www /opt /home -name 'wp-config.php' 2>/dev/null | head -10")
    print(f"wp-config.php 位置:\n{out}")
    if err:
        print(f"错误: {err}")
    
    # 2. 检查常见路径
    print("\n" + "=" * 60)
    print("2. 检查常见 Web 根目录")
    print("=" * 60)
    out, err = ssh_run(client, "ls -la /var/www/ 2>/dev/null; echo '---'; ls -la /var/www/html/ 2>/dev/null | head -20")
    print(out)
    
    # 3. 检查 Nginx 配置找到网站根目录
    print("\n" + "=" * 60)
    print("3. Nginx 站点配置")
    print("=" * 60)
    out, err = ssh_run(client, "ls -la /etc/nginx/sites-enabled/ 2>/dev/null; echo '==='; grep -r 'root\\|server_name' /etc/nginx/sites-enabled/ 2>/dev/null | head -30")
    print(out)
    
    # 4. 如果找到 WordPress，检查主题和插件
    print("\n" + "=" * 60)
    print("4. WordPress 主题和插件")
    print("=" * 60)
    # 先尝试找到 wp-content 路径
    out, err = ssh_run(client, "find /var/www /opt /home -type d -name 'wp-content' 2>/dev/null | head -5")
    wp_content_paths = out.strip().split('\n')
    print(f"wp-content 路径: {wp_content_paths}")
    
    for path in wp_content_paths:
        if path:
            print(f"\n--- 路径: {path} ---")
            # 主题
            out, _ = ssh_run(client, f"ls -la {path}/themes/ 2>/dev/null")
            print(f"主题:\n{out}")
            # 插件
            out, _ = ssh_run(client, f"ls -la {path}/plugins/ 2>/dev/null | head -30")
            print(f"插件:\n{out}")
    
    # 5. 检查 WP CLI 是否可用
    print("\n" + "=" * 60)
    print("5. WP CLI 状态")
    print("=" * 60)
    out, err = ssh_run(client, "which wp 2>/dev/null; wp --version 2>/dev/null || echo 'WP CLI 未安装'")
    print(out)
    
    # 6. 检查当前活动主题
    print("\n" + "=" * 60)
    print("6. 活动主题和 WooCommerce 版本")
    print("=" * 60)
    # 尝试通过 wp cli 或直接查数据库
    out, err = ssh_run(client, """
    WP_PATH=$(find /var/www /opt /home -name 'wp-config.php' 2>/dev/null | head -1 | xargs dirname)
    if [ -n "$WP_PATH" ]; then
        echo "WordPress 路径: $WP_PATH"
        if command -v wp &> /dev/null; then
            cd "$WP_PATH"
            wp theme list --allow-root 2>/dev/null
            echo "---"
            wp plugin list --allow-root 2>/dev/null | head -30
            echo "---"
            wp option get template --allow-root 2>/dev/null
            wp option get stylesheet --allow-root 2>/dev/null
        else
            echo "WP CLI 不可用，尝试直接查询..."
            # 从数据库查
            grep -r "DB_NAME\\|DB_USER\\|DB_PASSWORD\\|DB_HOST" "$WP_PATH/wp-config.php" 2>/dev/null | head -10
        fi
    else
        echo "未找到 WordPress"
    fi
    """)
    print(out)
    if err:
        print(f"错误: {err}")
    
    client.close()
    print("\n探查完成!")

if __name__ == "__main__":
    main()
