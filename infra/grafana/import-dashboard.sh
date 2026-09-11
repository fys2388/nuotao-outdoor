#!/bin/bash
# ============================================================
# Nuotao AI OS - Grafana 仪表盘导入脚本
# 用法: ./import-grafana-dashboard.sh [Grafana URL] [API Key]
# 示例: ./import-grafana-dashboard.sh http://localhost:3000 admin:admin
# ============================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 参数
GRAFANA_URL=${1:-"http://localhost:3000"}
GRAFANA_AUTH=${2:-"admin:admin"}
DASHBOARD_FILE="infra/grafana/dashboards/nuotao-ai-os.json"

echo ""
echo "============================================================"
echo "  Grafana 仪表盘导入脚本"
echo "============================================================"
echo ""
echo "Grafana URL: $GRAFANA_URL"
echo "仪表盘文件: $DASHBOARD_FILE"
echo ""

# ============================================================
# 步骤 1: 检查 Grafana 连接
# ============================================================
log_info "步骤 1/4: 检查 Grafana 连接..."

if curl -s -u "$GRAFANA_AUTH" "$GRAFANA_URL/api/health" | grep -q "database"; then
    log_success "Grafana 连接成功"
else
    log_error "Grafana 连接失败"
    echo "  请检查："
    echo "  1. Grafana 是否运行: docker ps | grep grafana"
    echo "  2. Grafana URL 是否正确"
    echo "  3. 账号密码是否正确（默认 admin:admin）"
    exit 1
fi

# ============================================================
# 步骤 2: 检查仪表盘文件
# ============================================================
log_info "步骤 2/4: 检查仪表盘文件..."

if [ ! -f "$DASHBOARD_FILE" ]; then
    log_error "仪表盘文件不存在: $DASHBOARD_FILE"
    exit 1
fi

DASHBOARD_SIZE=$(wc -c < "$DASHBOARD_FILE")
log_success "仪表盘文件存在（$DASHBOARD_SIZE 字节）"

# ============================================================
# 步骤 3: 获取数据源 UID
# ============================================================
log_info "步骤 3/4: 获取 Prometheus 数据源..."

DATASOURCES=$(curl -s -u "$GRAFANA_AUTH" "$GRAFANA_URL/api/datasources")
PROMETHEUS_UID=$(echo "$DATASOURCES" | grep -o '"uid":"[^"]*"' | head -1 | cut -d'"' -f4)

if [ -z "$PROMETHEUS_UID" ]; then
    log_warn "未找到 Prometheus 数据源，正在创建..."

    # 创建 Prometheus 数据源
    curl -s -u "$GRAFANA_AUTH" -X POST "$GRAFANA_URL/api/datasources" \
        -H "Content-Type: application/json" \
        -d '{
            "name": "Prometheus",
            "type": "prometheus",
            "url": "http://prometheus:9090",
            "access": "proxy",
            "isDefault": true
        }' > /dev/null

    # 重新获取 UID
    DATASOURCES=$(curl -s -u "$GRAFANA_AUTH" "$GRAFANA_URL/api/datasources")
    PROMETHEUS_UID=$(echo "$DATASOURCES" | grep -o '"uid":"[^"]*"' | head -1 | cut -d'"' -f4)
fi

if [ -n "$PROMETHEUS_UID" ]; then
    log_success "Prometheus 数据源 UID: $PROMETHEUS_UID"
else
    log_error "无法获取 Prometheus 数据源 UID"
    exit 1
fi

# ============================================================
# 步骤 4: 导入仪表盘
# ============================================================
log_info "步骤 4/4: 导入仪表盘..."

# 读取仪表盘 JSON 并替换数据源 UID
DASHBOARD_JSON=$(cat "$DASHBOARD_FILE")
DASHBOARD_JSON=$(echo "$DASHBOARD_JSON" | sed "s/\"datasource\":{\"type\":\"prometheus\",\"uid\":\"prometheus\"}/\"datasource\":{\"type\":\"prometheus\",\"uid\":\"$PROMETHEUS_UID\"}/g")

# 构建导入请求
IMPORT_PAYLOAD=$(cat <<EOF
{
    "dashboard": $DASHBOARD_JSON,
    "overwrite": true,
    "folderId": 0
}
EOF
)

# 导入仪表盘
IMPORT_RESULT=$(curl -s -u "$GRAFANA_AUTH" -X POST "$GRAFANA_URL/api/dashboards/db" \
    -H "Content-Type: application/json" \
    -d "$IMPORT_PAYLOAD")

# 检查导入结果
if echo "$IMPORT_RESULT" | grep -q "uid"; then
    DASHBOARD_UID=$(echo "$IMPORT_RESULT" | grep -o '"uid":"[^"]*"' | head -1 | cut -d'"' -f4)
    DASHBOARD_URL=$(echo "$IMPORT_RESULT" | grep -o '"url":"[^"]*"' | head -1 | cut -d'"' -f4)
    log_success "仪表盘导入成功！"
    echo ""
    echo "  仪表盘 UID: $DASHBOARD_UID"
    echo "  访问地址: $GRAFANA_URL$DASHBOARD_URL"
else
    log_error "仪表盘导入失败"
    echo "  错误信息: $IMPORT_RESULT"
    exit 1
fi

# ============================================================
# 完成
# ============================================================
echo ""
echo "============================================================"
echo -e "${GREEN}✅ Grafana 仪表盘导入完成！${NC}"
echo "============================================================"
echo ""
echo "访问地址："
echo "  - 仪表盘: $GRAFANA_URL$DASHBOARD_URL"
echo "  - Grafana 首页: $GRAFANA_URL"
echo ""
echo "默认账号："
echo "  - 用户名: admin"
echo "  - 密码: admin（首次登录后请修改）"
echo ""
echo "仪表盘包含："
echo "  - 系统概览（API/数据库/Redis 状态）"
echo "  - AI/LLM 监控（请求速率/响应时间/Tokens/成本）"
echo "  - 业务指标（产品/订单/客户总数）"
echo "  - 数据库监控（连接数/数据库大小）"
echo ""
echo "============================================================"
