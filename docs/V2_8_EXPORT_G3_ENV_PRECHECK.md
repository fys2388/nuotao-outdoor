# V2.8 EXPORT G3 真实运行环境准备预检报告（合成环境）

> 工作项：`V2.8-HISTORICAL-DATA-EXPORT-PREP`（Owner「定价原则评审 (2)」EXPORT G3/G4 审阅与 30 天验证最终指令，2026-11-24）。
> 角色：`v28-export-g4-workspace`。分支：`audit/pricing-v28-historical-export`（HEAD `122127f` → 本工作项新 HEAD）。
> 状态：**合成环境预检完成；真实 id_map_dir 尚未由 Owner 置备 → G3 真实环境预检仍阻塞**（红线：不得自行创建真实映射文件/接收生产 Salt）。
> 红线遵守：未连接生产库、未执行生产 SQL、未导出真实数据、未读取/接收生产 Salt、未创建真实映射文件、未做真实数据脱敏、未做历史财务重算。

---

## 1. 范围与依据

- **只做测试环境/合成数据预检**：`tests/v28_export_g3_env_precheck.py` 在 OS 临时目录（`C:\temp\dsh\v28-g3-precheck-*`）内，用合成 fixture（`tests/fixtures/v28_export_sample/raw/`）+ 测试专用 salt（`test-salt.txt`，仅测试）运行完整脱敏管线，逐项采集 G3 证据。**与生产数据无关**。
- 复用的既有证据：`tests/test_v28_export_desensitize.py`（G3 用例 `test_id_map_written_to_restricted_dir`、`test_id_map_not_in_git_and_rejected_inside_worktree`、`test_missing_id_map_dir_fails_closed`、`test_secure_path_overlapping_out_fails_closed`、`test_logs_and_errors_do_not_leak_original_ids`、`test_id_map_deterministic_across_runs`）。

## 2. 预检项与结果（合成环境）

| # | 检查项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 专用 `id_map_dir` 实际权限（POSIX 模式） | **⚠ 未达 0600/0700（Windows 宿主）** | `_id_map_pseudo.json` `stat` 模式 = `0o666`；目录 = `0o777`（`os.chmod(0o600/0o700)` 在 Windows 仅影响只读位，不产生 POSIX 限制） |
| 2 | 目录/文件所有权 | 合成宿主无法验证真实归属 | Windows `stat` 报 `uid/gid=0/0`（无 POSIX 语义）；真实归属须在目标宿主以 `ls -ld`/`stat -c %u:%g` 验证 |
| 3 | Windows NTFS ACL（`icacls`） | **⚠ 继承 FULL 控制，非最小权限** | `SYSTEM:(I)(F)`、`BUILTIN\Administrators:(I)(F)`、`OWNER RIGHTS:(I)(F)` —— 未做 `/inheritance:r` 收紧，当前用户未显式最小化 |
| 4 | Linux Unix 权限与 ACL | 未测（合成环境为 Windows；目标宿主未知） | 生产若为 Linux，须 `stat -c '%a'` 验证文件 `600`、目录 `700`，`ls -ld` 验证属主，`getfacl` 验证无 group/other 读 |
| 5 | 目录不属于 Git 工作树 | ✅ 通过 | 脚本 `_is_within_git_repository` 拒绝仓库内路径（exit 2）；既有测试 `test_id_map_not_in_git_and_rejected_inside_worktree` 在仓库内建探针并断言拒绝 |
| 6 | 目录不与 raw/out 重叠 | ✅ 通过 | `test_secure_path_overlapping_out_fails_closed`：`id_map_dir == out_dir` → exit 2「must be independent」，无输出产物 |
| 7 | 文件最终权限 | ⚠ 见 #1（Windows 宿主 0666） | 元数据如实声明 `file_mode_octal=0600`/`directory_mode_octal=0700`（`_id_map_payload`），实际生效依赖宿主 OS |
| 8 | 不在云同步/公共共享/普通交付目录 | ✅ 通过（合成） | `C:\temp\dsh\...` 未命中 OneDrive/Dropbox/Syncthing/Nextcloud 标记；生产置备时须再验（`/Users/<u>/OneDrive`、`~/Dropbox`、`/srv/shared`、`/var/www` 等） |
| 9 | salt 不被日志或异常泄露 | ✅ 通过 | `salt_present_in_logs=false`、`salt_in_id_map_payload=false`；既有测试 `test_logs_and_errors_do_not_leak_original_ids`（stdout/stderr/报告无原始 ID、无 salt） |
| 10 | id_map 不进入普通交付包 | ✅ 通过 | `delivery_package.files` 仅 12 CSV + `desensitization_report.json`，`_id_map_pseudo.json` 不在其中；报告 `id_map.delivered_with_package=false` |
| 11 | 不覆盖既有映射文件 | ✅ 通过 | 二次运行 → exit 2「target not created」（`O_EXCL`，不覆盖既有 `_id_map_pseudo.json`） |

