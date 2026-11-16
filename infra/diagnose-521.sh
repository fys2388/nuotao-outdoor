#!/usr/bin/env bash
# ============================================================
# Nuotao AI OS - 521 故障一键诊断
#
# 用途：当 Cloudflare 返回 521（Web server is down）时，
#       在 Hetzner 源站服务器上执行，输出足以定位根因的信息。
#
# 用法：sudo bash infra/diagnose-521.sh
#
# 输出结构（可整段复制到 AI 助手分析）：
#   [1] 时间戳 + 主机名 + 公网 IP
#   [2] 磁盘 / 内存 / inode 使用
#   [3] 关键端口监听状态
#   [4] systemd 服务状态（nginx / nuotao-backend / certbot.timer）
#   [5] nginx -t 配置校验
#   [6] 本地 curl 直连测试（绕过 Cloudflare）
#   [7] 证书到期时间
#   [8] 最近的 nginx / journal 错误
# ============================================================

set -u  # 不用 -e：诊断脚本允许单条失败继续

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

section() { echo ""; echo -e "${BLUE}===== $1 =====${NC}"; }
warn()    { echo -e "${YELLOW}[WARN] $1${NC}"; }
ok()      { echo -e "${GREEN}[OK]   $1${NC}"; }
bad()     { echo -e "${RED}[FAIL] $1${NC}"; }

if [ "$EUID" -ne 0 ]; then
    echo "请以 root 权限运行：sudo bash $0"
    exit 1
fi

section "[1] 主机基本信息"
date -u +"UTC time: %Y-%m-%d %H:%M:%S"
echo "hostname: $(hostname)"
echo "uptime:   $(uptime -p)"
echo "public IP: $(curl -s --max-time 5 ifconfig.me || echo 'N/A')"

section "[2] 磁盘 / 内存 / inode"
df -h / /var/log 2>/dev/null | sed 's/^/  /'
echo "  --- inode ---"
df -i / /var/log 2>/dev/null | sed 's/^/  /'
echo "  --- memory ---"
free -h | sed 's/^/  /'
echo "  --- swap ---"
swapon --show 2>/dev/null | sed 's/^/  /' || echo "  no swap"

# 磁盘爆掉是 521 的经典根因
ROOT_PCT=$(df / | awk 'NR==2 {gsub("%","",$5); print $5}')
if [ "${ROOT_PCT:-0}" -ge 95 ]; then
    bad "根分区已用 ${ROOT_PCT}%（≥95% 会导致 Nginx 写日志失败/进程退出）"
fi

section "[3] 关键端口监听"
LISTEN=$(ss -lntp 2>/dev/null | grep -E ':(80|443|8000|8001)\b' || true)
if [ -z "$LISTEN" ]; then
    bad "没有任何关键端口在监听 —— Nginx / 后端服务全部挂了"
else
    echo "$LISTEN" | sed 's/^/  /'
fi

section "[4] systemd 服务状态"
for svc in nginx nuotao-backend nuotao-backend-staging nuotao-agent-worker nuotao-agent-scheduler certbot.timer; do
    if systemctl list-unit-files "$svc.service" 2>/dev/null | grep -q "$svc"; then
        STATE=$(systemctl is-active "$svc" 2>/dev/null || true)
        UNIT=$(systemctl is-enabled "$svc" 2>/dev/null || true)
        printf "  %-30s active=%-10s enabled=%s\n" "$svc" "$STATE" "$UNIT"
    else
        printf "  %-30s (未安装)\n" "$svc"
    fi
done

section "[5] Nginx 配置校验"
if nginx -t 2>&1; then
    ok "nginx -t 通过"
else
    bad "nginx -t 失败 —— 重启会失败，必须先修配置"
fi

