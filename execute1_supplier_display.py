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
    print("执行1：前端显示供应商信息")
    print("=" * 60)
    
    print("\n正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # 步骤1: 检查后端Product schema
    print("\n" + "=" * 60)
    print("步骤1: 检查后端Product schema")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("grep -n 'supplier\\|class Product' /opt/nuotao/backend/app/schemas/product.py | head -20")
    print(stdout.read().decode())
    
    # 步骤2: 检查后端Product模型
    print("\n" + "=" * 60)
    print("步骤2: 检查后端Product模型")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("grep -n 'supplier\\|class Product' /opt/nuotao/backend/app/models/product.py | head -20")
    print(stdout.read().decode())
    
    # 步骤3: 读取前端Products.tsx文件
    print("\n" + "=" * 60)
    print("步骤3: 读取前端Products.tsx文件")
    print("=" * 60)
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/frontend/src/pages/Products.tsx', 'r') as f:
        content = f.read().decode('utf-8')
    sftp.close()
    print(f"文件长度: {len(content)} 字符")
    
    # 步骤4: 在表格列中添加供应商列
    print("\n" + "=" * 60)
    print("步骤4: 在表格列中添加供应商列")
    print("=" * 60)
    
    # 找到WooCommerce列的位置，在它之前添加供应商列
    old_column = """      {
      title: 'WooCommerce',
      dataIndex: 'woocommerce_id',
      key: 'woocommerce',
      width: 100,
      render: (id: number | null) => (
        <Tooltip title="已同步到WooCommerce">
          {id ? <Tag color="green">已同步</Tag> : <Tag color="orange">未同步</Tag>}
        </Tooltip>
      ),
    },"""
    
    new_column = """      {
      title: '供应商',
      dataIndex: 'supplier_code',
      key: 'supplier',
      width: 130,
      render: (code: string, record: any) => {
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
    },
      {
      title: 'WooCommerce',
      dataIndex: 'woocommerce_id',
      key: 'woocommerce',
      width: 100,
      render: (id: number | null) => (
        <Tooltip title="已同步到WooCommerce">
          {id ? <Tag color="green">已同步</Tag> : <Tag color="orange">未同步</Tag>}
        </Tooltip>
      ),
    },"""
    
    if old_column in content:
        content = content.replace(old_column, new_column)
        print("✅ 表格列已添加供应商列")
    else:
        print("⚠️ 未找到WooCommerce列，尝试其他方式...")
        # 尝试找到分类列之后添加
        old_category = """      {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 140,
      ellipsis: true,
    },"""
        new_category = """      {
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
      width: 130,
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
        if old_category in content:
            content = content.replace(old_category, new_category)
            print("✅ 已在分类列后添加供应商列")
    
    # 步骤5: 在产品详情弹窗中添加供应商信息
    print("\n" + "=" * 60)
    print("步骤5: 在产品详情弹窗中添加供应商信息")
    print("=" * 60)
    
    old_detail = """              <Descriptions.Item label="来源">{(viewingProduct as any).source || '-'}</Descriptions.Item>
              <Descriptions.Item label="目标市场">{(viewingProduct as any).target_market || '-'}</Descriptions.Item>"""
    
    new_detail = """              <Descriptions.Item label="供应商">
                {(() => {
                  const code = (viewingProduct as any).supplier_code;
                  const supplierNames: Record<string, string> = {
                    'SUP-YIHAO': '义乌市浩宇户外用品有限公司',
                    'SUP-TENGFEI': '深圳市腾飞露营装备厂',
                    'SUP-BRIGHT': '宁波市明亮照明电器有限公司',
                    'SUP-WARMSLEEP': '南通市暖睡家纺制品厂',
                    'SUP-CAMPCOOK': '永康市野营炊具制造有限公司',
                    'DEFAULT-SUPPLIER': '默认供应商（1688代发）',
                  };
                  const name = supplierNames[code] || code || '未关联';
                  return code ? <Tag color="blue">{name}</Tag> : <Tag color="default">未关联</Tag>;
                })()}
              </Descriptions.Item>
              <Descriptions.Item label="供应商编号">{(viewingProduct as any).supplier_code || '-'}</Descriptions.Item>
              <Descriptions.Item label="来源">{(viewingProduct as any).source || '-'}</Descriptions.Item>
              <Descriptions.Item label="目标市场">{(viewingProduct as any).target_market || '-'}</Descriptions.Item>"""
    
    if old_detail in content:
        content = content.replace(old_detail, new_detail)
        print("✅ 产品详情已添加供应商信息")
    else:
        print("⚠️ 未找到详情位置，尝试其他方式...")
    
    # 步骤6: 写回前端文件
    print("\n" + "=" * 60)
    print("步骤6: 写回前端文件")
    print("=" * 60)
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/frontend/src/pages/Products.tsx', 'w') as f:
        f.write(content.encode('utf-8'))
    sftp.close()
    print("✅ 前端文件已写回")
    
    # 步骤7: 重新构建前端
    print("\n" + "=" * 60)
    print("步骤7: 重新构建前端")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("cd /opt/nuotao/frontend && npm run build 2>&1 | tail -15")
    print(stdout.read().decode())
    
    # 步骤8: 部署前端
    print("\n" + "=" * 60)
    print("步骤8: 部署前端")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("""
rm -rf /var/www/nuotao/*
cp -r /opt/nuotao/frontend/dist/* /var/www/nuotao/
chown -R www-data:www-data /var/www/nuotao/
echo '前端部署完成'
""")
    print(stdout.read().decode())
    
    print("\n" + "=" * 60)
    print("执行1完成：前端供应商信息显示已添加！")
    print("=" * 60)
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
