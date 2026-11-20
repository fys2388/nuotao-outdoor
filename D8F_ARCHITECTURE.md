# D8-F 架构设计｜商品数据真实性、来源追溯与采集供应链

> 阶段：D8-F 架构蓝图（P0-2/P0-3/P0-4/P1 的实施依据）。
> 日期：2026-11-20。执行：DSH (sensenova)。
> 配套审计：`D8F_P0_DATA_TRUST_AUDIT.md`（缺口 N1-N7、R1-R7）。
> 核心原则：宁可少采集一个商品，也不能让虚假商品信息进入选品/利润分析/上架/采购决策。
> 铁律：不得另起证据标准，必须与现有 E0-E5 体系（`reports/b2b/M334_EVIDENCE_GRADE_SYSTEM.md`）打通。
> 本阶段仅设计 + 约定的最小实现；生产部署/批量改生产数据需 Owner 批准。

---

## 0. 设计目标（对应审计缺口）

| 目标 | 解决的审计缺口 |
|---|---|
| G1 字段级来源追溯 | R7（商品级真实≠字段级）、R4（采集方式/时间/证据等级不落库） |
| G2 来源信息全程可读 | N3（data_source 不下传，下游全盲） |
| G3 统一 Provider 接口 | 结构化采集入口，业务层不写 if/else 分叉 |
| G4 不依赖 Cookie 的人工采集 | 长期数据源被 API/牛顿/浏览器 Cookie 单点卡死 |
| G5 fail-closed 覆盖 10 类异常 | R1（登录墙放行）、N1（price 伪装）、R6（仅看 success） |
| G6 接入 E0-E5 证据等级 | R5（E0-E5 仅文档未打通） |
| G7 全链路审计 | N4（调用方只看 success） |

---

## 1. 分层架构

```
┌──────────────────────────────────────────────────────────┐
│ 消费层：选品闸门 / 利润分析 / WooCommerce 上架 / 采购决策  │
│  —— 每一步先读 provenance，非真实数据 fail-closed 拒绝     │
└───────────────────────┬──────────────────────────────────┘
                        │ 统一读取 ProductProvenance
        ┌───────────────▼───────────────┐
        │  ProvenanceService（新）      │  ← 来源追溯唯一来源
        │  get_provenance / validate    │
        │  assign_evidence_grade        │
        └───────────────┬───────────────┘
                        │ 写入 product_info['provenance'] + DB
   ┌────────────────────▼────────────────────┐
   │        I1688ProductProvider（新接口）    │
   │  collect / normalize / validate /        │
   │  get_provenance                          │
   └──┬──────────┬──────────┬──────────┬─────┘
      ▼          ▼          ▼          ▼
  Manual     Browser    Official    (预留)
  Provider   Cookie     APIProvider
  (P0-3重点) Provider   (GMV达标后)
  不依赖     (现有)     (sourcing_)
  Cookie     Cookie     1688)
```

## 2. 统一 Provider 接口（G3）

```python
# backend/app/services/data_providers/base.py（新）
class ProductProvenance(BaseModel):
    """字段级来源追溯。每个采集字段都可追溯到 provider+原始证据。"""
    provider: str                 # manual | browser_cookie | official_api
    source_reference: str | None  # 1688 offer_id / 人工录入单号
    source_url: str | None
    collected_at: datetime        # 采集时间（UTC）
    collected_by: str             # user_id / "system:scrapling"
    trace_id: str                 # 贯穿采集→分析→上架
    evidence_grade: str           # E0-E5（见 §5）
    field_provenance: dict[str, FieldProvenance]  # 字段级
    is_real: bool                 # 终极判据：能否进入自动化决策
    degraded_reason: str | None   # 非真实时必填原因

class FieldProvenance(BaseModel):
    """单个字段的来源与证据状态。商品级真实≠字段级真实。"""
    value: Any
    provider: str
    collected_at: datetime
    is_verified: bool             # 是否通过真实性校验
    raw_evidence_ref: str | None  # 原始页面片段/截图引用（不含凭据）

class I1688ProductProvider(Protocol):
    name: str
    def is_available(self) -> bool: ...
    def collect(self, url_or_id: str) -> ProviderResult: ...
    def normalize(self, raw: Any) -> dict: ...
    def validate(self, normalized: dict) -> ValidationResult: ...
    def get_provenance(self, product_id: str) -> ProductProvenance: ...
```

