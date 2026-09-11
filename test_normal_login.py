import paramiko
import socket
import time

host = "95.217.218.178"
port = 22

print(f"测试连接 {host}:{port}...")

# 测试端口是否开放
for i in range(5):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        if result == 0:
            banner = sock.recv(1024).decode().strip()
            print(f"端口22开放，Banner: {banner}")
            sock.close()
            break
        else:
            print(f"第{i+1}次: 端口22不可达")
        sock.close()
    except Exception as e:
        print(f"第{i+1}次: 测试失败 - {e}")
    time.sleep(5)

# 尝试用密码test123登录
print("\n尝试用密码test123登录...")
try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    ssh.connect(
        hostname=host,
        port=port,
        username="root",
        password="test123",
        timeout=30,
        allow_agent=False,
        look_for_keys=False
    )
    print("SSH密码登录成功！已进入正常系统")
    
    # 执行命令测试
    stdin, stdout, stderr = ssh.exec_command("hostname && whoami && uname -a && cat /etc/os-release | head -5")
    print("\n系统信息:")
    print(stdout.read().decode())
    
    # 检查SSH服务状态
    print("\n检查SSH服务状态...")
    stdin, stdout, stderr = ssh.exec_command("systemctl status ssh --no-pager | head -20")
    print(stdout.read().decode())
    
    # 检查fail2ban和ufw状态
    print("\n检查fail2ban和ufw状态...")
    stdin, stdout, stderr = ssh.exec_command("systemctl is-enabled fail2ban 2>/dev/null; systemctl is-enabled ufw 2>/dev/null; iptables -L -n | head -10")
    print(stdout.read().decode())
    
    ssh.close()
    print("\n连接已关闭")
    print("\n=== SSH登录问题已解决！ ===")
    
except paramiko.AuthenticationException as e:
    print(f"认证失败: {e}")
except Exception as e:
    print(f"连接失败: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
