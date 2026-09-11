#!/usr/bin/env python3
"""修复前端 API client 和页面，调用真实 API"""
import re

# 1. 修复 api/client.ts - 先恢复原始文件，然后正确添加方法
client_path = '/opt/nuotao/frontend/src/api/client.ts'
with open(client_path, 'r') as f:
    content = f.read()

# 移除错误添加的内容（从第一个错误的 getCoreProducts 开始到文件末尾）
# 找到原始文件的结尾（getB2BOrders 后面的 }）
original_end = content.find("  getB2BOrders: () => request('/p3/b2b/orders'),")
if original_end > 0:
    # 找到这一行后面的 }
    brace_pos = content.find('}', original_end)
    if brace_pos > 0:
        content = content[:brace_pos+1] + '\n'

# 正确添加新方法
new_methods = """
  // 产品管理（核心业务表）
  getCoreProducts: (page = 1, pageSize = 50) =>
    request(`/products?page=${page}&page_size=${pageSize}`),

  // 订单管理（核心业务表）
  getCoreOrders: (page = 1, pageSize = 50, status?: string) => {
    const params = new URLSearchParams()
    params.set('page', String(page))
    params.set('page_size', String(pageSize))
    if (status) params.set('status', status)
    return request(`/orders?${params.toString()}`)
  },

  // 订单详情
  getOrderDetail: (id: string) => request(`/orders/${id}`),
}
"""

# 替换最后的 }
content = content.rstrip()
if content.endswith('}'):
    content = content[:-1] + new_methods

with open(client_path, 'w') as f:
    f.write(content)

print("✅ api/client.ts 已修复")

# 2. 修改 Products.tsx - 调用真实 API
products_path = '/opt/nuotao/frontend/src/pages/Products.tsx'
with open(products_path, 'r') as f:
    products_content = f.read()

# 添加 api import
if "from '../api/client'" not in products_content:
    products_content = products_content.replace(
        "import { useState, useEffect } from 'react';",
        "import { useState, useEffect } from 'react';\nimport { api } from '../api/client';"
    )

# 修改 useEffect 调用真实 API
old_useEffect = """  useEffect(() => {
    setLoading(true);
    setTimeout(() => {
      setProducts(mockProducts);
      setLoading(false);
    }, 300);
  }, []);"""

new_useEffect = """  useEffect(() => {
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
  }, []);"""

products_content = products_content.replace(old_useEffect, new_useEffect)

with open(products_path, 'w') as f:
    f.write(products_content)

print("✅ Products.tsx 已修改为调用真实 API")

# 3. 修改 Orders.tsx - 调用真实 API
orders_path = '/opt/nuotao/frontend/src/pages/Orders.tsx'
with open(orders_path, 'r') as f:
    orders_content = f.read()

# 添加 api import
if "from '../api/client'" not in orders_content:
    orders_content = orders_content.replace(
        "import { useState, useEffect } from 'react';",
        "import { useState, useEffect } from 'react';\nimport { api } from '../api/client';"
    )

# 找到 useEffect 并修改
old_order_effect_pattern = r"  useEffect\(\(\) => \{\s*setLoading\(true\);\s*setTimeout\(\(\) => \{\s*setOrders\(mockOrders\);\s*setLoading\(false\);\s*\}, 300\);\s*\}, \[\]\);"

new_order_effect = """  useEffect(() => {
    const fetchOrders = async () => {
      setLoading(true);
      try {
        const data: any = await api.getCoreOrders();
        const items = Array.isArray(data) ? data : (data.items || data.data || []);
        const mapped = items.map((o: any, idx: number) => ({
          id: idx + 1,
          order_number: o.external_order_id || `ORDER-${o.external_order_id || idx}`,
          customer_name: o.customer_reference_id ? `客户#${o.customer_reference_id.slice(-6)}` : '访客客户',
          customer_email: '',
          total: parseFloat(o.total) || 0,
          status: o.status || 'pending',
          payment_method: o.payment_method || '未知',
          shipping_address: o.country ? `${o.country}` : '未提供',
          items: (o.items || []).map((item: any) => ({
            product_name: item.name || '',
            quantity: item.quantity || 1,
            price: parseFloat(item.unit_price) || 0,
            subtotal: parseFloat(item.line_total) || 0,
          })),
          created_at: o.received_at || o.created_at || '',
          updated_at: o.updated_at || '',
          woocommerce_id: parseInt(o.external_order_id) || 0,
        }));
        setOrders(mapped);
      } catch (err) {
        console.error('Failed to fetch orders:', err);
        setOrders(mockOrders);
      } finally {
        setLoading(false);
      }
    };
    fetchOrders();
  }, []);"""

orders_content = re.sub(old_order_effect_pattern, new_order_effect, orders_content, flags=re.DOTALL)

with open(orders_path, 'w') as f:
    f.write(orders_content)

print("✅ Orders.tsx 已修改为调用真实 API")

print("\n=== 前端页面修改完成 ===")
