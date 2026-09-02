# WooCommerce 集成配置指南

本文档介绍如何配置 Nuotao AI OS 与 WooCommerce 电商店铺的集成，实现产品、订单和客户数据的同步。

## 目录

1. [前置条件](#前置条件)
2. [WooCommerce API 密钥生成](#woocommerce-api-密钥生成)
3. [配置 Nuotao AI OS](#配置-nuotao-ai-os)
4. [测试连接](#测试连接)
5. [数据同步](#数据同步)
6. [Webhook 配置](#webhook-配置)
7. [故障排查](#故障排查)

---

## 前置条件

- WooCommerce 3.5+ 店铺（WordPress + WooCommerce 插件）
- WordPress 管理员权限
- Nuotao AI OS 后端服务运行中
- 网络可访问 WooCommerce 店铺的 REST API（`/wp-json/wc/v3/`）

---

## WooCommerce API 密钥生成

### 步骤 1：登录 WordPress 后台

访问你的 WordPress 后台地址（通常是 `https://yourdomain.com/wp-admin`），使用管理员账号登录。

### 步骤 2：进入 WooCommerce 设置

1. 在左侧菜单中点击 **WooCommerce** → **设置**
2. 点击顶部的 **高级**（Advanced）选项卡
3. 点击 **REST API** 子选项卡

### 步骤 3：创建 API 密钥

1. 点击 **添加密钥**（Add key）按钮
2. 填写以下信息：
   - **描述**（Description）：`Nuotao AI OS Integration`
   - **用户**（User）：选择管理员用户
   - **权限**（Permissions）：选择 **读取**（Read）- Nuotao AI OS 目前是只读集成
3. 点击 **生成 API 密钥**（Generate API key）

### 步骤 4：保存密钥信息

生成后，你会看到：
- **Consumer key**（消费者密钥）：格式如 `ck_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
- **Consumer secret**（消费者密钥）：格式如 `cs_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

**重要**：这两个密钥只会显示一次，请立即复制并保存到安全的地方。Consumer secret 关闭页面后将无法再次查看。

---

## 配置 Nuotao AI OS

### 方式一：通过 API 端点同步（推荐）

使用 `POST /api/v1/connectors/woocommerce/sync` 端点进行数据同步。

**请求体格式：**

```json
{
  "config": {
    "base_url": "https://yourdomain.com",
    "consumer_key": "ck_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "consumer_secret": "cs_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "kind": "products"
  },
  "data": null
}
```

**参数说明：**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `base_url` | string | 是 | WooCommerce 店铺根 URL（不含 `/wp-json/...`） |
| `consumer_key` | string | 是 | WooCommerce API Consumer Key |
| `consumer_secret` | string | 是 | WooCommerce API Consumer Secret |
| `kind` | string | 是 | 同步类型：`orders`、`products`、`customers` |
| `data` | array | 否 | 直接推送的数据数组（如果提供，则不调用 REST API） |

### 方式二：环境变量配置（可选）

在 `.env` 文件中添加以下配置（用于默认连接，API 调用时可不传 config）：

```env
WOOCOMMERCE_BASE_URL=https://yourdomain.com
WOOCOMMERCE_CONSUMER_KEY=ck_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
WOOCOMMERCE_CONSUMER_SECRET=cs_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
WOOCOMMERCE_WEBHOOK_SECRET=your-webhook-secret
```

---

## 测试连接

### 测试 1：同步产品数据

```bash
curl -X POST http://localhost:8000/api/v1/connectors/woocommerce/sync \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "base_url": "https://yourdomain.com",
      "consumer_key": "ck_...",
      "consumer_secret": "cs_...",
      "kind": "products"
    }
  }'
```

**预期响应：**

```json
{
  "id": "uuid",
  "connector": "woocommerce",
  "status": "completed",
  "summary": {
    "total": 50,
    "created": 45,
    "updated": 5,
    "failed": 0,
    "errors": []
  }
}
```

### 测试 2：同步订单数据

```bash
curl -X POST http://localhost:8000/api/v1/connectors/woocommerce/sync \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "base_url": "https://yourdomain.com",
      "consumer_key": "ck_...",
      "consumer_secret": "cs_...",
      "kind": "orders"
    }
  }'
```

### 测试 3：同步客户数据

```bash
curl -X POST http://localhost:8000/api/v1/connectors/woocommerce/sync \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "base_url": "https://yourdomain.com",
      "consumer_key": "ck_...",
      "consumer_secret": "cs_...",
      "kind": "customers"
    }
  }'
```

### 查看同步记录

```bash
curl http://localhost:8000/api/v1/connector-runs
```

---

## 数据同步

### 支持的数据类型

| 类型 | kind 值 | 说明 |
|---|---|---|
| 产品 | `products` | 同步 WooCommerce 产品到产品主数据（按 SKU 去重） |
| 订单 | `orders` | 同步订单到订单系统（按外部订单 ID 去重） |
| 客户 | `customers` | 同步客户到客户画像（PII 脱敏，仅保存哈希引用） |

### 同步策略

- **幂等性**：所有同步操作都是幂等的，重复同步不会创建重复数据
- **产品**：按 SKU 进行 upsert（存在则更新，不存在则创建）
- **订单**：按外部订单 ID 进行去重
- **客户**：按客户引用哈希进行 upsert

### PII 隐私保护

客户数据同步遵循严格的隐私保护策略：
- 客户姓名、邮箱、地址等 PII 数据**不会**存储在 Nuotao AI OS 中
- 仅保存客户身份的确定性哈希引用（SHA-256，前 40 位）
- 用于订单关联和客户行为分析，不暴露个人身份信息

---

## Webhook 配置

WooCommerce 支持通过 Webhook 实时推送数据变更到 Nuotao AI OS。

### 步骤 1：在 WooCommerce 中创建 Webhook

1. 进入 WordPress 后台 → **WooCommerce** → **设置** → **高级** → **Webhooks**
2. 点击 **添加 Webhook**
3. 填写以下信息：
   - **名称**：`Nuotao AI OS Order Sync`
   - **状态**：已启用
   - **主题**：选择 `订单已创建`（order.created）或其他需要的事件
   - **传送 URL**：`https://your-nuotao-domain.com/api/v1/webhooks/woocommerce`
   - **密钥**：设置一个安全的密钥（与 `.env` 中的 `WOOCOMMERCE_WEBHOOK_SECRET` 一致）
   - **API 版本**：WP REST API Integration v3
4. 点击 **保存 Webhook**

### 步骤 2：配置 Nuotao AI OS Webhook 密钥

在 `.env` 文件中设置：

```env
WOOCOMMERCE_WEBHOOK_SECRET=your-webhook-secret
```

### 支持的 Webhook 事件

- `order.created` - 订单创建
- `order.updated` - 订单更新
- `product.created` - 产品创建
- `product.updated` - 产品更新
- `customer.created` - 客户创建
- `customer.updated` - 客户更新

---

## 故障排查

### 问题 1：401 Unauthorized

**原因**：API 密钥不正确或权限不足。

**解决方案**：
1. 确认 Consumer Key 和 Consumer Secret 正确无误
2. 确认 API 密钥的权限至少为"读取"
3. 确认 WooCommerce REST API 已启用（WooCommerce → 设置 → 高级 → REST API）

### 问题 2：404 Not Found

**原因**：WooCommerce REST API 端点不可访问。

**解决方案**：
1. 确认 WordPress 固定链接已启用（设置 → 固定链接 → 非"朴素"）
2. 确认 WooCommerce 插件已启用
3. 测试访问 `https://yourdomain.com/wp-json/wc/v3/products` 是否返回数据

### 问题 3：SSL 证书错误

**原因**：WooCommerce 店铺使用自签名证书或证书无效。

**解决方案**：
1. 生产环境建议使用有效的 SSL 证书（Let's Encrypt 等）
2. 开发环境可在请求中禁用 SSL 验证（不推荐生产环境）

### 问题 4：同步超时

**原因**：数据量过大或网络延迟。

**解决方案**：
1. 分批同步（WooCommerce REST API 默认每页 10 条，最大 100 条）
2. 增加超时时间
3. 先同步产品，再同步订单，最后同步客户

### 问题 5：产品同步后数据不完整

**原因**：WooCommerce 产品字段映射问题。

**解决方案**：
1. 确认 WooCommerce 产品包含必要字段（SKU、名称、价格等）
2. 查看同步记录中的错误信息
3. 检查 Nuotao AI OS 日志中的详细错误

---

## 安全建议

1. **API 密钥权限**：生产环境使用最小权限原则，仅授予"读取"权限
2. **密钥存储**：API 密钥存储在环境变量或密钥管理服务中，不要硬编码在代码中
3. **HTTPS**：确保 WooCommerce 店铺和 Nuotao AI OS 都使用 HTTPS
4. **Webhook 密钥**：使用强随机密钥验证 Webhook 签名
5. **定期轮换**：定期轮换 API 密钥（建议每 90 天）
6. **审计日志**：定期查看连接器运行记录，监控异常同步行为

---

## 下一步

配置完成 WooCommerce 集成后，你可以：

1. **使用产品分析师 AI**：对同步的产品进行 AI 分析和选品建议
2. **订单数据分析**：分析订单趋势、客户行为、热销产品
3. **营销活动策划**：基于订单和客户数据，使用营销经理 AI 策划营销活动
4. **供应链优化**：基于订单和库存数据，使用供应链经理 AI 优化采购和库存
5. **客户服务改进**：基于客户反馈和订单数据，使用客服经理 AI 改进服务流程

---

## 联系与支持

如遇到配置问题，请查看：
- Nuotao AI OS 后端日志
- WooCommerce 系统状态（WooCommerce → 状态）
- WordPress 调试日志
