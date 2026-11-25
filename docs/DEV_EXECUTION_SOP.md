# 开发执行 SOP（ChatGPT 驱动的自治开发流程）

> **目的**：记录 DSH（DeepSeek Harness Agent）在 nuotao 项目中与 ChatGPT Owner 协作的**每一步标准流程**，实现后期**全自动化执行**，无需每次人工介入。
>
> **适用场景**：nuotao AI OS + 电商验收项目的迭代开发（D8 系列及后续）。
>
> **创建日期**：2026-11-19，基于 D8-C/D8-D 实战经验提炼。

---

## 0. 核心理念

```
┌─────────────────────────────────────────────────────────┐
│  ChatGPT Owner（战略决策/审核/授权）                      │
│         ↑ 汇报成果          │ 下发指令                    │
│         └──────── DSH ──────┘                            │
│            （自治执行：代码/部署/验证/报告）               │
└─────────────────────────────────────────────────────────┘
```

- **DSH 是自治执行者**：从 ChatGPT 获取任务 → 执行 → 产出证据/报告 → 汇报 → 获取下一任务（**闭环循环**）。
- **低风险、本地、可逆任务**：可在明确授权范围内自治执行。
- **ChatGPT Owner 负责**：项目任务范围、评审和授权流程。
- **人类项目 Owner / DBA / 系统管理员掌握**：实际生产资源、凭据和外部权限。
- **需要人类主体执行的凭据、生产目录、生产导出和生产操作**：必须**停止并请求对应授权者**（禁止以"不找人类用户"表达外部审批机制）。
- **部署不是自治开发的默认动作**：只有单独授权时才执行。
- **每个任务必须有真实证据**（BUILT/DEPLOYED/VERIFIED/BLOCKED/PENDING 标记），禁止包装。

### 0.1 任务闭环铁律（每个任务必须遵守）

> **DSH 是「根据 Owner 指令开发」，不是「自己设计」。** 开发方向、范围、边界、优先级一律来自 ChatGPT Owner 的指令；DSH 负责把指令落地执行 + 验证 + 汇报，**不自行决定开发什么、不自行扩大范围**。

每个任务严格走以下闭环，**汇报后必须停止等待，不得自行继续**：

```
Owner 指令 → DSH 执行开发 → 验证（测试/证据）→ 产出报告 → commit/push
   → 汇报 ChatGPT → 【停止，等待 Owner 下一步指令】→（收到指令后）下一轮
```

| 铁律 | 说明 |
|---|---|
| **依据指令开发** | DSH 不自行设计开发方向；范围/边界/红线以 Owner 指令为准，有歧义先请示不擅断 |
| **开发后必须验证** | 每个任务完成都要有真实验证证据（测试通过/CI 全绿/端到端确认），不验证不算完成 |
| **验证后必须汇报** | 验证通过即汇报 ChatGPT（剪贴板粘贴方案，见 §2.2），不等下一任务才一起报 |
| **汇报后必须停止** | 汇报发出即停止本轮工作，**等待 Owner 下一步指令**；禁止自行开始下一个任务或自行扩大范围 |
| **不越过审批 gate** | Owner 明确要求"批准后再做"的（如设计评审后才写代码），必须停下等批准，不得先行 |
| **外部授权请求** | 需人类 Owner/DBA/系统管理员执行的（凭据/生产目录/生产导出/生产操作），必须**明确请求并停止等待**，不得以"自治"绕过 |

### 0.2 Owner 终审驱动 + 证据分级（V2.8 EXPORT 审计模式，2026-11 实战提炼）

> V2.8 定价审计（3A-3D + EXPORT 五线）证明：**高风险/合规类开发不能只靠"开发-汇报"闭环，必须走「Owner 终审 + 红线 + 证据分级 + 隔离验证」审计闭环**。这是 SOP V2.0 的核心增量。

#### A. 角色与授权铁律（V2.8 红线 R1-R13 提炼）

| 铁律 | 说明 |
|---|---|
| **Owner 是终审 authority** | ChatGPT（本项目「定价原则评审 (2)」）对验收/授权有唯一终审权；DSH 是**提议者/实现者**，不是决策者 |
| **Git 授权 ≠ 生产授权** | 推分支/合代码不等同于允许连生产库、写 WC、部署、切生产引擎；生产动作必须单独书面批准 |
| **禁止自行宣布通过** | DSH 不得自行宣布 V2.8（或任何 Owner 验收项）通过；只能"提交验收"并等 Owner 终审 |
| **冻结项零改动** | Owner 冻结的项（如 0076）在解除前零改动，即使修复明显 bug 也先请示 |
| **不跨 worktree 覆盖 / 禁 git add .** | 多分支并行（3A/3B/3C/3D/EXPORT）各自隔离；禁止 `git add .` 误纳无关文件；禁止跨 worktree 覆盖他人改动 |
| **不合并 main（除非批准）** | 合入 main/生产分支必须 Owner 批准；审计分支保持独立直至收口 |
| **外部授权职责分离** | ChatGPT Owner 管任务范围/评审/授权；人类 Owner/DBA/系统管理员管实际生产资源/凭据/外部权限；需人类主体执行的动作必须请求并等待对应授权者 |

