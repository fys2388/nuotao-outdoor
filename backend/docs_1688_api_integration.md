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

---

# 阿里牛顿（Newton Cloud）AI Agent 接入指南

## 当前状态
- 服务实现: 完整（create/get/fetch/listModels/await_result/newton_agent_search/batch_inquiry）
- API凭证: 未配置（当前Mock降级模式，需appKey+appSecret+accessToken）
- Mock数据: 可用（保证闭环测试）
- 官方SDK: 仅Java SDK（newton-openapi-sdk），本项目为Python原生实现

## 牛顿 vs 传统1688 API

| 维度 | 传统1688 API | 阿里牛顿AI Agent |
|------|-------------|----------------|
| 找品方式 | 关键词+结构化参数 | 自然语言（帮我找户外灯10-30元） |
| 核心能力 | 搜索/详情/供应商/价格 | AI找品+比价+批量询盘+商品对比 |
| 认证方式 | appKey+Secret+MD5签名 | appKey+Secret+accessToken(OAuth) |
| 费用 | 5000次/日免费 | 免费（积分制，每日300积分） |
| 门槛 | 企业认证（营业执照） | 1688账号+绑定店铺 |
| 适用场景 | 批量数据采集/价格监控 | 智能选品/自然语言找品/询盘 |

## 对接步骤

### 1. 登录牛顿平台绑定店铺
- 访问: https://air.1688.com/app/newton/newton-cloud-open/
- 用1688账号登录，绑定1688店铺
- 每日登录领取300积分（单次调用消耗20-100积分）

### 2. 创建应用获取凭证
- 访问: https://open.1688.com/
- 创建自用型应用，获取 App Key 和 App Secret
- 申请牛顿云Agent API权限

### 3. OAuth授权获取Access Token
- 在应用控制台点击1688授权
- 授权完成后获取 access_token（有有效期，需定期刷新）

### 4. 配置环境变量
在 backend/.env 中填入:
ALI1688_APP_KEY=你的AppKey
ALI1688_APP_SECRET=你的AppSecret
ALI1688_ACCESS_TOKEN=你的AccessToken

### 5. 验证对接
运行: python verify_newton_agent.py
检查输出中 source 字段是否为 newton_api（非mock）

## 已实现功能

| 功能 | 函数 | Mock | 真实API |
|------|------|------|---------|
| 创建Agent任务 | create_agent_task(message, auto) | 是 | 是 |
| 查询任务状态 | get_task_status(task_id) | 是 | 是 |
| 获取任务结果 | fetch_task_result(task_id) | 是 | 是 |
| 列出可用模型 | list_models() | 是 | 是 |
| 一键调用(创建+轮询) | await_result(message, auto) | 是 | 是 |
| AI智能找品(高层封装) | newton_agent_search(query, ...) | 是 | 是 |
| 批量询盘 | batch_inquiry(product_ids, ...) | 是 | 是 |

## 使用示例

from app.services.newton_agent_service import newton_agent_search

result = newton_agent_search(
    query="户外露营灯",
    min_price=10,
    max_price=30,
    min_order_qty=50,
)

for product in result["products"]:
    print(f"[{product['score']}分] {product['subject']} - {product['price']}元")
    print(f"  推荐理由: {product['reason']}")

print(f"AI总结: {result['summary']}")

## 降级策略
- 未配置完整凭证 -> 自动使用Mock数据
- API调用失败 -> 自动降级为Mock
- 所有响应包含 source 字段（newton_api / mock）

## 成本与限制
- 牛顿平台: 免费（积分制，每日登录领300积分）
- 单次技能调用: 消耗20-100积分
- 生产环境: 加Redis缓存减少重复调用

## 与选品闭环集成
- 传统API: 精确批量采集（sourcing_1688_service.search_products()）
- 牛顿AI: 自然语言智能找品+比价+推荐（newton_agent_service.newton_agent_search()）
- 两者互补，根据场景选择使用
