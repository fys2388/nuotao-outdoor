# D8-F 验收清单｜商品数据真实性与采集供应链升级

> 阶段：D8-F 交付验收。日期：2026-11-20。执行：DSH (sensenova)。
> 用途：Owner / ChatGPT 验收 D8-F 六阶段是否达标。逐项勾选，证据见括号引用。

---

## A. 交付物齐全（5 份文档）

- [x] `D8F_P0_DATA_TRUST_AUDIT.md` — P0-1 审计（缺口 N1-N7 / R1-R7 / C1-C7，8 检查点全覆盖）
- [x] `D8F_ARCHITECTURE.md` — 架构蓝图（Provider 接口 + 字段级 provenance + fail-closed + E0-E5）
- [x] `D8F_IMPLEMENTATION_REPORT.md` — 实现报告（六阶段 + 10 异常映射 + 代码改动）
- [x] `D8F_TEST_REPORT.md` — 测试报告（专项 19 + 回归 46+ + CI 全绿）
- [x] `D8F_ACCEPTANCE_CHECKLIST.md` — 本清单

## B. 六阶段达成

- [x] **① 审计**：现有真实性门禁单点/单条件缺口定位，双子代理交叉验证（PR #16）
- [x] **② 字段级来源追溯**：ProductProvenance/FieldProvenance 模型 + migration 0088（data_source/collected_at/evidence_grade/provenance）+ Product 模型同步（PR #16/#17）
- [x] **③ 标准化人工 Provider**：I1688ProductProvider 协议 + ManualProvider（不依赖 Cookie；collect/normalize/validate/get_provenance）（PR #17）
- [x] **④ fail-closed 覆盖 10 类异常**：见实现报告 §3 映射表；专项测试逐条覆盖（PR #17/#18/#19）
- [x] **⑤ 接入 E0-E5**：EvidenceGrade 枚举复用 M334；禁止跳跃（初始 E0）；商品级≠字段级（field_provenance 独立）（PR #17）
- [x] **⑥ 测试+回归+PR**：专项 19 passed + 回归 46+ passed + 4 个 PR CI Pre-check 全绿（PR #16/#17/#18/#19）

## C. 核心原则落实

- [x] **宁可少采集，不进假数据**：price=35.8 伪造已删（N1）；价格缺失 fail-closed；ManualProvider ok=False → data=None
- [x] **不另起证据标准**：EvidenceGrade 复用 M334 E0-E5；市场研究 A-E 未混淆
- [x] **商品级 ≠ 字段级**：商品 evidence_grade 与 field_provenance[*].is_verified 独立（专项测试断言）
- [x] **禁止跳跃升级**：人工录入初始 E0，不可直接 E4/E5 做利润结论

## D. 审计 Critical/High 缺口封堵

- [x] **N1**（最高危）price=35.8 伪装真实 → 删除 + generic 补 price≤0 判定（PR #17）
- [x] **C5** listing_gate 不校验来源 → HARD_BLOCK 加 unauthentic_source（两路径，不可 force）（PR #18）
- [x] **C6** convert 丢标记 → 透传 data_source/is_authentic（PR #18）
- [x] **C2**（Critical）legacy listing 端点无鉴权 → 4 端点补 CurrentUser（PR #19）
- [x] **C4** newton 伪造 $5 售价污染利润 → 改 suggested_retail_price，无成本→None（PR #19）
- [x] **C3** Orchestrator 静默降级/伪造 $29.99 → pricing fail-closed + listing 查业务结果（PR #19）
- [x] **N3/N4** import_and_analyze 绕过 + 仅看 success → 白名单闸门无论 auto_run_pipeline 一律拦非真实来源（PR #17）

## E. 授权边界遵守（禁止项全部未触碰）

- [x] 未做生产部署
- [x] 未批量改生产数据（migration 0088 只加可空列不回填）
- [x] 未自动采购
- [x] 未调用付费 API
- [x] 未提取浏览器 Cookie/凭据

## F. 质量门禁

- [x] D8-F 专项测试 `tests/test_d8f_data_trust.py` 19 passed
- [x] 相关回归套件（闸门/毛利/桥接/上架/图片管线）46+ passed
- [x] 4 个 PR CI Pre-check（syntax+imports+smoke+Ruff+pytest+依赖扫描）success
- [x] 改动文件 Ruff 阻断规则（F821/F811/E9）All checks passed
- [x] 未破坏原有商品分析 Agent 业务接口（Agent 仍走 services 白名单）

## G. 已知边界（如实告知，不藏）

- [ ] 异常6 页面 ID 不匹配：靠存量 source_offer_id + provenance 记录，未新增独立强校验（后续增强）
- [ ] 异常9 来源冲突：当前白名单外标记人审，未做多 Provider 数值比对（Official API 接入后增强）
- [ ] E0-E5 升级"逐级补证归档"流程属业务侧，本阶段只落枚举+初始赋值
- [ ] 全量 pytest 受既有环境限制（langgraph 缺失 / 本地超时），CI 完整环境已跑通；非 D8-F 引入

---

## 验收结论

D8-F 六阶段全部完成并通过自动化验证。5 份交付物齐全，审计 Critical/High 缺口（N1/C2/C3/C4/C5/C6/N3/N4）全部封堵，E0-E5 打通未另起标准，授权禁止项全部未触碰。**建议 Owner 验收通过。**
