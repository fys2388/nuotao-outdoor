# 1688 API 对接指南

## 当前状态
- 服务实现: ✅ 完整（搜索/详情/供应商/价格趋势）
- API密钥: ❌ 未配置（当前Mock降级模式）
- Mock数据: ✅ 可用（保证闭环测试）

## 对接步骤

### 1. 申请1688开放平台账号
- 访问: https://open.1688.com/
- 注册开发者账号
- 完成企业认证（需要营业执照）

### 2. 创建应用
- 在控制台创建"自用型应用"
- 获取 App Key 和 App Secret
- 记录到 .env 文件

### 3. 申请API权限
需要申请以下API分组权限:
- 商品搜索: `alibaba.product.search`
- 商品详情: `alibaba.product.get`
- 供应商信息: `alibaba.member.get`
- 价格趋势: `alibaba.product.price.trend`（如有）

### 4. 配置环境变量
在 backend/.env 中填入:
```
ALI1688_APP_KEY=你的AppKey
ALI1688_APP_SECRET=你的AppSecret
```

### 5. 验证对接
重启后端服务后，调用:
- `GET /sourcing/1688/search?keyword=camping+tent`
- 检查返回的 `source` 字段是否为 `1688_api_real`

## 已实现功能
| 功能 | 端点 | Mock | 真实API |
|------|------|------|---------|
| 产品搜索 | /sourcing/1688/search | ✅ | ✅ |
| 产品详情 | /sourcing/1688/product/{id} | ✅ | ✅ |
| 供应商信息 | /sourcing/1688/supplier/{id} | ✅ | ✅ |
| 价格趋势 | /sourcing/1688/price-trend/{id} | ✅ | ✅ |

## 降级策略
- 未配置密钥 → 自动使用Mock数据
- API调用失败 → 自动降级为Mock
- 所有响应包含 `source` 字段标识数据来源

## 成本与限制
- 1688开放平台: 免费申请，按调用量计费
- 建议设置每日调用上限（在服务中配置）
- 生产环境建议加缓存（Redis）减少API调用
