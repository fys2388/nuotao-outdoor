# 1688 统一数据源 Provider 架构设计

> D8-E P1 产出。对应指令：建立统一数据源架构（仅设计与可行性评估，未经 Owner 批准不实施生产切换）。
> 日期：2026-11-20。配套文档：`1688_DATA_PROVIDER_EVALUATION.md`。

## 0. 设计目标（来自指令）

七条硬要求：
1. 商品数据必须记录来源。
2. 每次采集记录时间、商品 ID、来源和原始证据。
3. 真实数据与模拟数据严格隔离。
4. 来源不可信或验证失败时 fail-closed。
5. 不允许硬编码兜底数据进入自动采购、定价和上架流程。
6. 支持不同 Provider 平滑切换。
7. 不改变现有商品分析 Agent 的业务接口。

## 1. 现状与切入点

现有 `sourcing_1688_service.py` 已是事实上的单一 Provider，返回带 `source` 字段（`1688_open_api` / `1688_api_estimated` / `mock`），未配置时静默降级 Mock。问题：
- 无统一抽象，Provider 切换需改调用方。
- Mock 降级是"静默成功"（`success=True` 但 `source=mock`），易被上层误用。
- 采集元数据（时间/原始证据）未结构化落库。

切入点：在 service 层之上引入 **Provider 抽象 + 元数据信封**，不改 Agent 调用的函数签名（保持 `search_products/get_product_detail/...` 业务接口不变）。

## 2. 架构分层

```
┌─────────────────────────────────────────────┐
│  商品分析 Agent（选品/定价/上架）            │  ← 业务接口不变
│  调用 sourcing_1688_service.search/detail    │
└──────────────────┬──────────────────────────┘
                   │  (业务接口层，签名不变)
        ┌──────────▼──────────┐
        │ 1688DataProvider    │  ← 新增：统一抽象 + 路由 + fail-closed
        │ (路由/校验/信封)    │
        └──────────┬──────────┘
                   │ 选择 Provider
   ┌───────────────┼───────────────┬──────────────────┐
   ▼               ▼               ▼                  ▼
Official1688   AuthorizedThird  BrowserSession    (MockProvider
APIProvider    PartyProvider    Provider          仅测试环境)
(寻源通/simple │ (牛顿 Agent /   │ (现有 Playwright
 .get)         │  未来合规第三方)│  Cookie，临时过渡)
```

## 3. 数据信封（采集元数据）

所有 Provider 返回统一 `ProviderResult`，强制携带可审计元数据：

```python
@dataclass
class Provenance:
    provider: str          # "official_1688_api" | "third_party_newton" | "browser_session" | "mock"
    method: str            # 具体接口，如 "alibaba.product.simple.get"
    product_id: str
    fetched_at: str        # UTC ISO8601
    raw_evidence_ref: str  # 原始响应摘要/引用（不含凭据）
    verified: bool         # 是否通过真实性校验

@dataclass
class ProviderResult:
    ok: bool               # 是否拿到可信真实数据
    data: dict | None      # 归一化商品数据（ok=False 时为 None）
    provenance: Provenance
    degraded: bool = False # 是否降级（如 estimated/fallback）
    fail_closed_reason: str | None = None
```

关键：`ok` 与 `data` 绑定——**拿不到可信真实数据时 `ok=False` 且 `data=None`**，不再返回 `success=True` + 假数据。

## 4. 三个 Provider 契约

统一接口（抽象基类）：

```python
class I1688Provider(Protocol):
    name: str
    def is_available(self) -> bool: ...
    def search(self, keyword: str, **kw) -> ProviderResult: ...
    def get_detail(self, product_id: str) -> ProviderResult: ...
```

| Provider | 实现 | 生产可用 | 定位 |
|---|---|---|---|
| `Official1688APIProvider` | 寻源通 API（主）/ `simple.get`（过渡降级） | 条件就绪 | 生产自动流转主源 |
| `AuthorizedThirdPartyProvider` | 牛顿 Agent（找品建议）/ 未来合规第三方 | 否（建议层） | AI 找品建议，关键动作人审 |
| `BrowserSessionProvider` | 现有 Playwright + Cookie | 否（过渡） | 应急过渡，Cookie 过期即 fail-closed |
| `MockProvider` | 现有 mock | **仅测试环境** | 单元测试，生产禁用 |

## 5. 真实/模拟严格隔离

- `MockProvider` **只在测试环境注册**（`settings.ENV != "prod"`）。生产路由表物理上不含 Mock，杜绝误用。
- 所有 `estimated`（如 `get_price_trend` ±5% 模拟）、`degraded=True` 的结果，标记 `verified=False`，**不进入自动采购/定价/上架**。
- PR#13 闸门保持：`hardcoded_fallback` 数据阻断 `auto_run_pipeline`，并在此架构下沉为"永不注册到生产路由"。

## 6. Fail-closed 路由策略

```
请求 → 路由器按优先级选可用 Provider
  1. Official1688APIProvider.is_available()? → 用之
  2. 否则若 env=prod → **fail-closed**：返回 ok=False + fail_closed_reason
     （绝不静默降级到 Mock/fallback/浏览器抓取）
  3. env≠prod（开发/测试）→ 可降级 Mock，但 provenance.provider="mock"
```

- 来源不可信 / 验证失败 / Cookie 过期 → `ok=False`，上层收到明确失败而非假数据。
- 与 PR#13 一致：自动上架链路遇 `ok=False` 或 `degraded=True` 一律阻断。

## 7. 平滑切换

Provider 通过配置选择（如 `DATA_PROVIDER=official|third_party|browser`），路由器按序回退。新增 Provider 只需实现 `I1688Provider` 并注册，不改 Agent 业务接口（满足要求 6、7）。

## 8. 实施边界（本阶段）

**仅设计，不实施生产切换。** 本阶段交付：
- 本设计文档（契约 + 路由 + 信封 + 隔离 + fail-closed 策略）。
- 不改动现有 `sourcing_1688_service.py` 生产行为（避免影响 P0）。

## 9. 待 Owner 批准后才实施

- Provider 抽象落地为代码（新增 `data_providers/` 模块）。
- 生产路由表移除 Mock/fallback（配合 PR#13）。
- 采集元数据（Provenance）落库 `ai_agent_runs` / 新增采集审计表。
- 切换寻源通为生产主源（依赖 P0 凭证 + GMV 达标）。

## 10. 风险

- 路由器引入新故障点：需充分测试 fail-closed 路径。
- Provenance 落库增加存储：raw_evidence 只存摘要/引用，不存全量 HTML。
- Provider 契约若过早冻结，可能不适配寻源通真实字段：先以 simple.get 实测字段后再定稿契约。
