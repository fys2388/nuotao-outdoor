import { useState, useEffect, useMemo } from 'react';
import {
  Table, Button, Modal, Tag, Space, message, Card, Row, Col, Statistic,
  Select, Input, InputNumber, Popconfirm, Tooltip, Dropdown, Badge
} from 'antd';
import {
  PlusOutlined, SearchOutlined, ReloadOutlined, DownloadOutlined,
  EditOutlined, DeleteOutlined, EyeOutlined, FilterOutlined,
  CheckCircleOutlined, CloseCircleOutlined, SyncOutlined,
  ExportOutlined, SettingOutlined, UpOutlined, DownOutlined
} from '@ant-design/icons';
import type { ColumnsType, TableRowSelection } from 'antd/es/table';

interface Product {
  id: number;
  name: string;
  sku: string;
  price: number;
  stock: number;
  status: 'active' | 'inactive' | 'draft';
  category: string;
  description?: string;
  woocommerce_id?: number;
  supplier?: string;
  cost_price?: number;
  profit_rate?: number;
  score?: number;
  created_at: string;
  updated_at: string;
}

const mockProducts: Product[] = [
  { id: 1, name: '户外露营帐篷 4人', sku: 'CAMP-TENT-001', price: 599.00, stock: 150, status: 'active', category: '露营装备', description: '防水防风，适合4人使用', woocommerce_id: 101, supplier: '浙江户外用品有限公司', cost_price: 280, profit_rate: 53.3, score: 8.5, created_at: '2024-01-15', updated_at: '2024-03-20' },
  { id: 2, name: '便携折叠椅', sku: 'CAMP-CHAIR-002', price: 129.00, stock: 300, status: 'active', category: '露营装备', description: '轻量化设计，承重150kg', woocommerce_id: 102, supplier: '广东家具制造厂', cost_price: 45, profit_rate: 65.1, score: 7.8, created_at: '2024-01-20', updated_at: '2024-03-18' },
  { id: 3, name: '户外保温壶 1L', sku: 'OUTDOOR-BOTTLE-001', price: 89.00, stock: 500, status: 'active', category: '户外用品', description: '24小时保温，304不锈钢', woocommerce_id: 103, supplier: '浙江杯业有限公司', cost_price: 32, profit_rate: 64.0, score: 8.2, created_at: '2024-02-01', updated_at: '2024-03-15' },
  { id: 4, name: '登山背包 50L', sku: 'HIKING-BAG-001', price: 399.00, stock: 0, status: 'inactive', category: '登山装备', description: '专业登山背包，防水面料', woocommerce_id: 104, supplier: '福建箱包厂', cost_price: 180, profit_rate: 54.9, score: 7.5, created_at: '2024-02-10', updated_at: '2024-03-10' },
  { id: 5, name: 'LED头灯', sku: 'OUTDOOR-LIGHT-001', price: 59.00, stock: 800, status: 'draft', category: '户外用品', description: 'USB充电，三档亮度', supplier: '深圳电子厂', cost_price: 18, profit_rate: 69.5, score: 7.0, created_at: '2024-03-01', updated_at: '2024-03-01' },
  { id: 6, name: '太阳能露营灯', sku: 'NT-SOLAR-LANTERN-100W', price: 40.64, stock: 100, status: 'active', category: '露营装备', description: '太阳能充电，超长续航', woocommerce_id: 878, supplier: '中山市成铂照明科技有限公司', cost_price: 38, profit_rate: 6.5, score: 7.5, created_at: '2024-09-01', updated_at: '2024-09-03' },
  { id: 7, name: '户外防水背包 30L', sku: 'OUTDOOR-BAG-30L', price: 199.00, stock: 200, status: 'active', category: '户外用品', description: 'IPX6防水，多功能分区', supplier: '福建箱包厂', cost_price: 85, profit_rate: 57.3, score: 8.0, created_at: '2024-02-15', updated_at: '2024-03-12' },
  { id: 8, name: '野餐垫 200x200cm', sku: 'PICNIC-MAT-001', price: 69.00, stock: 400, status: 'draft', category: '露营装备', description: '防潮防水，可机洗', supplier: '浙江纺织品厂', cost_price: 22, profit_rate: 68.1, score: 6.8, created_at: '2024-03-05', updated_at: '2024-03-05' },
];

