# Nuotao AI OS - 灾难恢复演练指南

## 概述

本文档描述 Nuotao AI OS 系统的灾难恢复策略、演练流程和验证标准。

**目标**：确保在发生数据丢失、系统故障或灾难时，能够快速恢复业务运行，数据丢失量（RPO）不超过 24 小时，恢复时间（RTO）不超过 4 小时。

---

## 1. 灾难场景分类

| 场景 | 严重程度 | 预计恢复时间 | 数据丢失 |
|------|----------|--------------|----------|
| 单表数据误删 | 低 | 15 分钟 | 0（从备份恢复） |
| 数据库服务故障 | 中 | 30 分钟 | 0（重启/切换） |
| 服务器硬件故障 | 高 | 2 小时 | ≤24 小时 |
| 数据中心灾难 | 极高 | 4 小时 | ≤24 小时 |
| 人为恶意删除 | 高 | 2 小时 | ≤24 小时 |
| 勒索软件攻击 | 极高 | 4 小时 | ≤24 小时 |

---

## 2. 备份策略

### 2.1 备份类型

| 备份类型 | 频率 | 保留时间 | 存储位置 |
|----------|------|----------|----------|
| 完整数据库备份 | 每日 03:00 | 30 天 | 本地 + 对象存储 |
| 增量备份 | 每 6 小时 | 7 天 | 本地 |
| 配置文件备份 | 每周 | 90 天 | Git 仓库 |
| 日志备份 | 实时 | 30 天 | 本地 + 对象存储 |

### 2.2 备份验证

- 每日备份完成后自动验证完整性
- 每周执行一次恢复演练（测试环境）
- 每月执行一次完整恢复演练（预发布环境）
- 每季度执行一次灾难恢复演练（模拟真实场景）

---

## 3. 恢复流程

### 3.1 场景一：单表数据误删

**适用场景**：误操作删除了某张表的数据（如 products、orders）

**恢复步骤**：

1. **立即停止相关服务**
   ```bash
   # 停止后端服务，防止进一步数据污染
   # Windows: 停止 Nuotao AI OS.bat
   ```

2. **定位备份文件**
   ```bash
   # 列出最近的备份
   dir E:\AI\nuotao-ai-os\backups\database\
   ```

3. **恢复到临时数据库**
   ```powershell
   # 恢复到临时数据库（不影响生产）
   .\scripts\restore-database.ps1 -BackupFile "backups\database\nuotao_20260901_030000.sql.gz" -TargetDB "nuotao_restore_temp"
   ```

4. **验证恢复数据**
   ```sql
   -- 检查目标表数据量
   SELECT count(*) FROM products;
   SELECT count(*) FROM orders;
   ```

5. **导出误删表数据**
   ```bash
   # 导出单表
   pg_dump -h localhost -U nuotao -d nuotao_restore_temp -t products > products_backup.sql
   ```

6. **恢复到生产数据库**
   ```bash
   # 导入到生产
   psql -h localhost -U nuotao -d nuotao -f products_backup.sql
   ```

7. **验证并重启服务**
   ```bash
   # 验证数据
   psql -c "SELECT count(*) FROM products;"
   # 重启服务
   # 启动 Nuotao AI OS.bat
   ```

**预计恢复时间**：15 分钟
**数据丢失**：0（从最近备份恢复）

---

### 3.2 场景二：数据库服务故障

**适用场景**：PostgreSQL 服务崩溃、无法启动

**恢复步骤**：

1. **检查服务状态**
   ```powershell
   # 检查 PostgreSQL 服务状态
   Get-Service postgresql*
   # 查看错误日志
   Get-Content "C:\Program Files\PostgreSQL\17\data\log\*.log" -Tail 50
   ```

2. **尝试重启服务**
   ```powershell
   Restart-Service postgresql-x64-17
   ```

3. **如果重启失败，检查磁盘空间**
   ```powershell
   Get-PSDrive C
   # 如果磁盘满，清理旧日志/临时文件
   ```

4. **检查配置文件**
   ```bash
   # 验证 postgresql.conf 配置
   # 检查 pg_hba.conf 访问控制
   ```

5. **如果无法修复，从备份恢复到新实例**
   ```powershell
   # 安装新的 PostgreSQL 实例
   # 恢复数据库
   .\scripts\restore-database.ps1 -BackupFile "最新备份文件" -TargetDB "nuotao"
   ```

**预计恢复时间**：30 分钟
**数据丢失**：0

---

### 3.3 场景三：服务器硬件故障

**适用场景**：服务器硬件损坏、无法启动

**恢复步骤**：

1. **确认故障**
   - 联系服务器提供商确认硬件状态
   - 确认是否需要更换服务器

2. **准备新服务器**
   - 安装操作系统（Ubuntu 22.04 / Windows Server）
   - 配置网络、防火墙
   - 安装 PostgreSQL、Redis、Nginx

