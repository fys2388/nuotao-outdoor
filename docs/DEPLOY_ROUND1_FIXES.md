# Nuotao AI OS — 部署说明（Round 1 修复）

> 生成时间：2026-09-25
> 目标：部署已修复的 3 个 P0 Bug 到生产环境

---

## 已修复的 Bug

| Bug # | 问题 | 文件变更 |
|---|---|---|
| **3** | AI provider 配置（sensenova） | `backend/app/core/config.py` + `llm_gateway.py` |
| **17** | Listing Gate 未挂载 | `backend/app/services/listing_gate.py` + `product_pipeline_service.py` |
| **1** | 1688 导入错误处理 | 前端代码已有，无需修改 |

---

## 部署步骤

### 1. 提交代码

```bash
cd /path/to/nuotao-ai-os
git add backend/app/core/config.py \
        backend/app/services/llm_gateway.py \
        backend/app/services/listing_gate.py \
        backend/app/services/product_pipeline_service.py \
        docs/e2e_flow_test_round1.md \
        docs/e2e_flow_test_round1_fixes.md
git commit -m "fix: 修复 AI provider 配置、Listing Gate 未挂载、confirm_and_list 验证

- 添加 sensenova provider 支持到 LLM Gateway
- 复制 listing_gate.py 到主后端
- 在 confirm_and_list 中添加发布前验证（SKU、中文文案硬阻断）
- 添加 24 个 Bug 的完整记录和修复补丁

Refs: docs/e2e_flow_test_round1.md"
git push origin main
```

### 2. 触发 CI/CD 部署

**方式 A：GitHub Actions**

1. 访问 https://github.com/your-org/nuotao-ai-os/actions
2. 选择 `deploy.yml` workflow
3. 点击 "Run workflow"
4. 选择 `main` 分支
5. 确认部署

**方式 B：SSH 到服务器手动部署**

```bash
ssh user@server
cd /opt/nuotao-ai-os
git pull origin main

# 重启后端服务
sudo systemctl restart nuotao-backend
# 或
docker-compose restart backend

# 验证服务状态
sudo systemctl status nuotao-backend
curl http://localhost:8000/health
```

### 3. 配置 sensenova API Key

```bash
# 在服务器上编辑 .env 文件
cd /opt/nuotao-ai-os/backend
nano .env

# 添加或更新以下配置
SENSENOVA_API_KEY=<your-sensenova-api-key>
SENSENOVA_BASE_URL=https://api.sensenova.cn/v1
SENSENOVA_DEFAULT_MODEL=sensechat

# 保存并重启服务
sudo systemctl restart nuotao-backend
```

### 4. 创建 Webhook Secret

```bash
cd /opt/nuotao-ai-os/backend

# 生成随机字符串（至少 32 字符）
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > webhook_secret.txt

# 或者使用 openssl
openssl rand -base64 32 > webhook_secret.txt

# 设置权限
chmod 600 webhook_secret.txt
chown nuotao:nuotao webhook_secret.txt

# 验证文件已创建
ls -la webhook_secret.txt
cat webhook_secret.txt
```

### 5. 配置 WooCommerce Webhook

1. 登录 WooCommerce 后台
2. 进入 **系统状态 → Webhooks**
3. 点击 **Add webhook**
4. 配置：
   - **名称**：Nuotao AI OS Order Sync
   - **URL**：`https://admin.nuotaooutdoor.com/api/v1/woocommerce-sync/webhook`
   - **密钥**：`webhook_secret.txt` 中的内容
   - **事件**：`order.created`, `order.updated`
5. 保存

### 6. 验证部署

```bash
# 1. 检查后端服务状态
curl http://localhost:8000/health

# 2. 检查 sensenova provider 是否配置
curl http://localhost:8000/api/v1/health | jq '.llm_provider'

# 3. 检查 listing_gate 是否可用
curl http://localhost:8000/api/v1/products/1/listing-gate

# 4. 检查 webhook secret 文件
ls -la /opt/nuotao-ai-os/backend/webhook_secret.txt
```

---

## 验证清单

| 检查项 | 命令 | 预期结果 |
|---|---|---|
| 后端服务运行 | `systemctl status nuotao-backend` | `active (running)` |
| 健康检查 | `curl http://localhost:8000/health` | `{"status": "ok"}` |
| sensenova provider | `curl http://localhost:8000/api/v1/health \| jq '.llm_provider'` | `"sensenova"` 或 `"openai"` |
| webhook secret | `ls -la webhook_secret.txt` | 文件存在，权限 600 |
| listing_gate | `curl /api/v1/products/1/listing-gate` | 返回 gate 验证结果 |

---

## 部署后验证（第二轮复测）

部署完成后，通知我进行第二轮复测：

1. 登录 https://admin.nuotaooutdoor.com
2. 测试 1688 一键导入（验证 Bug #1）
3. 运行工作流（验证 Bug #3）
4. 执行上架确认（验证 Bug #17）
5. 测试回流同步（验证 Bug #19）

---

## 回滚计划

如果部署后出现问题：

```bash
# 回滚代码
cd /opt/nuotao-ai-os
git log --oneline -10
git checkout <previous-commit-hash>
git reset --hard <previous-commit-hash>

# 重启服务
sudo systemctl restart nuotao-backend

# 验证
curl http://localhost:8000/health
```
