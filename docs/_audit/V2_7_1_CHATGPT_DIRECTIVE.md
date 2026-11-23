# M4 V2.7.1 — Alembic 迁移链路完整性整改（Owner 正式指令）

> 来源：ChatGPT「定价原则评审」会话，V2.7 终审（21 项 PG 集成测试成果认可，0092 迁移链完整性尚未验收）后下达。
> 状态：**正式启动**（生产权限保持关闭）。

## 一、任务目标

解决 M4 V2.7 暴露的核心问题：`product_mappings` 不在当前 Alembic 迁移链中，Migration 0092 依赖人工创建的历史表结构，导致完整迁移链尚未被验证。本轮目标：
1. 查清 `product_mappings` 的历史来源。
2. 建立可复现的空数据库迁移路径。
3. 建立可复现的历史数据库升级路径。
4. 验证两个路径最终 schema 一致。
5. 修复既有迁移测试失败。
6. 补充 rate_limit.py 兼容性回归测试。

**本轮不增加新的生产业务能力。**

## 二、P0：调查 Migration 0070 / product_mappings 历史

**先审计，不要立即修改迁移文件。** 检查：
- 全部 Alembic revision 文件；`alembic history`；`alembic heads`；当前 migration graph；
- 0070 的原始迁移文件和 park 原因；
- `product_mappings` 最初的创建逻辑；
- ProductMapping SQLAlchemy Model；
- 后续所有相关 ALTER TABLE；
- 0092 对 product_mappings 的实际依赖；
- 项目历史文档中关于该表创建与上线的记录。

形成时间线：revision → 业务表创建 → 字段修改 → 索引约束 → 当前状态。

明确区分：A. 正式 Alembic 创建的表；B. 曾经执行、后来 park 的历史迁移；C. 人工 SQL 或其他方式创建的表；D. 仅存在于 SQLAlchemy Model、从未正式迁移的字段。

**不得直接恢复 0070，不得修改已应用迁移的历史语义，不得删除历史迁移文件。**

## 三、P0：设计完整迁移修复方案

基于调查结果提供至少两种方案比较：1. 现有 migration graph 的向前兼容修复；2. 新增 forward-only reconciliation migration。

每种方案说明：对已有数据库的影响；对全新数据库的影响；是否产生重复表或重复字段；索引和外键处理；事务边界；升级和降级策略；失败后恢复方式；已经应用过 0092 的数据库如何兼容。

优先保持已经应用的历史 revision 不可变。如果新增迁移，必须能够同时兼容：product_mappings 已存在/不存在；已存在部分 V2.6 字段/完整 V2.6 字段；存在历史重复映射；存在 NULL 身份记录。**不允许通过 IF NOT EXISTS 简单掩盖 schema 不一致。** 必须比较现有结构与预期结构，验证字段类型、约束、索引和外键是否真正正确。**先提交设计和测试方案，完成后再实现。**

## 四、P0：建立两条真实 PostgreSQL 迁移路径

必须使用 PostgreSQL 16。

**路径 A：空数据库。** 建立全新数据库；从当前正式 Alembic base 开始；运行完整迁移链；到达当前 head；验证所有业务表和索引；验证 identity model 字段和约束。**禁止人工提前创建正式迁移本应负责创建的业务表。**

**路径 B：历史数据库。** 按有证据的历史 0091 schema 构造隔离测试库；执行 0092；执行后续迁移至当前 head；验证表和约束；验证关键历史数据；验证最终 schema 与路径 A 一致。

两个路径均必须完整记录 Alembic revision。

## 五、P0：修复 test_postgres_migrations.py

原始结果：1 failed + 4 errors。必须逐项调查。尤其：`product_mappings does not exist`；旧 revision 断言 `==0024`。保留测试原本的业务意图。**修复后不得通过删除测试、无条件 skipif、放宽约束或 mock 数据库来获得 PASS。**

交付：原始失败；根因；修改文件；修复后测试结果；与当前 migration graph 的对应关系。

## 六、P1：修复映射冲突幂等性

针对 spec_conflict：1. 同一冲突证据重复提交；2. 相同 trace_id 重试；3. 不同 trace_id 但同一冲突事实；4. 不同供应商提供冲突规格；5. 人工审核后接受或驳回。确保冲突证据不会因为重试而无限重复创建。已验证映射不得被未经审核的新规格证据覆盖。

## 七、P1：rate_limit.py 回归测试

针对 `_read_file(*args, **kwargs)` 兼容改动，验证：有效 env 文件；不存在的 env 文件；env_file=None；其他参数传递；原有 rate limit 行为；原始配置加载行为。确认 monkeypatch 调用原始逻辑，没有绕过必要配置读取。**不得仅以 conftest 可以加载作为验收。**

## 八、测试与质量门槛

必须交付：1. 全新 PostgreSQL 数据库完整 upgrade PASS；2. 历史 0091 数据库升级 PASS；3. 两条路径 schema 对比一致；4. Upgrade/Downgrade 验证；5. 全部迁移测试结果；6. 现有核心测试结果；7. 身份模型 PostgreSQL 测试结果；8. Offer 冲突幂等测试；9. rate_limit 回归测试；10. Ruff All checks passed。**测试失败必须说明具体原因，不得隐藏。**

## 九、Git 管理

当前 V2.6/V2.7 代码尚未提交。先提交文件清单和 diff 审计结果。**不得将未验收的 Migration 0092 和其他改动混为一个无差别提交。** 整改完成后按职责分开提交：迁移链修复；身份模型及映射实现；测试；rate_limit 兼容修复。每个 commit 单独说明文件范围和测试证据。**禁止 git add .。**

## 十、生产禁令

本轮仍然禁止：生产数据库 migration；生产数据库回填；生产库存同步；WooCommerce API 写入；自动采购；自动加购；促销；商品调价；SKU 修改；生产规则修改；生产部署。**所有测试必须运行在隔离数据库。**

## 十一、完成后停止

提交 V2.7.1 完整报告：Alembic 历史调查；0070 park 原因；product_mappings 表来源；迁移修复设计；两条 PostgreSQL 迁移路径；schema 比较；migration 测试；rate_limit 回归测试；Offer 冲突幂等测试；完整测试及 Ruff；Git commit 与 worktree 状态；生产未写入证明。**完成后停止，等待 Owner 终审。未经 Owner 新的书面授权，不得执行任何生产迁移、回填或写操作。**
