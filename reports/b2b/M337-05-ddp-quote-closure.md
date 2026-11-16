# M3.37-05｜DDP 真实物流报价闭环
**生成时间**：2026-11-16  
**依据**：M3.37 指令任务 5；真实 DDP 报价 0/60，待 Owner 批准外部联系（APR-007）
---
## 1. 询价与比较模板（首批 1 条美国直发线路）
| 字段 | 内容 |
|---|---|
| freight_quote_type | 按票/按重 |
| quote_currency | USD |
| chargeable_weight | 待实测后填 |
| duty_included / broker_fee_included / disbursement_fee_included | 是/否（防重复扣费） |
| fuel_surcharge_basis | 待货代确认 |
| last_mile_included / insurance_included | 是/否 |
| importer_of_record / tax_payment_responsibility | 待确认 |
| quote_valid_until / destination_country / incoterm | __ / US / DDP |
---
## 2. 13 项成本字段（费用包含关系）
| 字段 | 当前 | 规则 |
|---|---|---|
| customs_broker_fee | MISSING | 不得默认 $0；无报价不得伪装为 0 |
| carrier_disbursement_fee | MISSING | 不得默认 $0；无报价不得伪装为 0 |
| domestic_freight | MISSING/ESTIMATED | 需真实报价后补 |
| international_freight | MISSING/ESTIMATED | 需真实报价后补 |
| fuel_surcharge | MISSING/ESTIMATED | 需真实报价后补 |
| last_mile_cost | MISSING/ESTIMATED | 需真实报价后补 |
| base_duty | MISSING/ESTIMATED | 需真实报价后补 |
| additional_duty | MISSING/ESTIMATED | 需真实报价后补 |
| insurance | MISSING/ESTIMATED | 需真实报价后补 |
| remote_area_surcharge | MISSING/ESTIMATED | 需真实报价后补 |
| handling_fee | MISSING/ESTIMATED | 需真实报价后补 |
| other_fees | MISSING/ESTIMATED | 需真实报价后补 |
---
## 3. 防重复扣费
- 报价含某费用时模型不再重复计；真实报价前维持 MISSING/ESTIMATED，**不把缺失当 0 计入已核实成本**。
