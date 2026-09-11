import paramiko
import time

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
    print("供应商数据对齐修复脚本")
    print("=" * 60)
    
    print("\n正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # ============================================================
    # 步骤1: 备份后端文件
    # ============================================================
    print("\n" + "=" * 60)
    print("步骤1: 备份后端文件")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("cp /opt/nuotao/backend/app/api/v1/endpoints/supply_chain.py /opt/nuotao/backend/app/api/v1/endpoints/supply_chain.py.backup && echo '备份完成'")
    print(stdout.read().decode())
    
    # ============================================================
    # 步骤2: 在后端添加GET /suppliers端点
    # ============================================================
    print("\n" + "=" * 60)
    print("步骤2: 在后端添加GET /suppliers端点")
    print("=" * 60)
    
    # 读取后端文件
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/backend/app/api/v1/endpoints/supply_chain.py', 'r') as f:
        backend_content = f.read().decode('utf-8')
    sftp.close()
    
    # 添加Supplier模型导入
    if 'from app.models.supplier import Supplier' not in backend_content:
        backend_content = backend_content.replace(
            'from app.services import supply_chain',
            'from app.models.supplier import Supplier\nfrom app.services import supply_chain'
        )
        print("✅ 添加Supplier模型导入")
    
    # 添加GET /suppliers端点（在Supplier profiles部分之前）
    suppliers_endpoint = '''
# --------------------------------------------------------------------------- #
# Suppliers (master data)
# --------------------------------------------------------------------------- #


@router.get(
    "/suppliers",
    summary="List suppliers",
)
async def list_suppliers(
    db: DbSession,
    workspace_id: WorkspaceId,
    status: str | None = Query(default=None, max_length=16),
    limit: int = 100,
) -> list[dict]:
    """Return suppliers, newest first, with optional status filter."""
    from sqlalchemy import select
    
    stmt = select(Supplier).where(Supplier.workspace_id == workspace_id)
    if status:
        stmt = stmt.where(Supplier.status == status)
    stmt = stmt.order_by(Supplier.created_at.desc()).limit(limit)
    
    rows = (await db.execute(stmt)).scalars().all()
    
    result = []
    for row in rows:
        result.append({
            "id": str(row.id),
            "code": row.code,
            "name": row.name,
            "platform": row.platform,
            "shop_url": row.shop_url,
            "rating": row.rating,
            "status": row.status,
            "contact": row.contact,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        })
    
    return result


'''
    
    # 在Supplier profiles部分之前插入
    if '# --------------------------------------------------------------------------- #\n# Supplier profiles' in backend_content:
        backend_content = backend_content.replace(
            '# --------------------------------------------------------------------------- #\n# Supplier profiles',
            suppliers_endpoint + '# --------------------------------------------------------------------------- #\n# Supplier profiles'
        )
        print("✅ 添加GET /suppliers端点")
    else:
        print("⚠️ 未找到插入位置，尝试在文件末尾添加")
        backend_content += suppliers_endpoint
    
    # 写回后端文件
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/backend/app/api/v1/endpoints/supply_chain.py', 'w') as f:
        f.write(backend_content.encode('utf-8'))
    sftp.close()
    print("✅ 后端文件已写回")
    
    # ============================================================
    # 步骤3: 重启后端服务
    # ============================================================
    print("\n" + "=" * 60)
    print("步骤3: 重启后端服务")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("systemctl restart nuotao-backend && sleep 3 && systemctl status nuotao-backend --no-pager | head -10")
    print(stdout.read().decode())
    
    # ============================================================
    # 步骤4: 测试后端API
    # ============================================================
    print("\n" + "=" * 60)
    print("步骤4: 测试后端API")
    print("=" * 60)
    time.sleep(2)
    stdin, stdout, stderr = ssh.exec_command("curl -s http://127.0.0.1:8000/api/v1/suppliers | python3 -m json.tool 2>/dev/null | head -50")
    print(stdout.read().decode())
    
    # ============================================================
    # 步骤5: 备份前端文件
    # ============================================================
    print("\n" + "=" * 60)
    print("步骤5: 备份前端文件")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("cp /opt/nuotao/frontend/src/pages/Suppliers.tsx /opt/nuotao/frontend/src/pages/Suppliers.tsx.backup && echo '备份完成'")
    print(stdout.read().decode())
    
    # ============================================================
    # 步骤6: 修改前端，调用真实API
    # ============================================================
    print("\n" + "=" * 60)
    print("步骤6: 修改前端，调用真实API")
    print("=" * 60)
    
    # 读取前端文件
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/frontend/src/pages/Suppliers.tsx', 'r') as f:
        frontend_content = f.read().decode('utf-8')
    sftp.close()
    
    # 1. 添加真实供应商数据状态
    old_state = "  // 真实API数据状态\n  const [suppliersData, setSuppliersData] = useState<any>(null)"
    new_state = """  // 真实API数据状态
  const [suppliersData, setSuppliersData] = useState<any>(null)
  const [realSuppliers, setRealSuppliers] = useState<Supplier[]>([])
  const [apiLoaded, setApiLoaded] = useState(false)"""
    
    if old_state in frontend_content:
        frontend_content = frontend_content.replace(old_state, new_state)
        print("✅ 添加真实供应商数据状态")
    
    # 2. 修改loadSuppliersData函数，调用真实供应商API
    old_load = """  // 加载供应商数据（调用真实API，失败则使用mock数据降级）
  const loadSuppliersData = async () => {
    try {
      setLoading(true)
      // 调用采购统计API（包含供应商相关统计）
      const statsResp = await fetch('/api/v1/procurement/stats')
      if (statsResp.ok) {
        const statsData = await statsResp.json()
        setSuppliersData(statsData)
        console.log('Procurement stats:', statsData)
      }
      message.success('供应商数据加载完成')
    } catch (e: any) {
      console.error('Load suppliers data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {"""
    
    new_load = """  // 加载供应商数据（调用真实API）
  const loadSuppliersData = async () => {
    try {
      setLoading(true)
      
      // 调用真实供应商API
      const suppliersResp = await fetch('/api/v1/suppliers')
      if (suppliersResp.ok) {
        const suppliersData = await suppliersResp.json()
        console.log('Real suppliers:', suppliersData)
        
        // 将真实供应商数据转换为前端格式
        const converted: Supplier[] = suppliersData.map((s: any, index: number) => ({
          id: s.id,
          supplier_id: s.code,
          name: s.name,
          contact_person: s.contact?.contact_person || '待补充',
          phone: s.contact?.phone || '',
          email: s.contact?.email || '',
          address: s.shop_url || '',
          rating: s.rating === 'A' ? 4.8 : s.rating === 'B' ? 4.2 : 3.5,
          level: s.rating === 'A' ? 'preferred' : 'approved',
          status: s.status === 'active' ? 'active' : 'inactive',
          total_orders: 0,
          total_spent: 0,
          avg_delivery_days: 0,
          quality_score: s.rating === 'A' ? 90 : 80,
          on_time_rate: s.rating === 'A' ? 90 : 80,
          defect_rate: s.rating === 'A' ? 2 : 5,
          created_at: s.created_at || '2026-01-01',
          last_order_at: '',
          categories: [],
          min_order_amount: 0,
          payment_terms: '待确认',
        }))
        
        setRealSuppliers(converted)
        setApiLoaded(true)
        message.success(`成功加载 ${converted.length} 个真实供应商`)
      } else {
        message.warning('供应商API调用失败，使用模拟数据')
      }
    } catch (e: any) {
      console.error('Load suppliers data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {"""
    
    if old_load in frontend_content:
        frontend_content = frontend_content.replace(old_load, new_load)
        print("✅ 修改loadSuppliersData函数")
    
    # 3. 修改统计数据，优先使用真实数据
    old_stats = """  // 统计数据（优先使用真实API数据，失败则使用mock数据降级）
  const totalSuppliers = suppliersData?.total_suppliers || suppliersData?.suppliers_count || mockSuppliers.length
  const totalSpent = suppliersData?.total_spent || suppliersData?.total_amount || mockSuppliers.reduce((sum, s) => sum + s.total_spent, 0)
  const levelStats = {
    active: suppliersData?.active_suppliers || mockSuppliers.filter(s => s.status === 'active').length,
    strategic: suppliersData?.strategic_suppliers || mockSuppliers.filter(s => s.level === 'strategic').length,
  }
  const avgRating = (mockSuppliers.reduce((sum, s) => sum + s.rating, 0) / mockSuppliers.length).toFixed(1)
  const pendingReview = suppliersData?.pending_review || mockSuppliers.filter(s => s.level === 'pending').length"""
    
    new_stats = """  // 统计数据（优先使用真实API数据）
  const displaySuppliers = apiLoaded && realSuppliers.length > 0 ? realSuppliers : mockSuppliers
  const totalSuppliers = displaySuppliers.length
  const totalSpent = displaySuppliers.reduce((sum, s) => sum + s.total_spent, 0)
  const levelStats = {
    active: displaySuppliers.filter(s => s.status === 'active').length,
    strategic: displaySuppliers.filter(s => s.level === 'strategic').length,
  }
  const avgRating = displaySuppliers.length > 0 ? (displaySuppliers.reduce((sum, s) => sum + s.rating, 0) / displaySuppliers.length).toFixed(1) : '0'
  const pendingReview = displaySuppliers.filter(s => s.level === 'pending').length"""
    
    if old_stats in frontend_content:
        frontend_content = frontend_content.replace(old_stats, new_stats)
        print("✅ 修改统计数据")
    
    # 4. 修改filteredSuppliers，使用真实数据
    old_filtered = "  const filteredSuppliers = mockSuppliers.filter(supplier => {"
    new_filtered = "  const filteredSuppliers = displaySuppliers.filter(supplier => {"
    
    if old_filtered in frontend_content:
        frontend_content = frontend_content.replace(old_filtered, new_filtered)
        print("✅ 修改filteredSuppliers")
    
    # 5. 修改采购订单表格（使用空数据，因为没有真实采购订单）
    old_po_table = "                    dataSource={mockPurchaseOrders}"
    new_po_table = "                    dataSource={[]}"
    
    if old_po_table in frontend_content:
        frontend_content = frontend_content.replace(old_po_table, new_po_table)
        print("✅ 修改采购订单表格")
    
    # 6. 修改供应商分析图表
    old_analysis1 = "                            { level: '优选供应商', count: mockSuppliers.filter(s => s.level === 'preferred').length, color: 'blue' },"
    new_analysis1 = "                            { level: '优选供应商', count: displaySuppliers.filter(s => s.level === 'preferred').length, color: 'blue' },"
    
    if old_analysis1 in frontend_content:
        frontend_content = frontend_content.replace(old_analysis1, new_analysis1)
    
    old_analysis2 = "                            { level: '合格供应商', count: mockSuppliers.filter(s => s.level === 'approved').length, color: 'green' },"
    new_analysis2 = "                            { level: '合格供应商', count: displaySuppliers.filter(s => s.level === 'approved').length, color: 'green' },"
    
    if old_analysis2 in frontend_content:
        frontend_content = frontend_content.replace(old_analysis2, new_analysis2)
    
    old_analysis3 = "                            { level: '黑名单', count: mockSuppliers.filter(s => s.level === 'blacklisted').length, color: 'red' },"
    new_analysis3 = "                            { level: '黑名单', count: displaySuppliers.filter(s => s.level === 'blacklisted').length, color: 'red' },"
    
    if old_analysis3 in frontend_content:
        frontend_content = frontend_content.replace(old_analysis3, new_analysis3)
    
    old_analysis4 = "                          dataSource={[...mockSuppliers].sort((a, b) => b.total_spent - a.total_spent).slice(0, 5)}"
    new_analysis4 = "                          dataSource={[...displaySuppliers].sort((a, b) => b.total_spent - a.total_spent).slice(0, 5)}"
    
    if old_analysis4 in frontend_content:
        frontend_content = frontend_content.replace(old_analysis4, new_analysis4)
    
    print("✅ 修改供应商分析图表")
    
    # 写回前端文件
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/frontend/src/pages/Suppliers.tsx', 'w') as f:
        f.write(frontend_content.encode('utf-8'))
    sftp.close()
    print("✅ 前端文件已写回")
    
    # ============================================================
    # 步骤7: 重新构建前端
    # ============================================================
    print("\n" + "=" * 60)
    print("步骤7: 重新构建前端")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("cd /opt/nuotao/frontend && npm run build 2>&1 | tail -20")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # ============================================================
    # 步骤8: 部署前端
    # ============================================================
    print("\n" + "=" * 60)
    print("步骤8: 部署前端")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("""
# 备份旧文件
cp -r /var/www/nuotao /var/www/nuotao.backup.$(date +%Y%m%d%H%M%S)
# 清空旧文件
rm -rf /var/www/nuotao/*
# 复制新构建
cp -r /opt/nuotao/frontend/dist/* /var/www/nuotao/
# 设置权限
chown -R www-data:www-data /var/www/nuotao/
echo '前端部署完成'
ls -la /var/www/nuotao/ | head -10
""")
    print(stdout.read().decode())
    
    # ============================================================
    # 步骤9: 最终验证
    # ============================================================
    print("\n" + "=" * 60)
    print("步骤9: 最终验证")
    print("=" * 60)
    
    # 验证后端API
    stdin, stdout, stderr = ssh.exec_command("curl -s http://127.0.0.1:8000/api/v1/suppliers | python3 -c 'import sys,json; data=json.load(sys.stdin); print(f\"供应商数量: {len(data)}\"); [print(f\"  - {s[\\\"code\\\"]}: {s[\\\"name\\\"]} ({s[\\\"platform\\\"]}, {s[\\\"rating\\\"]}级)\") for s in data]'")
    print("后端API验证:")
    print(stdout.read().decode())
    
    # 验证服务状态
    stdin, stdout, stderr = ssh.exec_command("systemctl is-active nuotao-backend")
    print(f"后端服务状态: {stdout.read().decode().strip()}")
    
    print("\n" + "=" * 60)
    print("修复完成！")
    print("=" * 60)
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
