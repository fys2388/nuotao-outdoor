#!/bin/bash
# Import all Grafana dashboards

set -e

BASE_URL="http://localhost:3000"
AUTH="Basic YWRtaW46TnVvdGFvX0dyYWZhbmFfMjAyNA=="
DASHBOARD_DIR="/opt/nuotao/infra"

echo "=========================================="
echo "  Nuotao AI OS - Grafana 仪表板导入"
echo "=========================================="
echo ""

# Import dashboards
DASHBOARDS=(
  "grafana-security-dashboard.json"
  "grafana-system-dashboard.json"
  "grafana-database-dashboard.json"
)

for dashboard in "${DASHBOARDS[@]}"; do
    echo "导入仪表板: $dashboard"
    
    # Create import JSON
    IMPORT_FILE="/tmp/import_$(basename $dashboard .json).json"
    
    python3 -c "
import json

with open('$DASHBOARD_DIR/$dashboard', 'r') as f:
    dashboard = json.load(f)

import_data = {
    'dashboard': dashboard,
    'overwrite': True,
    'inputs': [
        {
            'name': 'DS_PROMETHEUS',
            'label': 'Prometheus',
            'value': 'prometheus',
            'type': 'datasource'
        }
    ]
}

with open('$IMPORT_FILE', 'w') as f:
    json.dump(import_data, f, indent=2)
"
    
    # Import dashboard
    RESULT=$(curl -s -X POST $BASE_URL/api/dashboards/db \
      -H 'Content-Type: application/json' \
      -H "Authorization: $AUTH" \
      -d @$IMPORT_FILE)
    
    STATUS=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status', 'unknown'))" 2>/dev/null)
    
    if [ "$STATUS" = "success" ]; then
        echo "  ✅ 成功"
    else
        echo "  ❌ 失败: $RESULT"
    fi
    
    echo ""
done

echo "=========================================="
echo "  导入完成!"
echo "=========================================="