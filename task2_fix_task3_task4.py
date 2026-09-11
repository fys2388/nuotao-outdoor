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
    print("任务2修复 + 任务3 + 任务4：综合执行")
    print("=" * 60)
    
    print("\n正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # ============================================================
    # 任务2修复：检查procurement/stats API
    # ============================================================
    print("\n" + "=" * 60)
    print("任务2修复：检查procurement/stats API")
    print("=" * 60)
    
    # 测试API
    stdin, stdout, stderr = ssh.exec_command("curl -s http://127.0.0.1:8000/api/v1/procurement/stats | head -5")
    print(f"procurement/stats API: {stdout.read().decode()[:200]}")
    
    # 测试我创建的API
    stdin, stdout, stderr = ssh.exec_command("curl -s http://127.0.0.1:8000/api/v1/supply-chain/purchase-orders/stats | head -5")
    print(f"supply-chain/purchase-orders/stats API: {stdout.read().decode()[:200]}")
    
    # 修改Suppliers.tsx，调用正确的API
    print("\n修改Suppliers.tsx调用正确的API...")
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/frontend/src/pages/Suppliers.tsx', 'r') as f:
        suppliers_content = f.read().decode('utf-8')
    sftp.close()
    
    # 修改API调用路径
    old_api = "const statsResp = await fetch('/api/v1/procurement/stats')"
    new_api = "const statsResp = await fetch('/api/v1/supply-chain/purchase-orders/stats')"
    
    if old_api in suppliers_content:
        suppliers_content = suppliers_content.replace(old_api, new_api)
        print("✅ API调用路径已修改")
    else:
        print("⚠️ 未找到API调用路径")
    
    # 修改数据字段映射（supply-chain API返回total_amount而不是total_spent）
    old_total = "const totalSpent = suppliersData?.total_spent || suppliersData?.total_amount || mockSuppliers.reduce((sum, s) => sum + s.total_spent, 0)"
    new_total = "const totalSpent = suppliersData?.total_amount || suppliersData?.total_spent || mockSuppliers.reduce((sum, s) => sum + s.total_spent, 0)"
    
    if old_total in suppliers_content:
        suppliers_content = suppliers_content.replace(old_total, new_total)
        print("✅ 数据字段映射已修改")
    else:
        print("⚠️ 未找到totalSpent计算")
    
    # 写回文件
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/frontend/src/pages/Suppliers.tsx', 'w') as f:
        f.write(suppliers_content.encode('utf-8'))
    sftp.close()
    print("✅ Suppliers.tsx已写回")
    
    # ============================================================
    # 任务3：新建采购单功能（后端API）
    # ============================================================
    print("\n" + "=" * 60)
    print("任务3：新建采购单功能（后端API）")
    print("=" * 60)
    
    # 读取supply_chain.py
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/backend/app/api/v1/endpoints/supply_chain.py', 'r') as f:
        supply_chain_content = f.read().decode('utf-8')
    sftp.close()
    
    # 添加创建采购订单API
    create_po_endpoint = '''


@router.post(
    "/purchase-orders",
    summary="Create a new purchase order",
)
async def create_purchase_order(
    db: DbSession,
    workspace_id: WorkspaceId,
    body: dict = Body(...),
) -> dict:
    """Create a new purchase order."""
    from sqlalchemy import text
    from uuid import uuid4
    from datetime import datetime
    
    try:
        po_id = str(uuid4())
        po_number = body.get("po_number") or f"PO-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:4].upper()}"
        supplier_id = body.get("supplier_id")
        status = body.get("status", "pending")
        currency = body.get("currency", "CNY")
        subtotal = float(body.get("subtotal", 0))
        shipping_cost = float(body.get("shipping_cost", 0))
        total = float(body.get("total", subtotal + shipping_cost))
        expected_delivery_at = body.get("expected_delivery_at")
        notes = body.get("notes", "")
        
        await db.execute(text("""
            INSERT INTO purchase_orders 
            (id, workspace_id, po_number, supplier_id, status, currency, 
             subtotal, shipping_cost, total, expected_delivery_at, notes, created_at, updated_at)
            VALUES (:id, :workspace_id, :po_number, :supplier_id, :status, :currency,
                    :subtotal, :shipping_cost, :total, :expected_delivery_at, :notes, NOW(), NOW())
        """), {
            "id": po_id,
            "workspace_id": str(workspace_id),
            "po_number": po_number,
            "supplier_id": supplier_id,
            "status": status,
            "currency": currency,
            "subtotal": subtotal,
            "shipping_cost": shipping_cost,
            "total": total,
            "expected_delivery_at": expected_delivery_at,
            "notes": notes,
        })
        await db.commit()
        
        return {
            "success": True,
            "id": po_id,
            "po_number": po_number,
            "message": "采购订单创建成功",
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建采购订单失败: {str(e)}",
        )
'''
    
    if '"/purchase-orders"' not in supply_chain_content or 'Create a new purchase order' not in supply_chain_content:
        supply_chain_content += create_po_endpoint
        sftp = ssh.open_sftp()
        with sftp.file('/opt/nuotao/backend/app/api/v1/endpoints/supply_chain.py', 'w') as f:
            f.write(supply_chain_content.encode('utf-8'))
        sftp.close()
        print("✅ 创建采购订单API已添加")
    else:
        print("⚠️ 创建采购订单API已存在")
    
    # ============================================================
    # 任务4：采购订单状态流转（后端API）
    # ============================================================
    print("\n" + "=" * 60)
    print("任务4：采购订单状态流转（后端API）")
    print("=" * 60)
    
    # 添加更新采购订单状态API
    update_po_status_endpoint = '''


@router.patch(
    "/purchase-orders/{po_id}/status",
    summary="Update purchase order status",
)
async def update_purchase_order_status(
    po_id: str,
    db: DbSession,
    workspace_id: WorkspaceId,
    body: dict = Body(...),
) -> dict:
    """Update purchase order status (pending -> ordered -> shipped -> received)."""
    from sqlalchemy import text
    
    valid_statuses = ["pending", "ordered", "shipped", "received", "completed", "cancelled"]
    new_status = body.get("status")
    
    if not new_status or new_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的状态: {new_status}，有效状态: {', '.join(valid_statuses)}",
        )
    
    try:
        # 更新状态
        update_fields = "status = :status, updated_at = NOW()"
        params = {"status": new_status, "id": po_id, "workspace_id": str(workspace_id)}
        
        # 如果状态变为received，设置received_at
        if new_status == "received":
            update_fields += ", received_at = NOW()"
        
        result = await db.execute(text(f"""
            UPDATE purchase_orders 
            SET {update_fields}
            WHERE id = :id AND workspace_id = :workspace_id
            RETURNING po_number, status
        """), params)
        await db.commit()
        
        row = result.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="采购订单不存在",
            )
        
        return {
            "success": True,
            "po_number": row[0],
            "status": row[1],
            "message": f"状态已更新为: {new_status}",
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新状态失败: {str(e)}",
        )
'''
    
    if '"/purchase-orders/{po_id}/status"' not in supply_chain_content:
        supply_chain_content += update_po_status_endpoint
        sftp = ssh.open_sftp()
        with sftp.file('/opt/nuotao/backend/app/api/v1/endpoints/supply_chain.py', 'w') as f:
            f.write(supply_chain_content.encode('utf-8'))
        sftp.close()
        print("✅ 更新采购订单状态API已添加")
    else:
        print("⚠️ 更新采购订单状态API已存在")
    
    # 重启后端
    print("\n重启后端服务...")
    stdin, stdout, stderr = ssh.exec_command("systemctl restart nuotao-backend && sleep 3 && systemctl is-active nuotao-backend")
    print(f"后端服务状态: {stdout.read().decode().strip()}")
    
    # ============================================================
    # 任务3+4前端：修改PurchaseOrders.tsx添加新建和状态流转功能
    # ============================================================
    print("\n" + "=" * 60)
    print("任务3+4前端：修改PurchaseOrders.tsx")
    print("=" * 60)
    
    # 读取PurchaseOrders.tsx
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/frontend/src/pages/PurchaseOrders.tsx', 'r') as f:
        po_content = f.read().decode('utf-8')
    sftp.close()
    
    # 添加新建采购单弹窗状态
    old_state_po = "const [detailModalOpen, setDetailModalOpen] = useState(false)"
    new_state_po = """const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createForm, setCreateForm] = useState({
    supplier_id: '',
    subtotal: '',
    shipping_cost: '',
    expected_delivery_at: '',
    notes: '',
  })"""
    
    if old_state_po in po_content and 'createModalOpen' not in po_content:
        po_content = po_content.replace(old_state_po, new_state_po)
        print("✅ 新建弹窗状态已添加")
    else:
        print("⚠️ 状态已存在或未找到")
    
    # 添加创建采购单函数
    old_load = "const loadOrders = async () => {"
    new_load = """const handleCreateOrder = async () => {
    try {
      setCreating(true)
      const subtotal = parseFloat(createForm.subtotal) || 0
      const shipping_cost = parseFloat(createForm.shipping_cost) || 0
      
      const resp = await fetch('/api/v1/supply-chain/purchase-orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          supplier_id: createForm.supplier_id || null,
          subtotal,
          shipping_cost,
          total: subtotal + shipping_cost,
          expected_delivery_at: createForm.expected_delivery_at || null,
          notes: createForm.notes,
          status: 'ordered',
        }),
      })
      
      if (resp.ok) {
        message.success('采购订单创建成功')
        setCreateModalOpen(false)
        setCreateForm({ supplier_id: '', subtotal: '', shipping_cost: '', expected_delivery_at: '', notes: '' })
        loadOrders()
      } else {
        const err = await resp.json().catch(() => ({}))
        message.error(`创建失败: ${err.detail || resp.statusText}`)
      }
    } catch (e: any) {
      message.error(`创建失败: ${e.message}`)
    } finally {
      setCreating(false)
    }
  }

  const handleUpdateStatus = async (order: PurchaseOrder, newStatus: string) => {
    try {
      const resp = await fetch(`/api/v1/supply-chain/purchase-orders/${order.id}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      })
      
      if (resp.ok) {
        message.success(`状态已更新为: ${statusText[newStatus] || newStatus}`)
        loadOrders()
      } else {
        const err = await resp.json().catch(() => ({}))
        message.error(`更新失败: ${err.detail || resp.statusText}`)
      }
    } catch (e: any) {
      message.error(`更新失败: ${e.message}`)
    }
  }

  const loadOrders = async () => {"""
    
    if old_load in po_content and 'handleCreateOrder' not in po_content:
        po_content = po_content.replace(old_load, new_load)
        print("✅ 创建和状态更新函数已添加")
    else:
        print("⚠️ 函数已存在或未找到")
    
    # 修改新建按钮，打开弹窗
    old_new_button = "<Button type=\"primary\" icon={<PlusOutlined />}>新建采购单</Button>"
    new_new_button = "<Button type=\"primary\" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>新建采购单</Button>"
    
    if old_new_button in po_content:
        po_content = po_content.replace(old_new_button, new_new_button)
        print("✅ 新建按钮已修改")
    else:
        print("⚠️ 未找到新建按钮")
    
    # 在操作列添加状态流转按钮
    old_action = """      render: (_: any, record: PurchaseOrder) => (
        <Button type="link" icon={<EyeOutlined />} onClick={() => {
          setViewingOrder(record)
          setDetailModalOpen(true)
        }}>
          详情
        </Button>
      ),"""
    
    new_action = """      render: (_: any, record: PurchaseOrder) => (
        <Space>
          <Button type="link" icon={<EyeOutlined />} onClick={() => {
            setViewingOrder(record)
            setDetailModalOpen(true)
          }}>
            详情
          </Button>
          {record.status === 'pending' && (
            <Button type="link" size="small" onClick={() => handleUpdateStatus(record, 'ordered')}>下单</Button>
          )}
          {record.status === 'ordered' && (
            <Button type="link" size="small" onClick={() => handleUpdateStatus(record, 'shipped')}>发货</Button>
          )}
          {record.status === 'shipped' && (
            <Button type="link" size="small" onClick={() => handleUpdateStatus(record, 'received')}>收货</Button>
          )}
        </Space>
      ),"""
    
    if old_action in po_content and 'handleUpdateStatus' not in po_content:
        po_content = po_content.replace(old_action, new_action)
        print("✅ 操作列状态流转按钮已添加")
    else:
        print("⚠️ 操作列已修改或未找到")
    
    # 添加新建采购单弹窗（在详情弹窗之后）
    old_detail_modal_end = "      </Modal>"
    new_create_modal = """      </Modal>

      {/* 新建采购单弹窗 */}
      <Modal
        title="新建采购订单"
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setCreateModalOpen(false)}>取消</Button>,
          <Button key="submit" type="primary" loading={creating} onClick={handleCreateOrder}>创建</Button>,
        ]}
        width={600}
      >
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="供应商" span={2}>
            <Select
              style={{ width: '100%' }}
              placeholder="选择供应商"
              value={createForm.supplier_id || undefined}
              onChange={(value) => setCreateForm({ ...createForm, supplier_id: value })}
              options={[
                { value: '0deef793-744b-4fdc-8c5f-70f8dcc8a75b', label: '义乌市浩宇户外用品有限公司' },
                { value: 'ffa86a22-d3f0-4e2c-be20-6bd26aedf2d0', label: '深圳市腾飞露营装备厂' },
                { value: 'a72966e5-8555-4dee-b76d-dc70974848a4', label: '宁波市明亮照明电器有限公司' },
                { value: '73102aab-01c2-4865-8357-1c906d1f78a7', label: '南通市暖睡家纺制品厂' },
                { value: 'b3539998-badd-4258-8a2f-5b614a1d53cf', label: '永康市野营炊具制造有限公司' },
              ]}
            />
          </Descriptions.Item>
          <Descriptions.Item label="商品金额">
            <Input
              type="number"
              prefix="¥"
              placeholder="0.00"
              value={createForm.subtotal}
              onChange={(e) => setCreateForm({ ...createForm, subtotal: e.target.value })}
            />
          </Descriptions.Item>
          <Descriptions.Item label="运费">
            <Input
              type="number"
              prefix="¥"
              placeholder="0.00"
              value={createForm.shipping_cost}
              onChange={(e) => setCreateForm({ ...createForm, shipping_cost: e.target.value })}
            />
          </Descriptions.Item>
          <Descriptions.Item label="预计交货日期" span={2}>
            <Input
              type="date"
              value={createForm.expected_delivery_at}
              onChange={(e) => setCreateForm({ ...createForm, expected_delivery_at: e.target.value })}
            />
          </Descriptions.Item>
          <Descriptions.Item label="备注" span={2}>
            <Input.TextArea
              rows={3}
              placeholder="采购备注..."
              value={createForm.notes}
              onChange={(e) => setCreateForm({ ...createForm, notes: e.target.value })}
            />
          </Descriptions.Item>
        </Descriptions>
      </Modal>"""
    
    # 找到最后一个Modal结束标签并替换
    # 由于有多个Modal，我们需要找到详情弹窗的结束位置
    # 简单方案：在文件末尾的</div>之前添加新建弹窗
    if '新建采购订单' not in po_content:
        # 找到return的最后一个</div>之前
        old_return_end = "    </div>\n  )\n}"
        new_return_end = """    </div>

      {/* 新建采购单弹窗 */}
      <Modal
        title="新建采购订单"
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setCreateModalOpen(false)}>取消</Button>,
          <Button key="submit" type="primary" loading={creating} onClick={handleCreateOrder}>创建</Button>,
        ]}
        width={600}
      >
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="供应商" span={2}>
            <Select
              style={{ width: '100%' }}
              placeholder="选择供应商"
              value={createForm.supplier_id || undefined}
              onChange={(value) => setCreateForm({ ...createForm, supplier_id: value })}
              options={[
                { value: '0deef793-744b-4fdc-8c5f-70f8dcc8a75b', label: '义乌市浩宇户外用品有限公司' },
                { value: 'ffa86a22-d3f0-4e2c-be20-6bd26aedf2d0', label: '深圳市腾飞露营装备厂' },
                { value: 'a72966e5-8555-4dee-b76d-dc70974848a4', label: '宁波市明亮照明电器有限公司' },
                { value: '73102aab-01c2-4865-8357-1c906d1f78a7', label: '南通市暖睡家纺制品厂' },
                { value: 'b3539998-badd-4258-8a2f-5b614a1d53cf', label: '永康市野营炊具制造有限公司' },
              ]}
            />
          </Descriptions.Item>
          <Descriptions.Item label="商品金额">
            <Input
              type="number"
              prefix="¥"
              placeholder="0.00"
              value={createForm.subtotal}
              onChange={(e) => setCreateForm({ ...createForm, subtotal: e.target.value })}
            />
          </Descriptions.Item>
          <Descriptions.Item label="运费">
            <Input
              type="number"
              prefix="¥"
              placeholder="0.00"
              value={createForm.shipping_cost}
              onChange={(e) => setCreateForm({ ...createForm, shipping_cost: e.target.value })}
            />
          </Descriptions.Item>
          <Descriptions.Item label="预计交货日期" span={2}>
            <Input
              type="date"
              value={createForm.expected_delivery_at}
              onChange={(e) => setCreateForm({ ...createForm, expected_delivery_at: e.target.value })}
            />
          </Descriptions.Item>
          <Descriptions.Item label="备注" span={2}>
            <Input.TextArea
              rows={3}
              placeholder="采购备注..."
              value={createForm.notes}
              onChange={(e) => setCreateForm({ ...createForm, notes: e.target.value })}
            />
          </Descriptions.Item>
        </Descriptions>
      </Modal>
  </div>
  )
}"""
        
        if old_return_end in po_content:
            po_content = po_content.replace(old_return_end, new_return_end)
            print("✅ 新建采购单弹窗已添加")
        else:
            print("⚠️ 未找到return结束位置")
    else:
        print("⚠️ 新建弹窗已存在")
    
    # 写回PurchaseOrders.tsx
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/frontend/src/pages/PurchaseOrders.tsx', 'w') as f:
        f.write(po_content.encode('utf-8'))
    sftp.close()
    print("✅ PurchaseOrders.tsx已写回")
    
    # ============================================================
    # 重新构建并部署前端
    # ============================================================
    print("\n" + "=" * 60)
    print("重新构建并部署前端")
    print("=" * 60)
    
    stdin, stdout, stderr = ssh.exec_command("cd /opt/nuotao/frontend && npm run build 2>&1 | tail -8")
    print(stdout.read().decode())
    
    stdin, stdout, stderr = ssh.exec_command("""
rm -rf /var/www/nuotao/*
cp -r /opt/nuotao/frontend/dist/* /var/www/nuotao/
chown -R www-data:www-data /var/www/nuotao/
echo '前端部署完成'
""")
    print(stdout.read().decode())
    
    print("\n" + "=" * 60)
    print("任务2修复 + 任务3 + 任务4完成！")
    print("=" * 60)
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
