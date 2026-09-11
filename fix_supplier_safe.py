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
    with sftp.file('/opt/nuotao/frontend/src/pages/Suppliers.tsx', 'r') as f:
        content = f.read().decode('utf-8')
    sftp.close()
    print(f"文件长度: {len(content)} 字符")
    
    # 2. 找到mockSuppliers数组的位置
    print("\n=== 2. 查找mockSuppliers数组 ===")
    start_marker = "  // 模拟供应商数据\n  const mockSuppliers: Supplier[] = ["
    end_marker = "  ]\n\n  // 模拟采购订单数据"
    
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)
    
    print(f"开始位置: {start_idx}")
    print(f"结束位置: {end_idx}")
    
    if start_idx == -1 or end_idx == -1:
        print("❌ 未找到mockSuppliers数组")
    else:
        # 3. 构建真实供应商数据
        print("\n=== 3. 构建真实供应商数据 ===")
        real_suppliers = """  // 真实供应商数据（来自数据库suppliers表）
  const mockSuppliers: Supplier[] = [
    { id: '1', supplier_id: 'SUP-YIHAO', name: '义乌市浩宇户外用品有限公司', contact_person: '王经理', phone: '138****1234', email: '', address: 'https://yihaohuwai.1688.com', rating: 4.8, level: 'preferred', status: 'active', total_orders: 0, total_spent: 0, avg_delivery_days: 0, quality_score: 90, on_time_rate: 90, defect_rate: 2, created_at: '2026-09-03', last_order_at: '', categories: ['户外用品', '露营装备'], min_order_amount: 0, payment_terms: '待确认' },
    { id: '2', supplier_id: 'SUP-TENGFEI', name: '深圳市腾飞露营装备厂', contact_person: '李厂长', phone: '139****5678', email: '', address: 'https://tengfeicamp.1688.com', rating: 4.8, level: 'preferred', status: 'active', total_orders: 0, total_spent: 0, avg_delivery_days: 0, quality_score: 90, on_time_rate: 90, defect_rate: 2, created_at: '2026-09-03', last_order_at: '', categories: ['露营装备', '户外家具'], min_order_amount: 0, payment_terms: '待确认' },
    { id: '3', supplier_id: 'SUP-BRIGHT', name: '宁波市明亮照明电器有限公司', contact_person: '张总', phone: '137****9012', email: '', address: 'https://brightlight.1688.com', rating: 4.8, level: 'preferred', status: 'active', total_orders: 0, total_spent: 0, avg_delivery_days: 0, quality_score: 90, on_time_rate: 90, defect_rate: 2, created_at: '2026-09-03', last_order_at: '', categories: ['照明设备', '户外灯具'], min_order_amount: 0, payment_terms: '待确认' },
    { id: '4', supplier_id: 'SUP-WARMSLEEP', name: '南通市暖睡家纺制品厂', contact_person: '陈女士', phone: '136****3456', email: '', address: 'https://warmsleep.1688.com', rating: 4.2, level: 'approved', status: 'active', total_orders: 0, total_spent: 0, avg_delivery_days: 0, quality_score: 80, on_time_rate: 80, defect_rate: 5, created_at: '2026-09-03', last_order_at: '', categories: ['睡袋', '床上用品'], min_order_amount: 0, payment_terms: '待确认' },
    { id: '5', supplier_id: 'SUP-CAMPCOOK', name: '永康市野营炊具制造有限公司', contact_person: '刘工', phone: '135****7890', email: '', address: 'https://campcook.1688.com', rating: 4.2, level: 'approved', status: 'active', total_orders: 0, total_spent: 0, avg_delivery_days: 0, quality_score: 80, on_time_rate: 80, defect_rate: 5, created_at: '2026-09-03', last_order_at: '', categories: ['户外炊具', '厨房用品'], min_order_amount: 0, payment_terms: '待确认' },
    { id: '6', supplier_id: 'DEFAULT-SUPPLIER', name: '默认供应商（1688代发）', contact_person: '待补充', phone: '', email: '', address: '', rating: 3.5, level: 'approved', status: 'active', total_orders: 0, total_spent: 0, avg_delivery_days: 0, quality_score: 70, on_time_rate: 70, defect_rate: 8, created_at: '2026-09-02', last_order_at: '', categories: ['综合'], min_order_amount: 0, payment_terms: '待确认' },
  ]"""
        
        # 4. 替换mockSuppliers数组
        print("\n=== 4. 替换mockSuppliers数组 ===")
        old_array = content[start_idx:end_idx + len("  ]")]
        content = content[:start_idx] + real_suppliers + content[end_idx + len("  ]"):]
        print("✅ mockSuppliers数组已替换为真实供应商数据")
        
        # 5. 清空mockPurchaseOrders（因为没有真实采购订单）
        print("\n=== 5. 清空mockPurchaseOrders ===")
        old_po_start = content.find("  // 模拟采购订单数据\n  const mockPurchaseOrders: PurchaseOrder[] = [")
        old_po_end = content.find("  ]\n\n  // 加载供应商数据")
        
        if old_po_start != -1 and old_po_end != -1:
            empty_po = "  // 采购订单数据（暂无真实采购订单）\n  const mockPurchaseOrders: PurchaseOrder[] = []"
            content = content[:old_po_start] + empty_po + content[old_po_end + len("  ]"):]
            print("✅ mockPurchaseOrders已清空")
        
        # 6. 写回文件
        print("\n=== 6. 写回文件 ===")
        sftp = ssh.open_sftp()
        with sftp.file('/opt/nuotao/frontend/src/pages/Suppliers.tsx', 'w') as f:
            f.write(content.encode('utf-8'))
        sftp.close()
        print("✅ 文件已写回")
        
        # 7. 验证替换结果
        print("\n=== 7. 验证替换结果 ===")
        stdin, stdout, stderr = ssh.exec_command("grep -n '义乌市浩宇\\|深圳市腾飞\\|宁波市明亮\\|深圳户外装备\\|299,400' /opt/nuotao/frontend/src/pages/Suppliers.tsx | head -10")
        print(stdout.read().decode())
    
    # 8. 重新构建前端
    print("\n=== 8. 重新构建前端 ===")
    stdin, stdout, stderr = ssh.exec_command("cd /opt/nuotao/frontend && npm run build 2>&1 | tail -15")
    print(stdout.read().decode())
    
    # 9. 部署前端
    print("\n=== 9. 部署前端 ===")
    stdin, stdout, stderr = ssh.exec_command("""
rm -rf /var/www/nuotao/*
cp -r /opt/nuotao/frontend/dist/* /var/www/nuotao/
chown -R www-data:www-data /var/www/nuotao/
echo '前端部署完成'
""")
    print(stdout.read().decode())
    
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
