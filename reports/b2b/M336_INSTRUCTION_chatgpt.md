# Nuotao Outdoor — DSH M3.36 执行指令

# 阶段名称
M3.36 — Evidence Acquisition & Cost Closure

# 一、阶段目标

基于 M3.35 的 8 份报告，推进 60 SKU 从估算成本向真实成本证据转化。

本阶段不再重复泛化市场调研，不进行机械涨价。

核心目标：

1. 修复证据等级与商品状态定义。
2. 建立 60 SKU 实际重量和包装尺寸采集流程。
3. 补齐 13 款高端 SKU 的采购成本证据。
4. 建立美国 HTSUS 正式归类与进口税费证据档案。
5. 获取完整 DDP 费用构成证据。
6. 重新核算 60 SKU 的单位经济模型。
7. 形成下一阶段 Owner 可审批的商品经营决策。

# 二、第一任务：M335 数据状态修正

读取全部 M3.35 报告及 M3.34、M3.33.1、M3.33.2、M3.33.3 历史报告。

重点检查：

## 2.1 COST_VERIFIED 状态

M3.35 原有 24 款 COST_VERIFIED，存在采购价已核实但重量和 HTSUS 未核实的问题。

修正为：

- PURCHASE_COST_VERIFIED
- COST_VERIFIED_PARTIAL
- COST_VERIFIED
- PROFIT_VERIFIED
- MARKET_VALIDATED

状态定义：

PURCHASE_COST_VERIFIED：
采购价具备真实有效的证据。

COST_VERIFIED_PARTIAL：
部分成本字段已核实，但仍存在关键成本缺口。

COST_VERIFIED：
采购价、实测包装重量与尺寸、适用税费、完整物流费用均已取得可靠证据。

PROFIT_VERIFIED：
完整成本已核实，且按照统一利润口径达到预设利润目标。

MARKET_VALIDATED：
具备真实订单、实际获客成本、退款退货和售后数据，证明商品有可持续经营能力。

禁止通过修改标签将估算数据升级为真实数据。

## 2.2 STOPPED 状态核验

重点检查：

- #1014 烧烤架
- #1013 收纳箱

查找是否存在明确 Owner 审批记录。

没有审批记录时，状态必须为：

STOP_PENDING_OWNER_APPROVAL

不得执行下架、删除、库存调整或 WooCommerce 状态修改。

# 三、第二任务：60 SKU 实际重量与包装尺寸采集

建立 60 SKU 的统一测量工作台。

每款商品记录：

- SKU
- 商品名称
- 供应商
- 1688 Offer ID
- 商品净重
- 包装后毛重
- 包装长度
- 包装宽度
- 包装高度
- 体积重
- 体积重计算除数
- 计费重量
- 测量日期
- 测量人
- 原始照片或证据文件
- 验证状态

要求：

1. 商品净重与包装后毛重必须分开。
2. 长宽高使用统一单位 cm。
3. 实测数据必须有原始记录。
4. 不允许将品类平均重量标记为实测重量。
5. 体积重除数必须依据实际承运商或货代规则。
6. 计费重量必须依据承运商的取大值及进位规则。
7. 未实测商品保持 ESTIMATED 或 MISSING。

优先级：

P0：M3.34 确定的 6 款大件商品。

P1：其余可能因体积重导致物流成本明显上升的商品。

P2：其余 SKU。

DSH 不具备实际物理测量能力。需要建立测量任务、责任人、记录模板和证据验收机制，等待 Owner 或内部团队提供实测结果。

# 四、第三任务：13 款高端 SKU 采购成本补证

目标 SKU：

#1719
#1720
#1721
#1722
#1723
#1724
#1725
#1726
#1727
#1728
#998
#1474
#1476

每款商品建立独立采购证据档案：

- 1688 原始 Offer ID
- 供应商名称
- 商品实际规格
- SKU 选项
- 当前采购报价
- 不同采购数量对应价格
- MOQ
- 报价日期
- 报价有效期
- 包装和配件是否包含
- 是否含税
- 是否含国内运费
- 价格证据来源
- 是否有历史订单或采购记录

证据状态：

VERIFIED
ESTIMATED
MISSING
CONFLICTED
EXPIRED

禁止把历史区间价直接认定为当前真实采购价。

本阶段只整理现有资料并生成补证清单，不自动联系供应商，不自动发送询价。

# 五、第四任务：美国 HTSUS 和进口税费证据

针对 60 SKU 建立 HTSUS 归类证据档案。

每款记录：

- 产品实际用途
- 材料组成
- 结构特征
- 工作原理
- 是否带电池
- 电池类型
- 产品图片
- 候选 HTSUS 编码
- 10 位 HTSUS 编码
- 普通关税
- Chapter 99 附加税适用情况
- 原产国
- 进口日期
- 归类依据
- 报关行确认文件
- 最终审核状态

严格要求：

1. 6 位 HS 编码不得作为美国最终归类。
2. 候选编码不得标记为正式归类。
3. 不得把普通税率等同于最终进口税负。
4. 不得将历史政策假设当作当前政策。
5. 必须记录进口日期、原产地及适用政策版本。
6. 不确定的商品标记 NEEDS_CUSTOMS_CLASSIFICATION。

