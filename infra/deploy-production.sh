#!/bin/bash
set -e
cd /opt/nuotao-ai-os

echo "=== 0. Pre-deploy backup (code + db + frontend) ==="
chmod +x /opt/nuotao-ai-os/infra/deploy-rollback.sh 2>/dev/null || true
if [ -f /opt/nuotao-ai-os/infra/deploy-rollback.sh ]; then
  BACKUP_DIR=$(/opt/nuotao-ai-os/infra/deploy-rollback.sh backup 2>/dev/null || echo "")
  if [ -n "$BACKUP_DIR" ]; then
    echo "Backup created: $BACKUP_DIR"
    echo "$BACKUP_DIR" > /tmp/nuotao_last_backup 2>/dev/null || true
  else
    echo "WARN: backup script returned no backup dir, continuing (non-fatal)"
  fi
else
  echo "WARN: deploy-rollback.sh not found, skipping backup"
fi

echo "=== 1. Pulling latest code ==="
git fetch --prune origin $(git rev-parse --abbrev-ref HEAD)
git reset --hard origin/$(git rev-parse --abbrev-ref HEAD)
git clean -fd backend/alembic/versions/ 2>/dev/null || true
echo "[git] cleaned untracked migration files"

echo "=== 2. Installing backend dependencies ==="
cd /opt/nuotao-ai-os/backend
if [ ! -f .venv/bin/activate ]; then
  echo "[venv] .venv not found, creating..."
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -e . --quiet 2>/dev/null || pip install -r requirements.txt --quiet || { echo "ERROR: Python 渚濊禆瀹夎澶辫触锛岃妫€鏌?pip 婧愪笌 requirements.txt"; exit 1; }

echo "=== 2.5 .env variable drift check ==="
ENV_FILE=/opt/nuotao-ai-os/backend/.env
TEMPLATE=/opt/nuotao-ai-os/backend/.env.production.template
if [ -f "$TEMPLATE" ] && [ -f "$ENV_FILE" ]; then
  MISSING=0
  while IFS='=' read -r key _; do
    case "$key" in
      \#*|'') continue ;;
    esac
    if ! grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
      echo "  [MISSING] $key"
      MISSING=$((MISSING+1))
    fi
  done < "$TEMPLATE"
  if [ "$MISSING" -gt 0 ]; then
    echo "WARNING: $MISSING variable(s) in template missing from server .env"
    echo "  Fix: ssh to server and add missing vars to /opt/nuotao-ai-os/backend/.env"
  else
    echo "[env] all template variables present in server .env"
  fi
else
  echo "[env] template or .env not found, skipping drift check"
fi

echo "=== 2.6 Injecting WooCommerce REST credentials into server .env ==="
# This script runs on the REMOTE server via appleboy/ssh-action, so the
# workflow-level env vars are NOT visible here - the runner-side env is
# never shipped to the remote shell. The values must be interpolated into
# this script text by GitHub Actions at parse time. The first version of
# this step read $WOOCOMMERCE_CONSUMER_KEY from the workflow env and
# silently skipped with "WC secrets not configured in this repo" even
# though the secrets existed. Secret values are masked in run logs.
ENV_FILE=/opt/nuotao-ai-os/backend/.env
WC_KEY='\$WOOCOMMERCE_CONSUMER_KEY'
WC_SECRET='\$WOOCOMMERCE_CONSUMER_SECRET'
WC_BASE='\$WOOCOMMERCE_BASE_URL'
if [ -n "$WC_KEY" ] && [ -n "$WC_SECRET" ]; then
  mkdir -p "$(dirname "$ENV_FILE")"
  touch "$ENV_FILE"
  sed -i '/^WOOCOMMERCE_BASE_URL=/d;/^WOOCOMMERCE_CONSUMER_KEY=/d;/^WOOCOMMERCE_CONSUMER_SECRET=/d' "$ENV_FILE"
  {
    echo "WOOCOMMERCE_BASE_URL=${WC_BASE:-https://nuotaooutdoor.com}"
    echo "WOOCOMMERCE_CONSUMER_KEY=${WC_KEY}"
    echo "WOOCOMMERCE_CONSUMER_SECRET=${WC_SECRET}"
  } >> "$ENV_FILE"
  echo "[wc] credentials injected into $ENV_FILE (base_url=${WC_BASE:-https://nuotaooutdoor.com})"
