# M3.36-05｜DDP 物流成本证据与费用包含关系报告
**生成时间**：2026-11-16  
**关键修正**：`customs_broker_fee` 与 `carrier_disbursement_fee` **不得默认视为零**；无实际报价标 MISSING
---
## 1. 统一物流成本字段（13 项）
| 字段 | 当前状态 | 说明 |
|---|---|---|
| product_cost | ESTIMATED | 34 款 D 档估算 |
| domestic_freight | ESTIMATED | 隐含在 $2/kg 假设 |
| international_freight | ESTIMATED | $2/kg 假设 |
| fuel_surcharge | ESTIMATED | 3.5% 假设 |
| last_mile_cost | ESTIMATED | $5.5/$11 假设 |
| base_duty | ESTIMATED | 品类假设，未拆 301 |
| additional_duty | ESTIMATED | 未拆 |
| customs_broker_fee | MISSING | **不得默认 $0**（此前按 $0 低估） |
| carrier_disbursement_fee | MISSING | **不得默认 $0**（此前按 $0 低估） |
| insurance | MISSING | 未单列 |
| remote_area_surcharge | MISSING | 未单列 |
| handling_fee | MISSING | 未单列 |
| other_fees | MISSING | 未单列 |
---
## 2. 每份物流报价必补字段（防止重复扣费）
| 字段 | 说明 |
|---|---|
| freight_quote_type | 按票/按重 |
| quote_currency | 币种 |
| chargeable_weight | 计费重 |
| duty_included | 是否已含关税 |
| broker_fee_included | 是否已含清关费 |
| disbursement_fee_included | 是否已含代垫费 |
| fuel_surcharge_basis | 燃油基数 |
| last_mile_included | 尾程是否已含 |
| insurance_included | 保险是否已含 |
| importer_of_record | 进口人 |
| tax_payment_responsibility | 税费支付方 |
| quote_valid_until | 报价有效期 |
| destination_country | 目的国 |
| incoterm | 贸易术语 |
---
## 3. 防重复扣费核查（M335 现状）
| 检查项 | 结果 |
|---|---|
| 关税重复计 | 无（采购×25% 一次） |
| 燃油重复计 | 无（头程+尾程×3.5%） |
| CAC 重复计 | 无（单列） |
| 清关费/代垫费 | **漏列按 $0 → 到岸低估**（M336 修正为 MISSING） |
| 真实 DDP 含税性 | 未核 → 需报价证据 |
---
## 4. 本阶段动作
- 生成 DDP 询价材料模板（13 字段 + 14 报价属性），交 Owner 批准后由商务执行（本阶段不联系货代）
- 修正 M335-05 到岸成本为保守低估的说明已保留；真实报价补齐前维持 MISSING 而非 0
---
*本阶段只准备询价材料，不联系货代或报关行。*
