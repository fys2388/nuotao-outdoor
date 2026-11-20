# CMP Staging 部署报告（D8-E Round 5，P1）

**执行日期**：2026-11-20
**Owner 授权**：CMP 有限范围部署（≤768MiB / ≤1vCPU / ≤8GB / 独立网络/DB/凭据 / 仅 SSH Tunnel）
**状态标记**：**部署完成（VERIFIED，容器级隔离）/ Complianz 插件 + 8 项测试待执行（PARTIAL）**

---

## 1. 部署结果（95.217.218.178）

| 容器 | 镜像 | 状态 | 内存 | 上限 |
|---|---|---|---|---|
| cmp-staging-db | mysql:8.0 | ✅ Up | 380.5 MiB | 384 MiB |
| cmp-staging-wp | wordpress:latest | ✅ Up | 71.9 MiB | 384 MiB |
| **合计** | — | — | **452 MiB** | **768 MiB** |

- **452 MiB < 768 MiB 门槛** ✅
- 独立网络 `cmp-staging_default`（不与生产 `nuotao-ai-os_default` 共用）✅
- 独立数据库 `cmp_staging` + 独立凭据（`cmp_user`，随机密码，未打印）✅
- **不发布公网端口**（仅内部网络，SSH Tunnel 访问）✅
- 不连接生产 DB（生产 postgres `daf138dd8924` 未接触）✅
- 不用生产 GA4 / 生产 Secret ✅
- 生产容器未受影响：scheduler/postgres/redis **Up 13 days healthy** ✅

## 2. 资源门槛计算（Owner 要求）

```
生产峰值（500 MiB 估算）+ Staging 上限（768 MiB）+ 安全余量（512 MiB）= 1780 MiB
1780 MiB < MemTotal 3809 MiB → ✅ 满足
```

## 3. 隔离等级

- **容器级隔离**（共享宿主机，共享内核）——如实记录，**非基础设施级隔离**（无独立 VM）
- 资源竞争风险：已通过 768MiB 上限 + 452MiB 实际占用控制（< 50% 门槛）

## 4. 待执行（PARTIAL）

| 项 | 状态 |
|---|---|
| Complianz 插件安装 | 待执行 |
| 8 项 CMP 测试（Accept All/Reject/Customize/Withdraw/Consistency/Cookie/Network/Google Consent）| 待执行 |
| SSH Tunnel 访问验证 | 待执行 |

## 5. 结论

- ✅ **CMP Staging 部署完成**（WP + MySQL 独立容器，452MiB < 768MiB，独立网络/DB/凭据，生产未受影响）
- ⏸️ **Complianz + 8 项测试**：PARTIAL（待执行，不与生产交互）
- **容器级隔离**如实记录（共享宿主机）

---

*CMP Staging 部署：2026-11-20，DSH 自治。部署 VERIFIED，测试 PARTIAL。*