#### B. 证据分级（E0 最弱 → E5 最强，与冻结设计 V1.3 完全一致）

> **E0-E5 仅用于项目已有 EvidenceGrade 定义的商品、供应商、成本等事实证据域**；**ACL 验证、CI、数据库迁移测试使用对应安全验证状态与运行环境证据（VERIFIED / REJECTED / NOT RUN、系统平台、执行主体、权限结果、测试产物），不套用 E0-E5**。

**聚合规则（两层，禁止对全部证据行做全局 MIN）**：
1. `critical_component_set` **在快照创建时冻结**（不得事后重新猜测历史快照关键组件）；
2. 先按 `critical_component_set` **逐组件**筛选 `verified` 且在评估时间有效的证据；
3. 未解决来源事实冲突 → **CONFLICT**；
4. 组件没有有效证据 → **UNKNOWN / INCOMPLETE**；
5. 每个组件按确定性证据选择规则计算 **component_grade**；
6. 再对关键组件的 component_grade 取 **MIN**；
7. 空或无法证明的 `critical_component_set` → 整体 **UNKNOWN / INCOMPLETE**；
8. **UNKNOWN ≠ FAILED；UNKNOWN ≠ E0**；
9. `grade_order` 使用**显式 CASE**（不依赖字符串序）。

**红线领域（按 R1-R13 真实业务领域列示，不设未经 Owner 确认的 P0/P1/P2 分组）**：
- 财务口径（R1/R2/R6/R7）：NetRevenue/GM/GMMargin/CP/CPMargin；SalesTax 不进收入；NetRevenue≤0 → CPMargin 不可计算。
- 成本库存（R3/R4/R5/R8/R9/R12/R13）、引擎（R10/R11）：按 Owner 已确认口径列示，不作主观优先级分组。

**fail-closed（区分语义）**：
- 缺少有效关键组件证据 → 证据状态 **UNKNOWN / INCOMPLETE**（不得伪装成 FAILED 或 E0）；
- 已验证证据之间存在未解决事实冲突 → **CONFLICT**；
- 未知成本 → 利润/定价决策 fail-closed，**不产生可用利润率**；
- 下游操作 gate：遇 **UNKNOWN / INCOMPLETE / CONFLICT** 按规则**拒绝继续**；
- 证据台账**保留 UNKNOWN / INCOMPLETE 原状态**（不把缺失证据编码为 E0）。

**ACL 强制矩阵（仅用于 G3 敏感映射文件写入）**：未验证/验证失败/Owner 无法确认/平台不支持 → **exit 2 + 零映射产物**；写入后**重读** ACL 复核；`acl_verified` 仅真实验证成功 true；禁止默认无验证写入路径。

#### C. 多环境隔离验证（跨平台）

- 目标宿主可能是 Windows（NTFS DACL）+ Linux（POSIX mode/getfacl）；**代码验证 ≠ 运行环境验证**，两层都要真实验证。
- 无本地 Linux 时用**隔离非生产 CI Runner**（如 `ubuntu-latest`），**禁止 WSL / Git Bash 模拟 Linux ACL / Windows chmod 冒充 Linux 权限证据**。
- 运行时验证需真实工具（`icacls`/`getfacl`/`setfacl`/`chown`），合成数据 + 临时目录；**权限不足导致的 skip 不得记为通过**（受控 root 单独跑需 root 的项）。
- **workflow_dispatch ≠ 安全**；必须审查**所有**事件触发器、分支/tag/path 条件、Job-level `if`/`needs`、独立 Job、reusable workflow、secrets、environment、外部 action 及副作用；判断实际运行 ref、commit SHA 和目标环境；workflow_dispatch 可触发生产操作，必须单独授权；不能仅凭审计分支名称或 workflow_dispatch-only 判断安全；push 前确认所有可能被触发的下游 workflow。

#### D. 提交链审计（Owner 要求基线同链）

- Owner 可能要求确认"此前已验收提交位于新提交祖先链"，避免不同基线验收。
- 只读证据：`git merge-base --is-ancestor <旧HEAD> <新HEAD>`（要求 exit 0）+ `git log --first-parent --oneline <旧HEAD>..<新HEAD>` + `git show -s --format="%H%n%P%n%s" <新HEAD>`。
- 中间存在其他提交**如实列明**，**不重写历史**；`--first-parent` 确认线性无合并。

---

## 1. 环境与凭证清单（自动化前置）

| 资源 | 访问方式 | 自动化要点 |
|---|---|---|
| **ChatGPT nuotao 项目对话** | 浏览器（bsk session）| URL: `https://chatgpt.com/g/g-p-6a9fb34c5aec8191ad2617bf6deb335e-nuotao/c/6aff03fb-abbc-83e9-a228-51d3652ec45e` |
| **GitHub repo** | gh CLI（fys2388/nuotao-outdoor）| `gh auth status` 确认；commit 走 pre-commit（详见 §6#9，`--no-verify` 仅限书面批准）|
| **Hetzner 生产服务器** | **GitHub Actions 通道**（不用本地 SSH）| workflow: `appleboy/ssh-action` + `secrets.SERVER_HOST/SERVER_USER/SSH_PRIVATE_KEY` |
| **Hetzner Cloud Console** | 浏览器（应急，需账号）| console.hetzner.cloud（SSH 被封时备用）|
| **Hostinger WP（nuotaooutdoor.com）** | 浏览器 hpanel + wp-admin | Code Snippets 部署 GA4/CMP |
| **Google Analytics（GA4）** | 浏览器（已登录 Google）| B2C Property 536153168 / B2B Property（G-39BRDMLCB3）|
| **本地浏览器 daemon** | `bsk daemon start --foreground`（后台 job）| daemon 不稳定，需定期检查/重启 |

