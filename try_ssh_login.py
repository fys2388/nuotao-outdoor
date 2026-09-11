#!/usr/bin/env python3
"""尝试用 SSH 密钥登录服务器"""

import paramiko
import sys

HOST = "95.217.218.178"
PORT = 22
KEY_PATH = r"C:\Users\神魂之人\.ssh\id_ed25519_nuotao"

# 尝试的用户名列表
USERNAMES = ["root", "ubuntu", "debian", "deploy", "nuotao", "admin", "cloud"]

def try_login(username):
    """尝试用指定用户名登录"""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        private_key = paramiko.Ed25519Key.from_private_key_file(KEY_PATH)
        ssh.connect(HOST, port=PORT, username=username, pkey=private_key, timeout=15, allow_agent=False, look_for_keys=False)
        
        # 登录成功
        print(f"✓ 登录成功！用户名: {username}")
        
        # 执行一些命令确认
        stdin, stdout, stderr = ssh.exec_command("whoami && hostname && uname -a")
        print(f"  whoami: {stdout.read().decode().strip()}")
        print(f"  hostname: {stdout.read().decode().strip()}")
        
        return ssh, username
        
    except paramiko.AuthenticationException as e:
        print(f"✗ {username}: 认证失败 - {e}")
    except Exception as e:
        print(f"✗ {username}: 错误 - {e}")
    finally:
        pass
    
    return None, None

def main():
    print("="*60)
    print("尝试 SSH 密钥登录")
    print(f"服务器: {HOST}:{PORT}")
    print(f"密钥: {KEY_PATH}")
    print("="*60)
    
    for username in USERNAMES:
        print(f"\n尝试用户名: {username}...")
        ssh, successful_user = try_login(username)
        if ssh:
            print(f"\n{'='*60}")
            print(f"成功！使用用户名: {successful_user}")
            print("="*60)
            
            # 检查是否有 sudo 权限
            print("\n检查 sudo 权限...")
            stdin, stdout, stderr = ssh.exec_command("sudo -n true 2>&1 && echo 'HAS_SUDO' || echo 'NO_SUDO'")
            sudo_result = stdout.read().decode().strip()
            print(f"  sudo 权限: {sudo_result}")
            
            ssh.close()
            return successful_user
    
    print("\n" + "="*60)
    print("所有用户名都登录失败")
    print("="*60)
    return None

if __name__ == "__main__":
    main()
