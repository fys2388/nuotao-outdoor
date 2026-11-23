# M4 V2.7.2 — 0076 历史迁移执行状态审计报告

> 指令：`docs/_audit/V2_7_2_CHATGPT_DIRECTIVE.md` §三（0076 特别限制）
> 角色：`v272-git-commit`（实现子代理）
> 结论：**本地无法确定生产执行状态**；0076 文件**暂缓提交**，等 Owner 提供生产 revision 或确认从未部署后拍板。
> 生产禁令：全程**未连接生产库、未使用生产凭据**；本报告不含真实密码/连接串。

---

## 一、0076 修改的精确性质（git diff 取证）

`git diff backend/alembic/versions/0076_first_batch_20_products.py` 显示**仅 2 行改动，全部位于 `downgrade()` 函数内**：

```diff
             DELETE FROM products
             WHERE sku LIKE :prefix
-              AND workspace_id = :workspace_id
+              AND workspace_id = CAST(:workspace_id AS uuid)
             """
-        ).bindparams(prefix=f"{prefix}%", workspace_id=WORKSPACE_ID)
+        ).bindparams(prefix=f"{prefix}%", workspace_id=str(WORKSPACE_ID))
```

- **改动语义**：`downgrade()` 里 `DELETE FROM products` 语句的 `workspace_id` 绑定参数，从「裸 UUID 对象（`WORKSPACE_ID`）」改为「`CAST(:workspace_id AS uuid)` + `str(WORKSPACE_ID)`」。
- **根因**：asyncpg（生产 PG 驱动）把裸字符串/UUID 绑定参数与 `uuid` 列比较时推断为 `character varying`，触发 `uuid = character varying` 类型错误。`CAST(... AS uuid)` 显式声明参数类型，`str(WORKSPACE_ID)` 提供规范化字符串。这是 **bind 类型修复**，不改变 DELETE 的过滤语义（仍是按 `prefix` + `workspace_id` 删 products）。
- **该语句此前从不被执行**：downgrade 到 0076 之前的版本才会触发；V2.7.1 的 downgrade drill 终点为 0091，未经过 0076，故此 bug 在 V2.7.1 才首次被真实执行暴露（见 `PRICING_V2_7_1_EXECUTION_REPORT.md` §八-5）。

---

## 二、Owner 五问诚实回答

### Q1：0076 是否已经在任何生产数据库执行？

**本地无法确定。** 生产库访问被禁令禁止，无生产连接、无生产凭据。

客观事实（可从仓库取证）：
- 0076（`0076_first_batch_20_products.py`）是 **Alembic 迁移链内的正式 revision**（非 park；park 的是 0070，见 `0070_product_mapping_workspace_scope.py.dsh-parked`）。
- 因此**理论上**：任何跑过完整 `alembic upgrade head`（到 0092）的库都会**依次执行到 0076 的 upgrade**。
- 但「理论上会执行」≠「生产真的跑过」。是否执行取决于生产部署历史（生产库是否做过 `alembic upgrade` 到 ≥0076 的版本）。

**需 Owner 提供**：生产库当前 `alembic_version`，或明确确认「生产从未部署/从未执行 0076」。本地无法替代此确认。

### Q2：当前生产数据库的 Alembic revision 是什么？

**本地无法确定（生产访问被禁）。**

可提供的**推断（明确标注为推断、非事实）**：
- 迁移链 head 为 **0092**（`0092_identity_model.py`）。若生产曾跑完整链到最新，则 `alembic_version` 应为 `0092`。
- 若生产停留在更早部署点，则可能是 0092 之前任一 revision（0076/0083/0091 等）。
- 0070 被 park，链绕过它（0071 down_revision 指向 0069），故 0070 不会出现在 version 历史里。
- **此推断不能替代事实**——只有查询生产 `alembic_version` 表才能确定。

### Q3：修改前后的 downgrade 差异具体是什么？

见 §一。精确差异：`downgrade()` 中 `DELETE FROM products ... AND workspace_id = :workspace_id` 的绑定参数，由「裸 UUID（asyncpg 推断为 varchar → 报类型错）」改为「`CAST(:workspace_id AS uuid)` + `str(WORKSPACE_ID)`」。**纯 bind 类型修复**，DELETE 过滤条件（prefix + workspace_id）语义不变。

