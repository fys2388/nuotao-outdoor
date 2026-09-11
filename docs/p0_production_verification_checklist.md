# P0 生产部署确认清单

> 版本：v1.0 | 日期：2026-09-08
> 目的：逐项确认 Nuotao AI OS 所有组件是否**真正云端常驻运行**，消除「应该在跑」的模糊状态。
> 背景：第三方评审指出 Backend / Worker / Scheduler 的生产化部署状态不明确，需要最终确认。
> 使用方式：每一项必须实际执行验证命令并记录结果，禁止凭印象勾选。

---

## 验证总览

| 组件 | 状态 | 验证时间 | 验证人 |
|---|---|---|---|
| 1. Frontend (nuotaooutdoor.com) | ⬜ 待验证 | | |
| 2. WooCommerce 商城 | ⬜ 待验证 | | |
| 3. Backend API (FastAPI) | ⬜ 待验证 | | |
| 4. Worker (后台任务) | ⬜ 待验证 | | |
| 5. Scheduler (定时调度) | ⬜ 待验证 | | |
| 6. PostgreSQL (Neon) | ⬜ 待验证 | | |
| 7. Redis (Upstash) | ⬜ 待验证 | | |
| 8. Clerk / Identity | ⬜ 待验证 | | |
| 9. Cloudflare (DNS/CDN) | ⬜ 待验证 | | |
| 10. LLM Gateway | ⬜ 待验证 | | |
| 11. 监控与告警 | ⬜ 待验证 | | |
| 12. 备份与恢复 | ⬜ 待验证 | | |

---

## 1. Frontend (nuotaooutdoor.com)

### 1.1 网站可访问性

| 检查项 | 验证命令/方法 | 预期结果 | 实际结果 |
|---|---|---|---|
| HTTPS 可访问 | `curl -sI https://nuotaooutdoor.com \| head -5` | HTTP/2 200 | |
| 首页加载 | 浏览器打开首页 | 正常渲染，无报错 | |
| SSL 证书有效 | `curl -sI https://nuotaooutdoor.com \| grep -i strict` | 有 HSTS 或证书有效 | |
| 全球可访问 | https://www.uptrends.com/tools/uptime 多节点测试 | 主要地区可达 | |

### 1.2 关键页面

| 页面 | URL | 状态 |
|---|---|---|
| 首页 | https://nuotaooutdoor.com/ | ⬜ |
| 商品列表 | https://nuotaooutdoor.com/shop | ⬜ |
| 购物车 | https://nuotaooutdoor.com/cart | ⬜ |
| 结账 | https://nuotaooutdoor.com/checkout | ⬜ |
| 我的账户 | https://nuotaooutdoor.com/my-account | ⬜ |

---

## 2. WooCommerce 商城

### 2.1 商城功能

| 检查项 | 验证方法 | 预期结果 | 实际结果 |
|---|---|---|---|
| 商品数量 | WP Admin → Products | ≥ 6 SKU（当前线上） | |
| 商品可浏览 | 前台点击任意商品 | 详情页正常 | |
| 加入购物车 | 前台 Add to Cart | 购物车数量 +1 | |
| Stripe 支付 | 结账页选择 Stripe | 支付表单加载 | |
| Webhook 连通 | WooCommerce → Settings → Advanced → Webhooks | 有 API 密钥配置 | |

### 2.2 WooCommerce REST API

```bash
# 在服务器上执行（替换 KEY/SECRET）
curl -s "https://nuotaooutdoor.com/wp-json/wc/v3/products?per_page=1" \
  -u "ck_XXX:cs_XXX" | jq '.id, .name'
```

预期：返回商品 ID 和名称。
实际：____

---

## 3. Backend API (FastAPI)

### 3.1 服务状态

```bash
# SSH 到生产服务器后执行
systemctl is-active nuotao-backend
# 预期: active

systemctl status nuotao-backend --no-pager | head -20
# 预期: running, 最近无 crash

ps aux | grep -E "uvicorn|fastapi" | grep -v grep
# 预期: 有 1-2 个进程（worker 数）
```

实际结果：____

### 3.2 API 健康检查

```bash
# 本地（服务器上）
curl -s http://localhost:8000/health | jq .
# 预期: {"status": "ok", ...}

# 外网（通过域名/IP）
curl -s https://api.nuotaooutdoor.com/health | jq .
# 或通过 nginx 反代的路径
curl -s https://nuotaooutdoor.com/api/v1/health | jq .
```

