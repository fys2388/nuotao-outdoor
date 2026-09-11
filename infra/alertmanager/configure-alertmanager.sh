#!/bin/bash
# ============================================================
# Nuotao AI OS - Alertmanager 配置脚本
# 用法: ./configure-alertmanager.sh
# 支持: 邮件、钉钉、企业微信、Slack
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

CONFIG_FILE="infra/alertmanager/alertmanager.yml"
TEMPLATE_FILE="infra/alertmanager/alertmanager.yml.template"

echo ""
echo "============================================================"
echo "  Alertmanager 配置脚本"
echo "============================================================"
echo ""

# ============================================================
# 步骤 1: 检查配置文件
# ============================================================
log_info "步骤 1/5: 检查配置文件..."

if [ ! -f "$CONFIG_FILE" ]; then
    log_error "配置文件不存在: $CONFIG_FILE"
    exit 1
fi

log_success "配置文件存在"

# ============================================================
# 步骤 2: 选择通知渠道
# ============================================================
log_info "步骤 2/5: 选择通知渠道..."

echo ""
echo "请选择要配置的通知渠道（可多选）："
echo "  1. 邮件通知 (SMTP)"
echo "  2. 钉钉机器人"
echo "  3. 企业微信机器人"
echo "  4. Slack Webhook"
echo "  5. 全部配置"
echo "  0. 跳过（使用默认配置）"
echo ""
read -p "请输入选项（如 1,2 或 5）: " CHANNELS

# ============================================================
# 步骤 3: 配置邮件通知
# ============================================================
if echo "$CHANNELS" | grep -q "1\|5"; then
    log_info "步骤 3/5: 配置邮件通知..."

    echo ""
    read -p "SMTP 服务器地址 (如 smtp.gmail.com:587): " SMTP_HOST
    read -p "发件人邮箱: " SMTP_FROM
    read -p "SMTP 用户名: " SMTP_USER
    read -s -p "SMTP 密码/授权码: " SMTP_PASSWORD
    echo ""
    read -p "收件人邮箱（多个用逗号分隔）: " SMTP_TO

    # 替换配置
    sed -i "s|smtp_smarthost: '.*'|smtp_smarthost: '$SMTP_HOST'|g" "$CONFIG_FILE"
    sed -i "s|smtp_from: '.*'|smtp_from: '$SMTP_FROM'|g" "$CONFIG_FILE"
    sed -i "s|smtp_auth_username: '.*'|smtp_auth_username: '$SMTP_USER'|g" "$CONFIG_FILE"
    sed -i "s|smtp_auth_password: '.*'|smtp_auth_password: '$SMTP_PASSWORD'|g" "$CONFIG_FILE"
    sed -i "s|to: '.*'|to: '$SMTP_TO'|g" "$CONFIG_FILE"

    log_success "邮件通知配置完成"
fi

# ============================================================
# 步骤 4: 配置钉钉机器人
# ============================================================
if echo "$CHANNELS" | grep -q "2\|5"; then
    log_info "步骤 4/5: 配置钉钉机器人..."

    echo ""
    echo "钉钉机器人配置步骤："
    echo "  1. 打开钉钉群 → 群设置 → 智能群助手 → 添加机器人"
    echo "  2. 选择「自定义」机器人"
    echo "  3. 设置机器人名称（如「Nuotao AI OS 告警」）"
    echo "  4. 安全设置选择「加签」或「自定义关键词」"
    echo "  5. 复制 Webhook 地址中的 access_token"
    echo ""
    read -p "钉钉机器人 Access Token: " DINGTALK_TOKEN

    # 替换配置
    sed -i "s|dingtalk_api_url: '.*'|dingtalk_api_url: 'https://oapi.dingtalk.com/robot/send?access_token=$DINGTALK_TOKEN'|g" "$CONFIG_FILE"

    log_success "钉钉机器人配置完成"
fi

