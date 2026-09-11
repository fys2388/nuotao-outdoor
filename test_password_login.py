import paramiko
import sys

host = "95.217.218.178"
port = 22
username = "root"
password = "Abkkpn9cCguX"

print(f"尝试SSH密码登录 {host}:{port} ...")

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    ssh.connect(hostname=host, port=port, username=username, password=password, timeout=20)
    print("SSH密码登录成功！已进入正常系统")
    
    # 执行命令测试
    stdin, stdout, stderr = ssh.exec_command("hostname && whoami && uptime")
    print("\n系统信息:")
    print(stdout.read().decode())
    
    # 检查后端服务状态
    print("\n检查后端服务状态:")
    stdin, stdout, stderr = ssh.exec_command("systemctl status nuotao-backend 2>&1 | head -20 || echo '服务不存在'")
    print(stdout.read().decode())
    
    # 检查Docker容器
    print("\n检查Docker容器:")
    stdin, stdout, stderr = ssh.exec_command("docker ps 2>&1 || echo 'Docker未运行'")
    print(stdout.read().decode())
    
    # 检查8000端口
    print("\n检查8000端口:")
    stdin, stdout, stderr = ssh.exec_command("ss -tlnp | grep :8000 || echo '8000端口未监听'")
    print(stdout.read().decode())
    
    ssh.close()
    print("\n连接已关闭")
    
except paramiko.AuthenticationException as e:
    print(f"认证失败: {e}")
except Exception as e:
    print(f"连接失败: {type(e).__name__}: {e}")
