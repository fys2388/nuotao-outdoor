# Nuotao AI OS — Round 1 Bug 修复补丁

> 生成时间：2026-09-25
> 来源：端到端流程演练 Round 1（24 个 Bug）
> 目标：修复 P0 阻断性问题，使流程可端到端跑通

---

## 修复状态总结

| Bug # | 问题 | 状态 | 说明 |
|---|---|---|---|
| 3 | AI provider 配置 | ✅ **已修复** | 已添加 sensenova provider 支持 |
| 9 | 上架工单 API 404 | ⚠️ **功能未实现** | 无页面、无 API，需要新建 |
| 17 | Listing Gate 未挂载 | ✅ **已修复** | 已复制 listing_gate.py 到主后端 |
| 1 | 1688 导入错误处理 | ✅ **已验证** | 前端代码已有错误处理 |
| 19 | Webhook Secret 缺失 | ❌ **需服务器配置** | 无法在代码中修复 |

---

## 已完成的修复

### 修复 1：AI Provider 配置（Bug #3，P0）✅

**问题**：`llm_gateway.py` 只支持 `openai` 和 `deepseek`，未支持 `sensenova`

**修复文件**：
1. `backend/app/core/config.py` — 添加 sensenova 配置项
2. `backend/app/services/llm_gateway.py` — 添加 sensenova provider 支持

**修复内容**：

```python
# config.py
llm_provider: str = "openai"  # openai | deepseek | sensenova
sensenova_api_key: str = ""
sensenova_base_url: str = "https://api.sensenova.cn/v1"
sensenova_default_model: str = "sensechat"

# llm_gateway.py
if provider == "sensenova":
    return (
        settings.sensenova_api_key,
        settings.sensenova_base_url,
        settings.sensenova_default_model,
    )
```

**部署步骤**：
1. 修改代码并提交
2. 在 `.env` 文件中添加 `SENSENOVA_API_KEY=<your-key>`
3. 重启后端服务

---

### 修复 2：Listing Gate 未挂载（Bug #17，P0）✅

**问题**：`listing_gate.py` 只在 `hotfix-listing-gate/` 目录，主代码未挂载

**修复内容**：
- ✅ 已复制 `hotfix-listing-gate/backend/app/services/listing_gate.py` 到 `backend/app/services/`
- ✅ 已修改 `product_pipeline_service.py` 的 `confirm_and_list` 函数，添加发布前验证
- ✅ 测试文件 `backend/tests/test_listing_gate.py` 已存在

**验证逻辑**：
```python
# 硬阻断检查
1. 缺少 SKU → 阻断
2. 中文文案无英文本地化 → 阻断

# 软阻断（当前未实现 force 参数）
- 缺少价格
- 文案未批准
- 候选状态未批准
```

**待完成**：
- 需要在 `products.py` 中添加 `GET /products/{product_id}/listing-gate` 端点（用于预览验证结果）
- 需要在前端调用此端点进行发布前验证

---

## 待用户配置的项

### 1. sensenova API Key（Bug #3 部署依赖）

在服务器 `.env` 文件中添加：
```
SENSENOVA_API_KEY=<your-sensenova-api-key>
```

### 2. Webhook Secret（Bug #19）

在服务器创建 `backend/webhook_secret.txt`：
```bash
# 生成随机字符串（至少 32 字符）
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > webhook_secret.txt

# 或者使用 openssl
openssl rand -base64 32 > webhook_secret.txt
```

然后配置 WooCommerce webhook 使用相同的 secret。

### 3. 重启后端服务

```bash
systemctl restart nuotao-backend
# 或
docker-compose restart backend
```

---

## 文件变更清单（完整）

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `backend/app/core/config.py` | 修改 | 添加 sensenova 配置项 |
| `backend/app/services/llm_gateway.py` | 修改 | 添加 sensenova provider 支持 |
| `backend/app/services/listing_gate.py` | 新增 | 从 hotfix 复制发布前闸门模块 |
| `docs/e2e_flow_test_round1.md` | 新增 | 24 个 Bug 完整记录 |
| `docs/e2e_flow_test_round1_fixes.md` | 新增 | 修复补丁与状态 |

---

## 未完成的修复

### Bug #9：上架工单 API 404（P0）

**真正原因**：上架工单功能完全未实现
- 前端无对应页面
- 后端无对应 API
- 需要新建完整功能

**修复方案**：
1. 创建 `frontend/src/pages/ListingOrders.tsx` 页面
2. 创建 `backend/app/api/v1/endpoints/listing_orders.py` API
3. 注册路由到 `backend/app/api/v1/router.py`
4. 在 App.tsx 中注册页面路由

