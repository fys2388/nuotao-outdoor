# 产品生命周期实施路线图 (Product Lifecycle Implementation Roadmap)

> **版本**: v1.0  
> **最后更新**: 2026-09-28  
> **状态**: Phase 3B Complete

---

## 1. 概述

本文档记录了产品生命周期功能从 Phase 3A 到 Phase 3B 的实施进度和后续计划。

---

## 2. 阶段划分

### Phase 3A: 后端基础 (Completed)

**目标**: 建立 Product Master 概念和审批工作流

**交付物**:
- ✅ `mastered_at` 字段 (DateTime, nullable, indexed)
- ✅ `mastered_by` 字段 (String(128))
- ✅ `mastered_trace_id` 字段 (String(64))
- ✅ 4 个新 API 端点:
  - `GET /products/workbench/summary`
  - `GET /products/workbench/tasks`
  - `GET /products/{id}/rule-results`
  - `GET /products/{id}/wc-status`
- ✅ Listing Approved 门控 (push-woocommerce)
- ✅ 25 个后端测试

**数据库迁移**: `0058_product_mastered_at.py`

---

### Phase 3B: 前端实现 (Completed)

**目标**: 实现 Product Workbench 和 Product Decision Cockpit

**交付物**:
- ✅ `ProductWorkbench.tsx` - 产品工作台页面
- ✅ `ProductDecisionCockpit.tsx` - 产品决策驾驶舱页面
- ✅ `deriveUserStage()` - 用户阶段映射函数
- ✅ 导航配置更新
- ✅ API 客户端方法添加

**关键修复**:
- ✅ DB SQLite 连接参数修复 (`ssl: False` → 条件配置)
- ✅ `product_workbench.py` 导入路径修复
- ✅ Starlette 版本升级 (0.29.0 → 0.46.2)
- ✅ `deriveUserStage()` 优先级顺序修复

---

### Phase 3C: 后续改进 (Planned)

**目标**: 完善用户阶段映射和文档

**待完成**:
- [ ] Stage Mapping 单元测试
- [ ] Browser 验收测试
- [ ] 补充 `pending_approval` 和 `listing` 阶段的数据获取

---

## 3. 依赖版本

| 包 | 版本 | 说明 |
|----|------|------|
| fastapi | 0.115.12 | Web 框架 |
| starlette | 0.46.2 | ASGI 框架 (需 >= 0.40.0, < 0.47.0) |
| httpx | 0.28.1 | HTTP 客户端 |
| sqlalchemy | >= 2.0.31 | ORM |
| pydantic | >= 2.8.0 | 数据验证 |

---

## 4. API 端点清单

| 端点 | 方法 | 描述 | 状态 |
|------|------|------|------|
| `/products/workbench/summary` | GET | 工作台阶段统计 | ✅ |
| `/products/workbench/tasks` | GET | 工作台任务列表 | ✅ |
| `/products/{id}/rule-results` | GET | 产品规则评估结果 | ✅ |
| `/products/{id}/wc-status` | GET | 产品 WooCommerce 状态 | ✅ |
| `/products/{id}` | GET | 产品详情 | ✅ |

---

## 5. 测试基线

### 当前状态 (2026-09-28)

| 指标 | 值 |
|------|-----|
| Collected | 893 |
| Passed | 待确认 (测试运行中) |
| Errors | 待确认 |
| Exit code | 待确认 |

### 历史基线

| 阶段 | Passed | Errors | Exit Code |
|------|--------|--------|-----------|
| Phase 3A | 72 | ~100 (Starlette) | 1 |
| Phase 3B (Starlette 0.29.0) | 171 | 100 | 1 |
| Phase 3B (Starlette 0.46.2) | 待确认 | 待确认 | 待确认 |

---

## 6. 已知问题

### 6.1 已修复

1. **DB SQLite 连接**: `ssl: False` 参数不兼容 aiosqlite
2. **导入路径错误**: `ListingJob` 和 `ProductCost` 从错误模块导入
3. **Starlette 版本**: 0.29.0 与 httpx 0.28.1 不兼容
4. **Stage 优先级**: `deriveUserStage()` 缺少终态优先检查

### 6.2 待解决

1. **Stage Mapping 单元测试**: 需要添加 8 个阶段的测试用例
2. **Browser 验收**: 需要完整的前端验证流程
3. **`pending_approval` 数据获取**: 前端需要调用额外 API 获取审批状态

---

## 7. 下一步计划

### 立即 (Phase 3B Closure)

- [ ] 完成测试套件运行
- [ ] 添加 Stage Mapping 单元测试
- [ ] Browser 验收测试
- [ ] 确认所有 API 端点正常工作

### 短期 (Phase 3C)

- [ ] 完善 `deriveUserStage()` 数据获取
- [ ] 添加更多阶段 (opportunity, pending_approval)
- [ ] 性能优化和错误处理改进

### 中期 (Phase 4)

- [ ] 产品生命周期仪表板
- [ ] 自动化状态转换提醒
- [ ] 生命周期分析报表

---

## 8. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-09-28 | 初始版本，记录 Phase 3A/3B 实施 |
