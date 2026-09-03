import { useState, useEffect } from 'react';
import { api } from '../api/client';

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
  created_at: string;
  updated_at: string;
}

const mockProducts: Product[] = [
  { id: 1, name: '户外露营帐篷 4人', sku: 'CAMP-TENT-001', price: 599.00, stock: 150, status: 'active', category: '露营装备', description: '防水防风，适合4人使用', woocommerce_id: 101, created_at: '2024-01-15', updated_at: '2024-03-20' },
  { id: 2, name: '便携折叠椅', sku: 'CAMP-CHAIR-002', price: 129.00, stock: 300, status: 'active', category: '露营装备', description: '轻量化设计，承重150kg', woocommerce_id: 102, created_at: '2024-01-20', updated_at: '2024-03-18' },
  { id: 3, name: '户外保温壶 1L', sku: 'OUTDOOR-BOTTLE-001', price: 89.00, stock: 500, status: 'active', category: '户外用品', description: '24小时保温，304不锈钢', woocommerce_id: 103, created_at: '2024-02-01', updated_at: '2024-03-15' },
  { id: 4, name: '登山背包 50L', sku: 'HIKING-BAG-001', price: 399.00, stock: 0, status: 'inactive', category: '登山装备', description: '专业登山背包，防水面料', woocommerce_id: 104, created_at: '2024-02-10', updated_at: '2024-03-10' },
  { id: 5, name: 'LED头灯', sku: 'OUTDOOR-LIGHT-001', price: 59.00, stock: 800, status: 'draft', category: '户外用品', description: 'USB充电，三档亮度', created_at: '2024-03-01', updated_at: '2024-03-01' },
];

const statusColors: Record<string, string> = {
  active: '#52c41a',
  inactive: '#999',
  draft: '#fa8c16',
};

const statusText: Record<string, string> = {
  active: '上架',
  inactive: '下架',
  draft: '草稿',
};