实际结果：____

### 3.3 关键 API 端点

| 端点 | 验证方法 | 预期 |
|---|---|---|
| `/api/v1/health` | curl | 200 OK |
| `/api/v1/products` | curl (带 auth) | 返回商品列表 |
| `/api/v1/agent-suggestions/pending/stats` | curl (带 auth) | 返回待审批统计 |
| `/docs` (Swagger) | 浏览器 | API 文档可访问 |

### 3.4 进程稳定性

```bash
# 查看最近重启次数
systemctl show nuotao-backend -p NRestarts
# 预期: 0 或很少

# 查看最近错误日志
journalctl -u nuotao-backend --since "24 hours ago" -p err --no-pager
# 预期: 无 ERROR 或仅有可恢复的 WARNING
```

实际结果：____

---

## 4. Worker (后台任务)

### 4.1 服务状态

```bash
# 确认 worker 服务名（可能是 nuotao-worker 或类似）
systemctl list-units --type=service | grep -i nuotao
# 列出所有 nuotao 相关服务

systemctl is-active nuotao-worker
# 预期: active（如果服务名不同，替换）

ps aux | grep -E "worker|celery|arq|rq" | grep -v grep
# 预期: 有 worker 进程在运行
```

实际结果：____

### 4.2 Worker 配置确认

| 检查项 | 说明 | 状态 |
|---|---|---|
| Worker 服务名 | （记录实际服务名） | |
| Worker 入口命令 | （如 `python -m app.worker`） | |
| 队列连接 | Redis URL 配置正确 | ⬜ |
| 并发数 | （记录配置值） | |
| 自动重启 | Restart=always | ⬜ |

### 4.3 Worker 任务处理验证

```bash
# 查看 worker 最近日志
journalctl -u nuotao-worker --since "1 hour ago" --no-pager | tail -30
# 预期: 有任务处理记录，或空闲等待

# 检查是否有失败任务
journalctl -u nuotao-worker --since "24 hours ago" -p err --no-pager
# 预期: 无持续 ERROR
```

实际结果：____

---

## 5. Scheduler (定时调度)

### 5.1 服务状态

```bash
systemctl is-active nuotao-agent-scheduler
# 预期: active

systemctl status nuotao-agent-scheduler --no-pager | head -15

ps aux | grep agent_scheduler | grep -v grep
# 预期: 恰好 1 个进程（确认无 crontab 双跑）
```

实际结果：____

### 5.2 确认无 crontab 冲突

```bash
# 检查 root crontab
crontab -l 2>/dev/null | grep -iE "scheduler|agent|nuotao"
# 预期: 无相关条目（已迁移到 systemd）

# 检查 /etc/cron.d
ls -la /etc/cron.d/ | grep -i nuotao
# 预期: 无
```

实际结果：____

### 5.3 调度任务清单验证

根据 `docs/agent_scheduler_deployment.md`，应运行以下任务：

| 任务 | 频率 | 上次执行时间 | 状态 |
|---|---|---|---|
| daily_product_analyst | 每 30 分钟 | | ⬜ |
| daily_marketing_manager | 每 30 分钟 | | ⬜ |
| daily_supply_chain_manager | 每 30 分钟 | | ⬜ |
| execute_pending_suggestions | 每 15 分钟 | | ⬜ |
| feedback_learning | 每 60 分钟 | | ⬜ |

```bash
# 查看调度器日志确认任务在执行
journalctl -u nuotao-agent-scheduler --since "2 hours ago" --no-pager | grep -E "task|execute|complete|error" | tail -20
```

实际结果：____

---

## 6. PostgreSQL (Neon)

### 6.1 连接性

```bash
# 从生产服务器测试连接（替换连接串）
psql "postgresql://user:pass@ep-xxx.neon.tech/nuotao?sslmode=require" -c "SELECT 1;"
# 预期: 返回 1

# 或用 Python 测试
python -c "import psycopg2; conn = psycopg2.connect('$DATABASE_URL'); print('OK'); conn.close()"
```

实际结果：____

### 6.2 数据库健康

```sql
-- 连接后执行
SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';
-- 预期: ≥ 20 张表

SELECT count(*) FROM products;
-- 预期: ≥ 6 条

SELECT count(*) FROM product_analysis_runs;
-- 预期: ≥ 1 条（AI 分析记录）

SELECT now();
-- 确认时间正确
```

