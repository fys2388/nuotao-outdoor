# 半自动代采（1688采购单）使用说明

> 功能：WooCommerce出单后自动生成1688采购单草稿 → 人工确认 → 1688网页端下单 → 回填物流单号 → 自动更新WooCommerce订单

## 一、完整流程

```
客户在WooCommerce下单
    ↓ (webhook order.created 自动触发)
系统自动生成采购单草稿（pending状态）
    ↓
人工查看采购单，确认商品/数量/地址无误
    ↓ (confirm)
采购单状态变为confirmed
    ↓
人工去1688网页端，按采购单中的商品链接下单支付
    ↓ (ordered，填写1688订单号)
采购单状态变为ordered
    ↓
供应商发货，获取物流单号
    ↓ (tracking，填写物流单号)
采购单状态变为shipped
    ✅ 系统自动更新WooCommerce订单，添加物流备注（客户可见）
    ↓
客户确认收货
    ↓ (complete)
采购单状态变为completed
```

## 二、商品映射配置

**文件位置**: `backend/data/supplier_product_mapping.json`

每个WooCommerce产品需要映射到对应的1688商品，才能自动生成采购单。

### 映射字段说明

| 字段 | 说明 | 示例 |
|---|---|---|
| `woo_product_id` | WooCommerce产品ID | 895 |
| `woo_sku` | WooCommerce SKU | NT-LANTERN-001 |
| `woo_name` | WooCommerce产品名称 | Rechargeable LED Camping Lantern |
| `woo_price` | WooCommerce售价 | 34.99 |
| `ali1688_product_id` | 1688商品ID | 1075485124628 |
| `ali1688_url` | 1688商品链接 | https://detail.1688.com/offer/1075485124628.html |
| `ali1688_supplier` | 1688供应商名称 | 中山市成铂照明科技有限公司 |
| `ali1688_cost` | 1688采购单价（元） | 10.50 |
| `ali1688_sku` | 1688商品规格 | 默认规格 |
| `min_order_qty` | 最小起订量 | 1 |
| `shipping_method` | 发货方式 | 国内集货仓转国际物流 |
| `status` | 映射状态（active=启用，pending_mapping=待配置） | active |

### 如何添加新映射

1. 用1688采购助手插件导出商品Excel
2. 运行 `python import_1688_products.py <文件名>.xlsx` 做选品分析
3. 选定商品后，在 `supplier_product_mapping.json` 中添加映射条目
4. 设置 `status: "active"`

## 三、CLI命令使用

**进入目录**: `cd E:\AI\nuotao-ai-os\backend`

### 3.1 查看采购单列表

```bash
# 查看所有采购单
python manage_purchase_orders.py list

# 按状态筛选
python manage_purchase_orders.py list --status pending
python manage_purchase_orders.py list --status confirmed
python manage_purchase_orders.py list --status ordered
python manage_purchase_orders.py list --status shipped

# 限制返回数量
python manage_purchase_orders.py list --limit 10
```

### 3.2 查看采购单详情

```bash
python manage_purchase_orders.py show PO-20260904-XXXX
```

显示内容：客户收货信息、采购商品明细（含1688链接）、未映射商品、1688订单信息、物流信息、成本汇总、操作历史。

### 3.3 确认采购单

人工核对商品、数量、地址无误后，确认采购单：

```bash
python manage_purchase_orders.py confirm PO-20260904-XXXX --notes "核对无误"
```

确认后状态变为 `confirmed`，可以去1688下单。

### 3.4 标记已下单

在1688网页端完成下单支付后，标记已下单并填写1688订单号：

```bash
python manage_purchase_orders.py ordered PO-20260904-XXXX \
  --ali-order-id 1688订单号 \
  --ali-order-url https://trade.1688.com/order/订单详情页 \
  --notes "已在1688下单支付"
```

### 3.5 添加物流跟踪号

供应商发货后，获取物流单号并回填：