---

## 2. ChatGPT 自动交互 SOP（核心：汇报 + 获取任务）

### 2.1 标准循环（每个开发轮次）

```
┌─► 1. 读 ChatGPT 最新 Owner 指令
│   2. 解析任务（工作包/红线/边界/交付物）
│   3. 执行任务（代码/部署/验证）
│   4. 产出交付物报告（Markdown，BUILT/DEPLOYED/...标记）
│   5. Git commit + push
│   6. 写汇报文本 → ChatGPT 发送
│   7. 【停止等待】读 ChatGPT 审核/下一指令 ──┐
│                                            │
└────────────────────────────────────────────┘
```

> ⚠️ **第 6→7 步是硬性停止点**：汇报一发出，本轮任务即结束，**必须停下等 Owner 下一步指令**，禁止自行开始下一个任务或自行扩大范围（详见 §0.1 任务闭环铁律）。

### 2.2 ChatGPT 汇报发送（自动化步骤，已验证可靠）

**关键经验**：ChatGPT 输入框是 ProseMirror（contenteditable），直接 evaluate insertText 易遇 "User activity revoked" 保护。**可靠方案 = 剪贴板粘贴**。

#### Step-by-step（每步工具调用）：

```powershell
# Step 1: 写汇报文本到文件（避免命令行引号/编码问题）
# 用 write 工具写 C:\temp\dsh\chatgpt_report_<轮次>.txt

# Step 2: Set-Clipboard（UTF8 读取，避免中文乱码）
$text = [System.IO.File]::ReadAllText("C:\temp\dsh\chatgpt_report_<轮次>.txt", [System.Text.UTF8Encoding]::new())
Set-Clipboard -Value $text
```

```
# Step 3: 浏览器打开 ChatGPT 对话（如果 session 失效，bsk_session start）
bsk_session start browser=381118ee url=<nuotao对话URL>

# Step 4: sync 获取 context + observation + 输入框 ref（@eN "询问 ChatGPT" textbox）
bsk_session sync session=<id>

# Step 5: click 输入框聚焦
bsk_interact click target=@eN(输入框) expect=[{field:exists,target:@eN}]

# Step 6: Ctrl+V 粘贴
bsk_interact press key=ctrl+v target=@eN(输入框)

# Step 7: sync 确认粘贴（输入框 [filled]）+ 找发送按钮（"发送" button，通常输入框同级）
bsk_session sync session=<id>

# Step 8: click 发送按钮
bsk_interact click target=@eM(发送按钮) expect=[{field:exists,target:@eM}]

# Step 9: sync 验证发送（我的消息出现在对话 + ChatGPT 开始回复"处理中"）
bsk_session sync session=<id>
```

#### 备选方案：直接 fill + 回车（2026-11-25 V2.8 EXPORT 汇报实战验证，更简单）

> 剪贴板方案（上）已验证可靠；若 clipboard 偶发不可用，可改用**直接 fill + Enter**。本次会话实际用此方案成功发送 E-2/E-3 汇报（无需写文件、无需剪贴板）。

```
# Step A: sync 获取 context_id + 输入框 ref
bsk_session sync policy=target        # 记录返回的 context_id（如 4e3e0106-...）
# 输入框 = @eN textbox "询问 ChatGPT"（composer）

# Step B: fill 填入汇报文本（显式传 contextId！不传会报 "requires a valid control context"）
bsk_interact fill target=@eN value=<汇报文本> contextId=<context_id>

# Step C: Enter 发送
bsk_interact press key=Enter target=@eN contextId=<context_id>

# Step D: sync 验证（输入框 [empty] + 我的消息出现在对话 + "回答中/评估"状态）
bsk_session sync policy=target
```

> ⚠️ **关键（问题 #25）**：sync 后必须把返回的 `context_id` **显式传入** `bsk_interact`（`contextId=`），否则点击/填充/发送报 "requires a valid control context from cooperate sync"。ref 也会随页面 re-render 偏移，每次交互前重新 sync 获取新 ref。

**发送前核对（按 Owner 评审）**：
- 确认当前是**正确项目会话**（对话标题/上下文匹配）；
- **每轮重新 sync**，使用**当前** `context_id` / ref（不跨会话混用、不缓存旧 ref）；
- 发送前**核对完整汇报文本**（不截断、不遗漏关键项）；
- 发送结果不确定时**先 sync 确认**（避免重复发送）；
- **不发送**密码、Token、Salt、PII 或未脱敏生产日志。