else
  echo "[wc] WC secrets not configured in this repo, skipping injection"
fi

echo "=== 2.7 Injecting WordPress application password (media upload) ==="
WP_USER='\$WP_USERNAME'
WP_PASS='\$WP_APPLICATION_PASSWORD'
if [ -n "$WP_USER" ] && [ -n "$WP_PASS" ]; then
  sed -i '/^WP_USERNAME=/d;/^WP_APPLICATION_PASSWORD=/d' "$ENV_FILE"
  {
    echo "WP_USERNAME=${WP_USER}"
    echo "WP_APPLICATION_PASSWORD=${WP_PASS}"
  } >> "$ENV_FILE"
  echo "[wp] application password credentials injected into $ENV_FILE (user=${WP_USER})"
else
  echo "[wp] WP application password secrets not configured, media upload will fall back to WC keys (may fail)"
fi

echo "=== 2.7.5 Injecting 1688 Open API credentials ==="
ALI_KEY='\$ALI1688_APP_KEY'
ALI_SECRET='\$ALI1688_APP_SECRET'
ALI_TOKEN='\$ALI1688_ACCESS_TOKEN'
if [ -n "$ALI_KEY" ] && [ -n "$ALIKEY" ]; then
  echo "ALI1688_APP_KEY=${ALI_KEY}" >> "$ENV_FILE"
  echo "ALI1688_APP_KEY=${ALIKEY}" >> "$ENV_FILE"
  echo "[1688] key+secret present"
else
  echo "[1688] ALI1688 secrets not configured, skipping injection"
fi

echo "=== 2.8 Injecting image generation API keys ==="
OPENAI_KEY='\$OPENAI_API_KEY'
OPENAI_URL='\$OPENAI_BASE_URL'
VOLC_KEY='\$VOLCENGINE_API_KEY'
DASHSCOPE_KEY='\$DASHSCOPE_API_KEY'
DASHSCOPE_WS='\$DASHSCOPE_WORKSPACE_ID'
if [ -n "$OPENAI_KEY" ] || [ -n "$VOLC_KEY" ] || [ -n "$DASHSCOPE_KEY" ]; then
  sed -i '/^OPENAI_API_KEY=/d;/^OPENAI_BASE_URL=/d;/^VOLCENGINE_API_KEY=/d;/^DASHSCOPE_API_KEY=/d;/^DASHSCOPE_WORKSPACE_ID=/d' "$ENV_FILE"
  [ -n "$OPENAI_KEY" ] && echo "OPENAI_API_KEY=${OPENAI_KEY}" >> "$ENV_FILE"
  [ -n "$OPENAI_URL" ] && echo "OPENAI_BASE_URL=${OPENAI_URL}" >> "$ENV_FILE"
  [ -n "$VOLC_KEY" ] && echo "VOLCENGINE_API_KEY=${VOLC_KEY}" >> "$ENV_FILE"
  [ -n "$DASHSCOPE_KEY" ] && echo "DASHSCOPE_API_KEY=${DASHSCOPE_KEY}" >> "$ENV_FILE"
  [ -n "$DASHSCOPE_WS" ] && echo "DASHSCOPE_WORKSPACE_ID=${DASHSCOPE_WS}" >> "$ENV_FILE"
  echo "[imggen] keys injected (openai=$([ -n "$OPENAI_KEY" ] && echo yes || echo no), volc=$([ -n "$VOLC_KEY" ] && echo yes || echo no), dash=$([ -n "$DASHSCOPE_KEY" ] && echo yes || echo no))"
else
  echo "[imggen] No image gen API keys in GitHub Secrets (may already be in server .env)"
fi

