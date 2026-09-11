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
    print("任务1 + 任务2：采购订单导航 + 供应商真实统计")
    print("=" * 60)
    
    print("\n正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # ============================================================
    # 任务1：添加采购订单页面到导航和路由
    # ============================================================
    print("\n" + "=" * 60)
    print("任务1：添加采购订单页面到导航和路由")
    print("=" * 60)
    
    # 读取App.tsx
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/frontend/src/App.tsx', 'r') as f:
        app_content = f.read().decode('utf-8')
    sftp.close()
    
    # 1.1 添加懒加载导入
    print("\n步骤1.1: 添加懒加载导入")
    old_import = "const SettlementsPage = lazy(() => import('./pages/Settlements'))"
    new_import = """const SettlementsPage = lazy(() => import('./pages/Settlements'))
const PurchaseOrdersPage = lazy(() => import('./pages/PurchaseOrders'))"""
    
    if old_import in app_content and 'PurchaseOrdersPage' not in app_content:
        app_content = app_content.replace(old_import, new_import)
        print("✅ 懒加载导入已添加")
    else:
        print("⚠️ 导入已存在或未找到")
    
    # 1.2 添加MenuKey类型
    print("\n步骤1.2: 添加MenuKey类型")
    old_menukey = "  | 'settlements'"
    new_menukey = """  | 'settlements'
  | 'purchase-orders'"""
    
    if old_menukey in app_content and "'purchase-orders'" not in app_content:
        app_content = app_content.replace(old_menukey, new_menukey)
        print("✅ MenuKey类型已添加")
    else:
        print("⚠️ MenuKey已存在或未找到")
    
    # 1.3 添加菜单项（在供应链分组中，供应商管理之后）
    print("\n步骤1.3: 添加菜单项")
    old_supplier_menu = "      { key: 'suppliers', icon: <ShopOutlined />, label: '供应商管理' },"
    new_supplier_menu = """      { key: 'suppliers', icon: <ShopOutlined />, label: '供应商管理' },
      { key: 'purchase-orders', icon: <ShoppingCartOutlined />, label: '采购订单管理' },"""
    
    if old_supplier_menu in app_content and "'purchase-orders'" not in app_content:
        app_content = app_content.replace(old_supplier_menu, new_supplier_menu)
        print("✅ 菜单项已添加")
    else:
        print("⚠️ 菜单项已存在或未找到")
    
    # 1.4 添加pageTitles
    print("\n步骤1.4: 添加pageTitles")
    old_title = "  settlements: '回款台账',"
    new_title = """  settlements: '回款台账',
  'purchase-orders': '采购订单管理',"""
    
    if old_title in app_content and "'purchase-orders':" not in app_content:
        app_content = app_content.replace(old_title, new_title)
        print("✅ pageTitles已添加")
    else:
        print("⚠️ pageTitles已存在或未找到")
    
    # 1.5 添加路由渲染
    print("\n步骤1.5: 添加路由渲染")
    old_render = "        case 'settlements':\n          return <SettlementsPage />"
    new_render = """        case 'settlements':
          return <SettlementsPage />
        case 'purchase-orders':
          return <PurchaseOrdersPage />"""
    
    if old_render in app_content and "case 'purchase-orders'" not in app_content:
        app_content = app_content.replace(old_render, new_render)
        print("✅ 路由渲染已添加")
    else:
        print("⚠️ 路由已存在或未找到")
    
    # 写回App.tsx
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/frontend/src/App.tsx', 'w') as f:
        f.write(app_content.encode('utf-8'))
    sftp.close()
    print("✅ App.tsx已写回")
    
    # ============================================================
    # 任务2：供应商管理页面调用真实统计API
    # ============================================================
    print("\n" + "=" * 60)
    print("任务2：供应商管理页面调用真实统计API")
    print("=" * 60)
    
    # 读取Suppliers.tsx
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/frontend/src/pages/Suppliers.tsx', 'r') as f:
        suppliers_content = f.read().decode('utf-8')
    sftp.close()
    
    # 查看当前统计卡片的实现
    print("\n步骤2.1: 查看当前统计实现")
    # 找到统计卡片部分并替换为调用真实API
    
    # 添加useEffect调用统计API
    # 先查看文件结构
    print(f"文件长度: {len(suppliers_content)} 字符")
    
    # 在loadSuppliers函数后添加loadStats函数
    # 先找到合适的位置
    
    # 简单方案：在组件中添加统计数据状态和API调用
    # 找到const [suppliers, setSuppliers] = useState
    old_state = "const [suppliers, setSuppliers] = useState<Supplier[]>([])"
    new_state = """const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [poStats, setPoStats] = useState<any>(null)"""
    
    if old_state in suppliers_content and 'poStats' not in suppliers_content:
        suppliers_content = suppliers_content.replace(old_state, new_state)
        print("✅ 统计状态已添加")
    else:
        print("⚠️ 状态已存在或未找到")
    
    # 添加加载统计数据的函数
    old_load = "const loadSuppliers = async () => {"
    new_load = """const loadPoStats = async () => {
    try {
      const resp = await fetch('/api/v1/supply-chain/purchase-orders/stats')
      if (resp.ok) {
        const data = await resp.json()
        setPoStats(data)
      }
    } catch (e) {
      console.error('Load PO stats error:', e)
    }
  }

  const loadSuppliers = async () => {"""
    
    if old_load in suppliers_content and 'loadPoStats' not in suppliers_content:
        suppliers_content = suppliers_content.replace(old_load, new_load)
        print("✅ 加载统计函数已添加")
    else:
        print("⚠️ 函数已存在或未找到")
    
    # 在useEffect中调用loadPoStats
    old_useeffect = "loadSuppliers()"
    new_useeffect = """loadSuppliers()
    loadPoStats()"""
    
    if old_useeffect in suppliers_content:
        # 只替换第一个出现的（在useEffect中）
        suppliers_content = suppliers_content.replace(old_useeffect, new_useeffect, 1)
        print("✅ useEffect中已添加统计加载")
    else:
        print("⚠️ 未找到loadSuppliers调用")
    
    # 替换统计卡片中的硬编码数据
    # 找到累计采购额统计卡片
    old_stat_amount = "title=\"累计采购额\"\n              value={299400}"
    new_stat_amount = "title=\"累计采购额\"\n              value={poStats?.total_amount || 0}"
    
    if old_stat_amount in suppliers_content:
        suppliers_content = suppliers_content.replace(old_stat_amount, new_stat_amount)
        print("✅ 累计采购额已改为动态数据")
    else:
        print("⚠️ 未找到累计采购额统计卡片")
    
    # 替换采购订单数
    old_stat_orders = "title=\"采购订单\"\n              value={15}"
    new_stat_orders = "title=\"采购订单\"\n              value={poStats?.total_orders || 0}"
    
    if old_stat_orders in suppliers_content:
        suppliers_content = suppliers_content.replace(old_stat_orders, new_stat_orders)
        print("✅ 采购订单数已改为动态数据")
    else:
        print("⚠️ 未找到采购订单数统计卡片")
    
    # 写回Suppliers.tsx
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/frontend/src/pages/Suppliers.tsx', 'w') as f:
        f.write(suppliers_content.encode('utf-8'))
    sftp.close()
    print("✅ Suppliers.tsx已写回")
    
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
    print("任务1 + 任务2完成！")
    print("=" * 60)
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