### 2.3 读取 ChatGPT 回复（Owner 指令）

```
# sync 后，spill 文件保存完整页面（C:\temp\dsh\dsh-spill-.../<obs>-bsk_session.txt）
# ChatGPT 回复在 "ChatGPT 说：" heading 后的 paragraph/heading/list

# 提取关键节（grep spill 文件）
grep "我的审核结论|批准|禁止|阶段|执行|优先级|红线" <spill文件>

# 或 pwsh 提取 JSON text 字段的关键节
```

**Owner 指令解析要点**：
- **工作包**：任务编号 + 执行内容
- **权限边界**：本轮批准 vs 不批准（严格遵守）
- **红线**：不发布生产、不注入生产、不创建测试订单、不关闭安全防护等
- **交付物**：报告文件 + 标记（BUILT/DEPLOYED/VERIFIED/BLOCKED/PENDING_REAL_ORDER）
- **停止条件**：完成授权范围后停止，等审核

---

## 3. 开发执行 SOP（按任务类型）

### 3.1 Hetzner 后端操作（生产 AI OS）

**⚠️ 关键：不要用本地 SSH**（服务器被暴力破解 + sshd 过载）。**用 GitHub Actions 通道**。

```yaml
# .github/workflows/<task-name>.yml
name: <Task Description>
on:
  workflow_dispatch:
jobs:
  task:
    runs-on: ubuntu-latest
    steps:
      - uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          port: 22
          script: |
            cd /opt/nuotao-ai-os
            # 只读诊断 或 安全操作（禁：关防火墙/关fail2ban/重置SSH/重启生产）
            <commands>
```

**执行**：
```powershell
# 1) 推送：仅在 Owner 已明确批准指定远程分支 push 后执行；main push 必须有单独书面 Owner 批准
git push origin <approved-remote> <approved-branch>

# 2) 生产 workflow dispatch：仅当存在单独的生产 workflow 书面批准时才允许
#    批准必须绑定：workflow、commit SHA、ref、环境、Job、全部输入参数、时间窗口、停止/回滚条件
#    未得到特定审批，禁止 dispatch；不得无条件使用 workflow_dispatch 默认输入
#    以下仅为命令格式示意；审批未绑定该 workflow/commit/ref/环境/输入时禁止执行
gh workflow run <approved-workflow>.yml --ref <approved-ref> -f <approved-input>=<approved-value>

$rid = (gh run list --workflow=<approved-workflow>.yml --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch $rid --exit-status
$jobId = gh api repos/fys2388/nuotao-outdoor/actions/runs/$rid/jobs -q '.jobs[0].id'
gh api "repos/.../actions/jobs/$jobId/logs" | Select-String "out:" | ...  # 提取 SSH 输出
```
> ⚠️ **`--no-verify` 不得作为通用正常流程示例**（仅按 §6 #9 书面批准规则例外使用）；不提供默认 `push origin main` / 默认 `gh workflow run` 命令。

**只读诊断模板**（已有）：`diagnose-ssh-fail2ban.yml`、`check-backend-emergency.yml`、`webhook-secret-diagnose.yml`

**生产 workflow 授权规则（按 Owner 评审）**：
- GitHub Actions 通道是**已授权操作**的执行方式，但 **workflow_dispatch 本身不是授权**；push main 不是默认动作。
- 每次生产 workflow 必须有**独立书面批准**，批准应绑定：workflow 文件、commit SHA、ref、目标环境、允许 Job、输入参数、时间窗口、回滚/停止条件。
- 每次执行前审查**所有 Job 和实际副作用**；不得无条件使用 workflow_dispatch 默认输入。
- **SOP V2.0 本次仅修改文档，不修改 workflow 文件。**

### 3.2 GA4 / Google 后台操作

**用浏览器自动化**（bsk session，Google 已登录）：
```
1. bsk_session start url=https://analytics.google.com/...
2. sync → 找 Admin/Property/创建按钮 ref
3. click/fill 逐步操作（创建 Property/Stream/事件配置）
4. sync 验证（Measurement ID/配置证据）
5. 截图/sync 记录证据
```

**经验**：GA4 创建流程 = Property基本信息 → 商家详情 → 业务目标 → 数据收集（Web Stream）→ Measurement ID。每步 sync 巨量，注意上下文预算。

### 3.3 WooCommerce / Hostinger WP 操作

**用浏览器**（hpanel + wp-admin）：
- LiteSpeed Cache：hpanel 清缓存按钮
- Code Snippets：wp-admin 部署 GA4/CMP 代码
- 插件管理：wp-admin 插件页

### 3.4 交付物报告规范

每个任务产出 `docs/acceptance/<TASK>_REPORT.md`：

```markdown
# <任务名> 报告
**状态**：BUILT / DEPLOYED / VERIFIED / BLOCKED / PENDING_REAL_ORDER

## 1. 执行内容
## 2. 证据（命令输出/截图/Measurement ID/commit）
## 3. 标记说明
- BUILT：已构建（代码/配置就绪）
- DEPLOYED：已部署（生产/隔离环境）
- VERIFIED：已验证（端到端测试通过）
- BLOCKED：受阻（说明阻塞点）
- PENDING_REAL_ORDER：待真实业务数据（无测试订单时）
## 4. 红线遵守确认
## 5. Git commits
```