实际结果：____

### 6.3 Neon 控制台确认

| 检查项 | 状态 |
|---|---|
| Neon 项目活跃 | ⬜ |
| 计算端点运行中 | ⬜ |
| 存储用量正常 | ⬜ |
| 无暂停/休眠 | ⬜（Neon 免费层可能自动暂停，需确认） |

> ⚠️ Neon 免费层计算端点会在空闲后自动暂停（通常 5 分钟），首次请求会有冷启动延迟（1-3 秒）。如果 Backend 报连接超时，可能是 Neon 冷启动导致。

---

## 7. Redis (Upstash)

### 7.1 连接性

```bash
# 从生产服务器测试
redis-cli -u "rediss://:pass@xxx.upstash.io:6379" ping
# 预期: PONG

# 或用 Python
python -c "import redis; r = redis.from_url('$REDIS_URL'); print(r.ping())"
```

实际结果：____

### 7.2 数据检查

```bash
redis-cli -u "$REDIS_URL" info keyspace
# 预期: 有 key 存在（缓存/队列）

redis-cli -u "$REDIS_URL" dbsize
# 预期: > 0
```

实际结果：____

### 7.3 Upstash 控制台确认

| 检查项 | 状态 |
|---|---|
| Upstash 数据库活跃 | ⬜ |
| 连接数正常 | ⬜ |
| 用量在免费额度内 | ⬜ |
| TLS 已启用 | ⬜ |

---

## 8. Clerk / Identity

### 8.1 服务状态

| 检查项 | 验证方法 | 预期 |
|---|---|---|
| Clerk 应用活跃 | Clerk Dashboard → API Keys | 显示 Active |
| Backend JWT 验证 | 调用需认证的 API | 401 时返回正确错误 |
| 登录页可访问 | 浏览器打开登录页 | Clerk 托管页正常 |
| Webhook 连通 | Clerk Dashboard → Webhooks | 有端点配置且最近成功 |

### 8.2 配置确认

```bash
# 在服务器上检查环境变量
grep -E "CLERK|JWT" /opt/nuotao/backend/.env | sed 's/=.*/=***/'
# 预期: CLERK_SECRET_KEY, CLERK_PUBLISHABLE_KEY 等已配置（不显示实际值）
```

实际结果：____

---

## 9. Cloudflare (DNS/CDN)

### 9.1 DNS 解析

```bash
# 检查域名解析
nslookup nuotaooutdoor.com
# 预期: 解析到 Cloudflare IP 或源站 IP

dig nuotaooutdoor.com +short
# 预期: 有 A 记录

# 检查 Cloudflare 代理
curl -sI https://nuotaooutdoor.com | grep -i "cf-ray\|server"
# 预期: 有 cf-ray 头或 server: cloudflare
```

实际结果：____

### 9.2 Cloudflare 控制台确认

| 检查项 | 状态 |
|---|---|
| 域名已接入 Cloudflare | ⬜ |
| DNS 记录正确 | ⬜ |
| SSL/TLS 模式正确（Full/Strict） | ⬜ |
| CDN 缓存已启用 | ⬜ |
| WAF/安全规则配置 | ⬜ |

---

## 10. LLM Gateway

### 10.1 配置确认

```bash
# 检查 LLM 相关环境变量（不显示密钥）
grep -E "OPENAI|DEEPSEEK|LITELLM|LLM" /opt/nuotao/backend/.env | sed 's/=.*/=***/'
# 预期: 至少一个 LLM 提供商已配置
```

实际结果：____

### 10.2 连通性测试

```bash
# 测试 OpenAI（如果配置了）
curl -s https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" | jq '.data[0].id' 2>/dev/null | head -1
# 预期: 返回模型 ID

# 测试 DeepSeek（如果配置了）
curl -s https://api.deepseek.com/models \
  -H "Authorization: Bearer $DEEPSEEK_API_KEY" | jq '.data[0].id' 2>/dev/null | head -1
```

实际结果：____

### 10.3 LLM 调用记录