## 3. 关键结论（如实披露，不粉饰）

1. **POSIX 0600/0700 在 Windows 宿主不生效**：`os.chmod(0o600/0o700)` 在 Windows 只切换只读位，`stat` 实际报告 0666/0777；真实限制由 NTFS ACL 决定，而合成临时目录的 ACL 是**继承的 FULL 控制**（SYSTEM/Admins/Owner Rights）。既有测试 `test_id_map_written_to_restricted_dir` **已正确地在 `os.name != "nt"` 才断言实际模式**，只对元数据 `file_mode_octal=0600` 做断言——即**测试未在 Windows 上假装 0600 生效**，诚实。
2. **生产置备要求（阻断项）**：真实 `id_map_dir` 必须在**目标宿主**满足下列**全部**条件后方可启用，否则脚本虽能跑但映射文件并非真正受限：
   - Linux/Unix：目录 `0700`（`chmod 700`）、文件 `0600`（`chmod 600`）、属主为运行账号（`chown`）、`getfacl` 无 group/other 读位；
   - Windows：显式收紧 ACL `icacls <dir> /inheritance:r /grant:r <account>:(OI)(CI)F`，文件再 `icacls <file> /inheritance:r /grant:r <account>:F`，**验证 `icacls` 输出只有该账号**；
   - 位于仓库外、与 `data/raw_export` 和 `data/desensitized` 不相交、非云同步/公共共享/交付目录；
   - 目录**已存在**且**为空**（脚本不创建目录，也不覆盖既有映射）。
3. **G3 真实环境预检当前阻塞**：Owner 尚未提供真实受限目录与真实 Salt（红线：本工作项不自行创建真实映射文件、不接收生产 Salt）。因此「真实 id_map_dir 是否满足上述条件」**无法在本工作项结论**——必须由 Owner 在目标宿主置备并回传 `stat`/`icacls`/`getfacl` 证据后，再由 DSH 做**启用前复验**。

## 4. 复验动作清单（Owner 置备后、启用前）

```text
[Linux 目标]  id_map_dir 置备后复验：
  stat -c '%a %U %G' <id_map_dir>            # 期望 700 属主=运行账号
  getfacl -p <id_map_dir>                    # 期望无 other 权限位
  运行一次管线后：stat -c '%a' <id_map_dir>/_id_map_pseudo.json  # 期望 600
[Windows 目标] id_map_dir 置备后复验：
  icacls <id_map_dir>                        # 期望仅目标账号 (OI)(CI)F，无继承
  icacls <id_map_dir>\_id_map_pseudo.json    # 期望仅目标账号 F
[通用]  验证：git -C <id_map_dir> rev-parse --show-toplevel  # 期望报错（不在仓库）
```

> 附：合成预检证据脚本 `tests/v28_export_g3_env_precheck.py`（可重复运行，全为临时目录/合成数据，不触碰生产）。

---

*（本报告为 EXPORT G3 真实运行环境准备预检证据；结论仅覆盖合成环境 + 既有测试，真实置备复验待 Owner。）*
