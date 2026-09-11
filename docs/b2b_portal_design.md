# B2B 代理商门户（端子）设计文档

> 版本：v1.0
> 状态：设计中
> 创建日期：2026-09-09
> 关联：`docs/development_roadmap.md` M6 里程碑、`docs/business_context.md` 阶段3

---

## 1. 目标与范围

### 1.1 目标

搭建独立的 B2B 代理商门户端子（`b2b.nuotaooutdoor.com`），使海外代理商能够：

- 自助登录门户
- 浏览批发价目表（按代理商等级差异化定价）
- 在线批量下单
- 查询订单状态与物流
- 查看账户信用额度与账单

### 1.2 范围（MVP）

| 模块 | 包含 | 不包含（后续迭代） |
|---|---|---|
| 代理商认证 | 邮箱/密码登录、JWT、密码重置 | 社交登录、SSO |
| 商品目录 | 商品列表、详情、批发价、库存 | 高级筛选、对比、收藏 |
| 下单 | 购物车、批量下单、订单提交 | 在线支付（先账期/对公转账） |
| 订单管理 | 订单列表、详情、状态跟踪 | 退换货流程、发票 |
| 账户中心 | 代理商资料、信用额度、账单 | 佣金报表、文档下载 |

### 1.3 与现有系统的关系

- **内部管理控制台**（`admin.nuotaooutdoor.com`）：运营人员管理代理商审批、定价、订单履约。现有 `B2BAgents.tsx` 页面升级为对接真实 API。
- **B2B 代理门户**（`b2b.nuotaooutdoor.com`）：面向代理商的自助站点，独立部署。
- **DTC 独立站**（`nuotaooutdoor.com`）：面向消费者，不受影响。
- **共享后端**：同一个 FastAPI 服务，B2B 门户 API 使用独立路由前缀 `/api/v1/b2b-portal/`，代理商认证独立于内部用户认证。

---

## 2. 域名与部署架构

```
                    ┌─────────────────────────┐
                    │   Nginx (Hetzner VPS)    │
                    │                         │
  nuotaooutdoor.com │── server_block ──► WooCommerce (Docker)
  admin.nuotao...   │── server_block ──► 前端控制台 + FastAPI /api
  b2b.nuotao...     │── server_block ──► B2B门户前端 + FastAPI /api/v1/b2b-portal
                    └─────────────────────────┘
```

- **子域名**：`b2b.nuotaooutdoor.com`
- **SSL**：Let's Encrypt（certbot --nginx）
- **前端部署路径**：`/var/www/b2b-portal/`
- **API 反代**：`b2b.nuotaooutdoor.com/api/` → `127.0.0.1:8000/api/`

---

## 3. 数据模型设计

### 3.1 b2b_agents（代理商账号）

独立于内部 `users` 表，代理商是外部实体。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| agent_number | String(32) UNIQUE | 代理商编号 AG-YYYYMMDD-XXXX |
| company_name | String(200) | 公司名称 |
| contact_name | String(100) | 联系人 |
| email | String(255) UNIQUE | 登录邮箱 |
| phone | String(50) | |
| country | String(64) | |
| city | String(100) | |
| address | String(500) | |
| hashed_password | String(255) | |
| tier | String(16) | bronze/silver/gold/platinum |
| status | String(16) | pending/active/suspended/rejected |
| commission_rate | Numeric(5,2) | 佣金率 % |
| discount_percent | Numeric(5,2) | 额外折扣 % |
| credit_limit | Numeric(12,2) | 信用额度 |
| current_balance | Numeric(12,2) | 当前欠款 |
| payment_terms_days | Integer | 账期天数 |
| currency | String(8) | 结算货币，默认 USD |
| notes | Text | 运营备注 |
| last_login_at | DateTime | |
| created_at / updated_at | DateTime | |

### 3.2 b2b_product_prices（分级定价）

商品批发价按等级配置，支持单个代理商覆盖。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| product_id | UUID FK → products.id | |
| tier | String(16) NULL | bronze/silver/gold/platinum，NULL 表示代理商专属 |
| agent_id | UUID FK → b2b_agents.id NULL | 专属定价时指定 |
| wholesale_price | Numeric(12,2) | 批发单价 |
| moq | Integer | 最小起订量 |
| currency | String(8) | |
| is_active | Boolean | |
| created_at / updated_at | DateTime | |

唯一约束：`(product_id, tier)` 当 agent_id IS NULL；`(product_id, agent_id)` 当 tier IS NULL。

定价优先级：代理商专属 > 等级定价 > 商品默认零售价 × (1 - discount_percent)。

### 3.3 b2b_orders（B2B 订单）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| order_number | String(32) UNIQUE | B2B-YYYYMMDD-XXXX |
| agent_id | UUID FK → b2b_agents.id | |
| status | String(16) | pending/confirmed/processing/shipped/delivered/cancelled |
| payment_status | String(16) | unpaid/partial/paid/overdue |
| subtotal | Numeric(12,2) | |
| discount_amount | Numeric(12,2) | |
| shipping_cost | Numeric(12,2) | |
| total | Numeric(12,2) | |
| currency | String(8) | |
| shipping_address | JSONB | 收货地址 |
| payment_due_date | Date | 账期到期日 |
| tracking_number | String(100) NULL | |
| tracking_carrier | String(50) NULL | |
| notes | Text | |
| created_at / updated_at | DateTime | |