---

## 4. 自动化脚本化建议（后期实现）

### 4.1 ChatGPT 交互脚本化（`scripts/chatgpt_report.sh` / `.ps1`）

```powershell
# 参数：汇报文本文件
param($ReportFile)
$text = [IO.File]::ReadAllText($ReportFile, [Text.UTF8Encoding]::new())
Set-Clipboard $text
# 调用 bsk CLI：sync → click 输入框 → ctrl+v → sync → click 发送 → sync
# （需封装 bsk session 管理 + ref 动态识别）
```

### 4.2 任务执行器（一次性，按 Owner 评审：禁止无限自动循环）

> **不得自动轮询/后台继续**：没有明确新 Owner 指令，不得读取并执行下一项任务。

```
# 一条明确 Owner 指令 → 一次执行 → 验证 → 报告 → 按授权提交/推送 → 汇报 → 进程退出
# 无新指令时进程退出（不 sleep 轮询、不后台常驻）
execute_once "$owner_instruction"
```

### 4.3 红线校验（`scripts/check_redline.sh`，仅辅助检查）

> **黑名单仅作辅助检查，不是授权控制**。高风险操作应采用**任务授权白名单 + 默认拒绝**机制。

```bash
# 辅助黑名单（仅提示越权风险，不替代授权）
FORBIDDEN=("关闭防火墙" "关闭fail2ban" "注入B2B生产" "创建生产测试订单" "轮换生产Secret" "引入GTM")
# 命中黑名单 → 停止并请求 Owner 澄清（默认拒绝，非自动放行）
```

---

## 5. 当前待办（2026-11-25 快照，随 Owner 指令滚动更新）

### 5.1 V2.8 定价审计五线（Owner 终审状态）

| 工作线 | 当前决定 |
|---|---|
| 3A 财务基线 | 最终通过，关闭 |
| 3B 库存语义 | 技术验收通过；0093 DBA 只读预检 P1-P5 有限授权，结果待返回，**生产迁移未授权** |
| 3C Lineage | V1.3 设计冻结；实施未授权 |
| 3D 双引擎 | 文档整改通过；方案 A 不变 |
| EXPORT G4 | 通过 |
| EXPORT G3 Runtime | 跨平台技术验证通过（代码+CLI 门禁+Windows NTFS+Linux mode/getfacl 四层 Owner 接受）；**正式目录待置备** |
| EXPORT G1/G2 | 阻塞 |

**G3 Runtime = VERIFIED；G3 overall = BLOCKED；V2.8 整体未通过最终验收；生产权限未授权；0076 冻结。**

### 5.2 剩余外部前置与待批事项（DSH 不可自行推进）

| 项 | 状态 | DSH 动作 |
|---|---|---|
| G3 正式 `id_map_dir` | Owner/系统管理员置备 | 置备后于实际目标宿主重新验证正式目录 ACL（路径隔离/所有权/DACL 或 mode+ACL/执行账号授权/写后重读/未授权主体拒/不进 Git·交付包·云同步） |
| EXPORT G1 30 天生产脱敏副本 | **真实导出尚未授权**（生产 DBA）| 不导出；等 DBA + 单独批准 |
| EXPORT G2 Owner 安全 Salt | 未提供（Owner/安全管理员）| 未接收 |
| 3B 0093 DBA 只读预检 | 已有限授权，结果待返回 | 等 DBA 结果（与 EXPORT G1 分开记录）|
| 3B 生产迁移 / 3C 实施（0094-0097）| 均需单独书面批准 | 不自行执行 |
| PR 合并（一般规则）| 合入 main 需 Owner 批准 + 评审；PR 保持 OPEN 直至批准 | 不自行合并 |

### 5.3 禁止事项（红线，持续有效）

1. 不自行创建/选取正式 `id_map_dir`；不生成真实映射文件
2. 不接收真实 Salt；不连接生产数据库；不导出生产数据；不执行真实脱敏
3. 不执行历史财务重算；不修改 WooCommerce；不部署
4. 不触碰 0076；不合并 main（除非批准）；不用 `git add .`
5. 不把权限不足的 skip 记为通过；不删除失败测试或放宽断言

### 5.4 历史（已完成，存档参考）

- **D8-D SSH 加固 S1-S5**：已按 GitHub Actions 通道执行并验证（Owner APPROVED WITH CONDITIONS）；S6 MaxStartups 调整为"先提供证据+方案，暂不批准"。
- **D8-D 其他**：Complianz 隔离环境 / B2C GA4 Realtime / Webhook 隔离测试 / LiteSpeed 缓存兼容性审计 —— 视 Owner 后续指令推进。
- **V2.8 五条工作线分别记录**（不写成"整体通过"）：
  - 3A 财务基线：**正式关闭**（Owner 最终验收通过）
  - 3B 库存语义：**技术验收通过**；0093 DBA 只读预检有限授权（结果待返回）；生产迁移未授权
  - 3C Lineage：**V1.3 设计冻结**；0094-0097 实施未授权
  - 3D 双引擎：**实验文档整改通过**；旧引擎维持生产路径；方案 A 不变
  - EXPORT：G4 **通过**；G3 Runtime **技术验证通过**（正式目录待置备）；G1/G2 **阻塞/未授权**
  - **V2.8 整体未通过最终验收；生产权限未授权；0076 冻结。**

