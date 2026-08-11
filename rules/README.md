# Rules — 运营规则参数配置目录

规则**规格**的唯一来源是 `docs/operating_rules.md`（10 大规则域）。
本目录用于存放可执行、版本化的**规则参数配置**（阈值/权重/限额），供规则引擎读取。

结构规划（M2 起填充）：

```text
rules/
  params/
    product_selection.yaml     # PROD-SEL
    product_scoring.yaml       # PROD-SCORE
    pricing.yaml               # PRICE
    profit.yaml                # PROFIT
    supplier.yaml              # SUPPLIER
    sku_lifecycle.yaml         # SKU-LIFE
    inventory.yaml             # INV
    ads_testing.yaml           # ADS-TEST
    customer_service.yaml      # CS
    agent_permissions.yaml     # AGENT-PERM
```

要求：参数集中配置、版本化（copy-on-write）、禁止硬编码在业务代码或提示词中。