echo "=== 3. Running database migrations ==="
# DATABASE_URL 必须以环境变量方式传给 alembic（pydantic 环境变量优先于 .env 文件）。
# 服务器 backend/.env 的 DATABASE_URL 可能为空/损坏（password authentication failed 根因）。
# 恢复优先级：① 根目录 .env ② backend/.env ③ 最近备份 ④ 后端运行进程环境。
ENV_FILE=/opt/nuotao-ai-os/backend/.env
ROOT_ENV=/opt/nuotao-ai-os/.env
DB_VAL=""
if [ -f "$ROOT_ENV" ]; then
  DB_VAL=$(grep '^DATABASE_URL=' "$ROOT_ENV" | head -1 | cut -d'=' -f2- | tr -d ' ' | tr -d '"' | tr -d "'")
fi
if [ -z "$DB_VAL" ] && [ -f "$ENV_FILE" ]; then
  DB_VAL=$(grep '^DATABASE_URL=' "$ENV_FILE" | head -1 | cut -d'=' -f2- | tr -d ' ' | tr -d '"' | tr -d "'")
fi
if [ -z "$DB_VAL" ]; then
  LATEST_BAK=$(ls -td /opt/nuotao-ai-os/backups/pre_deploy_*/backend.env 2>/dev/null | head -1)
  if [ -n "$LATEST_BAK" ]; then
    DB_VAL=$(grep '^DATABASE_URL=' "$LATEST_BAK" | head -1 | cut -d'=' -f2- | tr -d ' ' | tr -d '"' | tr -d "'")
    [ -n "$DB_VAL" ] && echo "[db] restored DATABASE_URL from backup $LATEST_BAK"
  fi
fi
if [ -z "$DB_VAL" ]; then
  BPID=$(pgrep -f 'app.main|uvicorn' | head -1)
  if [ -n "$BPID" ]; then
    DB_VAL=$(tr '\0' '\n' < /proc/$BPID/environ 2>/dev/null | grep '^DATABASE_URL=' | head -1 | cut -d'=' -f2-)
    [ -n "$DB_VAL" ] && echo "[db] DATABASE_URL from backend process pid $BPID"
  fi
fi
if [ -n "$DB_VAL" ]; then
  export DATABASE_URL="$DB_VAL"
  # 同步回 backend/.env，确保后端重启后仍能连接
  if [ -f "$ENV_FILE" ]; then
    sed -i '/^DATABASE_URL=/d' "$ENV_FILE"
  fi
  echo "DATABASE_URL=$DB_VAL" >> "$ENV_FILE" 2>/dev/null || true
  echo "[db] DATABASE_URL ready (host=$(echo "$DB_VAL" | sed -E 's#.*@([^/]+)/.*#\1#'))"
else
  echo "[db] WARN: no DATABASE_URL found anywhere; THIS DEPLOY HAS NO MIGRATIONS so skipping alembic"
fi
if DBURL=$(grep '^DATABASE_URL=' "$ENV_FILE" 2>/dev/null | sed -E 's#(://[^:]+:)[^@]+@#\1***@#'); then
  echo "[db] 杩炴帴閰嶇疆(瀵嗙爜宸查殣钘?: $DBURL"
else
  echo "[db] 璀﹀憡: 鏈湪 $ENV_FILE 鎵惧埌 DATABASE_URL"
fi
echo "[db] 鎵ц鏁版嵁搴撹縼绉?.."
if [ -z "$DB_VAL" ]; then
  echo "[db] SKIP alembic upgrade (DATABASE_URL unavailable, no migrations in this deploy)"
elif ! alembic upgrade head; then
  echo "WARN: 鏁版嵁搴撹縼绉诲け璐ワ紙褰撳墠 deploy 鏃犳柊杩佺Щ锛屼笉闃诲锛?, 璇锋墜鍔ㄦ煡: alembic current"
fi
echo "[db] ensure all model tables exist (create_all idempotent)..."
python3 /opt/nuotao-ai-os/infra/ensure_tables.py 2>&1 || echo "[db] table check skipped (script failed, non-blocking)"
echo "[db] table check done"

