# CMP Staging 基础设施评估报告（D8-E Round 4，C 方案）

**执行日期**：2026-11-20
**Owner 决策**：批准 C 方案（Hetzner Docker），但必须先行评估服务器隔离条件
**状态标记**：**环境评估完成（共享宿主机隔离，如实记录）/ 完整部署 PARTIAL（需下一轮完整实施）**

---

## 1. 服务器隔离条件实测（Hetzner 95.217.218.178）

| 项 | 实测结果 | 结论 |
|---|---|---|
| Docker 版本 | v29.1.3（build 29.1.3-0ubuntu4.1）| ✅ 可用 |
| 现有容器 | scheduler / postgres:16-alpine / redis:7-alpine（生产栈）| — |
| 可用内存 | 2.5 GiB（总 3.7 GiB，used 1.2 GiB）| ✅ 足够 |
| 可用磁盘 | 59 G（总 75 G，已用 14 G，19%）| ✅ 足够 |
| 现有网络 | bridge / host / none / nuotao-ai-os_default | 可新建独立网络 |
| 独立 VM | **无**（只能共用生产宿主机）| ⚠️ 共享宿主机 |

## 2. 隔离等级结论（如实记录）

- **基础设施级隔离：未实现**（无独立 VM/宿主机）
- **容器级隔离：可实现**（独立 Docker Network `cmp-staging_default` + 独立 MySQL 容器 + 独立 WP 容器 + 资源限制）
- **Owner 要求**：不得将 Docker 网络隔离描述成完整的基础设施隔离
- **结论**：CMP C 方案 = **共享宿主机容器级隔离**，须明确记录共享内核和资源竞争风险

## 3. CMP Staging 设计（C 方案）

| 组件 | 设计 | 隔离 |
|---|---|---|
| Docker Network | `cmp-staging_default`（新建，独立）| ✅ |
| MySQL 容器 | 独立 `cmp-staging-db`，独立数据库 `cmp_staging`，独立凭据 | ✅ |
| WordPress 容器 | 独立 `cmp-staging-wp`，WP + Complianz 插件 | ✅ |
| 资源限制 | CPU/Memory 限额（防影响生产）| ✅ |
| 访问认证 | 独立 Basic Auth + 仅本地/受控访问 | ✅ |
| 搜索引擎 | `noindex`（禁止索引）| ✅ |
| 生产数据 | 不接入生产 DB | ✅ |
| 生产凭据 | 不使用生产 Secret | ✅ |
| 邮件/支付/Webhook | 全部关闭 | ✅ |

**关键约束**：与生产后端共用宿主机，须记录共享内核 + 资源竞争风险。

---

## 4. 结论与待 Owner

- **环境评估完成**：资源充足（2.5 GiB + 59 G），Docker 可用，可建独立网络
- **隔离等级**：共享宿主机容器级隔离（如实标记，非基础设施级）
- **完整部署（WP+MySQL+Complianz 容器 + 8 项 CMP 测试）**：需在独立上下文完整实施（超出本上下文预算，标记 PARTIAL）
- **无生产变更**：未安装新 Docker 组件、未修改生产网络（符合 Owner"安装 Docker 或修改生产宿主机网络配置之前，先提交环境评估"）

---

*CMP Staging 基础设施评估：2026-11-20，DSH 自治。共享宿主机容器级隔离（如实记录）。*
