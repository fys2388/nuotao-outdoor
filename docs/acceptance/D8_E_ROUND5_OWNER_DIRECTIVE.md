# Owner D8-E Round 5 执行指令 + 补充授权（2026-11-20）

**授权来源**：ChatGPT "制定D8-E优先级" 对话（Owner）
**阶段**：Security Closure & Staging Validation
**执行模式**：DSH 自治，严格边界

---

## 一、Round 5 核心指令

### P0：历史凭据最终轮换（DB/1688/Hetzner/Rescue/JWT）
### P1：CMP Staging 环境建设（8 项测试：Accept All/Reject All/Customize/Withdraw/Consistency/Cookie/Network/Google Consent Mode）
### P2：WordPress Core 7.1.5 安全更新
### P3：三个插件 Staging 验证（ElementsKit ≥4.2.0 / JegKit ≥3.3.1 / Elementor 只审计）
### P4：运营安全监控（CI 四 Gate/Secret/Gitleaks/SSH S4/Fail2ban/GA4 真实访客）

---

## 二、补充授权（最终，2026-11-20）

### 1. CMP Staging 有限授权（现有 Hetzner Docker 环境）
- WP + MySQL 初始内存合计 **≤768 MiB**，CPU **≤1 vCPU**，磁盘 **≤8 GB**
- 独立 Docker Network / 独立数据库 / 独立凭据
- 禁止直接公开访问，初期仅 SSH Tunnel
- **不修改 Docker Daemon / 生产防火墙 / 安全组 / 反向代理 / 生产网络配置**
- **不连接生产数据库**；Staging 不生产 GA4 Measurement ID，不向生产 GA4 发测试数据
- 执行前核实：宿主机 total/available memory、生产服务资源峰值、磁盘、Docker cgroup 限制
- **生产资源安全余量不足 → 暂停并提交报告**

### 2. WordPress Core 7.1.5（升级优先级提高）
- 核实 Hostinger Smart Auto Updates 策略和待更新状态；不关闭正常安全更新机制
- 完成：数据库备份 / 网站文件备份 / 恢复可行性验证 / PHP 8.3 兼容检查 / WooCommerce 回归准备
- **将更新计划和维护时间提交 Owner；没有维护窗口确认，不要同时触发手动与自动更新**

### 3. 插件 Staging（ElementsKit ≥4.2.0 / JegKit ≥3.3.1 / Elementor 只审计）
- 所有测试完成后提交插件兼容性矩阵

### 4. JWT：DSH 自主完成调用链和有效凭据审计，必要轮换按已批准范围执行
### 5. 1688 / Hetzner API / Rescue：等待 Owner 安全渠道操作

---

## 三、最终交付（6 份报告）

1. `CMP_STAGING_DEPLOYMENT_REPORT.md`
2. `CMP_STAGING_PHASE1_ACCEPTANCE_REPORT.md`
3. `WORDPRESS_CORE_7_1_5_PRODUCTION_UPDATE_REPORT.md`
4. `WORDPRESS_PLUGIN_COMPATIBILITY_REPORT.md`
5. `ROUND5_SECRET_CLOSURE_REPORT.md`
6. `D8_E_ROUND5_EXECUTION_SUMMARY.md`

**规则**：
- 未完成任务保留 BLOCKED/PARTIAL
- **不允许因为部分任务完成而宣布整个 Round 5 PASS**
- 继续自主执行，不扩大生产授权

---

## 四、Owner 完成度判断（三层）

1. 工程基础稳定
2. 安全与合规整改中
3. 自主运营待验证

**下一次验收看三个结果**：
- ① CMP 真正部署并通过八项实测
- ② WordPress 完成安全更新且 WooCommerce 正常运营
- ③ 所有有效历史机密完成轮换、吊销及独立验证
- **三个结果完成后才讨论 D9 自治运维阶段**

---

*Owner Round 5 指令 + 补充授权存档：2026-11-20，DSH 从 ChatGPT 提取*
