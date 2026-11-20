# CMP 宿主机资源容量报告（D8-E Round 5，P1）

**执行日期**：2026-11-20
**Owner 授权**：CMP 有限范围部署（768MiB / 1vCPU / 8GB），需先核实资源门槛
**状态标记**：**资源门槛满足 → 部署有效（VERIFIED）**

---

## 1. 资源实测（95.217.218.178）

| 项 | 实测值 | 说明 |
|---|---|---|
| **MemTotal** | 3900600 kB ≈ **3809 MiB** | 宿主机总内存 |
| **MemAvailable** | 1905712 kB ≈ **1861 MiB** | 当前可用 |
| CPU | **2 核** | — |
| 磁盘 | 75G 总 / 57G 可用 | — |
| 磁盘 inode | 4940208 总 / 4674966 可用（6%）| ✅ 充足 |
| Swap | 2047 MiB 总 / 346 已用 / 1701 可用 | 有 Swap 缓冲 |
| Docker | 29.1.3，无全局 cgroup 限制 | 需容器级限制 |

## 2. 生产服务占用

| 服务 | 内存 |
|---|---|
| FastAPI（scheduler）| ~30 MiB |
| PostgreSQL | ~38 MiB |
| Redis | ~9 MiB |
| **生产合计** | **~77 MiB** |

## 3. 资源安全门槛计算（Owner 要求）

**公式**：生产峰值内存 + Staging 768MiB 上限 + 512MiB 安全余量 ≤ MemTotal

```
生产峰值（估算 500 MiB，含 FastAPI 尖峰）
+ Staging 上限（768 MiB）
+ 安全余量（512 MiB）
= 1780 MiB
```
**1780 MiB < MemTotal 3809 MiB** → ✅ **满足资源安全门槛**

## 4. CMP Staging 实际部署

| 容器 | 状态 | 内存 | 上限 |
|---|---|---|---|
| cmp-staging-db（MySQL 8.0）| Up | 380.5 MiB | 384 MiB |
| cmp-staging-wp（WordPress）| Up | 71.9 MiB | 384 MiB |
| **合计** | — | **452 MiB** | **768 MiB** |

- **452 MiB < 768 MiB 门槛** ✅
- 独立网络 `cmp-staging_default` ✅ / 独立 DB `cmp_staging` ✅ / 独立凭据 ✅
- 不发布公网端口（仅 SSH Tunnel）✅ / 不连生产 DB ✅ / 不用生产 GA4 ✅
- 生产容器（scheduler/postgres/redis）未受影响（Up 13 days healthy）✅

## 5. 结论

- **资源门槛满足**（1780MiB 最坏情况 < 3809MiB MemTotal）
- **CMP Staging 部署有效**（452MiB < 768MiB 上限）
- **容器级隔离**（共享宿主机，如实记录，非基础设施级）
- **生产未受影响**

## 6. 待办

- Complianz 插件安装（后续）
- 8 项 CMP 测试（后续）
- SSH Tunnel 访问验证（后续）

---

*CMP 资源容量：2026-11-20，DSH 自治。门槛满足，部署有效。*
