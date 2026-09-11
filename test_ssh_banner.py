import socket
import paramiko

host = "95.217.218.178"
port = 22

print(f"测试连接 {host}:{port}...")

# 测试端口是否开放
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    result = sock.connect_ex((host, port))
    if result == 0:
        print(f"端口 {port} 开放")
        
        # 获取SSH banner
        banner = sock.recv(1024).decode().strip()
        print(f"SSH Banner: {banner}")
    else:
        print(f"端口 {port} 关闭或不可达 (error: {result})")
    sock.close()
except Exception as e:
    print(f"连接失败: {e}")

# 尝试用不同的密码登录
print("\n尝试用不同的密码登录...")
passwords = ["test123", "Abkkpn9cCguX", "root", "password", "3khgtJNvXnFN"]

for pwd in passwords:
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=host,
            port=port,
            username="root",
            password=pwd,
            timeout=10,
            allow_agent=False,
            look_for_keys=False
        )
        print(f"密码 '{pwd}' 登录成功！")
        stdin, stdout, stderr = ssh.exec_command("hostname && whoami")
        print(stdout.read().decode())
        ssh.close()
        break
    except paramiko.AuthenticationException:
        print(f"密码 '{pwd}' 认证失败")
    except Exception as e:
        print(f"密码 '{pwd}' 连接失败: {type(e).__name__}: {e}")
