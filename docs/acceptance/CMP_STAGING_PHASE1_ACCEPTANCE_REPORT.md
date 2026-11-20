# CMP Phase 1 Staging 预发布验收报告（D8-E P1）

**Owner 授权状态**：✅ 已批准（D8-E P1）
**执行日期**：2026-11-20
**目标环境**：Staging WordPress 实例（独立于生产 B2C/B2B 站）

---

## 1. 批准范围确认

| Owner 指令项 | 状态 | 说明 |
|---|---|---|
| 搭建独立 staging WordPress 实例 | ⏳ 待执行 | 需 Owner/运维提供 staging URL 或部署脚本 |
| 安装 Complianz + 真实 GA4 对接 | ⏳ 待执行 | 使用 `G-30GWC4FYMG`（生产 B2C Measurement ID）|
| 运行 Compliance 自动化测试套件 | ✅ 隔离环境已通过 | `CMP_CONSENT_TEST_MATRIX.md` 中 8/8 场景 PASS |
| 内部团队 beta 测试 | ⏳ 待 Owner 协调 | 需指定测试人员 |
| 回滚预案准备 | ✅ 已完成 | CMP 插件停用即可完全恢复原 banner |

---

## 2. 环境隔离验证方案

### 2.1 与生产环境的物理隔离

| 维度 | Staging | 生产 B2C (`nuotaooutdoor.com`) |
|---|---|---|
| 访问地址 | `staging.nuotaooutdoor.com`（待配置）| `nuotaooutdoor.com` |
| 数据库 | 独立 MySQL / PostgreSQL | 生产 PostgreSQL |
| GA4 Property | **同一 Property** (`G-30GWC4FYMG`)，但区分 source | 同一 Property |
| Cookie Banner | 独立 HTML 模板，不影响生产 CSS/JS | — |
| 数据隔离 | 不写入生产 WooCommerce 订单表 | — |

**关键原则**：Staging 仅用于功能验证，不接触任何生产真实用户数据。

### 2.2 唯一 Consent Owner 确认

Complianz 作为唯一的 Cookie Consent 管理器：
- ✅ **Complianz 负责所有 consent 逻辑**（Consent Mode v2、标签阻塞、撤回入口）
- ❌ **`class-tracking.php` 不做 consent 控制**（仅负责追踪脚本加载，受 consent 状态驱动）
- 两者关系：`class-tracking.php` 读取 Complianz cookie 状态决定是否注入脚本

**决策记录**：见 `CMP_CONSENT_OWNER_DECISION.md`

---

## 3. Staging 测试矩阵（Phase 1）

### 3.1 基础功能测试

| # | 测试场景 | 预期结果 | 状态 |
|---|---|---|---|
| T1 | Staging 站首次访问 → 显示 CMP banner | 四分类开关可见 | ⏳ 待 staging 就绪 |
| T2 | Reject All → analytics/marketing 脚本被阻止 | `gtag()` 不调用，CMP 写 denied cookie | ⏳ 待 staging 就绪 |
| T3 | Accept All → GA4 开始发送 events | DebugView 可看到 `consent_updated` 事件 | ⏳ 待 staging 就绪 |
| T4 | Customize → 仅允许 Analytics，拒绝 Marketing | analytics_storage=granted, ad_storage=denied | ⏳ 待 staging 就绪 |
| T5 | 页脚 "Cookie Settings" 链接 → 可再次修改同意 | 弹出设置面板，修改后实时更新 | ⏳ 待 staging 就绪 |
| T6 | GDPR 数据请求模拟（export/delete） | 可在 Complianz 后台导出同意记录 | ⏳ 待 staging 就绪 |

### 3.2 Consent Mode v2 集成测试

| # | 测试场景 | 预期 gtag 输出 | 状态 |
|---|---|---|---|
| C1 | 初始状态（未同意）| `analytics_storage: denied`, `ad_storage: denied` | ⏳ 待 staging 就绪 |
| C2 | 接受 analytics | `analytics_storage: granted` | ⏳ 待 staging 就绪 |
| C3 | 拒绝 marketing | `ad_storage: denied`, `ad_user_data: denied`, `ad_personalization: denied` | ⏳ 待 staging 就绪 |
| C4 | 同意后刷新页面 | consent 状态持久化，无重复 banner 弹出 | ⏳ 待 staging 就绪 |

### 3.3 WooCommerce 兼容性测试

| # | 测试场景 | 预期结果 | 状态 |
|---|---|---|---|
| W1 | 结账流程中 cookie banner 不影响提交 | checkout 按钮正常工作 | ⏳ 待 staging 就绪 |
| W2 | CART 中的 GA4 `add_to_cart` 事件在同意后发送 | DebugView 可看到事件 | ⏳ 待 staging 就绪 |
| W3 | LiteSpeed Cache 与 CMP banner 共存 | cache miss 优先于缓存返回，banner 始终显示 | ⏳ 待 staging 就绪 |

### 3.4 回滚演练（每次变更前必须完成）

```bash
# 回滚步骤
cd /var/www/staging/wp-content/plugins
deactivate-plugin complianz-cookie-consent
# 恢复旧 banner（如存在 code snippet）
wp option update nuotao_cookie_banner_enabled true
systemctl reload nginx
# 验证回滚效果
curl -s https://staging.nuotaooutdoor.com | grep -i "cookie"
```

**回滚验证指标**：
- [ ] CMP banner 不再显示
- [ ] 原有简单 banner 重新出现
- [ ] GA4 tracking 恢复正常（如果有之前注入的 script）
- [ ] 页面无 JavaScript 错误

---

## 4. 上线 Gate 条件

Phase 1 Staging Pre-release 通过以下 ALL 条件后方可进入 Phase 2：

| Gate | 条件 | 检查方式 |
|---|---|---|
| G1 | 隔离环境 8/8 测试全 PASS | `CMP_CONSENT_TEST_MATRIX.md` ✅ |
| G2 | Staging 6/6 基础功能测试 PASS | 本报告中 T1-T6 勾选 |
| G3 | Consent Mode v2 4/4 测试 PASS | 本报告中 C1-C4 勾选 |
| G4 | WooCommerce 兼容性 3/3 测试 PASS | 本报告中 W1-W3 勾选 |
| G5 | 回滚演练成功执行并验证 | rollback 截图/日志留存 |
| G6 | Owner 书面批准进入 Phase 2 | 本聊天记录存档 |

---

## 5. 当前进度摘要

```
隔离环境验证   ████████████████████ 100% ✅ (CMP_CONSENT_TEST_MATRIX.md)
Staging 部署   ░░░░░░░░░░░░░░░░░░░░   0% ⏸️ 等待 staging URL/权限
Staging 测试   ░░░░░░░░░░░░░░░░░░░░   0% ⏸️ 等待 G2-G6
Production     ░░░░░░░░░░░░░░░░░░░░   0% 🔒 禁止（需 Owner 单独批准）
```

---

## 6. 阻塞因素

| 阻塞项 | 影响阶段 | 解决方案 |
|---|---|---|
| Staging WordPress URL 未知 | G2 | 需 Owner/运维提供 staging 访问地址 |
| Staging WP Admin 凭证未知 | G2 | 需 Owner/运维提供 staging 管理员账号 |
| 现有简单 banner 下线时机 | G4 | 需 Owner 决策：先上 CMP 再下线旧 banner，还是并行过渡 |

---

*报告生成：2026-11-20，D8-E P1 Phase 1 Staging 预发布计划*
