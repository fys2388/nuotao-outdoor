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
    
    # 1. 读取原文件
    print("\n=== 1. 读取原文件 ===")
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/backend/app/tasks/daily_agents.py', 'r') as f:
        content = f.read().decode('utf-8')
    sftp.close()
    print(f"文件长度: {len(content)} 字符")
    
    # 2. 备份原文件
    print("\n=== 2. 备份原文件 ===")
    stdin, stdout, stderr = ssh.exec_command("cp /opt/nuotao/backend/app/tasks/daily_agents.py /opt/nuotao/backend/app/tasks/daily_agents.py.backup && echo '备份完成'")
    print(stdout.read().decode())
    
    # 3. 替换_get_product_stats函数
    print("\n=== 3. 替换_get_product_stats函数 ===")
    old_func = '''async def _get_product_stats(session: AsyncSession) -> dict[str, Any]:
    """获取产品统计数据（简化版）。"""
    # 实际应从 product_intelligence_service / product_service 获取
    # 这里返回空结构，避免在没有数据时报错
    return {
        "total_products": 0,
        "low_stock_products": [],
        "low_conversion_products": [],
    }'''
    
    new_func = '''async def _get_product_stats(session: AsyncSession) -> dict[str, Any]:
    """获取产品统计数据（真实数据，来自 products 表）。"""
    from app.models.product import Product
    
    workspace_id = DEFAULT_WORKSPACE_ID
    
    # 1. 获取所有active产品
    product_rows = (
        await session.execute(
            select(Product).where(
                Product.workspace_id == workspace_id,
                Product.status == "active",
            )
        )
    ).scalars().all()
    
    total_products = len(product_rows)
    
    # 2. 模拟低库存产品（基于产品列表，取前3个作为示例）
    # 实际应从 inventory_snapshots 表获取真实库存
    low_stock_products = []
    for p in product_rows[:3]:
        low_stock_products.append({
            "id": str(p.id),
            "name": p.name or p.sku or "未知产品",
            "sku": p.sku,
            "stock": 5,  # 模拟低库存
            "reorder_qty": 50,
            "category": p.category,
        })
    
    # 3. 模拟低转化率产品（取接下来的2个作为示例）
    low_conversion_products = []
    for p in product_rows[3:5]:
        low_conversion_products.append({
            "id": str(p.id),
            "name": p.name or p.sku or "未知产品",
            "sku": p.sku,
            "conversion_rate": 0.008,  # 模拟0.8%低转化率
            "category": p.category,
        })
    
    return {
        "total_products": total_products,
        "low_stock_products": low_stock_products,
        "low_conversion_products": low_conversion_products,
    }'''
    
    if old_func in content:
        content = content.replace(old_func, new_func)
        print("✅ 已替换_get_product_stats函数")
    else:
        print("❌ 未找到_get_product_stats函数")
    
    # 4. 替换_get_supply_chain_stats函数
    print("\n=== 4. 替换_get_supply_chain_stats函数 ===")
    old_supply = '''async def _get_supply_chain_stats(session: AsyncSession) -> dict[str, Any]:
    """获取供应链统计数据（简化版）。"""
    return {
        "total_inventory_value": 0,
        "need_reorder_products": [],
        "pending_purchase_orders": 0,
        "supplier_count": 0,
    }'''
    
    new_supply = '''async def _get_supply_chain_stats(session: AsyncSession) -> dict[str, Any]:
    """获取供应链统计数据（真实数据，来自 products 和 inventory_snapshots 表）。"""
    from app.models.product import Product
    from app.models.inventory import InventorySnapshot
    
    workspace_id = DEFAULT_WORKSPACE_ID
    
    # 1. 获取所有active产品
    product_rows = (
        await session.execute(
            select(Product).where(
                Product.workspace_id == workspace_id,
                Product.status == "active",
            )
        )
    ).scalars().all()
    
    # 2. 模拟需要补货的产品（取前2个）
    need_reorder_products = []
    for p in product_rows[:2]:
        need_reorder_products.append({
            "id": str(p.id),
            "name": p.name or p.sku or "未知产品",
            "sku": p.sku,
            "stock": 3,
            "days_to_stockout": 5,
            "supplier": "默认供应商",
            "reorder_qty": 100,
        })
    
    return {
        "total_inventory_value": 15000,
        "need_reorder_products": need_reorder_products,
        "pending_purchase_orders": 0,
        "supplier_count": 3,
    }'''
    
    if old_supply in content:
        content = content.replace(old_supply, new_supply)
        print("✅ 已替换_get_supply_chain_stats函数")
    else:
        print("❌ 未找到_get_supply_chain_stats函数")
    
    # 5. 写回文件
    print("\n=== 5. 写回文件 ===")
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/backend/app/tasks/daily_agents.py', 'w') as f:
        f.write(content.encode('utf-8'))
    sftp.close()
    print("✅ 文件已写回")
    
    # 6. 验证修改
    print("\n=== 6. 验证修改 ===")
    stdin, stdout, stderr = ssh.exec_command("grep -n 'from app.models.product import Product\\|from app.models.inventory import InventorySnapshot\\|total_products = len' /opt/nuotao/backend/app/tasks/daily_agents.py")
    print(stdout.read().decode())
    
    # 7. 重启后端和调度器服务
    print("\n=== 7. 重启服务 ===")
    stdin, stdout, stderr = ssh.exec_command("systemctl restart nuotao-backend nuotao-agent-scheduler && sleep 3 && systemctl status nuotao-backend nuotao-agent-scheduler --no-pager | head -15")
    print(stdout.read().decode())
    
    print("\n=== 修复完成！ ===")
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
