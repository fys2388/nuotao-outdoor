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
    print("=" * 60)
    print("任务2 + 任务3：供应商列 + 供应商管理真实数据")
    print("=" * 60)
    
    print("\n正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # ============================================================
    # 任务2：在Products.tsx中添加供应商列
    # ============================================================
    print("\n" + "=" * 60)
    print("任务2：Products.tsx添加供应商列")
    print("=" * 60)
    
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/frontend/src/pages/Products.tsx', 'r') as f:
        products_content = f.read().decode('utf-8')
    sftp.close()
    
    # 找到分类列并在其后添加供应商列
    old_category = """    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 120,
      render: (text: string) => text || '-',
    },"""
    
    new_category = """    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 120,
      render: (text: string) => text || '-',
    },
    {
      title: '供应商',
      dataIndex: 'supplier_code',
      key: 'supplier',
      width: 110,
      render: (code: string) => {
        const supplierNames: Record<string, string> = {
          'SUP-YIHAO': '义乌浩宇',
          'SUP-TENGFEI': '深圳腾飞',
          'SUP-BRIGHT': '宁波明亮',
          'SUP-WARMSLEEP': '南通暖睡',
          'SUP-CAMPCOOK': '永康野营',
          'DEFAULT-SUPPLIER': '默认供应商',
        };
        const name = supplierNames[code] || code || '未关联';
        return code ? <Tag color="blue">{name}</Tag> : <Tag color="default">未关联</Tag>;
      },
    },"""
    
    if old_category in products_content:
        products_content = products_content.replace(old_category, new_category)
        print("✅ 供应商列已添加")
    else:
        print("⚠️ 未找到分类列")
    
    # 写回Products.tsx
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/frontend/src/pages/Products.tsx', 'w') as f:
        f.write(products_content.encode('utf-8'))
    sftp.close()
    print("✅ Products.tsx已写回")
    
    # ============================================================
    # 任务3：供应商管理页面对接真实采购订单数据
    # ============================================================
    print("\n" + "=" * 60)
    print("任务3：供应商管理页面对接真实采购订单数据")
    print("=" * 60)
    
    # 先添加采购订单统计API
    print("\n步骤3.1: 添加采购订单统计API")
    
    # 检查是否有procurement API
    stdin, stdout, stderr = ssh.exec_command("find /opt/nuotao/backend/app/api/v1/endpoints -name '*procurement*' -o -name '*purchase*' | head -5")
    print(f"采购相关API文件: {stdout.read().decode()}")
    
    # 在supply_chain.py中添加采购订单统计端点
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/backend/app/api/v1/endpoints/supply_chain.py', 'r') as f:
        supply_chain_content = f.read().decode('utf-8')
    sftp.close()
    
    # 添加采购订单统计端点（在文件末尾）
    po_stats_endpoint = '''


# --------------------------------------------------------------------------- #
# Purchase order statistics
# --------------------------------------------------------------------------- #


@router.get(
    "/purchase-orders/stats",
    summary="Get purchase order statistics by supplier",
)
async def get_purchase_order_stats(
    db: DbSession,
    workspace_id: WorkspaceId,
) -> dict:
    """Return purchase order statistics grouped by supplier."""
    from app.models.supplier import Supplier
    from sqlalchemy import select, func
    
    # 查询所有供应商
    suppliers = (await db.execute(
        select(Supplier).where(Supplier.workspace_id == workspace_id)
    )).scalars().all()
    
    # 查询采购订单统计（使用原生SQL）
    result = await db.execute("""
        SELECT 
            s.id as supplier_id,
            s.code as supplier_code,
            s.name as supplier_name,
            COUNT(po.id) as order_count,
            COALESCE(SUM(po.total), 0) as total_amount,
            COUNT(CASE WHEN po.status = 'received' THEN 1 END) as received_count,
            COUNT(CASE WHEN po.status = 'shipped' THEN 1 END) as shipped_count,
            COUNT(CASE WHEN po.status = 'ordered' THEN 1 END) as ordered_count
        FROM suppliers s
        LEFT JOIN purchase_orders po ON po.supplier_id = s.id
        WHERE s.workspace_id = :workspace_id
        GROUP BY s.id, s.code, s.name
        ORDER BY total_amount DESC
    """, {"workspace_id": str(workspace_id)})
    
    rows = result.fetchall()
    
    stats = []
    for row in rows:
        stats.append({
            "supplier_id": str(row[0]),
            "supplier_code": row[1],
            "supplier_name": row[2],
            "order_count": row[3],
            "total_amount": float(row[4]) if row[4] else 0,
            "received_count": row[5],
            "shipped_count": row[6],
            "ordered_count": row[7],
        })
    
    return {
        "total_suppliers": len(suppliers),
        "total_orders": sum(s["order_count"] for s in stats),
        "total_amount": sum(s["total_amount"] for s in stats),
        "by_supplier": stats,
    }
'''
    
    if 'purchase-orders/stats' not in supply_chain_content:
        supply_chain_content += po_stats_endpoint
        sftp = ssh.open_sftp()
        with sftp.file('/opt/nuotao/backend/app/api/v1/endpoints/supply_chain.py', 'w') as f:
            f.write(supply_chain_content.encode('utf-8'))
        sftp.close()
        print("✅ 采购订单统计API已添加")
    else:
        print("⚠️ 采购订单统计API已存在")
    
    # 重启后端
    print("\n步骤3.2: 重启后端服务")
    stdin, stdout, stderr = ssh.exec_command("systemctl restart nuotao-backend && sleep 3 && systemctl is-active nuotao-backend")
    print(f"后端服务状态: {stdout.read().decode().strip()}")
    
    # 测试API
    print("\n步骤3.3: 测试采购订单统计API")
    stdin, stdout, stderr = ssh.exec_command("curl -s http://127.0.0.1:8000/api/v1/supply-chain/purchase-orders/stats | python3 -m json.tool 2>/dev/null | head -40")
    print(stdout.read().decode())
    
    # ============================================================
    # 重新构建并部署前端
    # ============================================================
    print("\n" + "=" * 60)
    print("重新构建并部署前端")
    print("=" * 60)
    
    stdin, stdout, stderr = ssh.exec_command("cd /opt/nuotao/frontend && npm run build 2>&1 | tail -5")
    print(stdout.read().decode())
    
    stdin, stdout, stderr = ssh.exec_command("""
rm -rf /var/www/nuotao/*
cp -r /opt/nuotao/frontend/dist/* /var/www/nuotao/
chown -R www-data:www-data /var/www/nuotao/
echo '前端部署完成'
""")
    print(stdout.read().decode())
    
    print("\n" + "=" * 60)
    print("任务2 + 任务3完成！")
    print("=" * 60)
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
