# WooCommerce 快速配置指南

## 3 步完成 WooCommerce 集成

---

## 第 1 步：获取 API 密钥

1. 登录 WordPress 后台：`https://你的店铺.com/wp-admin`
2. 进入 **WooCommerce → 设置 → 高级 → REST API**
3. 点击 **添加密钥**
4. 填写：
   - 描述：`Nuotao AI OS`
   - 用户：管理员
   - 权限：**读取**（只读集成，安全）
5. 点击 **生成 API 密钥**
6. 保存以下信息（只显示一次！）：
   - Consumer Key：`ck_xxxxxxxxxxxxxxxx`
   - Consumer Secret：`cs_xxxxxxxxxxxxxxxx`

---

## 第 2 步：测试连接

在项目根目录运行：

```bash
cd backend
python configure_woocommerce.py --test \
  --base-url https://你的店铺.com \
  --consumer-key ck_xxxxxxxx \
  --consumer-secret cs_xxxxxxxx
```

**预期输出：**
```
✅ Connection successful!
Store: 你的店铺名称
WooCommerce Version: 8.x.x
Currency: USD
Products: 50
Orders: 120
Customers: 80
```

---

## 第 3 步：保存配置并同步数据

### 保存到 .env

```bash
python configure_woocommerce.py --save-env \
  --base-url https://你的店铺.com \
  --consumer-key ck_xxxxxxxx \
  --consumer-secret cs_xxxxxxxx
```

### 同步产品

```bash
# 测试获取产品
python configure_woocommerce.py --sync products --per-page 5

# 通过 API 端点同步到 Nuotao AI OS
curl -X POST http://localhost:8000/api/v1/connectors/woocommerce/sync \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "base_url": "https://你的店铺.com",
      "consumer_key": "ck_xxxxxxxx",
      "consumer_secret": "cs_xxxxxxxx",
      "kind": "products"
    }
  }'
```

### 同步订单

```bash
curl -X POST http://localhost:8000/api/v1/connectors/woocommerce/sync \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "base_url": "https://你的店铺.com",
      "consumer_key": "ck_xxxxxxxx",
      "consumer_secret": "cs_xxxxxxxx",
      "kind": "orders"
    }
  }'
```

### 同步客户

```bash
curl -X POST http://localhost:8000/api/v1/connectors/woocommerce/sync \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "base_url": "https://你的店铺.com",
      "consumer_key": "ck_xxxxxxxx",
      "consumer_secret": "cs_xxxxxxxx",
      "kind": "customers"
    }
  }'
```

---

## 常见问题

### Q: 测试连接返回 401 Unauthorized
**A:** 检查 Consumer Key 和 Secret 是否正确，确认 API 密钥权限为"读取"。

### Q: 测试连接返回 404 Not Found
**A:** 确认 WooCommerce REST API 已启用，固定链接设置为非"朴素"模式。

### Q: 如何配置 Webhook 实时同步？
**A:** 参见 `docs/woocommerce_setup_guide.md` 中的 Webhook 配置章节。

### Q: 客户数据会存储 PII 吗？
**A:** 不会。Nuotao AI OS 仅保存客户身份的哈希引用，不存储姓名、邮箱、地址等个人信息。

---

## 下一步

配置完成后，你可以：
1. 在前端控制台查看同步的产品和订单
2. 使用产品分析师 AI 对产品进行选品分析
3. 使用商业分析师 AI 分析订单数据和销售趋势
4. 使用营销经理 AI 基于客户数据策划营销活动
