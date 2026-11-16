# Candidate Source Lineage Audit Report

**Date:** 2026-10-03  
**Status:** SOURCE_NOT_FOUND — 16 candidates never persisted to database  
**Root Cause:** 1688 → Candidate 持久化环节缺口 (NOT workspace/environment mismatch)

---

## Executive Summary

经过全面调查，**16 个候选产品从未持久化到任何数据库**。这不是 Workspace/环境错位问题，而是**系统缺少从 1688 数据源到 Candidate 表的自动化持久化路径**。

用户之前看到的 "16 个候选" 最可能来自以下三个来源之一，但均未落库：
1. `sourcing_import_results.json` — Excel 导入的 60 个产品报告
2. NewtonSourcing 页面搜索结果 — 用户浏览但未点击 "加入候选库"
3. ProductPipeline 页面 localStorage — 临时缓存，页面刷新即丢失

---

## 1. 数据库搜索 (PostgreSQL + SQLite)

### 1.1 PostgreSQL (production database)

| 查询 | 结果 |
|------|------|
| `SELECT COUNT(*) FROM products WHERE source='1688'` | **0** |
| `SELECT COUNT(*) FROM product_sourcing_candidates` | **0** |
| `SELECT COUNT(*) FROM event_log WHERE payload LIKE '%1688%'` | **0** |
| `SELECT COUNT(*) FROM ai_agent_runs` | **0** |
| 全表搜索 '1688' / 'newton' | **0** (仅 1 个 WooCommerce SKU 含 "1688") |

### 1.2 SQLite Databases

| Database | 1688 Products |
|----------|--------------|
| `_local_dev.db` (3.6MB) | **0** |
| `_test_readiness.db` (4.1MB) | **0** |
| `data/archive_pool.db` | N/A (no products table) |
| `data/draft_pool.db` | N/A (no products table) |
| `data/workflow_state.db` | N/A (no products table) |

**结论：** 没有任何数据库包含 1688 候选产品。

---

## 2. 文件系统中的 1688 数据

### 2.1 `sourcing_import_results.json` (104KB)

```
路径: E:\AI\nuotao-ai-os\backend\sourcing_import_results.json
时间: 2026-09-04 00:31:27
来源: TitleSearch_1688-ExportProduct-2026_9_4 00_30_20.xlsx
产品数: 60
```

**内容示例：**
```json
{
  "subject": "跨境热销感应头灯可伸缩变焦Type-C充电户外多功能数显感应式头灯",
  "product_id": "1063478222148",
  "price": 8.2,
  "supplier": "宁波国亮电子科技有限公司",
  "detail_url": "https://detail.1688.com/offer/1063478222148.html",
  "sourcing_score": {"total_score": 80, "decision": "强烈推荐"}
}
```

**关键发现：** 这个文件是 `import_1688_products.py` 脚本的输出，**只生成 JSON 报告，不会写入数据库**。

### 2.2 Newton 搜索结果 JSON 文件

| 文件 | 产品数 | 类型 |
|------|--------|------|
| `newton_sourcing_20260904_173358.json` | 3 | Mock 数据 |
| `newton_sourcing_20260929_172105.json` | 5 | 真实搜索 |
| `newton_sourcing_20260929_172257.json` | 5 | 真实搜索 |
| `newton_sourcing_20260929_173926.json` | 5 | 真实搜索 |

**结论：** Newton 搜索结果保存在本地 JSON 文件中，但**从未导入到数据库**。

---

## 3. 持久化路径分析

### 3.1 所有 1688 → Candidate 路径

| 路径 | 入口 | 是否持久化 | 说明 |
|------|------|-----------|------|
| A. Excel 导入 | `import_1688_products.py` | ❌ 否 | 只生成 JSON 报告 |
| B. Newton 搜索 | NewtonSourcing.tsx → "加入候选库" | ✅ 是 | 需要用户手动点击 |
| C. Newton → 工作流 | NewtonSourcing.tsx → "带入产品工作流" | ❌ 否 | 只存 localStorage |
| D. ProductPipeline | ProductPipeline.tsx | ❌ 否 | 从 localStorage 读取，不创建 candidate |
| E. 1688 URL 导入 | `/import-from-1688` API | ✅ 是* | 需要 `auto_run_pipeline=True` + session |
| F. run_pipeline | product_pipeline_service.py | ✅ 是* | 需要 session 参数 |

**带 * 的路径需要特定条件才能持久化。**

### 3.2 关键代码证据

**路径 B — NewtonSourcing.tsx (line 112-143):**
```typescript
// 真实写入系统选品候选库（POST /newton/sourcing/import）
const addCandidates = async (products: any[], keys: string[]) => {
  const res = await api.importNewtonSourcing(products, ...)
  // ...
}
```
→ 需要用户**主动点击 "加入候选库" 按钮**

