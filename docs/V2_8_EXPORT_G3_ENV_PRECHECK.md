# V2.8 EXPORT G3 真实运行环境准备预检报告（合成环境 + ACL 守卫补强）

> 工作项：`V2.8-HISTORICAL-DATA-EXPORT-PREP`（Owner「定价原则评审 (2)」EXPORT G3/G4 审阅与 30 天验证最终指令，2026-11-24）。
> 角色：`v28-export-g4-workspace` / `v28-export-g3-acl`。分支：`audit/pricing-v28-historical-export`（HEAD `e129681` → 本工作项新 HEAD，见 git log 首条）。
> 状态：**合成环境预检完成；G3 ACL 守卫已实现（读取/验证，fail-closed）；真实 id_map_dir 尚未由 Owner 置备 → G3 真实环境预检仍阻塞**（红线：不得自行创建真实映射文件/接收生产 Salt）。
> 红线遵守：未连接生产库、未执行生产 SQL、未导出真实数据、未读取/接收生产 Salt、未创建真实映射文件、未做真实数据脱敏、未做历史财务重算；**未修改任何文件系统权限**（守卫仅读取/验证，管线不再调用 `os.chmod`）。

---

## 1. 范围与依据

- **只做测试环境/合成数据预检**：`tests/v28_export_g3_env_precheck.py` 在 OS 临时目录（`C:\temp\dsh\v28-g3-precheck-*`）内，用合成 fixture（`tests/fixtures/v28_export_sample/raw/`）+ 测试专用 salt（`test-salt.txt`，仅测试）运行完整脱敏管线，逐项采集 G3 证据。**与生产数据无关**。
- 复用的既有证据：`tests/test_v28_export_desensitize.py`（G3 用例 `test_id_map_written_to_restricted_dir`、`test_id_map_not_in_git_and_rejected_inside_worktree`、`test_missing_id_map_dir_fails_closed`、`test_secure_path_overlapping_out_fails_closed`、`test_logs_and_errors_do_not_leak_original_ids`、`test_id_map_deterministic_across_runs`）。
- **新增 ACL 守卫**：`scripts/v28_export_acl_guard.py`（纯求值器 + 细粒度平台读取器，**绝不修改权限**）+ `tests/test_v28_export_acl_guard.py`（纯逻辑单测 + Windows 真实 DACL 读取冒烟）。

## 2. 预检项与结果（合成环境）

| # | 检查项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 专用 `id_map_dir` 实际权限（POSIX 模式） | **⚠ Windows 宿主无 POSIX 语义** | 管线**不再调用 `os.chmod`**；仅在创建时请求 `0600`（`os.open` 模式）。Windows `stat` 仍报告 0666/0777（无 POSIX 限制）；真实限制由 NTFS DACL 决定，由 ACL 守卫验证（见 #12） |
| 2 | 目录/文件所有权 | 合成宿主无法验证真实归属 | Windows `stat` 报 `uid/gid=0/0`；真实归属须在目标宿主以 `ls -ld`/`stat -c %u:%g` 验证；ACL 守卫在 Windows 读取真实 Owner SID 并核对运行账号（规则 4） |
| 3 | Windows NTFS ACL（真实 DACL） | **⚠ 合成临时目录为继承 FULL → 守卫正确拒绝（fail-closed）** | `Get-Acl` 读取真实 DACL：`SYSTEM`/`BUILTIN\Administrators`/`OWNER RIGHTS` 继承 FULL → `verify_restricted_dir_acl` 判定 `allowed=false`；生产须 `/inheritance:r` 收紧后才会 `allowed=true` |
| 4 | Linux Unix 权限与 ACL | 逻辑已单测；真实宿主未测 | `_evaluate_linux`：`mode==0o700/0o600`、`uid==运行账号`、`getfacl` 无 named/mask/other 扩权位；单测覆盖 0755/0644/属主不匹配/命名 ACL 扩权 → 均拒绝 |
| 5 | 目录不属于 Git 工作树 | ✅ 通过 | `_is_within_git_repository` 拒绝仓库内路径（exit 2）；`test_id_map_not_in_git_and_rejected_inside_worktree` |
| 6 | 目录不与 raw/out 重叠 | ✅ 通过 | `test_secure_path_overlapping_out_fails_closed`：`id_map_dir == out_dir` → exit 2「must be independent」 |
| 7 | 文件最终权限 | 元数据如实声明 `file_mode_octal=0600`/`directory_mode_octal=0700`；**真实保护由 ACL 守卫验证** | `_id_map_payload.security` 现含 `acl_verified`（`--verify-id-map-acl` 且目录守卫通过才为 `true`），不再仅凭 `os.chmod` 成功宣称受限 |
| 8 | 不在云同步/公共共享/普通交付目录 | ✅ 通过（合成） | `C:\temp\dsh\...` 未命中 OneDrive/Dropbox/Syncthing/Nextcloud 标记；生产置备时须再验 |
| 9 | salt 不被日志或异常泄露 | ✅ 通过 | `salt_present_in_logs=false`、`salt_in_id_map_payload=false`；`test_logs_and_errors_do_not_leak_original_ids` |
| 10 | id_map 不进入普通交付包 | ✅ 通过 | `delivery_package.files` 仅 12 CSV + `desensitization_report.json`；报告 `id_map.delivered_with_package=false` |
| 11 | 不覆盖既有映射文件 | ✅ 通过 | 二次运行 → exit 2「target not created」（`O_EXCL`） |
| 12 | **Windows 真实 NTFS DACL 读取+验证** | ✅ 守卫已实现；合成目录被拒（证明非仅凭 POSIX/chmod） | `_read_windows_acl` 经 `Get-Acl` 读取 SID/type/rights/inheritance（SID 翻译），`evaluate_acl` 逐 ACE 判定；合成继承 ACL 因公共/继承主体被拒（`allowed=false`） |
| 13 | **Linux 真实权限+ACL 扩权检测** | 逻辑单测通过；真实宿主待测 | `_read_linux_acl`：`os.lstat` 取 mode/uid/gid + `getfacl` 检测 named user/group、`mask`、`other` 扩权；`mode` group/other==0 时 mask 封顶，`getfacl` 缺失也不误放行 |
| 14 | **公共主体有访问即拒绝**（规则 5/6） | ✅ 通过 | `evaluate_acl` 拒绝 Everyone(`S-1-1-0`)、Authenticated Users(`S-1-5-11`)、`BUILTIN\Users`(`S-1-5-32-545`)、INTERACTIVE(`S-1-5-4`)、Power Users(`S-1-5-32-547`) 的 allow ACE；SYSTEM/Administrators/Creator Owner/Owner Rights 识别为受控、不误判为公共 |
| 15 | **ACL 不可读/无法确认 → fail-closed**（规则 7） | ✅ 通过 | owner 缺失、空 ACE 集、JSON/`getfacl` 解析失败、平台不支持 → `allowed=false`；单测覆盖 |

