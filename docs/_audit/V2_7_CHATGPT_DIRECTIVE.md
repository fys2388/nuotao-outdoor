# M4 V2.7 — PostgreSQL 数据库集成验证与 Migration 0092 安全验收（Owner 正式指令）

> 来源：ChatGPT「定价原则评审」会话，V2.6 条件通过（数据库层验收未完成）后下达。
> 状态：**正式启动 V2.7**（V2.6 不返工整个身份模型，但 PostgreSQL 验收必须补齐）。

## 一、任务定位

V2.6 的核心设计与应用层实现方向已获条件通过。当前阻塞是 PostgreSQL 集成测试未执行。V2.7 只负责完成真实 PostgreSQL 环境中的：Migration 0092 验证；三态身份模型数据库约束验证；Supplier / Offer 数据关联验证；历史数据迁移验证；Migration downgrade 验证；全链路数据库集成测试。**不得扩大到新的生产业务功能。**

## 二、P0：建立隔离 PostgreSQL 测试环境

1. 确认项目生产目标 PostgreSQL 主版本。
2. 使用相同主版本建立一次性隔离测试数据库。
3. 禁止连接生产数据库。禁止使用生产凭据。
4. 记录 PostgreSQL 版本、测试数据库名称、测试时间。
5. 测试结束后清理隔离测试数据。
6. 如果本地 Docker 不可用，可以采用其他隔离 PostgreSQL 环境，但**必须是真实 PostgreSQL，而不是 SQLite 替代**。
7. **不得因为环境问题将 PostgreSQL 测试标记为 PASS。**

## 三、P0：验证 Migration 0092

从 Migration 0092 的真实前置版本开始执行：
- Alembic upgrade 至 0092。
- 验证全部新增字段。
- 验证 PRODUCT 部分唯一索引。
- 验证 VARIATION 部分唯一索引。
- 验证 workspace_id 隔离。
- 验证 NULL 行为。
- 验证 SKU 非唯一辅助索引。
- 检查历史数据兼容性。
- 执行 downgrade。
- 验证回滚后的表、索引、约束恢复情况。

必须验证：同一 workspace 同一 Product 不允许重复创建商品级映射；同一 workspace 同一 Variation 不允许重复创建变体级映射；不同 workspace 可以拥有相同外部 WooCommerce ID；NULL 不会绕过业务身份校验；未知身份不会被数据库或应用自动归类为 PRODUCT。**禁止仅检查 migration Python 语法或 SQLAlchemy create_all 就判定通过。**

## 四、P0：修订身份判定边界

明确区分：A. 已确认没有变体；B. 变体列表尚未完整获取；C. WooCommerce API 请求失败；D. 本地变体数据尚未同步完整；E. 有变体但当前记录缺少 Variation ID。**只有 A 可以判定为 PRODUCT。B、C、D、E 必须保持 UNKNOWN_LEGACY 或适当的未确认状态。** 要求测试数据覆盖以上所有情况。

## 五、P0：修订 Supplier / Offer 冲突策略

**禁止直接使用最新 effective_at 自动覆盖规格映射冲突。** 必须区分：同一 Offer 的报价更新；同一 Offer 的规格映射变更；多供应商独立报价；同一 Offer 的冲突规格证据。冲突必须：保留全部历史证据；保持映射未确认；记录冲突原因及 trace_id；不自动覆盖已验证映射；等待人工或经过批准的证据审核。

## 六、P1：真实 PostgreSQL 集成测试

至少覆盖：PRODUCT 唯一性；VARIATION 唯一性；UNKNOWN_LEGACY；部分唯一索引；NULL 边界；workspace 隔离；SKU 重复与缺失；多供应商、多 Offer；Offer 报价历史；Offer 失效归档；映射冲突；OrderItem 变体关联；InventorySnapshot 变体级更新；父商品误更新阻断；CostSnapshot 历史不覆盖；历史数据回填幂等；event_service 和 trace_id；migration upgrade / downgrade。**不能只测 Repository mock，必须通过真实 PostgreSQL 完成数据库读写。**

## 七、修复测试环境依赖问题

调查 slowapi 0.1.10 与 Starlette 1.6.0 不兼容：确认项目真实依赖约束；查明该冲突是否来自已有依赖漂移；优先建立可复现、兼容的测试依赖锁定方案；如果需要修改项目依赖，必须单独说明变更影响；不得为绕过错误而跳过核心测试；确保 V2.7 测试与现有核心测试都能运行。

## 八、Git 管理

检查：V2.5 文档基线 f7ee816；V2.6 代码文件；V2.6 未提交文件；Migration 0092；新增测试；无关改动。修订完成并通过测试后，**单独提交 V2.6/V2.7 实现及测试文件。禁止 git add .。**

## 九、生产限制

本轮仍然禁止：生产 Migration 0092；生产数据库回填；生产库存同步；WooCommerce API 写入；自动采购；自动加购；促销；商品调价；SKU 修改；未经 Owner 审批的规则修改；生产部署。

## 十、最终交付与停止条件

提交：PostgreSQL 版本及隔离环境证明；Migration 0092 upgrade 报告；Migration 0092 downgrade 报告；数据库索引和约束验证报告；三态身份边界测试报告；Supplier / Offer 冲突处理修订；真实 PostgreSQL 集成测试结果；现有核心测试结果；Ruff 检查结果；依赖兼容性处理报告；Git commit SHA、branch、diff、worktree；生产环境未发生写入的确认报告。

**全部完成后停止，交由 Owner 终审。** 未经 Owner 新的书面授权，不得执行生产迁移或任何生产写操作。