export function Products() {
  const [products, setProducts] = useState<Product[]>(mockProducts);
  const [loading, setLoading] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [showModal, setShowModal] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [formData, setFormData] = useState({ name: '', sku: '', price: 0, stock: 0, status: 'active' as const, category: '', description: '' });

  useEffect(() => {
    const fetchProducts = async () => {
      setLoading(true);
      try {
        const data: any = await api.getCoreProducts();
        const items = Array.isArray(data) ? data : (data.items || data.data || []);
        const mapped = items.map((p: any, idx: number) => ({
          id: idx + 1,
          name: p.name || '',
          sku: p.sku || '',
          price: p.attributes?.price ? parseFloat(p.attributes.price) : 0,
          stock: p.attributes?.stock_quantity || 0,
          status: p.status || 'draft',
          category: p.category || '未分类',
          description: p.description || '',
          woocommerce_id: p.meta?.woocommerce_id || p.attributes?.wc_product_id,
          created_at: p.created_at || '',
          updated_at: p.updated_at || '',
        }));
        setProducts(mapped);
      } catch (err) {
        console.error('Failed to fetch products:', err);
        setProducts(mockProducts);
      } finally {
        setLoading(false);
      }
    };
    fetchProducts();
  }, []);

  const filteredProducts = products.filter((p) => {
    const matchSearch = !searchText || p.name.toLowerCase().includes(searchText.toLowerCase()) || p.sku.toLowerCase().includes(searchText.toLowerCase());
    const matchStatus = statusFilter === 'all' || p.status === statusFilter;
    return matchSearch && matchStatus;
  });

  const stats = {
    total: products.length,
    active: products.filter((p) => p.status === 'active').length,
    outOfStock: products.filter((p) => p.stock === 0).length,
    totalValue: products.reduce((sum, p) => sum + p.price * p.stock, 0),
  };

  const openModal = (product?: Product) => {
    if (product) {
      setEditingProduct(product);
      setFormData({ name: product.name, sku: product.sku, price: product.price, stock: product.stock, status: product.status, category: product.category, description: product.description || '' });
    } else {
      setEditingProduct(null);
      setFormData({ name: '', sku: '', price: 0, stock: 0, status: 'active', category: '', description: '' });
    }
    setShowModal(true);
  };

  const handleSave = () => {
    if (editingProduct) {
      setProducts(products.map((p) => (p.id === editingProduct.id ? { ...p, ...formData, updated_at: new Date().toISOString().split('T')[0] } : p)));
    } else {
      const newProduct: Product = { id: Math.max(...products.map((p) => p.id)) + 1, ...formData, created_at: new Date().toISOString().split('T')[0], updated_at: new Date().toISOString().split('T')[0] };
      setProducts([newProduct, ...products]);
    }
    setShowModal(false);
  };

  const handleDelete = (id: number) => {
    if (confirm('确定删除该产品？')) {
      setProducts(products.filter((p) => p.id !== id));
    }
  };

  const handleExport = () => {
    const csv = ['ID,名称,SKU,价格,库存,状态,分类', ...products.map((p) => `${p.id},${p.name},${p.sku},${p.price},${p.stock},${p.status},${p.category}`)].join('\n');
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `products_${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
  };

  const cardStyle: React.CSSProperties = { background: '#fff', borderRadius: 8, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' };
  const btnStyle: React.CSSProperties = { padding: '6px 16px', borderRadius: 4, border: '1px solid #d9d9d9', background: '#fff', cursor: 'pointer', fontSize: 14 };
  const primaryBtnStyle: React.CSSProperties = { ...btnStyle, background: '#1890ff', color: '#fff', borderColor: '#1890ff' };
  const inputStyle: React.CSSProperties = { padding: '6px 12px', borderRadius: 4, border: '1px solid #d9d9d9', fontSize: 14, width: '100%', boxSizing: 'border-box' };

  return (
    <div style={{ padding: 24 }}>
      {/* 统计卡片 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 24 }}>
        <div style={cardStyle}><div style={{ color: '#666', fontSize: 14 }}>产品总数</div><div style={{ fontSize: 28, fontWeight: 600, marginTop: 8 }}>{stats.total}</div></div>
        <div style={cardStyle}><div style={{ color: '#666', fontSize: 14 }}>上架产品</div><div style={{ fontSize: 28, fontWeight: 600, marginTop: 8, color: '#52c41a' }}>{stats.active}</div></div>
        <div style={cardStyle}><div style={{ color: '#666', fontSize: 14 }}>缺货产品</div><div style={{ fontSize: 28, fontWeight: 600, marginTop: 8, color: '#f5222d' }}>{stats.outOfStock}</div></div>
        <div style={cardStyle}><div style={{ color: '#666', fontSize: 14 }}>库存总价值</div><div style={{ fontSize: 28, fontWeight: 600, marginTop: 8 }}>¥{stats.totalValue.toFixed(2)}</div></div>
      </div>

      {/* 操作栏 */}
      <div style={{ ...cardStyle, marginBottom: 16, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <input style={{ ...inputStyle, width: 250 }} placeholder="搜索产品名称或 SKU" value={searchText} onChange={(e) => setSearchText(e.target.value)} />
        <select style={{ ...inputStyle, width: 120 }} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="all">全部状态</option>
          <option value="active">上架</option>
          <option value="inactive">下架</option>
          <option value="draft">草稿</option>
        </select>
        <button style={btnStyle} onClick={() => setProducts([...mockProducts])}>刷新</button>
        <button style={btnStyle} onClick={handleExport}>导出 CSV</button>
        <button style={btnStyle} onClick={() => alert('WooCommerce 同步功能')}>同步 WooCommerce</button>
        <button style={primaryBtnStyle} onClick={() => openModal()}>+ 新增产品</button>
      </div>

      {/* 产品表格 */}
      <div style={cardStyle}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #f0f0f0' }}>
              <th style={{ textAlign: 'left', padding: '12px 8px', fontSize: 14, color: '#666' }}>ID</th>
              <th style={{ textAlign: 'left', padding: '12px 8px', fontSize: 14, color: '#666' }}>产品名称</th>
              <th style={{ textAlign: 'left', padding: '12px 8px', fontSize: 14, color: '#666' }}>分类</th>
              <th style={{ textAlign: 'left', padding: '12px 8px', fontSize: 14, color: '#666' }}>价格</th>
              <th style={{ textAlign: 'left', padding: '12px 8px', fontSize: 14, color: '#666' }}>库存</th>
              <th style={{ textAlign: 'left', padding: '12px 8px', fontSize: 14, color: '#666' }}>状态</th>
              <th style={{ textAlign: 'left', padding: '12px 8px', fontSize: 14, color: '#666' }}>WooCommerce</th>
              <th style={{ textAlign: 'left', padding: '12px 8px', fontSize: 14, color: '#666' }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} style={{ textAlign: 'center', padding: 40, color: '#999' }}>加载中...</td></tr>
            ) : filteredProducts.map((product) => (
              <tr key={product.id} style={{ borderBottom: '1px solid #f0f0f0' }}>
                <td style={{ padding: '12px 8px', fontSize: 14 }}>{product.id}</td>
                <td style={{ padding: '12px 8px', fontSize: 14 }}>
                  <div style={{ fontWeight: 500 }}>{product.name}</div>
                  <div style={{ color: '#999', fontSize: 12 }}>SKU: {product.sku}</div>
                </td>
                <td style={{ padding: '12px 8px', fontSize: 14 }}>{product.category}</td>
                <td style={{ padding: '12px 8px', fontSize: 14, color: '#f5222d', fontWeight: 500 }}>¥{product.price.toFixed(2)}</td>
                <td style={{ padding: '12px 8px', fontSize: 14 }}>
                  <span style={{ color: product.stock > 100 ? '#52c41a' : product.stock > 0 ? '#fa8c16' : '#f5222d' }}>
                    {product.stock > 0 ? `${product.stock} 件` : '缺货'}
                  </span>
                </td>
                <td style={{ padding: '12px 8px', fontSize: 14 }}>
                  <span style={{ display: 'inline-block', padding: '2px 8px', borderRadius: 4, background: statusColors[product.status] + '20', color: statusColors[product.status], fontSize: 12 }}>
                    {statusText[product.status]}
                  </span>
                </td>
                <td style={{ padding: '12px 8px', fontSize: 14 }}>
                  {product.woocommerce_id ? <span style={{ color: '#1890ff' }}>已同步 #{product.woocommerce_id}</span> : <span style={{ color: '#999' }}>未同步</span>}
                </td>
                <td style={{ padding: '12px 8px', fontSize: 14 }}>
                  <button style={{ ...btnStyle, padding: '2px 8px', fontSize: 12, marginRight: 8 }} onClick={() => openModal(product)}>编辑</button>
                  <button style={{ ...btnStyle, padding: '2px 8px', fontSize: 12, color: '#f5222d', borderColor: '#f5222d' }} onClick={() => handleDelete(product.id)}>删除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ textAlign: 'right', padding: '12px 8px', color: '#666', fontSize: 14 }}>共 {filteredProducts.length} 条记录</div>
      </div>

      {/* 新增/编辑弹窗 */}
      {showModal && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ background: '#fff', borderRadius: 8, padding: 24, width: 500, maxHeight: '80vh', overflow: 'auto' }}>
            <h3 style={{ marginTop: 0 }}>{editingProduct ? '编辑产品' : '新增产品'}</h3>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', marginBottom: 4, fontSize: 14, color: '#333' }}>产品名称 *</label>
              <input style={inputStyle} value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} placeholder="请输入产品名称" />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 14, color: '#333' }}>SKU *</label>
                <input style={inputStyle} value={formData.sku} onChange={(e) => setFormData({ ...formData, sku: e.target.value })} placeholder="请输入 SKU" />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 14, color: '#333' }}>分类 *</label>
                <select style={inputStyle} value={formData.category} onChange={(e) => setFormData({ ...formData, category: e.target.value })}>
                  <option value="">请选择分类</option>
                  <option value="露营装备">露营装备</option>
                  <option value="户外用品">户外用品</option>
                  <option value="登山装备">登山装备</option>
                </select>
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 14, color: '#333' }}>价格 (¥) *</label>
                <input type="number" style={inputStyle} value={formData.price} onChange={(e) => setFormData({ ...formData, price: Number(e.target.value) })} placeholder="请输入价格" />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 14, color: '#333' }}>库存 *</label>
                <input type="number" style={inputStyle} value={formData.stock} onChange={(e) => setFormData({ ...formData, stock: Number(e.target.value) })} placeholder="请输入库存" />
              </div>
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', marginBottom: 4, fontSize: 14, color: '#333' }}>状态 *</label>
              <select style={inputStyle} value={formData.status} onChange={(e) => setFormData({ ...formData, status: e.target.value as 'active' | 'inactive' | 'draft' })}>
                <option value="active">上架</option>
                <option value="inactive">下架</option>
                <option value="draft">草稿</option>
              </select>
            </div>
            <div style={{ marginBottom: 24 }}>
              <label style={{ display: 'block', marginBottom: 4, fontSize: 14, color: '#333' }}>产品描述</label>
              <textarea style={{ ...inputStyle, minHeight: 80, resize: 'vertical' }} value={formData.description} onChange={(e) => setFormData({ ...formData, description: e.target.value })} placeholder="请输入产品描述" />
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
              <button style={btnStyle} onClick={() => setShowModal(false)}>取消</button>
              <button style={primaryBtnStyle} onClick={handleSave}>保存</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
