import paramiko
import json

# SSH连接配置
hostname = "95.217.218.178"
port = 22
username = "root"
password = "test123"

# 创建SSH客户端
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    print("正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # 1. 通过API登录获取token
    print("\n=== 1. 通过API登录 ===")
    stdin, stdout, stderr = ssh.exec_command("""
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123"
""")
    response = stdout.read().decode()
    print(f"响应: {response}")
    
    # 解析token
    try:
        data = json.loads(response)
        access_token = data.get('access_token', '')
        refresh_token = data.get('refresh_token', '')
        print(f"\nAccess Token: {access_token[:50]}...")
        print(f"Refresh Token: {refresh_token[:50]}...")
        
        # 保存token到文件
        with open(r'E:\AI\nuotao-ai-os\admin_token.txt', 'w') as f:
            f.write(access_token)
        print("\nToken已保存到 admin_token.txt")
    except Exception as e:
        print(f"解析token失败: {e}")
    
except Exception as e:
    print(f"错误: {e}")
finally:
    ssh.close()
    print("\nSSH连接已关闭")