---

## 6. 开发问题日志（问题 → 根因 → 解决方案 → 预防）

> **这是 SOP 最有价值的部分**：记录开发过程中实际遇到的每个问题，供后期自动化规避。

### 6.1 Hetzner / 生产服务器类

| # | 问题现象 | 根因 | 解决方案 | 预防 |
|---|---|---|---|---|
| 1 | SSH 直连 95.217.218.178 "Connection closed"，TCP 22 可达 | 服务器被**多 IP 持续暴力破解**，sshd `MaxStartups 10:30:100` 被攻击占满，合法连接被挤掉 | 用 **GitHub Actions 通道**（runner IP ≠ 本地，不受 sshd 过载影响）执行所有 Hetzner 操作 | **COMPLETED/VERIFIED**：S3/S4 已按 GitHub Actions 通道执行并验证（Owner APPROVED WITH CONDITIONS）|
| 2 | 误判为 "fail2ban 封禁" | 未先检查就假设 | 先只读诊断（`diagnose-ssh-fail2ban.yml`）确认 fail2ban **未安装**，根因是 sshd 过载 | **Owner 红线**：不把"疑似"当"确认"，先诊断后结论 |
| 3 | fail2ban 未安装（`command not found`）| 生产服务器裸奔，无暴力破解防护 | **COMPLETED/VERIFIED**：S3-S5 已执行并验证（安装 fail2ban + 配置 SSH jail + 测试）；**S6 NOT AUTHORIZED**（暂不批准）| 新服务器初始化必装 fail2ban |
| 4 | GitHub Actions `gh run view --log` 超时/无输出 | 日志下载慢或 Select-String 过滤无匹配 | 用 `gh api repos/.../actions/jobs/$jobId/logs` + `Select-String "out:"` 提取 SSH 输出 | 封装为标准取日志函数 |
| 5 | pwsh 复杂 Python/SSH 命令引号转义失败 | 嵌套引号 + pwsh 转义冲突 | 写脚本文件 → scp 上传 → ssh 执行；或 GitHub Actions workflow 内联 | 复杂命令一律写文件，不内联 |
| 6 | 本地代理 fake-ip 劫持 DNS（8.8.8.8 也返回 198.18.x）| Clash 类代理 TUN 模式劫持所有 DNS | 直连 IP（95.217.218.178）绕过 DNS；或 GitHub Actions 通道 | Hetzner 操作优先 GitHub Actions，不依赖本地网络 |

### 6.2 后端代码 / 部署类

| # | 问题现象 | 根因 | 解决方案 | 预防 |
|---|---|---|---|---|
| 7 | wc-clickback 端点返回 500（非 401）| `wc_clickback.py` line134 `get_trace_id(request)` —— `get_trace_id()` 无参，传 request 抛 TypeError | 改 `get_trace_id()`（commit 0e5f2d7）| **原有 bug 非本次引入**；端点测试覆盖无签名/错误签名路径可早发现 |
| 8 | Webhook 端点测试 404（非 401）| 用了错误路径 `/webhooks/wc`（不存在）| 先 `app.routes` 发现真实路由（`/webhooks/woocommerce` 等），再用正确路径测试 | 测试前先发现路由，不假设路径 |
| 9 | pre-commit hook "No module named pre_commit" 失败 | 本地 venv 无 pre_commit | **优先修复环境/hook 配置**；不可运行的检查标 **NOT RUN**；仅书面 Owner 批准时一次性限定范围 `--no-verify`，并列出跳过 hooks/替代检查/剩余风险 | 初始化本地 pre-commit 环境；CI 通过≠未执行 hooks 自动记为通过；不将绕过门禁作为默认 SOP |
| 10 | 生产 WEBHOOK_SECRET 误判为空（is_empty=True）| 诊断脚本读错变量名（`WEBHOOK_SECRET`，实际是 `WOOCOMMERCE_WEBHOOK_SECRET`）| 深度诊断确认 `WOOCOMMERCE_WEBHOOK_SECRET=64字符强值`，`webhook_secret_is_insecure=False` | 诊断脚本变量名先 grep .env 确认，不硬编码假设 |
| 29 | Linux 测试 test_3 Named ACL 断言失败（reason 是 "mode" 非 "widening"）| `setfacl -m u:<uid>:rx` 会扩大 ACL mask → POSIX mode 从 0o700 变 0o750，守卫经 **mode 检查**先拒（allowed=False 正确），但测试断言 reason 必须是 widening/acl 而失败 | test_3 用 `setfacl -m u:<uid>:rx -m m:---`（ACL mask 复位 `---`）使 mode 保持 0o700，真正触发 **ACL widening 路径**（断言 premise mode==0o700 + reason 含 widening/acl）| 验证 ACL 逻辑时确保 mode 不干扰（mask 复位）；先确认守卫求值顺序（mode→getfacl→widening）再写断言 |