section "[6] 本地 curl 直连（绕过 Cloudflare）"
for host in admin.nuotaooutdoor.com b2b.nuotaooutdoor.com nuotaooutdoor.com; do
    # 80/443 本地走 nginx
    HTTP=$(curl -s -o /dev/null --max-time 5 -w "%{http_code}" \
        --resolve "$host:80:127.0.0.1" "http://$host/" 2>/dev/null || echo "000")
    HTTPS=$(curl -sk -o /dev/null --max-time 5 -w "%{http_code}" \
        --resolve "$host:443:127.0.0.1" "https://$host/" 2>/dev/null || echo "000")
    printf "  %-32s  HTTP=%-4s HTTPS=%s\n" "$host" "$HTTP" "$HTTPS"
done
echo "  --- 后端 127.0.0.1:8000 ---"
BACKEND_HTTP=$(curl -s -o /dev/null --max-time 3 -w "%{http_code}" "http://127.0.0.1:8000/health" 2>/dev/null || echo "000")
BACKEND_READY=$(curl -s -o /dev/null --max-time 3 -w "%{http_code}" "http://127.0.0.1:8000/healthz" 2>/dev/null || echo "000")
echo "  127.0.0.1:8000/health  -> $BACKEND_HTTP"
echo "  127.0.0.1:8000/healthz -> $BACKEND_READY"

section "[7] Let's Encrypt 证书到期"
if command -v certbot &> /dev/null; then
    certbot certificates 2>/dev/null | grep -E '^\s+(Certificate Name|Domains Valid|Expiry|Remaining)' | sed 's/^/  /'
else
    warn "certbot 未安装，无法查询证书状态"
fi
# 直接读证书文件（不依赖 certbot）
for d in /etc/letsencrypt/live/*/; do
    if [ -f "$d/fullchain.pem" ]; then
        EXP=$(openssl x509 -in "$d/fullchain.pem" -noout -enddate 2>/dev/null | cut -d= -f2)
        echo "  $d -> expires $EXP"
    fi
done

section "[8] UFW / iptables 是否挡住 Cloudflare"
if command -v ufw &> /dev/null; then
    ufw status verbose 2>/dev/null | sed 's/^/  /'
fi
# Cloudflare IP 段的粗略检查：如果 80/443 只对 127.0.0.1 监听，Cloudflare 绝对连不进来
if ss -lnt 2>/dev/null | grep -qE '0\.0\.0\.0:(80|443)\s'; then
    ok "80/443 监听在 0.0.0.0（对外可达）"
elif ss -lnt 2>/dev/null | grep -qE '127\.0\.0\.1:(80|443)\s'; then
    bad "80/443 只监听 127.0.0.1 —— Cloudflare 一定连不上，这就是 521 的直接原因"
fi

section "[9] 最近错误日志（每个最多 20 行）"
echo "--- journalctl -u nginx (last 20 ERROR/WARN) ---"
journalctl -u nginx --no-pager -n 200 --since "6 hours ago" 2>/dev/null \
    | grep -Ei 'error|fail|emerg|refused|denied' | tail -20 | sed 's/^/  /'
echo ""
echo "--- journalctl -u nuotao-backend (last 20 ERROR) ---"
journalctl -u nuotao-backend --no-pager -n 200 --since "6 hours ago" 2>/dev/null \
    | grep -Ei 'error|traceback|exception|refused' | tail -20 | sed 's/^/  /'
echo ""
echo "--- nginx error.log (last 20 lines) ---"
tail -20 /var/log/nginx/error.log 2>/dev/null | sed 's/^/  /' || echo "  (no /var/log/nginx/error.log)"

section "=== 快速自查表 ==="
echo "如果以下任一条为 FAIL，按对应指引处理："
echo "  - 根分区 ≥ 95%  → 清理 /var/log、docker 镜像、旧 release"
echo "  - 80/443 未监听  → systemctl start nginx 或修 nginx.conf"
echo "  - nginx -t 失败  → 按报错修配置，再 systemctl reload nginx"
echo "  - 证书已过期     → sudo certbot renew --force-renewal --cert-name <name>"
echo "  - 80/443 只听 127.0.0.1 → 检查 nginx.conf 里 listen 指令或 bind 参数"
echo "  - backend 未监听 :8000  → journalctl -u nuotao-backend -n 50 看崩溃原因"
echo ""
echo "把以上输出（==== 括号里的 section ====）整段发给 AI 助手即可分析。"
