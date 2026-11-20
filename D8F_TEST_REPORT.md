# D8-F 测试报告｜商品数据真实性与采集供应链

> 阶段：D8-F 测试与回归验证。日期：2026-11-20。执行：DSH (sensenova)。
> 核心原则：宁可少采集一个商品，也不能让虚假商品信息进入选品/利润分析/上架/采购决策。

---

## 1. 测试范围与结论

| 类别 | 文件/命令 | 结果 |
|---|---|---|
| D8-F 专项（10 异常 + E0-E5） | `tests/test_d8f_data_trust.py` | **19 passed** |
| 1688 兜底闸门 | `tests/test_1688_fallback_gate.py` | passed |
| 上架毛利门禁 | `tests/test_listing_gate_margin.py` | passed |
| 选品-上架桥接 | `tests/test_selection_listing_bridge.py` | passed |
| 上架任务 | `tests/test_listing_job.py` | passed |
| 图片-WC 管线 | `tests/test_image_wc_pipeline.py` | passed |
| 回归合计（相关套件） | 上述合并 | **46+ passed** |
| CI Pre-check（4 个 PR：#16/#17/#18/#19） | Backend syntax+imports+smoke+Ruff+pytest+依赖扫描 | **success** |

## 2. D8-F 专项测试覆盖（`test_d8f_data_trust.py`）

### 2.1 fail-closed 10 类异常
| 测试 | 覆盖异常 | 断言 |
|---|---|---|
| `test_manual_collect_ok_is_real_but_e0` | 基线 | 有效录入 ok=True、is_real=True、grade=E0、字段级已记录 |
| `test_manual_placeholder_name_fail_closed` | 3 占位名 | 占位/空名 → ok=False、data=None、"占位" 原因 |
| `test_manual_missing_price_fail_closed` | 4 价格为空 | None/""/0/"0"/-1 全拒，绝不伪造（对应 N1） |
| `test_manual_spec_missing_is_degraded_flag_not_fake` | 5 规格缺失 | 不伪造 SKU |
| `test_manual_untraceable_source_still_records_provider` | 8 不可追溯 | 无链接仍记 provider/时间/trace_id |
| `test_import_gate_blocks_all_non_authentic` | 1/2/3/10 | hardcoded_fallback/unknown/空/login_wall/placeholder 全拦，**无论 auto_run_pipeline**，is_authentic=False |
| `test_import_gate_allows_authentic_scrapling` | 白名单 | scrapling 放行自动流转（不误杀合法采集） |
| `test_listing_gate_blocks_fallback_source` | 10 | hardcoded_fallback 上架 blocked + unauthentic_source |
| `test_listing_gate_blocks_missing_source` | 8 | 来源缺失上架 blocked |
| `test_listing_gate_passes_authentic_source` | 白名单 | scrapling/manual/1688_open_api 不误拦 |
| `test_provider_result_fail_closed_no_data_on_reject` | 铁律 | ok=False → data=None、provenance=None |

### 2.2 接入 E0-E5（不另起标准）
| 测试 | 断言 |
|---|---|
| `test_evidence_grade_values_match_m334` | 枚举 = E0..E5，与 M334 一致 |
| `test_evidence_grade_manual_starts_at_e0` | 人工录入初始 E0，非 E4/E5（不可跳级做利润结论） |
| `test_provenance_product_level_vs_field_level` | 商品级 E0 ≠ 价格字段级 verified（二者独立） |
| `test_field_provenance_carries_provider_and_time` | 字段级带 provider + collected_at（可审计） |

## 3. 回归验证要点

- **删 price=35.8（N1）**：`test_manual_missing_price_fail_closed` + fallback 闸门测试确认价格缺失 fail-closed，不伪造。
- **白名单闸门**：`test_import_gate_blocks_all_non_authentic`（参数化 5 种非真实来源 × auto True/False）确认旧"仅 hardcoded_fallback+True 才拦"的绕过已封堵；`test_import_gate_allows_authentic_scrapling` 确认合法采集不被堵。
- **listing_gate unauthentic_source**：确认 fallback/缺失来源 blocked，真实来源 passed（不误杀）。`test_listing_gate_margin.py` fixture 加 `data_source="manual"` 后毛利测试仍全过。
- **CI 阻断规则**：改动文件 `ruff check --select F821,F811,E9` 全部 All checks passed。

## 4. 环境限制说明（非 D8-F 引入）

- 全量 `pytest tests/` 受**既有环境问题**限制，与 D8-F 改动无关：
  - `tests/test_selection_batch_service.py` 收集失败：`ModuleNotFoundError: No module named 'langgraph'`（本地 venv 未装，CI 有）。
  - 全量套件本地运行超时（测试量大），故按相关套件分批验证；CI Pre-check 在完整环境跑通（success）。
- 中文全角字符触发 Ruff RUF002/RUF003，属**既有噪音**（既有 service 文件同样命中），不在 CI 阻断集（`--select F821,F811,E9`），CI 全量报告 `--exit-zero`。

## 5. 结论

D8-F 六阶段全部通过自动化验证：10 类异常 fail-closed 覆盖、E0-E5 打通、删伪造价格、白名单闸门、下游 provenance 贯通、legacy 鉴权、Orchestrator fail-closed。相关套件 + CI Pre-check 全绿，无回归。