### 6.3 ChatGPT 交互类（自动化核心）

| # | 问题现象 | 根因 | 解决方案 | 预防 |
|---|---|---|---|---|
| 11 | evaluate insertText "User activity revoked this action" | ChatGPT 页面反自动化保护（检测非人类输入）| **剪贴板粘贴方案**：写文件 → Set-Clipboard → click 聚焦 → Ctrl+V | 长文本一律 clipboard，不用 insertText |
| 12 | Ctrl+V 粘贴后 inputLen=0（粘贴失效）| 焦点未在输入框 / 剪贴板未就绪 | 先 click 输入框聚焦 → 确认 clipboard 已设置 → Ctrl+V → sync 验证 [filled] | 粘贴前确认焦点 + clipboard |
| 13 | Set-Clipboard 中文乱码 | `Get-Content` 默认 GBK 读 UTF-8 文件 | `[System.IO.File]::ReadAllText($file, [Text.UTF8Encoding]::new())` | 统一 UTF8Encoding 读文件 |
| 14 | `#prompt-textarea` 选择器 NOT_FOUND | ChatGPT 改版，输入框 id/结构变化 | 探测多选择器：`#prompt-textarea` / `[contenteditable="true"]` / `.ProseMirror` / `div[role="textbox"]` | 封装"找输入框"函数（多候选 + 动态探测）|
| 15 | 发送按钮 ref 失效（removed from document）| 页面 re-render（发送后 / 输入后），ref 过期 | 重新 sync 获取新 ref；或 evaluate 动态探测发送按钮（`data-testid="send-button"` / `aria-label="发送"`）| 每次发送前重新定位发送按钮，不缓存 ref |
| 16 | ChatGPT 免费版上下文达上限 | 原对话轮次过多 | 在 nuotao 项目**新建会话**汇报 | 长项目定期新建会话，或精简汇报 |

### 6.4 浏览器自动化类（bsk / daemon）

| # | 问题现象 | 根因 | 解决方案 | 预防 |
|---|---|---|---|---|
| 17 | 浏览器 daemon 反复退出（后台 job exit 1）| `bsk daemon start --foreground` 在后台 job 里不稳定（Job Object 限制）| 定期检查 daemon，session 失效（"does not belong to this plugin"）时重启 daemon + 重开 session | 长会话定期 sync 检测 daemon 存活 |
| 18 | session 失效 "does not belong to this plugin" | daemon 重启导致旧 session 丢失 | 重开 session（bsk_session start）| daemon 重启后所有旧 session 作废，需重开 |
| 19 | ProseMirror 不支持 fill（内容不清空/不输入）| ChatGPT/GA4 用 ProseMirror（非普通 input）| 用 clipboard + Ctrl+V（非 fill）| ProseMirror 一律 clipboard |
| 20 | bsk plan "unrecognized subcommand" | plan 参数格式错误 | 改分步 click + press（不用 plan）| 复杂多步用分步，plan 格式需查文档 |
| 21 | GA4 sync 输出巨量（溢出上下文）| GA4 页面 DOM 复杂（几百节点）| 控制上下文预算；用 spill 文件 + grep 提取关键节；避免连续多次 sync | GA4 操作前评估上下文预算，必要时分会话 |
| 22 | bsk evaluate "requires unused strict observation" | 上次 action 消耗了 observation | 重新 sync 获取新 observation_id | 每次 evaluate 前确保有 fresh observation |
| 25 | bsk_interact click 报 "requires a valid control context from cooperate sync" | 未显式传 `contextId`（sync 返回的 `context_id`），默认上下文失效 | sync 获取 `context_id` 后**显式传 `contextId` 给 bsk_interact**（click/fill/press/send）| 每次 bsk 交互前 sync 拿新 `context_id`，显式传入；不依赖默认上下文 |

### 6.5 Git / CI 类

| # | 问题现象 | 根因 | 解决方案 | 预防 |
|---|---|---|---|---|
| 23 | git push 显示 exit 1 但实际成功 | stderr 输出被 pwsh 当错误 | 检查 `git log` / `gh` 确认 push 成功（忽略 stderr exit 1）| push 后验证 `git log origin/main` |
| 24 | **CI Pre-check 持续 failure**（所有 push 都失败）| `test_pii_ci_integration.py:76` `db_url` fixture 用 `assert` —— 无 DB 环境（CI Pre-check 无 postgres）直接 fail，阻塞 Deploy gated | 改 `db_url` fixture：无 DB URL 时 `pytest.skip`（非 assert fail），有 DB 环境正常跑（commit 707ebfe）| 集成测试（需 DB）应 skip 无 DB 环境，而非 fail；CI Pre-check 与专门 DB workflow 分离 |
| 26 | push 审计分支可能触发部署 workflow | 未全面审查 workflow 触发条件，仅凭分支名/workflow_dispatch-only 误判安全 | push 前审查**所有**事件触发器、分支/tag/path 条件、Job-level if/needs、独立 Job、reusable workflow、secrets/environment/外部 action；判断实际 ref/commit SHA/目标环境；workflow_dispatch 可触发生产操作，必须单独授权 | push 前确认所有可能被触发的下游 workflow；git 推送 ≠ 部署；不把 workflow_dispatch-only 当安全条件 |
| 27 | 本宿主 Windows 无 Linux，无法真实验证 Linux ACL | WSL 未装（需管理员+重启）、Docker 未装、Git Bash 非 Linux 内核 | 采用**隔离非生产 CI Runner**（`ubuntu-latest`，方案 B）跑真实 Linux 运行时验证（getfacl/setfacl/chown）；禁 WSL/Git Bash 模拟 | 跨平台验证一律用隔离 CI Runner；禁本地模拟代替真实环境证据 |
| 28 | Owner 要求提交链补证（旧 HEAD 与旧提交非直接父子）| 审计分支多个提交叠加，Owner 需确认验收基线同链 | `git merge-base --is-ancestor <旧HEAD> <新HEAD>`（exit 0 为同链）+ `git log --first-parent --oneline <旧HEAD>..<新HEAD>` 如实列中间提交；不重写历史 | 每次 Owner 验收记录 HEAD；跨提交验收前先跑 merge-base 确认同链 |