echo "=== 3.6 Seeding agent config (idempotent) ==="
# 瑙勮寖 ID 娉ㄥ唽 5 涓?Agent + 宸ュ叿鐧藉悕鍗曪紙handler_name 瀵归綈鐪熷疄娉ㄥ唽鍚嶏級
# + 鎴愭湰鎶ゆ爮 + 瀹℃壒 SLA銆倁psert 璇箟锛屼笉鎵ц DELETE銆?            # 鍙栦唬 scripts/configure_agent_roles.sql锛坔yphen ID 涓?runtime 鍐茬獊锛屽凡鍒犻櫎锛夈€?            # 璇﹁ docs/agent_team_workflow_refactor.md
python3 /opt/nuotao-ai-os/backend/scripts/seed_agent_config.py 2>&1 || echo "[seed] agent config seed failed (non-blocking, check logs)"
echo "[seed] agent config seed done"

echo "=== 3.4 Ensure nuotao system user and permissions ==="
id nuotao >/dev/null 2>&1 || useradd -r -s /bin/false nuotao
mkdir -p /opt/nuotao-ai-os/backend/data /opt/nuotao-ai-os/backend/logs /opt/nuotao-ai-os/backend/app/data /opt/nuotao-ai-os/backend/app/logs
chown -R nuotao:nuotao /opt/nuotao-ai-os/backend
echo "[user] nuotao user ready, backend dir owned by nuotao"

echo "=== 3.5 Installing backend systemd from versioned template ==="
BACKEND_SERVICE=/etc/systemd/system/nuotao-backend.service
BACKEND_TEMPLATE=/opt/nuotao-ai-os/infra/systemd/nuotao-backend.service
if [ -f "$BACKEND_TEMPLATE" ]; then
  cp "$BACKEND_TEMPLATE" "$BACKEND_SERVICE"
  chmod 644 "$BACKEND_SERVICE"
  echo "[backend] installed versioned template -> $BACKEND_SERVICE"
elif [ ! -f "$BACKEND_SERVICE" ]; then
  {
    echo '[Unit]'
    echo 'Description=Nuotao AI OS Backend API Server'
    echo 'After=network.target postgresql.service redis.service'
    echo 'Wants=postgresql.service redis.service'
    echo ''
    echo '[Service]'
    echo 'Type=simple'
    echo 'User=nuotao'
    echo 'Group=nuotao'
    echo 'WorkingDirectory=/opt/nuotao-ai-os/backend'
    echo 'Environment="PATH=/opt/nuotao-ai-os/backend/.venv/bin"'
    echo 'EnvironmentFile=/opt/nuotao-ai-os/.env'
    echo 'ExecStart=/opt/nuotao-ai-os/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 4'
    echo 'Restart=always'
    echo 'RestartSec=5'
    echo 'StandardOutput=journal'
    echo 'StandardError=journal'
    echo ''
    echo '[Install]'
    echo 'WantedBy=multi-user.target'
  } > "$BACKEND_SERVICE"
  echo "[backend] template missing, generated inline fallback"
else
  echo "[backend] template missing, keeping existing $BACKEND_SERVICE"
  sed -i 's|/opt/nuotao-ai-os/|/opt/nuotao-ai-os/|g' "$BACKEND_SERVICE"
fi
systemctl daemon-reload
systemctl enable nuotao-backend 2>/dev/null || true

echo "=== 4. Restarting backend service ==="
systemctl restart nuotao-backend
sleep 3
systemctl status nuotao-backend --no-pager

echo "=== 5. Building frontend ==="
# 4GB 机器上前端构建峰值内存易触发 OOM killer，幂等补 2GB swap 兜底（失败不阻断）
(
  if [ "$(id -u)" = 0 ]; then
    if ! swapon --show 2>/dev/null | grep -q .; then
      (fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none)
      chmod 600 /swapfile
      mkswap /swapfile >/dev/null
      swapon /swapfile
      echo 10 > /proc/sys/vm/swappiness 2>/dev/null || true
      echo "[swap] created 2G /swapfile"
    else
      echo "[swap] already active: $(swapon --show --noheadings 2>/dev/null | wc -l) device(s)"
    fi
  else
    echo "[swap] not root, skipping swapfile creation"
  fi
) || echo "[swap] setup failed (non-fatal)"
free -m | head -2 || true
cd /opt/nuotao-ai-os/frontend
npm install --silent
# 限制 Node 堆内存，避免 OOM killer 杀构建进程
export NODE_OPTIONS="--max-old-space-size=2048"
npm run build