### 3.4 b2b_order_items（订单明细）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| order_id | UUID FK → b2b_orders.id | |
| product_id | UUID FK → products.id | |
| product_name | String(255) | 快照 |
| sku | String(64) | 快照 |
| quantity | Integer | |
| unit_price | Numeric(12,2) | 快照（下单时批发价） |
| subtotal | Numeric(12,2) | |

---

## 4. API 设计

所有 B2B 门户 API 前缀：`/api/v1/b2b-portal`

### 4.1 认证

| 方法 | 路径 | 说明 | 鉴权 |
|---|---|---|---|
| POST | /auth/login | 邮箱密码登录，返回 JWT | 公开 |
| GET | /auth/me | 当前代理商信息 | Bearer |
| POST | /auth/change-password | 修改密码 | Bearer |

JWT payload 包含 `sub`（agent_id）、`role: "b2b_agent"`、`tier`。

### 4.2 商品

| 方法 | 路径 | 说明 | 鉴权 |
|---|---|---|---|
| GET | /products | 商品列表（含该代理商批发价、库存） | Bearer |
| GET | /products/{id} | 商品详情 | Bearer |

查询参数：`page`、`page_size`、`category`、`search`、`in_stock_only`。

### 4.3 购物车（前端 localStorage，不存后端）

MVP 阶段购物车存前端 localStorage，下单时直接提交。

### 4.4 订单

| 方法 | 路径 | 说明 | 鉴权 |
|---|---|---|---|
| POST | /orders | 创建订单（提交购物车） | Bearer |
| GET | /orders | 我的订单列表 | Bearer |
| GET | /orders/{id} | 订单详情（含明细） | Bearer |

### 4.5 账户

| 方法 | 路径 | 说明 | 鉴权 |
|---|---|---|---|
| GET | /account/summary | 账户概览（信用额度、余额、账期） | Bearer |
| GET | /account/transactions | 账单流水 | Bearer |

---

## 5. 前端门户设计

### 5.1 技术栈

- React 18 + Vite + TypeScript（与控制台一致）
- Ant Design 6
- 独立构建产物，部署到 `/var/www/b2b-portal/`
- API base：`/api/v1/b2b-portal`（同域反代）

### 5.2 页面结构

```
/login                    登录页
/                         首页（品牌介绍 + 热门商品）
/products                 商品列表
/products/:id             商品详情
/cart                     购物车
/checkout                 确认下单
/orders                   我的订单
/orders/:id               订单详情
/account                  账户中心
```

### 5.3 关键交互

- 未登录访问商品页 → 跳转登录（B2B 价格不公开）
- 商品列表显示批发价（按登录代理商等级）、MOQ、库存
- 购物车支持修改数量、MOQ 校验
- 下单时显示信用额度占用、账期到期日
- 订单详情显示物流跟踪号（如有）

---

## 6. 安全与合规

1. **认证隔离**：代理商 JWT 与内部用户 JWT 使用不同的 token type claim（`token_type: "b2b_access"`），防止跨域越权。
2. **数据隔离**：所有 B2B 门户 API 强制过滤 `agent_id = current_agent.id`，代理商只能看到自己的订单和数据。
3. **价格保密**：批发价仅对已登录且状态为 active 的代理商可见。
4. **PII 保护**：代理商地址、电话等字段加密存储（L4 级别），日志脱敏。
5. **限流**：登录接口限流（5次/分钟/IP），防止暴力破解。
6. **审批流**：新代理商注册需运营审批（status=pending → active），MVP 阶段由运营在后台手动创建账号。

---

## 7. 实施步骤

| 步骤 | 内容 | 产出 |
|---|---|---|
| 1 | 数据模型 + Alembic 迁移 | `b2b_agent.py`、迁移文件 |
| 2 | B2B 门户 API（认证、商品、订单、账户） | `b2b_portal.py` 端点 + `b2b_portal_service.py` |
| 3 | 前端 B2B 门户 | `frontend-b2b/` 独立项目 |
| 4 | 内部控制台 B2B 管理对接真实 API | 升级 `B2BAgents.tsx` |
| 5 | Nginx 配置 + SSL + 部署 | 部署脚本、上线 |
| 6 | 测试验证 | 单元测试 + 端到端验证 |

---

## 8. 后续迭代（Backlog）

- 代理商自助注册 + 审批流
- 在线支付（Stripe B2B / PayPal）
- 退换货流程
- 佣金报表与自动结算
- B2B 开放 API（带 API Key + 配额）
- 多语言（德语等）
- 商品高级筛选与收藏
- 文档下载中心（产品手册、认证文件）

---

## 9. 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-09-09 | 初稿，B2B 端子 MVP 设计 |
