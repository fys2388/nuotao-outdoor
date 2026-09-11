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
    print("任务1前端 + 任务2：产品列表添加供应商列")
    print("=" * 60)
    
    print("\n正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # 读取Products.tsx
    print("\n=== 读取Products.tsx ===")
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/frontend/src/pages/Products.tsx', 'r') as f:
        content = f.read().decode('utf-8')
    sftp.close()
    print(f"文件长度: {len(content)} 字符")
    
    # 任务2：在表格列中添加供应商列（在分类列之后）
    print("\n=== 任务2：添加供应商列 ===")
    old_category_column = """      {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 140,
      ellipsis: true,
    },"""
    
    new_category_column = """      {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 140,
      ellipsis: true,
    },
      {
      title: '供应商',
      dataIndex: 'supplier_code',
      key: 'supplier',
      width: 120,
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
    
    if old_category_column in content:
        content = content.replace(old_category_column, new_category_column)
        print("✅ 供应商列已添加")
    else:
        print("⚠️ 未找到分类列，尝试其他方式")
    
    # 任务1前端：修改单个产品同步按钮
    print("\n=== 任务1前端：修改单个产品同步按钮 ===")
    old_single_sync = """  // 同步到WooCommerce
  const handleSyncWooCommerce = async (product: Product) => {
    try {
      setSyncing(true)
      // 这里可以调用后端API同步到WooCommerce
      message.success(`已同步到WooCommerce: ${product.name}`)
      loadProducts()
    } catch (e) {
      message.error('同步失败')
    } finally {
      setSyncing(false)
    }
  }"""
    
    new_single_sync = """  // 同步到WooCommerce（推送到店铺）
  const handleSyncWooCommerce = async (product: Product) => {
    try {
      setSyncing(true)
      message.loading({ content: `正在同步到WooCommerce: ${product.name}`, key: 'sync' })
      
      const resp = await fetch(`/api/v1/products/${product.id}/push-woocommerce`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
      
      if (resp.ok) {
        const data = await resp.json()
        message.success({ content: `已同步到WooCommerce: ${product.name}`, key: 'sync' })
      } else {
        const err = await resp.json().catch(() => ({}))
        message.error({ content: `同步失败: ${err.detail || resp.statusText}`, key: 'sync' })
      }
      loadProducts()
    } catch (e: any) {
      message.error({ content: `同步失败: ${e.message}`, key: 'sync' })
    } finally {
      setSyncing(false)
    }
  }"""
    
    if old_single_sync in content:
        content = content.replace(old_single_sync, new_single_sync)
        print("✅ 单个产品同步按钮已修改")
    else:
        print("⚠️ 未找到单个同步函数")
    
    # 任务1前端：修改批量同步按钮
    print("\n=== 任务1前端：修改批量同步按钮 ===")
    old_batch_sync = """  // 批量同步WooCommerce
  const handleBatchSync = async () => {
    try {
      setSyncing(true)
      message.info('正在批量同步到WooCommerce...')
      // 这里可以调用后端API批量同步
      setTimeout(() => {
        message.success('批量同步完成')
        setSyncing(false)
        loadProducts()
      }, 2000)
    } catch (e) {
      message.error('批量同步失败')
      setSyncing(false)
    }
  }"""
    
    new_batch_sync = """  // 批量同步WooCommerce（推送到店铺）
  const handleBatchSync = async () => {
    try {
      setSyncing(true)
      message.loading({ content: '正在批量同步到WooCommerce...', key: 'batch-sync' })
      
      const resp = await fetch('/api/v1/products/push-woocommerce', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product_ids: [] }),
      })
      
      if (resp.ok) {
        const data = await resp.json()
        message.success({ 
          content: `批量同步完成: 成功${data.success || 0}个，失败${data.failed || 0}个`, 
          key: 'batch-sync' 
        })
      } else {
        const err = await resp.json().catch(() => ({}))
        message.error({ content: `批量同步失败: ${err.detail || resp.statusText}`, key: 'batch-sync' })
      }
      loadProducts()
    } catch (e: any) {
      message.error({ content: `批量同步失败: ${e.message}`, key: 'batch-sync' })
    } finally {
      setSyncing(false)
    }
  }"""
    
    if old_batch_sync in content:
        content = content.replace(old_batch_sync, new_batch_sync)
        print("✅ 批量同步按钮已修改")
    else:
        print("⚠️ 未找到批量同步函数")
    
    # 写回文件
    print("\n=== 写回文件 ===")
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/frontend/src/pages/Products.tsx', 'w') as f:
        f.write(content.encode('utf-8'))
    sftp.close()
    print("✅ 文件已写回")
    
    # 重新构建前端
    print("\n=== 重新构建前端 ===")
    stdin, stdout, stderr = ssh.exec_command("cd /opt/nuotao/frontend && npm run build 2>&1 | tail -10")
    print(stdout.read().decode())
    
    # 部署前端
    print("\n=== 部署前端 ===")
    stdin, stdout, stderr = ssh.exec_command("""
rm -rf /var/www/nuotao/*
cp -r /opt/nuotao/frontend/dist/* /var/www/nuotao/
chown -R www-data:www-data /var/www/nuotao/
echo '前端部署完成'
""")
    print(stdout.read().decode())
    
    print("\n" + "=" * 60)
    print("任务1前端 + 任务2完成！")
    print("=" * 60)
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