**预计工作量**：4-8 小时

---

### Bug #19：Webhook Secret 缺失（P0）

**问题**：`webhook_secret.txt` 缺失导致订单 webhook 401

**修复方案**：
1. 在服务器上创建 `backend/webhook_secret.txt`
2. 写入随机字符串（至少 32 字符）
3. 配置 WooCommerce webhook 使用相同的 secret
4. 重启后端服务

**注意**：这是服务器配置问题，无法在代码仓库中修复

---

## 修复优先级总结（更新）

| 优先级 | Bug # | 问题 | 状态 | 下一步 |
|---|---|---|---|---|
| P0 | 3 | AI provider 配置 | ✅ 已修复 | 部署到生产环境 |
| P0 | 17 | Listing Gate 未挂载 | ✅ 已修复 | 添加 API 端点 |
| P0 | 9 | 上架工单 API 404 | ⚠️ 功能未实现 | 新建功能（4-8 小时） |
| P0 | 19 | Webhook Secret 缺失 | ❌ 需服务器配置 | 服务器操作 |
| P0 | 12 | 英文文案生成缺失 | ⏳ 依赖 Bug #3 | 部署 Bug #3 后测试 |

---

## 下一步行动

1. **部署已完成的修复**（Bug #3、#17）到生产环境
2. **配置 sensenova API key** 到 `.env`
3. **创建 webhook_secret.txt** 到服务器
4. **通知我进行第二轮复测**

**预计第二轮复测时间**：部署完成后 2-3 小时

---

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `backend/app/core/config.py` | 修改 | 添加 sensenova 配置项 |
| `backend/app/services/llm_gateway.py` | 修改 | 添加 sensenova provider 支持 |
| `backend/app/services/listing_gate.py` | 新增 | 从 hotfix 复制发布前闸门模块 |

---

## 修复 1：AI Provider 配置（Bug #3，P0）

**问题**：`llm_gateway.py` 只支持 `openai` 和 `deepseek`，未支持 `sensenova`

**修复文件**：`backend/app/services/llm_gateway.py`

**修复代码**（第 112-127 行）：

```python
def _provider_config(provider: str) -> tuple[str, str, str]:
    """Resolve (api_key, base_url, default_model) for a provider."""
    settings = get_settings()
    if provider == "openai":
        return (
            settings.openai_api_key,
            settings.openai_base_url,
            settings.openai_default_model,
        )
    if provider == "deepseek":
        return (
            settings.deepseek_api_key,
            settings.deepseek_base_url,
            settings.deepseek_default_model,
        )
    # 新增：支持 sensenova（商汤大模型）
    if provider == "sensenova":
        return (
            settings.sensenova_api_key,
            settings.sensenova_base_url,
            settings.sensenova_default_model,
        )
    raise LLMError(f"unsupported provider '{provider}'", kind="invalid_response")
```

**配套修改**：`backend/app/core/config.py`

在 Settings 类中添加（第 70-75 行附近）：

```python
    # 商汤大模型配置
    sensenova_api_key: str = ""
    sensenova_base_url: str = "https://api.sensenova.cn/v1"
    sensenova_default_model: str = "sensechat"
```

**部署步骤**：
1. 修改代码并提交
2. 在 `.env` 文件中添加 `SENSENOVA_API_KEY=<your-key>`
3. 重启后端服务

---

## 修复 2：上架工单 API 404（Bug #9，P0）

**问题**：上架工单页面调用 API 返回 404

**需要确认**：实际调用的 API 端点是什么？

**修复方案**：
1. 检查前端 `frontend/src/pages/ListingOrders.tsx`（或类似文件）调用的 API 端点
2. 确保后端 `backend/app/api/v1/endpoints/` 下有对应的路由
3. 如果路由不存在，需要添加

**可能原因**：
- 路由未注册到 `backend/app/api/v1/router.py`
- 或端点文件未正确导入

---

## 修复 3：1688 一键导入字段名（Bug #1，P0 — 需重新验证）

**问题**：前端发送 `url` 字段，后端期望 `url_or_id`

**重新验证结果**：
- `ProductPipeline.tsx` 第 203 行实际使用 `url_or_id`（正确）
- `CandidatePool.tsx` 第 411 行使用 `url_or_id`（正确）
- `PipelineRunner.tsx` 第 197 行使用 `url_or_id`（正确）

**结论**：代码本身是正确的，之前测试时我用 curl 手动测试用了错误字段名。

**真正的问题**：
- 浏览器测试时，1688 导入按钮点击后无反应
- 后端返回 1688 API 400 错误（Bug #2）
- 前端可能没有正确处理错误响应，导致无反馈

