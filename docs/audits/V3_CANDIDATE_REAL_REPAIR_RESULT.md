# V3 Candidate Real Repair Result

**Date:** 2026-10-03  
**Status:** ❌ **REAL_CANDIDATE_REPAIR_BLOCKED**  
**Reason:** 数据库中不存在 16 个 1688 候选产品

---

## 1. Migration 0071 状态

### 1.1 迁移检查

```bash
alembic current
```

**结果:** `0071 (head)` ✅

迁移 0071 已成功应用。

### 1.2 数据完整性字段验证

products 表已添加 6 个新字段：

| 字段 | 类型 | 可空 |
|------|------|------|
| `data_integrity_status` | VARCHAR | YES |
| `data_integrity_score` | NUMERIC | YES |
| `data_integrity_missing` | JSONB | NO |
| `data_integrity_checked_at` | TIMESTAMPTZ | YES |
| `data_integrity_trace_id` | VARCHAR | YES |
| `data_integrity_version` | VARCHAR | NO |

---

## 2. 数据库状态

### 2.1 产品总数

| 来源 | 数量 |
|------|------|
| woocommerce | 37 |
| manual | 6 |
| intake | 1 |
| **总计** | **44** |

### 2.2 候选状态

| candidate_status | 数量 |
|-----------------|------|
| NULL | 42 |
| candidate | 1 |
| testing | 1 |

### 2.3 1688 候选产品

| 来源 | 数量 |
|------|------|
| 1688 | **0** |

**结论:** 数据库中**不存在** 16 个 1688 候选产品。

### 2.4 现有候选产品

| ID | Name | SKU | Source | Status | Weight |
|----|------|-----|--------|--------|--------|
| bb07802a... | Test Outdoor Tent | TEST-TENT-001 | intake | candidate | 2.500 |
| f58a4d1e... | Premium Camping Tent 4-Person | NT-TENT-005 | manual | testing | 3.500 |

---

## 3. Backfill Results

**未执行** — 无 1688 候选产品可回填。

---

## 4. Cost Sync

**未执行** — 无 1688 候选产品可同步成本。

---

## 5. Data Readiness

**未执行** — 无 1688 候选产品可评估。

---

## 6. V3 Scores

**未执行** — 无 1688 候选产品可评分。

---

## 7. Hard Rules

**未执行** — 无 1688 候选产品可评估。

---

## 8. Decision Readiness

**未执行** — 无 1688 候选产品可准备决策。

---

## 9. Blockers

| # | Blocker | Impact | Resolution |
|---|---------|--------|------------|
| 1 | 数据库中没有 16 个 1688 候选产品 | 无法执行 REAL 16-Candidate Repair | 需要先导入 1688 候选产品 |
| 2 | product_sourcing_candidates 表为空 (0 条) | 无候选数据 | 需要运行 1688 数据导入 |

---

## 10. PHASE 5: Gate Audit

### 10.1 GATE_MIN_SCORE=40 实际代码

```python
# backend/app/services/data_integrity_gate.py
GATE_MIN_SCORE = Decimal("40.0")
```

### 10.2 门类型判定

**GATE_MIN_SCORE=40 是 A. data completeness gate（数据完整性门）**

理由：
1. 该门检查产品的**数据完整性**，而非 V3.0 评分
2. 权重分配基于**数据字段**是否存在：
   - operational_dimensions: 30%
   - margin_rate: 10%
   - shipping_ratio: 10%
   - reference_price_usd: 10%
   - weight_kg: 10%
   - supplier_rating: 10%
   - brand_fit: 10%
   - category: 5%
   - return_rate: 5%
3. 如果数据完整性分数 < 40，门阻断评分，产品保持当前漏斗阶段

### 10.3 Data Readiness 与 V3 Score 分离

**完全分离** ✅

流程：
1. **Data Readiness Gate** (`check_integrity()`) → 检查数据完整性
   - 如果门失败：返回 `gate_blocked=True, score=None`
   - 如果门通过：继续到步骤 2
2. **V3.0 Score** (`map_dimensions_strict()`) → 计算 Nuotao Score
   - 使用严格映射器，缺失数据抛出 `DataInsufficientError`
   - 绝不使用 NEUTRAL=5.0 默认值

---

## 11. Failures

| Phase | Status | Error |
|-------|--------|-------|
| PHASE 1 (Migration) | ✅ Pass | 0071 已应用 |
| PHASE 2 (Real 16 Candidates) | ❌ Blocked | 数据库中无 1688 候选 |
| PHASE 3 (Output) | ❌ Blocked | 无数据可统计 |
| PHASE 4 (Per-Candidate Report) | ❌ Blocked | 无候选产品 |
| PHASE 5 (Gate Audit) | ✅ Pass | GATE_MIN_SCORE=40 是数据完整性门 |
| PHASE 6 (Decision Preparation) | ❌ Blocked | 无候选产品 |
| PHASE 7 (No Product Master) | ✅ Pass | 未创建任何 Product Master |
| PHASE 8 (Audit) | ✅ Pass | 本报告已创建 |

---

## 12. 最终状态

**REAL_CANDIDATE_REPAIR_BLOCKED** ❌

### 原因

数据库中**不存在** 16 个 1688 候选产品：
- `products` 表：44 条记录，0 条来自 1688
- `product_sourcing_candidates` 表：0 条记录
- 现有候选产品：1 个 intake 来源，1 个 manual 来源

### 下一步

要执行 REAL 16-Candidate Repair，需要：
1. 确认 16 个 1688 候选产品应该从哪个来源导入
2. 运行 1688 数据导入流程（通过 Newton Agent 或 1688 API）
3. 重新执行 `backend/scripts/repair_16_candidates.py`

### 已完成的准备工作

- ✅ Migration 0071 已应用
- ✅ 数据完整性字段已添加
- ✅ 1688 回填服务已实现
- ✅ 成本同步服务已实现
- ✅ 数据完整性门已实现
- ✅ 严格映射器已实现
- ✅ 346/346 测试通过
- ✅ 修复脚本已创建

---

## 13. Trace ID

N/A — 未执行实际评估。

---

*Report generated: 2026-10-03*  
*Database: PostgreSQL nuotao@localhost:5432*  
*Migration: 0071 (head)*