**ProviderResult** 取代裸 dict：`{ok, data, provenance, degraded, fail_closed_reason}`。
`ok=False` 时 `data=None`——**拿不到可信真实数据即失败，不再返回 success=True + 假数据**。

### 2.1 Provider 注册与路由
- `ManualProvider`（P0-3）：人工表单建档，`is_available()` 恒 True，不依赖 Cookie/API。
- `BrowserCookieProvider`：包装现有 `scrape_1688.scrape_1688_product`（Cookie 失效即 fail-closed）。
- `OfficialApiProvider`：包装现有 `sourcing_1688_service`（GMV 达标后启用）。
- 路由：按可用性 + 证据等级择优；**任何 Provider 拿不到真实数据 → 整体 fail-closed，绝不降级到假数据**。

## 3. 字段级来源追溯（G1/G2）

### 3.1 data_source 全程携带
- `convert_1688_to_pipeline_input`（:2527）**增补**：把 `data_source` + `ProductProvenance` 写入 `product_info['provenance']`。
- 下游 `run_pipeline` / V3.0 选品闸门 / AI 分析 / `listing_gate` **统一从 `product_info['provenance']` 读**，不再依赖单点。
- 闸门从"import_from_1688 单点"变"每个消费点都可校验"。

### 3.2 DB 落库（Alembic 迁移，P0-2）
products 表新增（复用/扩展现有字段，不另起体系）：
```python
data_source: str           # 采集方式 provider 名
collected_at: datetime     # 采集时间
evidence_grade: str        # E0-E5
provenance: AI_JSON        # 完整 ProductProvenance（含 field_provenance）
# 已有复用：source, source_url, source_offer_id, data_integrity_*, trace_id
```
`ProductSource` 表（product_intelligence.py:64）扩展 `field_provenance` JSON 列。

## 4. fail-closed 门禁（G5，覆盖 10 类异常）

统一策略：**隔离 + 记录 trace_id + 保留原始证据 + 生成"待处理"状态，绝不静默降级为假数据。**

| # | 异常 | 检测 | 处置 |
|---|---|---|---|
| 1 | Cookie 失效 | 返回登录墙壳页/占位名 | fail-closed，`is_real=False` |
| 2 | 登录墙页面 | name ∈ 登录墙占位黑名单（即使长度≥10） | fail-closed |
| 3 | 占位名 | name ∈ {"1688 Product","1688产品","Product","商品"} | fail-closed |
| 4 | 价格为空/为0 | price 缺失或 0 | fail-closed（**删除 :437 的 35.8 硬编码**） |
| 5 | 规格缺失 | SKU/variations 空 | 降级标记，禁止自动上架 |
| 6 | 页面 ID≠请求 ID | 解析 ID 与 source_offer_id 不符 | fail-closed |
| 7 | 解析器不兼容 | 结构突变/解析异常 | fail-closed |
| 8 | 原始数据不可追溯 | 无 raw_evidence_ref | 降级标记 |
| 9 | 来源冲突 | 多 Provider 数据矛盾 | 标记 + 人审 |
| 10 | hardcoded_fallback 意外调用 | data_source==hardcoded_fallback 进入任何消费点 | fail-closed |

**核心修点**：
- **删 `scrape_1688.py:437` 的 `price=35.8`**（N1）——price 解析失败即 fail-closed，绝不伪造真实价格。
- 闸门条件从 `data_source=="hardcoded_fallback" and auto_run_pipeline` 改为**白名单**：仅 `is_real=True` 才放行，覆盖 import_and_analyze（N3→G2）、hydrate（N2）、仅看 success（N4）。

## 5. 接入 E0-E5 证据等级（G6）

复用 `M334_EVIDENCE_GRADE_SYSTEM.md` 定义，落为代码枚举：
```python
class EvidenceGrade(str, Enum):
    E0="仅有商品基础信息"; E1="采购资料已核对"; E2="采购+物流完备"
    E3="HTSUS已核实"; E4="完整落地成本"; E5="经营利润确认"
```
- **采集时按来源赋初始等级**：真实抓取→E0（仅基础信息）；人工核对采购价→E1；实测重量→E2……
- **禁止跳跃升级**（E0 不能直接到 E4），每级需对应证据文件归档。
- **禁止降级使用**：E 级不达标不得做对应动作（E0 不能做利润结论，E1 不能做完整核算）。
- **商品级≠字段级**：`evidence_grade` 是商品级，`field_provenance[*].is_verified` 是字段级；价格字段 E1 ≠ 整商品 E1。
- 证据过期机制（采购价 6 个月等）落 `collected_at` + 定期失效。