### 6.5.1 GitHub 推送运行监控（强制步骤）

**每次 git push 后必须检查 workflow 运行情况**（用户要求"时刻关注 github 实际推送运行情况"）：

```powershell
# push 后检查所有触发的 workflow 状态
gh run list --limit 10 2>&1 | Select-Object -First 12
# 关注：CI Pre-check（语法/测试）、Deploy to Production（gated）、Secret Scanning
# 失败的 workflow：gh run view <run-id> --log-failed 查原因
```

**监控要点**：
- **CI Pre-check**：语法 + imports + 单测 + smoke（检查其实际 Job 与依赖；**不假设 CI fail 就一定阻断部署 workflow 的所有独立 Job**）
- **Deploy to Production (staging-gated)**：检查独立 Job 和生产副作用；push 后核实实际 run/ref/commit/job；不自动重推 main 或重跑生产 workflow
- **专门 workflow**（PII CI / SSH Harden 等）：workflow_dispatch 或 push 触发（workflow_dispatch 触发需单独授权，不等同安全）
- **失败必查根因**（不忽略），修复后重新 push 验证

### 6.6 问题记录规范（后期新问题追加此处）

每个新问题按此格式追加：
```
| # | 问题现象 | 根因 | 解决方案 | 预防 |
```
- **问题现象**：具体报错/表现
- **根因**：诊断确认的真实原因（非猜测）
- **解决方案**：实际生效的解法（含 commit/命令）
- **预防**：后期如何避免（流程/脚本/红线）

---

## 7. 下一步（DSH 自治执行）

**V2.8 EXPORT G3 跨平台 ACL 验证已闭合（代码+CLI 门禁+Windows NTFS+Linux mode/getfacl 四层 Owner 接受，G3 Runtime = VERIFIED）。**

1. **外部准备（Owner/DBA/系统管理员，DSH 不可自行推进）**：
   - G3 正式 `id_map_dir`：Owner/系统管理员置备 → 置备后于实际目标宿主重新验证正式目录 ACL（路径隔离/所有权/DACL 或 mode+ACL/执行账号授权/写后重读/未授权主体拒/不进 Git·交付包·云同步）
   - EXPORT G1 生产只读脱敏副本：生产 DBA（真实导出未授权）
   - EXPORT G2 安全 Salt：Owner/安全管理员（未提供）
2. **等待 Owner 单独批准的执行事项**：3B 库存语义生产迁移 / 3C Lineage 实施（0094-0097）/ 真实数据导出·脱敏·历史财务重算（均未授权）。
3. **DSH 已完成且关闭的工作线**：3A 财务基线（关闭）/ 3D 双引擎（方案 A 不变）/ EXPORT G4（通过）/ EXPORT G3 Runtime 技术验证（VERIFIED，正式目录待置备）。
4. **需人类主体履行的审批或资源操作**：明确请求对应授权者并**停止等待**（不以"闭环，不找人类用户"表达外部审批）。
5. **SOP 持续迭代**：本文件已升至 V2.0（新增 §0.2 Owner 终审驱动 + 证据分级 + 隔离验证 + 提交链审计；§6 问题 #25-#29）；后续每轮实战经验按 §6.6 追加。
6. **禁止事项不变**：不自行创建/选取正式 id_map_dir；不生成真实映射；不接收真实 Salt；不连生产库；不导出生产数据；不执行真实脱敏；不执行历史财务重算；不修改 WC；不部署；不触碰 0076；不合并 main（除非批准）；不用 `git add .`。

---

*SOP 版本 V2.0（2026-11-25），基于 D8-C/D8-D 实战 + V2.8 EXPORT G3 审计实战（Owner 终审驱动/证据分级/跨平台隔离验证/提交链审计）。已按 Owner 评审修改指令 V1.0 修订（外部授权职责分离、E0-E5 与 V1.3 一致、workflow_dispatch≠安全、--no-verify 仅书面批准、禁无限任务循环、G1/3B 分开、CI gate 修正）。后期每轮迭代更新。*
