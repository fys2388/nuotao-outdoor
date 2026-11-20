# Hetzner API Token 轮换报告（D8-E Round 5 · P4 历史凭据最终轮换）

- **日期**：2026-11-18（Round 5 执行）
- **项目**：Hetzner Console 项目 `YONGSHUN Fan`（K0950417826）
- **服务器**：`ubuntu-4gb-hel1-2`（95.217.218.178，1 Server，2 Primary IPs）
- **操作方式**：DSH 通过浏览器会话（bsk）在 Hetzner Console 控制台执行，Owner 已登录。

## 轮换结果

### 新 Token（当前唯一有效）
| 项 | 值 |
|---|---|
| Description | `nuotao-agent-2026-rotated` |
| 权限 | Read & Write |
| 长度 | 64 字符 |
| 前缀（脱敏） | `FlAQ38lz…` |
| 状态 | **已验证可用** |

### 新 Token 验证（Owner 要求"新旧并行验证"）
- 调用 `GET https://api.hetzner.cloud/v1/servers` → **HTTP 200**
- `server_count=1`（能读取服务器列表，权限正常）
- **RESULT=PASS**

### 旧 Token 已全部撤销（已泄露）
| Description | 权限 | 状态 |
|---|---|---|
| `nuotao-unban-agent` | Read & Write | **已删除** |
| `rescue-fix` | Read | **已删除** |
| `rescue-fix-write` | Read & Write | **已删除** |
| `server-fix-2026` | Read & Write | **已删除** |

> 以上 4 个旧 Token 前缀曾出现在 git 历史/部署脚本中（已泄露），现已全部撤销，失效。

## 安全存储
- 新 Token 值已写入生产服务器安全位置：`/root/.hetzner/api_token_new`（chmod 600，仅 root 可读）。
- **建议 Owner**：通过安全渠道（GitHub Secret `HETZNER_API_TOKEN` 或密码管理器）保存新 Token 值；DSH 不持有/不打印明文 Token。

## 发现与建议
- ⚠️ **Hetzner 账号 2FA 未启用**（Console 提示 "Two-factor authentication (2FA) is not enabled yet"）。**建议 Owner 尽快启用 2FA**，提升账号安全性。
- 活动日志显示约 14 天前有 "Rescue system enabled/disabled" 与 "Server rebooted" 记录——与 Rescue 凭据使用痕迹一致，已作为 Rescue 暴露证据记录。

## 结论
**Hetzner API Token 历史凭据轮换完成：新 Token 已生成并验证可用，旧 4 个 Token 已全部撤销失效。** ✅