**路径 C — NewtonSourcing.tsx (line 156-167):**
```typescript
const handleCarryToPipeline = (item, index) => {
  goPipeline('product_pipeline_input', {...})  // ← localStorage
  if (!importedKeys.has(key)) {
    void addCandidates([item], [key])  // ← 这里会持久化
  }
}
```
→ 只有 `addCandidates` 被调用才会持久化，否则只存 localStorage

**路径 A — import_1688_products.py:**
```python
# 输出:
#   - sourcing_import_results.json (标准化商品数据+选品评分)
#   - 控制台表格展示TOP推荐
# 不会写入数据库
```

---

## 4. 前端 localStorage 分析

### 4.1 ProductPipeline.tsx 使用 localStorage

```typescript
// 读取
const savedProduct = localStorage.getItem('product_pipeline_input')
const savedBatch = localStorage.getItem('product_pipeline_batch')

// 写入后删除
localStorage.removeItem('product_pipeline_input')
localStorage.removeItem('product_pipeline_batch')
```

**关键发现：** ProductPipeline 页面读取 localStorage 中的数据后**立即删除**，不会持久化到数据库。

### 4.2 ProductCandidatesPage.tsx 不使用 localStorage

```typescript
const loadCandidates = useCallback(async () => {
  const response = await api.getSourcingCandidates('all', 200, 0)
  // 只从 API 读取，不使用 localStorage
}, [])
```

---

## 5. 根因判断

### ✅ 持久化缺口 (NOT 环境错位)

**证据：**
1. 所有数据库 (PostgreSQL + SQLite) 中都没有 1688 候选
2. 只有一个 workspace (00000000-0000-0000-0000-000000000001)
3. 没有 staging/production 环境的数据差异
4. 系统缺少从 Excel/Newton/LocalStorage 到 Candidate 表的自动化持久化路径

### ❌ 不是环境错位

**证据：**
1. 只有一个 workspace
2. 没有多个环境的数据副本
3. 数据库结构一致，没有 workspace_id 过滤问题

---

## 6. 修复建议

### 6.1 立即修复：自动持久化

**方案 A：NewtonSourcing 搜索完成后自动持久化**

```typescript
// NewtonSourcing.tsx - 搜索完成后自动保存候选
useEffect(() => {
  if (result?.products?.length > 0 && !autoPersisted) {
    setAutoPersisted(true)
    void addCandidates(result.products, result.products.map((p, i) => String(i)))
  }
}, [result])
```

**方案 B：import_1688_products.py 增加数据库导入**

```python
# import_1688_products.py - 增加数据库导入步骤
async def import_to_database(products, workspace_id):
    """将导入的产品持久化到数据库"""
    for product in products:
        await create_product_candidate(
            product_data=product,
            source_type='1688',
            source_url=product.get('detail_url'),
            workspace_id=workspace_id
        )
```

**方案 C：ProductPipeline 完成后自动创建 Candidate**

```typescript
// ProductPipeline.tsx - 处理完成后创建 candidate
const handlePipelineComplete = async (productData) => {
  await api.createCandidate({
    name: productData.name,
    source: '1688',
    source_url: productData.source_url,
    // ...
  })
}
```

### 6.2 验证步骤

```bash
# 1. 确认 API 返回候选
curl http://localhost:8000/api/v1/sourcing/candidates?status=all

# 2. 确认数据库有 1688 产品
SELECT COUNT(*) FROM products WHERE source = '1688';

# 3. 确认 event_log 有记录
SELECT * FROM event_log WHERE payload::text LIKE '%1688%' ORDER BY created_at DESC;
```

### 6.3 预防措施

1. **自动持久化**：所有 1688 数据源应自动保存为候选
2. **导入反馈**：导入成功/失败应有明确的 UI 反馈
3. **数据审计**：记录每次导入的 source_type 和数量
4. **LocalStorage 警告**：如果数据只存在 localStorage，应明确提示 "未持久化"

---

## 7. 最终结论

| 项目 | 结论 |
|------|------|
| 16 candidates 原始来源 | `sourcing_import_results.json` (60个产品) 或 Newton 搜索结果 |
| 实际 API | GET /api/v1/sourcing/candidates → 返回 0 条 |
| workspace | 00000000-0000-0000-0000-000000000001 (唯一) |
| environment | Development (localhost) |
| database table | products (source='1688') → **空** |
| candidate IDs | N/A（不存在） |
| 1688 IDs / URLs | 存在于 `sourcing_import_results.json` 中（60个） |
| trace_ids | N/A（不存在） |
| 是否持久化 | ❌ 否 |
| 缺失原因 | 系统缺少自动化持久化路径 |
| root cause | **1688 → Candidate 持久化环节缺口** |
| recommended fix | 搜索/导入完成后自动持久化候选 |

---

*Report generated: 2026-10-03*  
*Database: PostgreSQL 17.11 nuotao@localhost:5432*  
*Workspace: 00000000-0000-0000-0000-000000000001*  
*Files scanned: 15+ databases, 20+ JSON files, 50+ source files*