> ⚠️ 两套证据体系勿混淆：**采购 SKU 用 E0-E5**（M334_SKU 证据：E0 基础信息→E5 经营利润确认）；**市场研究证据用 A/B/C/D/E**（MarketResearch SOP：A=官方 B=权威 C=品牌 D=用户 E=二手）。D8-F 商品采集对接的是 **E0-E5**，不得套用 A-E。

## 5b. 下游发布层门禁（补 C1-C7 Critical 缺口，审计 §下游）

数据真实性门禁必须**下沉到发布咽喉点**，不能只在 import 阶段：
- **C5**：`listing_gate.evaluate_gate` / `evaluate_gate_from_dict` 的 HARD_BLOCK **增列 `unauthentic_source`**——`data_source ∈ {hardcoded_fallback, unknown}` 或 `evidence_grade == placeholder` 即 fail-closed 拒绝，与 missing_price/negative_margin 同级不可 force。
- **C1**：`confirm_and_list`(:2018) 校验 provenance；fallback 导入须先建档评分（不得 funnel_stage=NULL 放行）。
- **C2**：给 legacy `/products/listing/single|batch`(:69,89) **补鉴权**（对齐 listing_publish.py:49-52 CurrentUser），并要求携带可验证 source_offer_id/落库 product_id。
- **C3**：PipelineOrchestrator 接入 V3.0 闸门，移除 `_safe_call`(:27-37) 静默降级，失败即 fail-closed。
- **C4**：移除 newton `newton_sourcing_storage.py:229-232` 的 `purchase_cost*3/min$5` 硬编码倍率（违反 AGENTS.md §1.2.5）；无真实售价时不写 `meta.regular_price`，让 profit_analysis 保持 MISSING fail-closed。
- **C6**：`convert_1688_to_pipeline_input`(:2527) 必须保留 source 标记（→ §3.1 写入 provenance）。
- **C7**：run_pipeline session=None 不得静默 skip 选品闸门。

## 6. 全链路审计（G7）

- `trace_id` 贯穿采集→分析→上架→发布，落 `ai_agent_runs` / `product_analysis_runs`。
- API 层与异步任务（N4）**必须读 data_source/provenance**，兜底数据返回明确降级状态而非 success=True。

## 7. 测试矩阵（P1-2，对应审计 §8 五类缺口 + 10 异常）

| 类别 | 用例 |
|---|---|
| 闸门 | hardcoded_fallback 阻断（已有）、登录墙占位拒绝、price=35.8 已删除、unknown 拒绝 |
| 路径 | import_and_analyze 绕过已封堵、hydrate 回填校验、auto_run_pipeline=False |
| Provider | ManualProvider collect/normalize/validate/get_provenance、BrowserCookie 失效 fail-closed |
| E0-E5 | 初始等级赋值、禁止跳跃、禁止降级使用、字段级≠商品级 |
| 下游 | listing_gate 拒绝非真实、选品闸门读 provenance、WooCommerce 不收假数据 |
| 回归 | Ruff + 原有测试全通过 |

## 8. 实施边界（本阶段）

- **仅设计 + 约定的最小实现**。生产部署、批量改生产数据、自动采购需 Owner 批准。
- 先复用现有实现（scrape_1688 / sourcing_1688 / data_integrity_* / ProductSource），不另起体系。
- 不改变现有商品分析 Agent 业务接口（Agent 仍调 services 白名单）。

## 9. 实施顺序（后续轮次）

1. **P0-2**：Alembic 迁移加 DB 字段 + `ProvenanceService` + `convert_1688_to_pipeline_input` 写 provenance。
2. **P0-3**：`ManualProvider` + Provider 接口 + 路由。
3. **P0-4**：fail-closed 10 异常 + 删 price=35.8 + 白名单闸门。
4. **P1-1**：Provider 接口统一 + 下游接入 provenance。
5. **P1-2**：测试矩阵 + Ruff 回归 + PR。

## 10. 风险

- DB 迁移需谨慎（已有 data_integrity_* 字段，避免列冲突）。
- 闸门改白名单可能"拦掉"现有依赖降级数据的流程——需先摸清下游，渐进收紧。
- E0-E5 赋值规则需与业务确认（初始等级怎么定），避免主观。
- Provider 抽象过早冻结可能不适配真实字段——先以 BrowserCookie 实测字段后定稿。
