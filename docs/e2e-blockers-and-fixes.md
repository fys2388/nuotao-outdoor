# E2E Blockers & Fixes (SKU-01 皮革游泳收纳包 → WC)

- 时间：2026-07-07
- 目标：单个 SKU（SKU-01 皮革游泳收纳包）跑通 Newton → 商品工作台 → 生成文案 → 推 WC → 前台可见
- 审批模式：A（人工在关键节点审批）
- 用户指令：**严禁自动跳过既定步骤**（m00800）

---

## 流程节点记录

### Step 1 · Newton 找品 ✅ 完成
- 输入：`户外防水收纳袋 30L 一件代发 适合跨境电商` + ¥10-35
- 耗时：约 5-6 分钟
- 积分消耗：1.2（从 9987.7 → 9986.5）
- 任务 ID：`3a553140…`
- 返回 2 款候选：
  - **#1** 皮革游泳收纳包干湿分离包，id=`800075224932`，URL `https://detail.1688.com/offer/800075224932.html`，¥14，3100+ 销量，超级工厂（义乌圣薇箱包 5 年），召回分 92 · S
  - **#2** 户外雪拉碗包餐具收纳袋，id=`676368516186`，¥10.3，30+ 销量，源头旗舰（义乌德通厚源 14 年），召回分 87 · S
- 目标选定：**SKU-01 = #1**（销量/成熟度高）

### Step 2 · 加入候选库 ❌ BLOCKED (Bug-12)

用户要求走标准流程（加入候选库 → V3.0 评分 → 选品审批闸门）。

发现 Newton 页面的「加入候选库」按钮**没有真实落库**：

- **文件**：`frontend/src/pages/NewtonSourcing.tsx:457`
- **代码**：
  ```javascript
  <Button
    size="small"
    icon={<StarOutlined />}
    onClick={() => message.success('已加入选品候选库')}  // ← 只弹提示！
  >
    加入候选
  </Button>
  ```
- **对比**：同页面「导入到工作流」按钮（`NewtonSourcing.tsx:461-487`）**是真功能**：
  ```javascript
  localStorage.setItem('product_pipeline_input', JSON.stringify(productData))
  window.location.hash = '#/product-pipeline'
  ```
- **现象**：点击后弹「已加入选品候选库」提示，但 `GET /api/v1/products` 或候选池 API 没有任何写入
- **V3.0 评分影响**：`CandidatePool.tsx` 页面理论上会显示评分入口，但因为 Newton → 候选库的数据链路是断的，评分流程空转
- **选品审批影响**：`POST /api/v1/products/{id}/approve-product-localization` 需要 candidate_id，而 candidate_id 从未创建
- **严重级别**：**高**——V3.0 评分 + 选品审批闸门形同虚设，任何 Newton 找到的商品都只能走「导入到工作流」绕过审批

**候选路径选择**：

| 路径 | 描述 | 合规性 | 可用性 |
|---|---|---|---|
| 加入候选库（按钮） | 空壳，无落库 | ❌ | ❌ 不可用 |
| 导入到工作流 | 写 localStorage + 跳 product-pipeline | ⚠️ 绕过候选池评分 | ✅ 可用（但违反 SOP） |

**决策**：由于用户 m00800 明确要求「严格执行既定步骤」+「严禁自动跳过」，而既定步骤的入口（加入候选库）本身是空壳，**该步骤在当前代码状态下无法通过既有按钮完成**。

- **选项 A**：修 `NewtonSourcing.tsx:457` 让它真发 API 落候选库，再重跑 Newton → 加入候选库 → V3.0 评分 → 审批
- **选项 B**：直接调后端 API（`POST /api/v1/products`）创建 candidate + 手工推进状态到 `scored`，然后走审批
- **选项 C**：记录此 blocker，改用「导入到工作流」（承认审批闸门失效，直接走通到 WC 前台）

等用户裁决。

---

## Blocker 汇总（截至本次运行）

| ID | 位置 | 类型 | 严重级别 |
|---|---|---|---|
| Bug-12 | `NewtonSourcing.tsx:457` | 加入候选库是空壳（UI 假成功） | 高 |
| Bug-01 | `product_pipeline.py` | push-woocommerce HTTP 200 但产品未创建 | 高 |
| Bug-02 | 同上 | 生成文案缺 bullet points | 中 |
| Bug-03 | 同上 | 强制校验声明与实现不一致 | 中 |
| Bug-07 | 后端 | 一键导入依赖 `ALI1688_APP_KEY` | 待验证 |

## 累计积分消耗
- Newton 找品：1.2（9987.7 → 9986.5）
- 后续流程未消耗
