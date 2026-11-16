# 1688 采购ERP对接 API 申请指南

## 📋 核心发现：您需要「采购解决方案」而非「跨境综合解决方案」

根据1688开放平台的官方文档，您作为**跨境买家**需要的是：

> **"买卖家自开发模式"** - 有开发能力的1688商家或买家，使用平台解决方案，开发满足自身电商场景所需的工具，如买家采购场景。

---

## 🔑 所需API能力

### 商品搜索与详情（核心需求）

| API名称 | 功能 | 适用场景 |
|---------|------|----------|
| `product.search` | 关键词搜索商品列表 | 选品、商品搜索 |
| `product.get` | 获取单个商品详情 | 获取标题、价格、SKU、图片 |
| `product.imageSearch` | 图片搜索相似商品 | 以图搜款 |
| `product.category.get` | 获取商品类目树 | 商品分类筛选 |

### 交易相关（采购下单）

| API名称 | 功能 | 适用场景 |
|---------|------|----------|
| `order.create` | 创建订单 | 自动采购下单 |
| `order.get` | 查询订单详情 | 订单状态跟踪 |
| `order.list` | 查询订单列表 | 批量订单管理 |
| `payment.create` | 发起支付 | 批量付款 |

---

## 📝 申请流程

### Step 1: 评估接口是否符合业务模式
- ✅ 确认API功能覆盖您的选品、导入、采购需求
- ✅ 确认月度GMV目标 ≥ 160,000元

### Step 2: 联系跨境小二加白名单
```
📍 钉钉搜索：sicongwz（跨境小二）
📍 或访问：https://work.1688.com
```

**发送消息模板：**
```
您好，我司（广西诺涛户外运动用品有限公司，1688账号tb638676）需要申请
「采购解决方案」API权限，用于ERP系统对接，实现商品搜索、详情获取、
自动下单采购等功能。

公司信息：
- 1688账号：tb638676
- AppKey：2819733
- 账号类型：采购服务商

预计调用量：日均200-300次
业务场景：跨境电商ERP系统对接

盼加白名单，谢谢！
```

### Step 3: 等待技术加白（通常1-3工作日）

### Step 4: 点击「立即订购」开通方案
```
访问: https://open.1688.com/solution/solutionDetail.htm?solutionKey=1697014160788
点击: 「立即订购」→ 选择「采购解决方案」
```

---

## ⚠️ API使用门槛要求

| 考核项 | 要求 | 说明 |
|--------|------|------|
| **月度GMV** | ≥ 160,000 元 | 通过1688站内及寻源通API成交的月销售额 |
| **单次调用GMV** | ≥ 0.5 元 | 月度销售额 / 月度API调用次数 |

**达标示例：**
```
月度GMV = 160,000 元
月度调用 = 320,000 次
单次GMV = 0.5 元 ✅ 达标
```

---

## 🔗 技术文档链接

### 开发指南
- [1688开放平台介绍](https://open.1688.com/doc/doc.htm?treeId=33&articleId=10017&docType=1)
- [API签名规则](https://open.1688.com/doc/doc.htm?treeId=40&articleId=10137&docType=1)
- [API调用说明](https://open.1688.com/doc/docList.htm?treeId=41&docType=1)

### 商品API文档
- [product.search 关键词搜索](https://open.1688.com/doc/docList.htm?treeId=40&docType=1)
- [product.get 商品详情](https://open.1688.com/doc/docList.htm?treeId=40&docType=1)
- [product.imageSearch 图片搜索](https://open.1688.com/doc/docList.htm?treeId=40&docType=1)

### 交易API文档
- [order.create 创建订单](https://open.1688.com/doc/docList.htm?treeId=40&docType=1)
- [order.get 订单查询](https://open.1688.com/doc/docList.htm?treeId=40&docType=1)

---

## 📞 联系方式

| 渠道 | 信息 |
|------|------|
| **钉钉** | 搜索：`sicongwz`（跨境小二） |
| **客服电话** | 400-800-1688 |
| **在线客服** | https://work.1688.com |
| **邮箱** | openapi@alibaba-inc.com |

---

## ✅ 申请前检查清单

- [ ] 确认1688账号：tb638676 已登录且状态正常
- [ ] 确认AppKey：2819733 已配置
- [ ] 确认契约身份：采购服务商
- [ ] 准备月度GMV目标（≥160,000元）
- [ ] 发送申请消息给跨境小二

---

## 🔄 后续步骤

1. **发送申请** → 通过钉钉联系 sicongwz
2. **等待加白** → 通常1-3个工作日
3. **点击订购** → 在开放平台点击「立即订购」
4. **技术对接** → 参考开发文档进行集成
5. **测试验证** → 使用沙箱环境测试API
6. **正式上线** → 切换生产环境