3. **恢复数据库**
   ```bash
   # 从对象存储下载最新备份
   # 恢复数据库
   ./scripts/restore-database.sh -f /path/to/backup.sql.gz -d nuotao
   ```

4. **部署应用**
   ```bash
   # 克隆代码
   git clone <repo>
   # 安装依赖
   pip install -r requirements.txt
   npm install && npm run build
   # 配置环境变量
   cp .env.production .env
   # 启动服务
   systemctl start nuotao-backend
   systemctl start nuotao-frontend
   ```

5. **验证业务**
   - 访问前端页面
   - 测试 API 端点
   - 验证 WooCommerce 同步
   - 测试订单流程

**预计恢复时间**：2 小时
**数据丢失**：≤24 小时（最近一次备份）

---

### 3.4 场景四：数据中心灾难

**适用场景**：整个数据中心不可用（火灾、地震、网络中断）

**恢复步骤**：

1. **启动灾难恢复预案**
   - 通知所有相关人员
   - 确认数据中心状态
   - 启动备用数据中心

2. **切换 DNS**
   ```bash
   # 将域名指向备用数据中心
   # 修改 DNS A 记录
   # 等待 DNS 传播（通常 5-30 分钟）
   ```

3. **恢复数据**
   - 从异地备份恢复数据库
   - 同步最新数据（如果有主从复制）

4. **部署应用**
   - 在备用数据中心部署应用
   - 配置负载均衡
   - 启动所有服务

5. **验证并通知**
   - 全面验证业务功能
   - 通知客户系统已恢复
   - 监控系统稳定性

**预计恢复时间**：4 小时
**数据丢失**：≤24 小时

---

## 4. 演练计划

### 4.1 演练频率

| 演练类型 | 频率 | 环境 | 参与人员 |
|----------|------|------|----------|
| 单表恢复演练 | 每周 | 测试环境 | 运维 |
| 完整恢复演练 | 每月 | 预发布环境 | 运维 + 开发 |
| 灾难恢复演练 | 每季度 | 生产环境（模拟） | 全员 |
| 切换演练 | 每半年 | 生产环境 | 全员 |

### 4.2 演练检查清单

每次演练必须完成以下检查：

- [ ] 备份文件可正常读取
- [ ] 备份文件完整性验证通过
- [ ] 数据库恢复成功
- [ ] 所有关键表数据完整
- [ ] 应用服务正常启动
- [ ] API 端点响应正常
- [ ] 前端页面可访问
- [ ] 用户登录功能正常
- [ ] 订单创建/查询功能正常
- [ ] WooCommerce 同步功能正常
- [ ] 飞书通知功能正常
- [ ] 监控告警功能正常
- [ ] 恢复时间在目标范围内
- [ ] 数据丢失量在目标范围内
- [ ] 演练记录已归档
- [ ] 发现的问题已记录并跟踪

---

## 5. 角色与职责

| 角色 | 职责 |
|------|------|
| 运维负责人 | 整体协调、备份管理、恢复执行 |
| 开发负责人 | 应用部署、代码修复、功能验证 |
| 数据负责人 | 数据一致性验证、数据修复 |
| 安全负责人 | 安全审计、访问控制、漏洞修复 |
| 业务负责人 | 业务验证、客户通知、影响评估 |

---

## 6. 联系与升级

### 6.1 紧急联系人

| 角色 | 联系方式 | 响应时间 |
|------|----------|----------|
| 运维负责人 | （待填写） | 15 分钟 |
| 开发负责人 | （待填写） | 30 分钟 |
| 数据负责人 | （待填写） | 30 分钟 |
| 安全负责人 | （待填写） | 1 小时 |

### 6.2 升级流程

1. **L1 支持**：运维人员初步处理（30 分钟内）
2. **L2 支持**：开发/数据专家介入（1 小时内）
3. **L3 支持**：外部供应商/云厂商支持（2 小时内）
4. **管理层升级**：如果超过 RTO 目标，立即通知管理层

---

## 7. 附录

### 7.1 常用命令

```bash
# 查看备份列表
ls -lh /backups/database/

# 验证备份文件完整性
gzip -t backup.sql.gz

# 查看数据库大小
psql -c "SELECT pg_size_pretty(pg_database_size('nuotao'));"

# 查看表数量
psql -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"

# 查看最近备份时间
ls -lt /backups/database/ | head -5
```

### 7.2 关键配置文件

| 文件 | 位置 | 说明 |
|------|------|------|
| 数据库配置 | `backend/.env` | DATABASE_URL |
| Redis 配置 | `backend/.env` | REDIS_URL |
| Nginx 配置 | `infra/nginx/nginx.conf` | 反向代理 |
| 备份脚本 | `scripts/backup-database.ps1` | 每日备份 |
| 恢复脚本 | `scripts/restore-database.ps1` | 数据恢复 |
| 监控脚本 | `scripts/monitor_service.py` | 系统监控 |

---

**文档版本**：v1.0
**最后更新**：2026-09-02
**审核人**：（待填写）