本阶段只准备商品信息卡、归类问题清单和外部确认模板。

不得自行宣称已经获得报关行正式确认。

# 六、第五任务：完整 DDP 物流成本核验

统一物流成本字段：

- product_cost
- domestic_freight
- international_freight
- fuel_surcharge
- last_mile_cost
- base_duty
- additional_duty
- customs_broker_fee
- carrier_disbursement_fee
- insurance
- remote_area_surcharge
- handling_fee
- other_fees

每份物流报价必须补充：

- freight_quote_type
- quote_currency
- chargeable_weight
- duty_included
- broker_fee_included
- disbursement_fee_included
- fuel_surcharge_basis
- last_mile_included
- insurance_included
- importer_of_record
- tax_payment_responsibility
- quote_valid_until
- destination_country
- incoterm

重要要求：

customs_broker_fee 和 carrier_disbursement_fee 不得默认视为零。

如果没有实际报价，标记 MISSING，不得把零值伪装成已核实成本。

必须防止 DDP 报价已包含某项费用，却又在模型中重复扣除。

本阶段只准备询价材料，不联系货代或报关行。

# 七、第六任务：重新计算 60 SKU 单位经济模型

统一计算三种利润口径。

A. 商品毛利率：

售价扣除商品采购成本。

B. 履约贡献利润率：

进一步扣除国际物流、关税、清关、尾程、支付平台费用、售后准备金等订单履约成本。

C. 扣 CAC 后订单净利润率：

在履约贡献利润基础上继续扣除获客成本 CAC 及其他订单级费用。

必须：

1. 不重复扣除费用。
2. 不遗漏费用。
3. 缺失成本不得默认为零。
4. 真实数据与估算数据分开计算。
5. 输出悲观、中性、乐观情景。
6. 输出利润率置信度。
7. 输出成本缺口对利润率的影响。

建议状态：

LOW_CONFIDENCE
MEDIUM_CONFIDENCE
HIGH_CONFIDENCE

只有真实数据满足验证条件时，才允许升级置信度。

# 八、第七任务：60 SKU 经营决策矩阵

最终分类：

- BLOCKED
- NEEDS_EVIDENCE
- PURCHASE_COST_VERIFIED
- COST_VERIFIED_PARTIAL
- COST_VERIFIED
- PROFIT_VERIFIED
- MARKET_VALIDATED
- STOP_PENDING_OWNER_APPROVAL
- STOPPED
- RESTRUCTURE

特别关注：

#1014：停止经营审批状态核验。

#1013：停止经营审批状态核验。

#1722：国内直发与海外仓单位经济比较。

13 款高端 SKU：采购成本补证。

其余 SKU：完整成本缺口和利润敏感性分析。

禁止自动审批停售、改价、切换海外仓或扩大广告预算。

# 九、交付物

生成以下 8 份报告：

M336-01：M3.35 状态与证据等级修订报告。

M336-02：60 SKU 实际重量与包装尺寸采集工作台。

M336-03：13 款高端 SKU 采购成本补证报告。

M336-04：60 SKU HTSUS 归类证据档案。

M336-05：DDP 物流成本证据与费用包含关系报告。

M336-06：60 SKU 单位经济模型重算报告。

M336-07：60 SKU 商品组合与 Owner 决策矩阵。

M336-08：Owner 执行摘要与下一阶段授权清单。

# 十、严格权限边界

本阶段只允许：

- 读取历史报告和本地商品资料。
- 整理已有证据。
- 建立本地工作台和补证任务。
- 编制实测模板、询价模板和报关归类资料。
- 运行本地成本模型。
- 生成报告。

禁止：

- 联系供应商、货代、报关行。
- 自动发送询价或邮件。
- 采购商品或样品。
- 修改 WooCommerce 价格。
- 修改库存或商品上下架状态。
- 修改生产数据库。
- 调用生产 API。
- 执行生产部署。
- 修改 DNS、Cloudflare 或服务器配置。
- 自动批准停售或改变履约模式。
- 自动批准广告预算。

# 十一、验收标准

1. 60 SKU 均有独立证据状态。
2. 采购价实价、区间价、文档价和品类估算严格区分。
3. 60 SKU 的重量和尺寸缺口清晰可见。
4. 13 款高端 SKU 均有明确补证状态。
5. HTSUS 候选编码与正式归类严格区分。
6. DDP 费用包含关系明确。
7. 清关费和代垫费不得无证据默认为零。
8. 三种利润口径计算无重复、无遗漏。
9. #1014、#1013 的停售状态具备 Owner 审批证据。
10. #1722 的海外仓建议有完整成本比较。
11. 不得将估算数据标记为 VERIFIED。
12. 所有生产权限边界均得到遵守。

最终状态只能为：

COMPLETED
COMPLETED_WITH_NEEDS_EVIDENCE
BLOCKED

报告结束时必须列出：

- 完成任务
- 未完成任务
- 真实证据覆盖率
- 估算数据覆盖率
- 关键风险
- Owner 待审批事项
- 报告路径
- 测试结果
- Git 状态
- 是否发生任何生产操作

未经 Owner 明确授权，不得进入任何外部联络、采购、生产或部署阶段。
