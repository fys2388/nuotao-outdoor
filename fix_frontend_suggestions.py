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
    print("正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # 1. 读取前端文件
    print("\n=== 1. 读取前端文件 ===")
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/frontend/src/pages/AgentSuggestions.tsx', 'r') as f:
        content = f.read().decode('utf-8')
    sftp.close()
    print(f"文件长度: {len(content)} 字符")
    
    # 2. 修复第105行 - setSuggestions(data || []) -> setSuggestions(data.items || data || [])
    print("\n=== 2. 修复setSuggestions ===")
    old1 = "setSuggestions(data || [])"
    new1 = "setSuggestions(data.items || data || [])"
    if old1 in content:
        content = content.replace(old1, new1)
        print("✅ 已修复 setSuggestions")
    else:
        print("❌ 未找到 setSuggestions")
    
    # 3. 修复统计部分 - const all = await allResponse.json() -> 取items
    print("\n=== 3. 修复统计部分 ===")
    old2 = """      const allResponse = await fetch(`${API_BASE}?limit=200`)
      const all = await allResponse.json()
      setStats({
        pending: all.filter((s: AgentSuggestion) => s.status === 'pending_approval').length,"""
    new2 = """      const allResponse = await fetch(`${API_BASE}?limit=200`)
      const allData = await allResponse.json()
      const all = allData.items || allData || []
      setStats({
        pending: all.filter((s: AgentSuggestion) => s.status === 'pending_approval').length,"""
    if old2 in content:
        content = content.replace(old2, new2)
        print("✅ 已修复统计部分")
    else:
        print("❌ 未找到统计部分")
        # 尝试查找
        import re
        match = re.search(r'const allResponse.*?const all =.*?all\.filter', content, re.DOTALL)
        if match:
            print(f"找到类似代码: {match.group()[:200]}")
    
    # 4. 写回文件
    print("\n=== 4. 写回文件 ===")
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/frontend/src/pages/AgentSuggestions.tsx', 'w') as f:
        f.write(content.encode('utf-8'))
    sftp.close()
    print("✅ 文件已写回")
    
    # 5. 验证修复
    print("\n=== 5. 验证修复 ===")
    stdin, stdout, stderr = ssh.exec_command("grep -n 'data.items\\|allData.items' /opt/nuotao/frontend/src/pages/AgentSuggestions.tsx")
    print(stdout.read().decode())
    
    # 6. 重新构建前端
    print("\n=== 6. 重新构建前端 ===")
    stdin, stdout, stderr = ssh.exec_command("cd /opt/nuotao/frontend && npm run build 2>&1 | tail -20")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 7. 部署到服务器
    print("\n=== 7. 部署到服务器 ===")
    stdin, stdout, stderr = ssh.exec_command("""
# 备份旧文件
cp -r /var/www/nuotao /var/www/nuotao.backup.$(date +%Y%m%d%H%M%S)

# 清空旧文件
rm -rf /var/www/nuotao/*

# 复制新构建
cp -r /opt/nuotao/frontend/dist/* /var/www/nuotao/

# 设置权限
chown -R www-data:www-data /var/www/nuotao/

echo "部署完成"
ls -la /var/www/nuotao/assets/ | head -10
""")
    print(stdout.read().decode())
    
    print("\n=== 前端修复并部署完成！ ===")
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
