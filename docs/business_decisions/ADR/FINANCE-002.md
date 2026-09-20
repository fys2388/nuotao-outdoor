# ADR FINANCE-002 — 可审计汇率与报告币种换算

> 状态：**Accepted**（2026-09-13）  
> 决策编号：FINANCE-002  
> 关联：`FINANCE-001`、`PRICING-001`、`docs/b2c_b2b_compatibility_audit.md`

---

## Context（背景）

系统同时保存 USD、EUR、CNY、GBP 等币种的订单、成本、发票和收款。此前渠道分析
按币种分别展示；B2B 毛利还可能直接用销售币种收入减去采购币种成本。没有统一
汇率事实来源时，合并报表会出现跨币种无汇率相加，或者由代码隐式假设汇率。

## Decision（决策）

### 1. 汇率采用工作区级不可变日快照

新增 `exchange_rates`：

```text
workspace_id
base_currency
quote_currency
rate
effective_date
source
source_reference
created_by
created_at
```

`rate` 表示 `1 base_currency = rate quote_currency`。唯一键为：

```text
workspace_id + base_currency + quote_currency + effective_date
```

同一天同一货币对只保留一个事实值；更正必须通过新的生效日期或明确的数据修复流程，
不能静默覆盖历史证据。

### 2. 不自动推断反向汇率

系统只使用明确维护的直接汇率：

```text
USD -> EUR
```

不能自动把 `EUR -> USD` 当作 `1 / rate`。反向换算需要运营维护对应的直接汇率，
避免来源、精度和财务口径不明。相同币种换算固定为 `1`。

### 3. 换算日期按业务事实选择

- 订单收入和订单毛利使用订单日期。
- 采购成本先按成本有效日期从成本币种换算到订单币种，再计算订单毛利。
- 应收账龄按报告截止日换算。
- 渠道合并报表使用业务日期当天或之前最近一条直接汇率。

### 4. 缺失汇率必须显式失败

- 未指定报告币种时，继续按原币种分别展示，不合并金额。
- 指定报告币种时，任一所需汇率缺失，API 返回 `422`，不生成部分可信的合并数字。
- 成本汇率缺失时，单条 B2B 毛利不计入利润覆盖；页面显示为部分覆盖。

### 5. 管理端必须可维护和可追溯

内部管理端提供：

```text
GET  /api/v1/admin/currency-rates
GET  /api/v1/admin/currency-rates/resolve
POST /api/v1/admin/currency-rates
```

新增汇率仅管理员可操作，保存来源、来源凭证、维护人和创建时间。

## Consequences（后果）

### 正面

- B2C/B2B 收入和成本可以在明确报告币种下合并。
- B2B 毛利不再直接相减不同币种。
- 汇率来源、生效日期和换算口径可以审计。
- 没有汇率时系统拒绝伪造合并结果。

### 成本

- 运营必须维护交易所需货币对和有效日期。
- 多来源、实时汇率 API、复杂税务折算仍属于后续增强。
- 历史调整需要新增或修复汇率记录，不能改写已发生订单金额。

## Verification（验收）

- 同一货币对选择生效日不晚于业务日期的最近汇率。
- 反向货币对未配置时明确报错。
- 跨工作区不能读取或新增汇率。
- 指定报告币种后，B2C/B2B 收入、毛利和应收按直接汇率合并。
- B2B 采购成本使用成本币种汇率换算后再计算毛利。
- 缺失汇率返回 `422`，不会返回静默推断值。