# ============================================================
# 步骤 5: 配置企业微信机器人
# ============================================================
if echo "$CHANNELS" | grep -q "3\|5"; then
    log_info "步骤 5/5: 配置企业微信机器人..."

    echo ""
    echo "企业微信机器人配置步骤："
    echo "  1. 打开企业微信群 → 右键 → 添加群机器人"
    echo "  2. 点击「新创建一个机器人」"
    echo "  3. 设置机器人名称（如「Nuotao AI OS 告警」）"
    echo "  4. 复制 Webhook 地址中的 key"
    echo ""
    read -p "企业微信机器人 Webhook Key: " WECHAT_KEY

    # 替换配置
    sed -i "s|wechat_api_url: '.*'|wechat_api_url: 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=$WECHAT_KEY'|g" "$CONFIG_FILE"

    log_success "企业微信机器人配置完成"
fi

# ============================================================
# 配置 Slack Webhook
# ============================================================
if echo "$CHANNELS" | grep -q "4\|5"; then
    log_info "配置 Slack Webhook..."

    echo ""
    echo "Slack Webhook 配置步骤："
    echo "  1. 访问 https://api.slack.com/apps"
    echo "  2. 创建新应用或选择现有应用"
    echo "  3. 启用 Incoming Webhooks"
    echo "  4. 添加新 Webhook 到工作区"
    echo "  5. 选择频道并授权"
    echo "  6. 复制 Webhook URL"
    echo ""
    read -p "Slack Webhook URL (完整地址): " SLACK_WEBHOOK

    # 提取 Webhook 路径
    SLACK_PATH=$(echo "$SLACK_WEBHOOK" | sed 's|https://hooks.slack.com/services/||')

    # 替换配置
    sed -i "s|slack_api_url: '.*'|slack_api_url: 'https://hooks.slack.com/services/$SLACK_PATH'|g" "$CONFIG_FILE"

    log_success "Slack Webhook 配置完成"
fi

# ============================================================
# 验证配置
# ============================================================
log_info "验证配置文件..."

if command -v amtool &> /dev/null; then
    if amtool check-config "$CONFIG_FILE"; then
        log_success "配置文件验证通过"
    else
        log_error "配置文件验证失败，请检查语法"
        exit 1
    fi
else
    log_warn "未安装 amtool，跳过配置验证"
    log_info "可以使用以下命令手动验证："
    echo "  docker run --rm -v $(pwd)/$CONFIG_FILE:/etc/alertmanager/alertmanager.yml prom/alertmanager:latest --config.check"
fi

# ============================================================
# 完成
# ============================================================
echo ""
echo "============================================================"
echo -e "${GREEN}✅ Alertmanager 配置完成！${NC}"
echo "============================================================"
echo ""
echo "配置文件: $CONFIG_FILE"
echo ""
echo "配置的通知渠道："
if echo "$CHANNELS" | grep -q "1\|5"; then echo "  ✅ 邮件通知"; fi
if echo "$CHANNELS" | grep -q "2\|5"; then echo "  ✅ 钉钉机器人"; fi
if echo "$CHANNELS" | grep -q "3\|5"; then echo "  ✅ 企业微信机器人"; fi
if echo "$CHANNELS" | grep -q "4\|5"; then echo "  ✅ Slack Webhook"; fi
if [ "$CHANNELS" = "0" ]; then echo "  ⚠️  使用默认配置（未配置实际通知渠道）"; fi
echo ""
echo "下一步："
echo "  1. 重启 Alertmanager 服务："
echo "     docker compose -f docker-compose.prod.yml restart alertmanager"
echo ""
echo "  2. 测试告警通知："
echo "     curl -X POST http://localhost:9093/api/v1/alerts \\"
echo "       -H 'Content-Type: application/json' \\"
echo "       -d '[{"labels":{"alertname":"测试告警","severity":"warning"},"annotations":{"description":"这是一条测试告警"}}]'"
echo ""
echo "  3. 查看 Alertmanager 状态："
echo "     http://localhost:9093"
echo ""
echo "告警分级："
echo "  - Critical（严重）: 立即通知所有渠道，1 小时重复"
echo "  - Warning（警告）: 邮件 + 钉钉，4 小时重复"
echo "  - Info（信息）: 仅记录，不通知"
echo ""
echo "============================================================"