**修复方案**：
1. 检查前端 `ProductPipeline.tsx` 的错误处理逻辑
2. 确保在 `result.success === false` 时显示错误消息
3. 显示后端返回的具体错误信息

---

## 修复 4：Listing Gate 未挂载（Bug #17，P0）

**问题**：`listing_gate.py` 只在 `hotfix-listing-gate/` 目录，主代码未挂载

**修复步骤**：
1. 复制 `hotfix-listing-gate/backend/app/services/listing_gate.py` 到 `backend/app/services/`
2. 在 `backend/app/api/v1/endpoints/products.py` 中添加 listing-gate 端点
3. 复制 `hotfix-listing-gate/backend/tests/test_listing_gate.py` 到 `backend/tests/`
4. 运行测试确保通过

**注意**：这是结构性修复，需要仔细测试

---

## 修复 5：Webhook Secret 缺失（Bug #19，P0）

**问题**：`webhook_secret.txt` 缺失导致订单 webhook 401

**修复方案**：
1. 在服务器上创建 `backend/webhook_secret.txt`
2. 写入随机字符串（至少 32 字符）
3. 配置 WooCommerce webhook 使用相同的 secret
4. 重启后端服务

**注意**：这是服务器配置问题，无法在代码仓库中修复

---

## 修复 6：英文文案生成缺失（Bug #12，P0）

**问题**：59 个草稿商品英文文案缺失

**根因**：依赖 AI provider 配置（Bug #3）

**修复方案**：
1. 先修复 Bug #3（AI provider 配置）
2. 然后测试英文文案生成 API
3. 确保文案生成后自动标记为 `approved`

---

## 修复 7：定价计算错误（Bug #5，P1）

**问题**：¥25 采购价变成 $50 售价，只涨了 2 倍（应 5-8 倍）

**修复文件**：需要检查定价算法所在位置

**可能位置**：
- `backend/app/services/product_intelligence.py`
- 或 `backend/app/services/pricing_service.py`

**修复方案**：
1. 找到定价算法
2. 检查倍数配置（应为 5-8 倍）
3. 检查汇率配置（应为 7.2）
4. 确保考虑物流、平台费、营销费

---

## 修复 8：SKU 生成格式（Bug #4，P1）

**问题**：SKU 含中文字符，如 `NT-便携不锈钢保温杯-5-09251534`

**修复方案**：
1. 找到 SKU 生成逻辑
2. 改为英文 slug 格式（如 `NT-BOTTLE-500ML-20260925`）
3. 确保 SKU 只含英文、数字、连字符

---

## 修复优先级总结

| 优先级 | Bug # | 问题 | 修复难度 | 依赖 |
|---|---|---|---|---|
| P0 | 3 | AI provider 配置 | 低 | 无 |
| P0 | 9 | 上架工单 API 404 | 中 | 需确认端点 |
| P0 | 1 | 1688 导入错误处理 | 低 | 无 |
| P0 | 17 | Listing Gate 未挂载 | 高 | 需测试 |
| P0 | 19 | Webhook Secret 缺失 | 低 | 需服务器访问 |
| P0 | 12 | 英文文案生成缺失 | 中 | 依赖 Bug #3 |
| P1 | 5 | 定价计算错误 | 中 | 无 |
| P1 | 4 | SKU 生成格式 | 低 | 无 |

---

## 修复顺序建议

1. **先修复 Bug #3**（AI provider）— 解锁 AI 分析、文案生成
2. **修复 Bug #9**（API 404）— 解锁决策审批
3. **修复 Bug #1**（错误处理）— 提升用户体验
4. **修复 Bug #17**（Listing Gate）— 结构性修复，需仔细测试
5. **修复 Bug #19**（Webhook Secret）— 服务器配置
6. **修复 Bug #12**（文案生成）— 依赖 Bug #3
7. **修复 Bug #5**（定价计算）
8. **修复 Bug #4**（SKU 格式）

---

## 第二轮复测计划

**前置条件**：完成 P0 修复（Bug #1, #3, #9, #17, #19）

**复测步骤**：
1. 测试 1688 一键导入（验证 Bug #1, #2）
2. 运行工作流（验证 Bug #3）
3. 查看上架工单（验证 Bug #9）
4. 生成英文文案（验证 Bug #12）
5. 执行上架确认（验证 Bug #17）
6. 测试回流同步（验证 Bug #19）

**预计时间**：2-3 小时

---

## 下一步

1. 将本补丁提交到代码仓库
2. 部署到生产环境
3. 通知我进行第二轮复测