### Q4：这两行修复是否只影响 downgrade，不影响 upgrade？

**是，只影响 downgrade。** git diff 证明改动全部在 `downgrade()` 函数体内；`upgrade()`（0076 的 20 个商品 seed 逻辑）**一行未动**。因此：
- 已应用 0076 的库：upgrade 行为零影响。
- 未来 downgrade 经过 0076 的库：使用新代码。

### Q5：对已经执行过 0076 的数据库，是否会造成迁移历史或回滚行为不一致？

**诚实分析（分 upgrade / downgrade 两面）：**

- **upgrade 面：零影响、无不一致。** Alembic 只在**首次**应用某 revision 时执行其 `upgrade()`；已应用 0076 的库，`alembic_version` 已记录 0076，**修改 0076 文件不会重跑其 upgrade**。故 upgrade 历史与 schema 完全不变。

- **downgrade 面：从「报错」变「正常执行」，属修复而非破坏。** 旧行为（裸 UUID）在 asyncpg 下 downgrade 经过 0076 时会抛 `uuid = character varying` 类型错误 → **downgrade 本来就是坏的（无法完成）**。新行为修复类型推断 → downgrade 可正常删除目标 products 行。所以对已执行库，将来 downgrade 经过 0076 时**行为从「失败」改进为「成功」**，不会破坏既有数据或迁移历史。

- **迁移历史一致性**：修改 0076 文件**不改变** `revision`/`down_revision` 标识，Alembic version graph 不变，已记录的 version 历史不受影响。

**最终结论需 Owner 确认 Q1**（生产是否跑过 0076）才能下定论；但即便已部署，本修复对已执行库也是「downgrade 修复、upgrade 无影响」，无回滚不一致风险。

---

## 三、两种情形与建议

| 情形 | 含义 | 对 0076 提交的建议 |
|---|---|---|
| **A. 生产从未执行 0076**（从未部署到 ≥0076，或生产库不存在） | 0076 从未在任何受管理环境跑过，无旧行为依赖 | **可安全提交**。修复让首次 downgrade 即正确，无历史包袱。 |
| **B. 生产已执行 0076** | 已应用库 upgrade 不重跑（零影响）；将来 downgrade 经过 0076 由「报错」变「正常删除」 | 属**改进**，技术上可提交；但按指令「若已在生产执行，原则上不继续改历史迁移，应评估放新迁移或专门回滚工具」——**需 Owner 拍板**是否接受改历史文件，或改为把修复挪到新迁移/回滚工具。 |

**子代理建议**：Owner 先确认生产 `alembic_version`（区分情形 A/B）。
- 若 A → 可在下一轮授权单独提交 0076（`fix(alembic)`）。
- 若 B → Owner 决定：接受改历史文件，或将 `CAST` 修复迁移到专门回滚工具/新迁移。
- **在 Owner 拍板前，0076 文件保持未提交**（遵守指令 §三）。本轮其他已批准文件已按职责独立提交，不受 0076 暂缓影响。

---

## 四、补充：0076 的 93 个 pre-existing Ruff 违规

- 0076 全文报 **93 项 pre-existing Ruff 违规**（I001 import 排序、F401 未用导入 `UUID`/`JSONB`、大量格式化建议），**遍及全文、非本轮引入**（git diff 证明本轮仅改 downgrade 2 行）。
- 按 V2.7.2 指令 §一，本轮**不清理**这 93 项历史违规（避免对历史迁移文件做无业务意义的大 diff）。
- 本报告**不声称** 0076 Ruff 全绿；仅声明：本轮对 0076 的 2 行修改本身符合 Ruff，93 项历史违规保留记录、留待将来的独立「历史迁移文件清理」任务处理。

---

## 五、生产未写入确认

- 本审计**未连接生产数据库**，未查询生产 `alembic_version`，未执行任何生产迁移/回滚/写入。
- 所有结论基于：本地 git diff、迁移链文件结构、仓库内既有报告（V2.7.1）。
- 报告不含任何真实密码/凭据/生产连接串。

**审计完成，0076 暂缓提交，等 Owner 拍板。**