## 3. 关键结论（如实披露，不粉饰）

1. **POSIX 0600/0700 在 Windows 宿主不生效**：管线不再调用 `os.chmod`（Owner 规则：只检查、不修改权限），仅在创建时以 `os.open(...,0o600)` 请求模式；Windows 实际限制由 NTFS DACL 决定，现由 **ACL 守卫读取真实 DACL 验证**（`--verify-id-map-acl`，fail-closed）。
2. **ACL 守卫满足 Owner 7 项规则**：Windows 读真实 NTFS DACL（非 POSIX/chmod 推断）；Linux 验证真实 mode+owner 并检测 `getfacl` 扩权；拒绝不安全继承权限；确认执行账号为授权账号（Owner SID/名称比对）；拒绝公共主体（Everyone/Users/Authenticated Users 等）访问；识别 SYSTEM/Administrators/Creator Owner/Owner Rights 为受控；任何读取/解析失败 fail-closed（`allowed=false`）。
3. **`--verify-id-map-acl` 为显式开关（默认关）**：合成/既有测试的 `tmp_path` 目录在多数机器继承宽泛 ACL（Authenticated Users/Users），若把 ACL 门槛设为常开会破坏既有测试（红线：不删除/不放宽既有断言）。因此真实 ACL 校验在**生产置备后由 Owner 显式开启**；默认行为与 HEAD 完全一致（除 `security.acl_verified` 记录为 `false`）。
4. **生产置备要求（阻断项，未变）**：真实 `id_map_dir` 须在**目标宿主**满足全部条件后方可启用：
   - Linux/Unix：目录 `0700`、文件 `0600`、属主为运行账号、`getfacl` 无 group/other 读位；
   - Windows：显式收紧 `icacls <dir> /inheritance:r /grant:r <account>:(OI)(CI)F`，**验证 `Get-Acl`/`icacls` 输出仅含该账号**（守卫在此条件下 `allowed=true`）；
   - 位于仓库外、与 `data/raw_export` 和 `data/desensitized` 不相交、非云同步/公共共享/交付目录；目录已存在且为空。
5. **G3 真实环境预检当前阻塞**：Owner 尚未提供真实受限目录与真实 Salt。因此「真实 id_map_dir 是否满足上述条件」**无法在本工作项结论**——须 Owner 置备后回传 `stat`/`icacls`/`getfacl` 证据，再以 `--verify-id-map-acl` 做启用前复验。

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

## 5. ACL 守卫实现（`scripts/v28_export_acl_guard.py`）

- **入口**：`verify_restricted_dir_acl(path, *, kind="dir|file", authorized_sid/name/uid, expected_mode_octal) -> AclVerification`；默认授权账号 = 当前执行账号；**从不修改权限**（无 chmod/chown/setfacl/icacls）。
- **Windows 读取器**：PowerShell `Get-Acl`（`-LiteralPath`，SID 翻译，`AreAccessRulesProtected`），结构化 JSON → `parse_windows_acl_json`。
- **Linux 读取器**：`os.lstat`（mode/uid/gid）+ `getfacl -p`（可选；`mode` group/other==0 封顶任何 ACL mask，`getfacl` 缺失不误放行）。
- **纯求值器**：`evaluate_acl(snapshot, ...)` 逐 ACE 判定（allow/deny、公共/受控/授权、继承）；`parse_getfacl_output` 解析命名/掩码/other。
- **规则映射**：规则 1=Windows 真实 DACL；规则 2=Linux mode+ACL；规则 3=拒绝不安全继承；规则 4=Owner SID/名称比对授权账号；规则 5=拒绝公共主体 allow；规则 6=受控主体白名单；规则 7=任何不可读/不可确认 → `allowed=false`。
- **接入点**：`scripts/v28_export_desensitize.py` 新增 `--verify-id-map-acl`；开启时在写入前验证目录（失败 → exit 2，不写任何产物），写入后验证文件并记录进报告 `id_map.acl_dir`/`acl_file`；`_id_map_payload.security.acl_verified` 如实反映是否通过真实 ACL 验证。

> 附：合成预检证据脚本 `tests/v28_export_g3_env_precheck.py`（可重复运行，全为临时目录/合成数据，不触碰生产）。

---

*（本报告为 EXPORT G3 真实运行环境准备预检证据；结论仅覆盖合成环境 + 既有测试 + ACL 守卫纯逻辑/读取验证，真实置备复验待 Owner。）*
