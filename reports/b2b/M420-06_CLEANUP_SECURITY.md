# M420-06 workflow 清理与凭证安全审计报告

> 状态：**PASS** ｜ 范围：M420-06 ｜ 日期：2026-11-17

## 一、临时 workflow 清理 ✅
- 删除 **13 个一次性 workflow**（12 个审计/探测/导入类 + `fix-headlamp-copy`），`git rm` + 推送。
- 保留可复用：`sync-wc-images.yml`、`import-wc-products.yml`、`close-legacy-products.yml`（幂等）+ 生产 workflow（ci/deploy/pages/backup/secret-scanning 等）。
- 验证：GitHub 侧 `state=deleted` / 本地文件不存在。

## 二、凭证安全审计 ✅（核心）
- **git 追踪 + 全历史**：**无真实 WC 凭证**。`ck_/cs_` 命中均为文档占位符（`ck_xxx…`）；`consumer_key/secret` 命中为变量名引用（非值）。`.env`/`backend/.env` 被 gitignore 忽略。
- **工作区清理**：33 个含明文 key 脚本已备份（`C:\temp\wc_secret_scripts_backup_20261117\`）+ 删除；6 个功能文件硬编码 key → env 读取（`backend/tools/wc_image_workflow.py`、`upload_wc_images.py`、`skills/…/verify_listing.py`、`configure_seo.py`、`associate_images.py`、`references/api_configuration.md`）。
- **`.gitignore` 加强**：追加 `/backend/check_*.py`（防 backend 根 check 脚本误提交）。
- **验证**：工作区 `.py` 含真实 key = **0**；git 历史含真实 key = **False**。

## 三、修复的 workflow 触发问题（重要）
- **根因**：workflow `script: |` 块内 Python 行**顶格（0 缩进）**导致 YAML 解析失败 → GitHub run 0 job failure；`Set-Content` 重写破坏文件编码（非 UTF-8）→ 解析失败。
- **修复**：Python 脚本改为 **base64 内联**（单行，无缩进冲突）+ 确保 UTF-8；恢复 `import-wc-products.yml`/`deploy.yml` 原编码。
- **验证**：`Import 8 WC products` success（20s）、`Fix headlamp copy` success（13s）、Deploy 正常。

## 四、已知问题（非阻塞）
- **secret-scanning**：每次 push `failure`（0s、0 job）、`state=active`、无 workflow_dispatch 触发（422）——**预先存在**（2026-11-17 前已如此），不影响 CI/Deploy。需单独排查。
- **WC 凭证轮换建议**：见 M420-07 已知问题（git 未泄露，但明文 key 曾散落工作区；建议 WC 后台轮换）。