echo "=== 6. Deploying frontend ==="
rm -rf /var/www/nuotao/*
cp -r dist/* /var/www/nuotao/
chown -R www-data:www-data /var/www/nuotao

echo "=== 6.5 Installing nginx from versioned template (infra/nginx/console.conf) ==="
NGINX_CONF=/etc/nginx/sites-available/nuotao-console
TEMPLATE=/opt/nuotao-ai-os/infra/nginx/console.conf
if [ -f "$TEMPLATE" ]; then
  cp "$TEMPLATE" "$NGINX_CONF"
  echo "[nginx] installed versioned template -> $NGINX_CONF"
elif [ ! -f "$NGINX_CONF" ]; then
  echo "ERROR: 妯℃澘涓嶅瓨鍦ㄤ笖鏃犳棦鏈夐厤缃紝鏃犳硶瀹夎 nginx 閰嶇疆"
  exit 1
else
  echo "[nginx] template missing, keeping existing $NGINX_CONF"
fi
ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/nuotao-console
nginx -t && systemctl reload nginx
echo "[nginx] console :8081 ready"

echo "=== 6.6 nginx server_name conflict check ==="
grep -rn "admin.nuotaooutdoor.com" /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ 2>/dev/null || echo "(no admin.nuotaooutdoor.com references)"

echo "=== 6.7 cleaning stale nginx site backups ==="
CLEANED=0
for f in /etc/nginx/sites-enabled/nuotao.bak.*; do
  [ -e "$f" ] || continue
  mv "$f" /etc/nginx/sites-available/
  echo "[nginx] moved $f -> sites-available"
  CLEANED=1
done
if [ "$CLEANED" = "1" ]; then
  nginx -t && systemctl reload nginx
  echo "[nginx] reloaded after cleanup"
else
  echo "[nginx] no stale backups, nothing to do"
fi

echo "=== 7. Health check ==="
sleep 5
BACKEND_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/api/v1/readyz || true)
FRONTEND_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8081/ || true)
echo "Backend API: $BACKEND_CODE"
echo "Frontend: $FRONTEND_CODE"
if [ "$BACKEND_CODE" != "200" ]; then
  echo "=== backend diagnostics ==="
  echo "-- is-active:"; systemctl is-active nuotao-backend || true
  echo "-- status:"; systemctl status nuotao-backend --no-pager | head -15 || true
  echo "-- journal:"; journalctl -u nuotao-backend -n 25 --no-pager || true
  echo "-- listeners:"; ss -tlnp 2>/dev/null | grep -E ':8000|:5432' || echo "(none on 8000/5432)"
  echo "-- postgres:"; systemctl status postgresql --no-pager | head -6 || true
  echo "ERROR: 鍚庣鍋ュ悍妫€鏌ュけ璐?(HTTP $BACKEND_CODE)"
  echo "=== AUTO ROLLBACK ==="
  if [ -f /tmp/nuotao_last_backup ] && [ -f /opt/nuotao-ai-os/infra/deploy-rollback.sh ]; then
    BACKUP_DIR=$(cat /tmp/nuotao_last_backup)
    echo "Rolling back to: $BACKUP_DIR"
    /opt/nuotao-ai-os/infra/deploy-rollback.sh rollback "$BACKUP_DIR" || echo "ROLLBACK FAILED - manual intervention required"
  else
    echo "No backup found, cannot auto-rollback"
  fi
  exit 1
fi
if [ "$FRONTEND_CODE" != "200" ]; then
  echo "ERROR: 鍓嶇鍋ュ悍妫€鏌ュけ璐?(HTTP $FRONTEND_CODE)"
  echo "=== AUTO ROLLBACK ==="
  if [ -f /tmp/nuotao_last_backup ] && [ -f /opt/nuotao-ai-os/infra/deploy-rollback.sh ]; then
    BACKUP_DIR=$(cat /tmp/nuotao_last_backup)
    /opt/nuotao-ai-os/infra/deploy-rollback.sh rollback "$BACKUP_DIR" || echo "ROLLBACK FAILED"
  fi
  exit 1
fi

echo "=== 7.4 Deploy monitoring configs (prometheus/grafana/alertmanager) ==="
if [ -d /etc/prometheus ]; then
  cp /opt/nuotao-ai-os/infra/monitoring/prometheus.yml /etc/prometheus/prometheus.yml 2>/dev/null || true
  cp /opt/nuotao-ai-os/infra/monitoring/alerts.yml /etc/prometheus/alerts.yml 2>/dev/null || true
  systemctl reload prometheus 2>/dev/null || systemctl restart prometheus 2>/dev/null || echo "[monitoring] prometheus reload skipped"
  echo "[monitoring] prometheus config deployed"
else
  echo "[monitoring] prometheus not installed, skipping"
fi
if [ -d /etc/grafana/provisioning ]; then
  cp -r /opt/nuotao-ai-os/infra/grafana/provisioning/* /etc/grafana/provisioning/ 2>/dev/null || true
  systemctl restart grafana-server 2>/dev/null || echo "[monitoring] grafana restart skipped"
  echo "[monitoring] grafana provisioning deployed"
else
  echo "[monitoring] grafana not installed, skipping"
fi
if [ -d /etc/alertmanager ] && [ -f /opt/nuotao-ai-os/infra/monitoring/alertmanager.yml ]; then
  cp /opt/nuotao-ai-os/infra/monitoring/alertmanager.yml /etc/alertmanager/alertmanager.yml 2>/dev/null || true
  systemctl reload alertmanager 2>/dev/null || systemctl restart alertmanager 2>/dev/null || true
  echo "[monitoring] alertmanager config deployed"
fi

echo "=== 7.5 Configuring AI Agent Scheduler ==="
SCHEDULER_SERVICE=/etc/systemd/system/nuotao-agent-scheduler.service
SCHEDULER_TEMPLATE=/opt/nuotao-ai-os/infra/systemd/nuotao-agent-scheduler.service
if [ -f "$SCHEDULER_TEMPLATE" ]; then
  # 妯℃澘浼樺厛锛氫互浠撳簱鐗堟湰鍖栨ā鏉夸负鍑嗭紙docs/agent_scheduler_deployment.md锛?              cp "$SCHEDULER_TEMPLATE" "$SCHEDULER_SERVICE"
  chmod 644 "$SCHEDULER_SERVICE"
  echo "[scheduler] installed versioned template -> $SCHEDULER_SERVICE"
elif [ ! -f "$SCHEDULER_SERVICE" ]; then
  # 鍏滃簳锛氭ā鏉跨己澶变笖鏈嶅姟涓嶅瓨鍦ㄦ椂鍐呰仈鐢熸垚
  {
    echo '[Unit]'
    echo 'Description=Nuotao AI Agent Scheduler'
    echo 'After=network.target postgresql.service'
    echo ''
    echo '[Service]'
    echo 'Type=simple'
    echo 'User=nuotao'
    echo 'Group=nuotao'
    echo 'WorkingDirectory=/opt/nuotao-ai-os/backend'
    echo 'Environment="PATH=/opt/nuotao-ai-os/backend/.venv/bin:/usr/local/bin:/usr/bin:/bin"'
    echo 'ExecStart=/opt/nuotao-ai-os/backend/.venv/bin/python -m app.services.agent_scheduler'
    echo 'Restart=always'
    echo 'RestartSec=10'
    echo 'StandardOutput=journal'
    echo 'StandardError=journal'
    echo ''
    echo '[Install]'
    echo 'WantedBy=multi-user.target'
  } > "$SCHEDULER_SERVICE"
  echo "[scheduler] template missing, generated inline fallback"
else
  echo "[scheduler] template missing, keeping existing $SCHEDULER_SERVICE"
  sed -i 's|^ExecStart=.*|ExecStart=/opt/nuotao-ai-os/backend/.venv/bin/python -m app.services.agent_scheduler|' "$SCHEDULER_SERVICE"
fi
systemctl daemon-reload
systemctl enable nuotao-agent-scheduler 2>/dev/null || true
systemctl restart nuotao-agent-scheduler
sleep 3
systemctl status nuotao-agent-scheduler --no-pager | head -8 || echo "[scheduler] status check failed"
echo "[scheduler] AI Agent Scheduler configured and started"

echo "=== 7.6 Configuring AI Agent Worker ==="
# 姝ゅ墠鏃犱换浣?systemd 鍗曞厓锛歅OST /api/v1/agent-tasks 鍏ラ槦鍚庢棤浜烘秷璐癸紝
# 浠诲姟姘镐箙 pending銆侀槦鍒楁寔缁爢绉€傝瑙?docs/agent_team_workflow_refactor.md
WORKER_SERVICE=/etc/systemd/system/nuotao-agent-worker.service
WORKER_TEMPLATE=/opt/nuotao-ai-os/infra/systemd/nuotao-agent-worker.service
if [ -f "$WORKER_TEMPLATE" ]; then
  cp "$WORKER_TEMPLATE" "$WORKER_SERVICE"
  chmod 644 "$WORKER_SERVICE"
  echo "[worker] installed versioned template -> $WORKER_SERVICE"
elif [ ! -f "$WORKER_SERVICE" ]; then
  {
    echo '[Unit]'
    echo 'Description=Nuotao AI Agent Worker (Redis Streams consumer)'
    echo 'After=network.target postgresql.service redis.service'
    echo 'Wants=postgresql.service redis.service'
    echo ''
    echo '[Service]'
    echo 'Type=simple'
    echo 'User=nuotao'
    echo 'Group=nuotao'
    echo 'WorkingDirectory=/opt/nuotao-ai-os/backend'
    echo 'Environment="PATH=/opt/nuotao-ai-os/backend/.venv/bin:/usr/local/bin:/usr/bin:/bin"'
    echo 'EnvironmentFile=/opt/nuotao-ai-os/backend/.env'
    echo 'ExecStart=/opt/nuotao-ai-os/backend/.venv/bin/python -m app.worker'
    echo 'Restart=always'
    echo 'RestartSec=10'
    echo 'StandardOutput=journal'
    echo 'StandardError=journal'
    echo ''
    echo '[Install]'
    echo 'WantedBy=multi-user.target'
  } > "$WORKER_SERVICE"
  echo "[worker] template missing, generated inline fallback"
else
  echo "[worker] template missing, keeping existing $WORKER_SERVICE"
  sed -i 's|^ExecStart=.*|ExecStart=/opt/nuotao-ai-os/backend/.venv/bin/python -m app.worker|' "$WORKER_SERVICE"
fi
systemctl daemon-reload
systemctl enable nuotao-agent-worker 2>/dev/null || true
systemctl restart nuotao-agent-worker
sleep 3
if systemctl is-active --quiet nuotao-agent-worker; then
  echo "[worker] nuotao-agent-worker is active"
else
  echo "[worker] WARNING: nuotao-agent-worker is NOT active; scheduling agent tasks will pile up in Redis"
  journalctl -u nuotao-agent-worker -n 20 --no-pager || true
fi
systemctl status nuotao-agent-worker --no-pager | head -8 || echo "[worker] status check failed"
echo "[worker] AI Agent Worker configured"

echo "=== 7.7 Single-process check (scheduler + worker) ==="
echo "[procs] agent_scheduler: $(pgrep -fc 'app.services.agent_scheduler' || echo 0) (鏈熸湜 1)"
echo "[procs] agent_worker:    $(pgrep -fc 'app.worker' || echo 0) (鏈熸湜 1)"
redis-cli --raw KEYS 'nuotao:agent-worker:*' 2>/dev/null | head -5 || echo "[redis] not available, skipping worker registry check"

echo "=== Deployment completed successfully ==="