```bash
python manage_purchase_orders.py tracking PO-20260904-XXXX \
  --tracking SF1234567890 \
  --carrier 顺丰速运 \
  --tracking-url https://www.sf-express.com/... \
  --notes "供应商已发货"
```

**重要**: 添加物流单号后，系统会**自动更新WooCommerce订单**，添加客户可见的物流备注（含承运商、追踪号、查询链接）。

### 3.6 完成采购单

客户确认收货后，完成采购单：

```bash
python manage_purchase_orders.py complete PO-20260904-XXXX --notes "客户已确认收货"
```

### 3.7 取消采购单

```bash
python manage_purchase_orders.py cancel PO-20260904-XXXX --reason "客户取消订单"
```

### 3.8 查看统计

```bash
python manage_purchase_orders.py stats
```

显示：总采购单数、各状态数量、采购总成本。

### 3.9 手动从WooCommerce订单生成采购单

如果webhook没有自动触发，可以手动生成：

```bash
python manage_purchase_orders.py generate-from-wc 903
```

## 四、Webhook自动触发

### 工作原理

WooCommerce配置了 `order.created` webhook，当有新订单时，WooCommerce会自动推送订单数据到后端API。后端接收到后：

1. 同步订单到数据库
2. 发送订单确认邮件给客户
3. **自动生成1688采购单草稿**（新增功能）
4. 检查重复（同一订单不会重复生成）

### 前提条件

- WooCommerce webhook已配置并正常工作（已验证）
- 订单中的商品已在 `supplier_product_mapping.json` 中配置了1688映射
- 映射状态为 `active`

### 未映射商品处理

如果订单中有商品没有配置1688映射，采购单仍然会生成，但该商品会被标记为 `unmapped_items`（未映射商品），需要人工手动处理。

## 五、状态机说明

| 状态 | 含义 | 可流转到 |
|---|---|---|
| `pending` | 待确认（系统自动生成） | confirmed, cancelled |
| `confirmed` | 已确认（人工核对无误） | ordered, cancelled |
| `ordered` | 已下单（1688已下单支付） | shipped, cancelled |
| `shipped` | 已发货（已回填物流单号） | completed |
| `completed` | 已完成（客户确认收货） | — |
| `cancelled` | 已取消 | — |

**状态流转严格校验**：不允许跳过状态（如pending不能直接到ordered），不允许逆向流转（如completed不能回到shipped）。

## 六、数据文件

| 文件 | 位置 | 说明 |
|---|---|---|
| 商品映射 | `backend/data/supplier_product_mapping.json` | Woo产品↔1688商品映射 |
| 采购单 | `backend/data/purchase_orders.json` | 所有采购单数据 |

**备份建议**: 定期备份 `data/` 目录，避免数据丢失。

## 七、常见问题

### Q1: 订单生成了采购单，但商品显示"未映射"怎么办？

A: 在 `supplier_product_mapping.json` 中为该商品添加1688映射，设置 `status: "active"`。然后取消原采购单，重新生成。

### Q2: 可以批量下单吗？

A: 当前版本是逐单处理。如果多个采购单是同一个供应商，可以在1688购物车中合并下单，但需要分别标记ordered。

### Q3: 物流单号填错了怎么办？

A: 可以再次运行 `tracking` 命令覆盖物流单号（状态为shipped时允许重复添加）。

### Q4: 如何知道有新的待确认采购单？

A: 定期运行 `python manage_purchase_orders.py list --status pending` 查看。后续可以配置邮件/飞书提醒。

### Q5: 1688下单时收货地址填什么？

A: 取决于你的物流模式：
- **国内集货仓模式**: 填集货仓的国内地址，集货仓收到后统一发国际物流
- **供应商直发模式**: 如果供应商支持跨境物流，填客户的国外地址（需翻译成英文/当地语言）
- **海外仓模式**: 先批量采购到海外仓，从海外仓发货给客户

当前采购单中记录的是客户的原始收货地址，你可以根据实际物流模式选择使用哪个地址。