```sql
-- 连接 PostgreSQL 后检查 AI 运行记录
SELECT count(*) FROM ai_agent_runs WHERE created_at > now() - interval '7 days';
-- 预期: > 0（最近 7 天有 AI 调用）

SELECT agent, count(*) FROM ai_agent_runs 
WHERE created_at > now() - interval '7 days' 
GROUP BY agent;
-- 预期: product-analyst 等有记录
```

实际结果：____

---

## 11. 监控与告警

### 11.1 日志可访问

```bash
# 检查结构化日志
ls -la /opt/nuotao/backend/logs/ 2>/dev/null || echo "logs dir not found"
# 或检查 journalctl 是否有日志

journalctl -u nuotao-backend --since "1 hour ago" --no-pager | tail -5
# 预期: 有最近日志
```

实际结果：____

### 11.2 告警通道

| 检查项 | 状态 |
|---|---|
| Sentry 已配置（如果有） | ⬜ |
| 飞书/邮件告警通道 | ⬜ |
| 服务宕机告警 | ⬜ |
| 错误率告警 | ⬜ |

---

## 12. 备份与恢复

### 12.1 数据库备份

| 检查项 | 验证方法 | 状态 |
|---|---|---|
| 自动备份已配置 | crontab / 定时任务 / Neon 控制台 | ⬜ |
| 最近备份存在 | 检查备份文件/对象存储 | ⬜ |
| 备份可恢复 | 定期演练（每季度） | ⬜ |

### 12.2 备份验证命令

```bash
# 如果有本地备份
ls -la /opt/nuotao/backups/ | tail -5

# 检查备份大小（非空）
find /opt/nuotao/backups/ -name "*.sql" -o -name "*.dump" | head -5
```

实际结果：____

---

## 验证结论

### 整体状态

| 评级 | 条件 |
|---|---|
| ✅ 生产就绪 | 12 项全部通过 |
| ⚠️ 基本可用但有缺口 | 核心组件（1-7）通过，非核心有缺口 |
| ❌ 未生产化 | 核心组件（Backend/Worker/Scheduler）有未通过项 |

### 当前评级：⬜ 待验证

### 未通过项清单

| # | 组件 | 问题描述 | 严重程度 | 修复计划 |
|---|---|---|---|---|
| | | | | |

### 下一步行动

1. ____
2. ____
3. ____

---

## 附录：快速验证脚本

将以下脚本保存为 `verify-production.sh`，在生产服务器上执行可一次性输出核心组件状态：

```bash
#!/bin/bash
echo "=== Nuotao AI OS 生产环境快速验证 ==="
echo "时间: $(date)"
echo ""

echo "1. Backend API:"
systemctl is-active nuotao-backend 2>/dev/null || echo "  服务未找到"
curl -s http://localhost:8000/health 2>/dev/null | head -1 || echo "  本地健康检查失败"
echo ""

echo "2. Worker:"
systemctl is-active nuotao-worker 2>/dev/null || echo "  服务未找到/名称不同"
ps aux | grep -E "worker|celery" | grep -v grep | head -2
echo ""

echo "3. Scheduler:"
systemctl is-active nuotao-agent-scheduler 2>/dev/null || echo "  服务未找到"
ps aux | grep agent_scheduler | grep -v grep | wc -l | xargs echo "  进程数:"
echo ""

echo "4. 数据库连接:"
# 需要 DATABASE_URL 环境变量
python3 -c "
import os
try:
    import psycopg2
    url = os.environ.get('DATABASE_URL','')
    if url:
        conn = psycopg2.connect(url)
        cur = conn.cursor()
        cur.execute('SELECT count(*) FROM information_schema.tables WHERE table_schema=%s', ('public',))
        print(f'  连接OK, 表数量: {cur.fetchone()[0]}')
        conn.close()
    else:
        print('  DATABASE_URL 未设置')
except Exception as e:
    print(f'  连接失败: {e}')
" 2>/dev/null
echo ""

echo "5. Redis 连接:"
python3 -c "
import os
try:
    import redis
    url = os.environ.get('REDIS_URL','')
    if url:
        r = redis.from_url(url)
        print(f'  PING: {r.ping()}')
        print(f'  DB size: {r.dbsize()}')
    else:
        print('  REDIS_URL 未设置')
except Exception as e:
    print(f'  连接失败: {e}')
" 2>/dev/null
echo ""

echo "=== 验证完成 ==="
```

---

*清单结束 — 完成所有验证后，将本文件更新为实际结果并归档到 docs/。*