const statusColors: Record<string, string> = {
  active: 'green',
  inactive: 'default',
  draft: 'orange',
};

const statusText: Record<string, string> = {
  active: '上架',
  inactive: '下架',
  draft: '草稿',
};

const categories = ['露营装备', '户外用品', '登山装备', '照明设备', '炊具餐具', '其他'];

export default function Products() {
  const [products, setProducts] = useState<Product[]>(mockProducts);
  const [loading, setLoading] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState<string[]>([]);
  const [categoryFilter, setCategoryFilter] = useState<string[]>([]);
  const [priceRange, setPriceRange] = useState<[number, number] | null>(null);
  const [stockFilter, setStockFilter] = useState<string>('all');
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [formData, setFormData] = useState({ name: '', sku: '', price: 0, stock: 0, status: 'active' as const, category: '', description: '', supplier: '', cost_price: 0 });
  const [showBatchModal, setShowBatchModal] = useState(false);
  const [batchAction, setBatchAction] = useState<string>('');
  const [batchCategory, setBatchCategory] = useState('');
  const [batchPriceAdjust, setBatchPriceAdjust] = useState(0);

  useEffect(() => {
    setLoading(true);
    setTimeout(() => {
      setProducts(mockProducts);
      setLoading(false);
    }, 300);
  }, []);

  const filteredProducts = useMemo(() => {
    return products.filter((p) => {
      const matchSearch = !searchText ||
        p.name.toLowerCase().includes(searchText.toLowerCase()) ||
        p.sku.toLowerCase().includes(searchText.toLowerCase()) ||
        (p.supplier && p.supplier.toLowerCase().includes(searchText.toLowerCase()));
      const matchStatus = statusFilter.length === 0 || statusFilter.includes(p.status);
      const matchCategory = categoryFilter.length === 0 || categoryFilter.includes(p.category);
      const matchPrice = !priceRange || (p.price >= priceRange[0] && p.price <= priceRange[1]);
      const matchStock = stockFilter === 'all' ||
        (stockFilter === 'inStock' && p.stock > 0) ||
        (stockFilter === 'outOfStock' && p.stock === 0) ||
        (stockFilter === 'lowStock' && p.stock > 0 && p.stock < 50);
      return matchSearch && matchStatus && matchCategory && matchPrice && matchStock;
    });
  }, [products, searchText, statusFilter, categoryFilter, priceRange, stockFilter]);

  const stats = useMemo(() => ({
    total: products.length,
    active: products.filter((p) => p.status === 'active').length,
    outOfStock: products.filter((p) => p.stock === 0).length,
    totalValue: products.reduce((sum, p) => sum + p.price * p.stock, 0),
    selected: selectedRowKeys.length,
  }), [products, selectedRowKeys]);

  const rowSelection: TableRowSelection<Product> = {
    selectedRowKeys,
    onChange: (keys) => setSelectedRowKeys(keys),
    preserveSelectedRowKeys: true,
  };

  const openModal = (product?: Product) => {
    if (product) {
      setEditingProduct(product);
      setFormData({
        name: product.name, sku: product.sku, price: product.price,
        stock: product.stock, status: product.status, category: product.category,
        description: product.description || '', supplier: product.supplier || '',
        cost_price: product.cost_price || 0
      });
    } else {
      setEditingProduct(null);
      setFormData({ name: '', sku: '', price: 0, stock: 0, status: 'active', category: '', description: '', supplier: '', cost_price: 0 });
    }
    setShowModal(true);
  };

  const handleSave = () => {
    if (!formData.name || !formData.sku) {
      message.warning('请填写产品名称和SKU');
      return;
    }
    if (editingProduct) {
      setProducts(products.map((p) => (p.id === editingProduct.id ? { ...p, ...formData, updated_at: new Date().toISOString().split('T')[0] } : p)));
      message.success('产品更新成功');
    } else {
      const newProduct: Product = {
        id: Math.max(...products.map((p) => p.id)) + 1,
        ...formData,
        created_at: new Date().toISOString().split('T')[0],
        updated_at: new Date().toISOString().split('T')[0],
      };
      setProducts([newProduct, ...products]);
      message.success('产品创建成功');
    }
    setShowModal(false);
  };

  const handleDelete = (id: number) => {
    setProducts(products.filter((p) => p.id !== id));
    message.success('产品已删除');
  };

  const handleBatchAction = (action: string) => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择产品');
      return;
    }
    if (action === 'delete') {
      Modal.confirm({
        title: '确认删除',
        content: `确定要删除选中的 ${selectedRowKeys.length} 个产品吗？此操作不可恢复。`,
        okText: '确认删除',
        okType: 'danger',
        cancelText: '取消',
        onOk: () => {
          setProducts(products.filter((p) => !selectedRowKeys.includes(p.id)));
          setSelectedRowKeys([]);
          message.success(`已删除 ${selectedRowKeys.length} 个产品`);
        },
      });
      return;
    }
    if (action === 'category' || action === 'price') {
      setBatchAction(action);
      setShowBatchModal(true);
      return;
    }
    const statusMap: Record<string, 'active' | 'inactive'> = { activate: 'active', deactivate: 'inactive' };
    if (statusMap[action]) {
      setProducts(products.map((p) =>
        selectedRowKeys.includes(p.id) ? { ...p, status: statusMap[action], updated_at: new Date().toISOString().split('T')[0] } : p
      ));
      message.success(`已${action === 'activate' ? '上架' : '下架'} ${selectedRowKeys.length} 个产品`);
    }
  };

  const handleBatchConfirm = () => {
    if (batchAction === 'category' && batchCategory) {
      setProducts(products.map((p) =>
        selectedRowKeys.includes(p.id) ? { ...p, category: batchCategory, updated_at: new Date().toISOString().split('T')[0] } : p
      ));
      message.success(`已将 ${selectedRowKeys.length} 个产品分类修改为「${batchCategory}」`);
    }
    if (batchAction === 'price' && batchPriceAdjust !== 0) {
      setProducts(products.map((p) =>
        selectedRowKeys.includes(p.id)
          ? { ...p, price: Math.round(p.price * (1 + batchPriceAdjust / 100) * 100) / 100, updated_at: new Date().toISOString().split('T')[0] }
          : p
      ));
      message.success(`已将 ${selectedRowKeys.length} 个产品价格${batchPriceAdjust > 0 ? '上调' : '下调'} ${Math.abs(batchPriceAdjust)}%`);
    }
    setShowBatchModal(false);
    setBatchAction('');
    setBatchCategory('');
    setBatchPriceAdjust(0);
  };

  const handleExport = (selectedOnly = false) => {
    const data = selectedOnly ? products.filter((p) => selectedRowKeys.includes(p.id)) : filteredProducts;
    const csv = ['ID,名称,SKU,分类,价格,成本,利润率,库存,状态,供应商,WooCommerce ID,创建时间,更新时间',
      ...data.map((p) => `${p.id},${p.name},${p.sku},${p.category},${p.price},${p.cost_price || ''},${p.profit_rate || ''},${p.stock},${statusText[p.status]},${p.supplier || ''},${p.woocommerce_id || ''},${p.created_at},${p.updated_at}`)
    ].join('\n');
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `products_${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
    message.success(`已导出 ${data.length} 个产品`);
  };

  const resetFilters = () => {
    setSearchText('');
    setStatusFilter([]);
    setCategoryFilter([]);
    setPriceRange(null);
    setStockFilter('all');
  };

  const columns: ColumnsType<Product> = [
    {
      title: 'ID', dataIndex: 'id', key: 'id', width: 60,
      sorter: (a, b) => a.id - b.id,
    },
    {
      title: '产品信息', dataIndex: 'name', key: 'name', minWidth: 220,
      render: (_, record) => (
        <div>
          <div style={{ fontWeight: 500, marginBottom: 4 }}>{record.name}</div>
          <div style={{ color: '#999', fontSize: 12 }}>SKU: {record.sku}</div>
          {record.supplier && <div style={{ color: '#1890ff', fontSize: 12 }}>供应商: {record.supplier}</div>}
        </div>
      ),
      sorter: (a, b) => a.name.localeCompare(b.name),
    },
    {
      title: '分类', dataIndex: 'category', key: 'category', width: 110,
      filters: categories.map(c => ({ text: c, value: c })),
      onFilter: (value, record) => record.category === value,
      render: (cat) => <Tag color="blue">{cat}</Tag>,
    },
    {
      title: '价格', dataIndex: 'price', key: 'price', width: 100,
      sorter: (a, b) => a.price - b.price,
      render: (price, record) => (
        <div>
          <div style={{ color: '#f5222d', fontWeight: 600 }}>¥{price.toFixed(2)}</div>
          {record.cost_price && <div style={{ color: '#999', fontSize: 12 }}>成本: ¥{record.cost_price}</div>}
          {record.profit_rate && <div style={{ color: '#52c41a', fontSize: 12 }}>利润: {record.profit_rate}%</div>}
        </div>
      ),
    },
    {
      title: '库存', dataIndex: 'stock', key: 'stock', width: 90,
      sorter: (a, b) => a.stock - b.stock,
      render: (stock) => (
        <span style={{ color: stock > 100 ? '#52c41a' : stock > 0 ? '#fa8c16' : '#f5222d', fontWeight: 500 }}>
          {stock > 0 ? `${stock} 件` : '缺货'}
        </span>
      ),
    },
    {
      title: '评分', dataIndex: 'score', key: 'score', width: 80,
      sorter: (a, b) => (a.score || 0) - (b.score || 0),
      render: (score) => score ? <Tag color={score >= 8 ? 'green' : score >= 7 ? 'orange' : 'red'}>{score.toFixed(1)}</Tag> : '-',
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      filters: [
        { text: '上架', value: 'active' },
        { text: '下架', value: 'inactive' },
        { text: '草稿', value: 'draft' },
      ],
      onFilter: (value, record) => record.status === value,
      render: (status) => <Tag color={statusColors[status]}>{statusText[status]}</Tag>,
    },
    {
      title: 'WooCommerce', dataIndex: 'woocommerce_id', key: 'woocommerce_id', width: 110,
      render: (id) => id ? <a href={`https://nuotaooutdoor.com/wp-admin/post.php?post=${id}&action=edit`} target="_blank" rel="noreferrer">已同步 #{id}</a> : <span style={{ color: '#999' }}>未同步</span>,
    },
    {
      title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 110,
      sorter: (a, b) => a.updated_at.localeCompare(b.updated_at),
    },
    {
      title: '操作', key: 'action', width: 160, fixed: 'right',
      render: (_, record) => (
        <Space size="small">
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openModal(record)}>编辑</Button>
          <Popconfirm title="确定删除该产品？" onConfirm={() => handleDelete(record.id)} okText="确定" cancelText="取消">
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const batchMenuItems = [
    { key: 'activate', icon: <CheckCircleOutlined />, label: '批量上架' },
    { key: 'deactivate', icon: <CloseCircleOutlined />, label: '批量下架' },
    { key: 'category', icon: <SettingOutlined />, label: '批量修改分类' },
    { key: 'price', icon: <SyncOutlined />, label: '批量调整价格' },
    { type: 'divider' as const },
    { key: 'exportSelected', icon: <ExportOutlined />, label: '导出选中产品' },
    { type: 'divider' as const },
    { key: 'delete', icon: <DeleteOutlined />, danger: true, label: '批量删除' },
  ];

  return (
    <div style={{ padding: 24 }}>
      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="产品总数" value={stats.total} /></Card></Col>
        <Col span={6}><Card><Statistic title="上架产品" value={stats.active} valueStyle={{ color: '#52c41a' }} /></Card></Col>
        <Col span={6}><Card><Statistic title="缺货产品" value={stats.outOfStock} valueStyle={{ color: '#f5222d' }} /></Card></Col>
        <Col span={6}><Card><Statistic title="库存总价值" value={stats.totalValue} prefix="¥" precision={2} /></Card></Col>
      </Row>

      {/* 筛选栏 */}
      <Card style={{ marginBottom: 16 }}>
        <Space wrap size="middle">
          <Input
            placeholder="搜索产品名称 / SKU / 供应商"
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ width: 280 }}
          />
          <Select
            mode="multiple"
            placeholder="状态筛选"
            value={statusFilter}
            onChange={setStatusFilter}
            style={{ width: 160 }}
            maxTagCount={1}
            options={[
              { value: 'active', label: '上架' },
              { value: 'inactive', label: '下架' },
              { value: 'draft', label: '草稿' },
            ]}
          />
          <Select
            mode="multiple"
            placeholder="分类筛选"
            value={categoryFilter}
            onChange={setCategoryFilter}
            style={{ width: 180 }}
            maxTagCount={1}
            options={categories.map(c => ({ value: c, label: c }))}
          />
          <Select
            placeholder="库存筛选"
            value={stockFilter}
            onChange={setStockFilter}
            style={{ width: 130 }}
            options={[
              { value: 'all', label: '全部库存' },
              { value: 'inStock', label: '有库存' },
              { value: 'lowStock', label: '低库存(<50)' },
              { value: 'outOfStock', label: '缺货' },
            ]}
          />
          <InputNumber
            placeholder="最低价"
            value={priceRange?.[0]}
            onChange={(v) => setPriceRange([v || 0, priceRange?.[1] || 99999])}
            style={{ width: 110 }}
            prefix="¥"
          />
          <span style={{ color: '#999' }}>-</span>
          <InputNumber
            placeholder="最高价"
            value={priceRange?.[1]}
            onChange={(v) => setPriceRange([priceRange?.[0] || 0, v || 99999])}
            style={{ width: 110 }}
            prefix="¥"
          />
          <Button icon={<FilterOutlined />} onClick={resetFilters}>重置筛选</Button>
        </Space>
      </Card>

      {/* 操作栏 + 批量操作 */}
      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openModal()}>新增产品</Button>
          <Button icon={<ReloadOutlined />} onClick={() => { setLoading(true); setTimeout(() => { setProducts(mockProducts); setLoading(false); }, 300); }}>刷新</Button>
          <Button icon={<DownloadOutlined />} onClick={() => handleExport(false)}>导出全部</Button>
          <Dropdown menu={{ items: batchMenuItems, onClick: ({ key }) => {
            if (key === 'exportSelected') { handleExport(true); }
            else { handleBatchAction(key); }
          }}}>
            <Button icon={<SettingOutlined />}>
              批量操作 <Badge count={selectedRowKeys.length} showZero style={{ marginLeft: 8 }} />
            </Button>
          </Dropdown>
          {selectedRowKeys.length > 0 && (
            <span style={{ color: '#1890ff' }}>
              已选择 {selectedRowKeys.length} 项
              <Button type="link" onClick={() => setSelectedRowKeys([])}>取消选择</Button>
            </span>
          )}
        </Space>
      </Card>

      {/* 产品表格 */}
      <Card>
        <Table<Product>
          rowSelection={rowSelection}
          columns={columns}
          dataSource={filteredProducts}
          rowKey="id"
          loading={loading}
          scroll={{ x: 1400 }}
          pagination={{
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `共 ${total} 条记录`,
            pageSizeOptions: ['10', '20', '50', '100'],
            defaultPageSize: 20,
          }}
        />
      </Card>

      {/* 新增/编辑弹窗 */}
      <Modal
        title={editingProduct ? '编辑产品' : '新增产品'}
        open={showModal}
        onOk={handleSave}
        onCancel={() => setShowModal(false)}
        width={600}
        okText="保存"
        cancelText="取消"
      >
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={{ display: 'block', marginBottom: 4, fontSize: 14 }}>产品名称 *</label>
            <Input value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} placeholder="请输入产品名称" />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontSize: 14 }}>SKU *</label>
            <Input value={formData.sku} onChange={(e) => setFormData({ ...formData, sku: e.target.value })} placeholder="请输入 SKU" />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontSize: 14 }}>分类 *</label>
            <Select value={formData.category} onChange={(v) => setFormData({ ...formData, category: v })} style={{ width: '100%' }} placeholder="请选择分类">
              {categories.map(c => <Select.Option key={c} value={c}>{c}</Select.Option>)}
            </Select>
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontSize: 14 }}>售价 (¥) *</label>
            <InputNumber value={formData.price} onChange={(v) => setFormData({ ...formData, price: v || 0 })} style={{ width: '100%' }} placeholder="请输入售价" />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontSize: 14 }}>成本价 (¥)</label>
            <InputNumber value={formData.cost_price} onChange={(v) => setFormData({ ...formData, cost_price: v || 0 })} style={{ width: '100%' }} placeholder="请输入成本价" />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontSize: 14 }}>库存 *</label>
            <InputNumber value={formData.stock} onChange={(v) => setFormData({ ...formData, stock: v || 0 })} style={{ width: '100%' }} placeholder="请输入库存" />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontSize: 14 }}>状态 *</label>
            <Select value={formData.status} onChange={(v) => setFormData({ ...formData, status: v })} style={{ width: '100%' }}>
              <Select.Option value="active">上架</Select.Option>
              <Select.Option value="inactive">下架</Select.Option>
              <Select.Option value="draft">草稿</Select.Option>
            </Select>
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={{ display: 'block', marginBottom: 4, fontSize: 14 }}>供应商</label>
            <Input value={formData.supplier} onChange={(e) => setFormData({ ...formData, supplier: e.target.value })} placeholder="请输入供应商名称" />
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={{ display: 'block', marginBottom: 4, fontSize: 14 }}>产品描述</label>
            <Input.TextArea value={formData.description} onChange={(e) => setFormData({ ...formData, description: e.target.value })} placeholder="请输入产品描述" rows={3} />
          </div>
        </div>
      </Modal>

      {/* 批量操作弹窗 */}
      <Modal
        title={batchAction === 'category' ? '批量修改分类' : '批量调整价格'}
        open={showBatchModal}
        onOk={handleBatchConfirm}
        onCancel={() => { setShowBatchModal(false); setBatchAction(''); }}
        okText="确认"
        cancelText="取消"
      >
        <p style={{ marginBottom: 16 }}>将对选中的 <strong style={{ color: '#1890ff' }}>{selectedRowKeys.length}</strong> 个产品执行此操作。</p>
        {batchAction === 'category' && (
          <div>
            <label style={{ display: 'block', marginBottom: 8, fontSize: 14 }}>选择新分类</label>
            <Select value={batchCategory} onChange={setBatchCategory} style={{ width: '100%' }} placeholder="请选择分类">
              {categories.map(c => <Select.Option key={c} value={c}>{c}</Select.Option>)}
            </Select>
          </div>
        )}
        {batchAction === 'price' && (
          <div>
            <label style={{ display: 'block', marginBottom: 8, fontSize: 14 }}>价格调整百分比（正数上调，负数下调）</label>
            <InputNumber
              value={batchPriceAdjust}
              onChange={setBatchPriceAdjust}
              style={{ width: '100%' }}
              placeholder="例如：10 表示上调10%，-10 表示下调10%"
              min={-90}
              max={500}
              addonAfter="%"
            />
          </div>
        )}
      </Modal>
    </div>
  );
}
