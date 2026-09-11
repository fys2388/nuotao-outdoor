import paramiko

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
    
    # 备份原文件
    print("\n=== 1. 备份原文件 ===")
    stdin, stdout, stderr = ssh.exec_command("cp /opt/nuotao/backend/app/api/v1/endpoints/b2b_admin.py /opt/nuotao/backend/app/api/v1/endpoints/b2b_admin.py.backup && echo '备份完成'")
    print(stdout.read().decode())
    
    # 2. 读取原文件内容
    print("\n=== 2. 读取原文件 ===")
    stdin, stdout, stderr = ssh.exec_command("cat /opt/nuotao/backend/app/api/v1/endpoints/b2b_admin.py")
    content = stdout.read().decode()
    print(f"文件长度: {len(content)} 字符")
    
    # 3. 修复导入语句 - 添加selectinload
    print("\n=== 3. 修复导入语句 ===")
    old_import = "from sqlalchemy import func, select, or_"
    new_import = "from sqlalchemy import func, select, or_\nfrom sqlalchemy.orm import selectinload"
    if old_import in content:
        content = content.replace(old_import, new_import)
        print("已添加 selectinload 导入")
    else:
        print("未找到导入语句")
    
    # 4. 修复订单列表查询 - 添加selectinload
    print("\n=== 4. 修复订单列表查询 ===")
    old_query = "query = select(B2BOrder)"
    new_query = "query = select(B2BOrder).options(selectinload(B2BOrder.agent))"
    if old_query in content:
        content = content.replace(old_query, new_query)
        print("已修复订单列表查询")
    else:
        print("未找到订单列表查询")
    
    # 5. 修复订单详情函数 - 使用selectinload查询
    print("\n=== 5. 修复订单详情函数 ===")
    old_get_order = '''    order = await db.get(B2BOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return _order_to_response(order)'''
    new_get_order = '''    result = await db.execute(
        select(B2BOrder).options(selectinload(B2BOrder.agent)).where(B2BOrder.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return _order_to_response(order)'''
    if old_get_order in content:
        content = content.replace(old_get_order, new_get_order)
        print("已修复订单详情函数")
    else:
        print("未找到订单详情函数")
    
    # 6. 修复订单状态更新函数 - refresh时加载agent
    print("\n=== 6. 修复订单状态更新函数 ===")
    old_refresh = "    await db.commit()\n    await db.refresh(order)"
    new_refresh = "    await db.commit()\n    await db.refresh(order, ['agent'])"
    if old_refresh in content:
        content = content.replace(old_refresh, new_refresh)
        print("已修复订单状态更新函数")
    else:
        print("未找到订单状态更新函数")
    
    # 7. 写回文件
    print("\n=== 7. 写回文件 ===")
    # 使用临时文件写入
    stdin, stdout, stderr = ssh.exec_command(f"cat > /opt/nuotao/backend/app/api/v1/endpoints/b2b_admin.py << 'ENDOFFILE'\n{content}\nENDOFFILE")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 8. 验证文件
    print("\n=== 8. 验证文件 ===")
    stdin, stdout, stderr = ssh.exec_command("grep -n 'selectinload' /opt/nuotao/backend/app/api/v1/endpoints/b2b_admin.py")
    print(stdout.read().decode())
    
    # 9. 重启后端服务
    print("\n=== 9. 重启后端服务 ===")
    stdin, stdout, stderr = ssh.exec_command("systemctl restart nuotao-backend && sleep 2 && systemctl status nuotao-backend --no-pager | head -10")
    print(stdout.read().decode())
    
    # 10. 测试API
    print("\n=== 10. 测试B2B订单API ===")
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3ODkwMzY1NDYsInN1YiI6ImM2ZmU2YjE4LTk4NGQtNDE4NC04MDk1LWY2OGE4NmVkN2QxZiIsInR5cGUiOiJhY2Nlc3MiLCJpYXQiOjE3ODg5NTAxNDYsInJvbGUiOiJhZG1pbiIsInVzZXJuYW1lIjoiYWRtaW4iLCJlbWFpbCI6ImFkbWluQG51b3Rhby5jb20ifQ.yMgcFVqX8lMKF2ax-OpIYOELFgx6CRH-cx7EgXI4mPo"
    stdin, stdout, stderr = ssh.exec_command(f"""
curl -s -w "\\nHTTP Status: %{{http_code}}\\n" \\
  -H "Authorization: Bearer {token}" \\
  "http://127.0.0.1:8000/api/v1/admin/b2b/orders?page=1&page_size=5" | head -50
""")
    print(stdout.read().decode())
    
    print("\n=== 修复完成！ ===")
    
except Exception as e:
    print(f"错误: {e}")
finally:
    ssh.close()
    print("\nSSH连接已关闭")
